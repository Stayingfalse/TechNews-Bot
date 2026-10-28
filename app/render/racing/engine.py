"""The race video: scenes in order, glitch moments, sound, and the ffmpeg encode. Theme-agnostic:
the spec names its theme, and the theme draws each scene.

Scenes: boot → hook → grid → race → finish → result → [table on Sundays] → card → outro.
A launch video ("launch": true) is boot → hook → rules → card → outro. The outro fades back to
the boot screen's first frame, so an autoplay replay loops without a jump.
"""
from __future__ import annotations

import json
import logging
import multiprocessing as mp
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ..audio import write_wav
from . import sound
from .themes import get as get_theme
from .themes.base import FPS, H, W

log = logging.getLogger(__name__)
LOUDNESS = float(os.environ.get("LOUDNESS_LUFS", "-14"))
GLITCH_FRAMES = 3


def timeline(spec: dict) -> list[tuple[str, float]]:
    if spec.get("launch"):
        return [("boot", 0.6), ("hook", 2.8), ("rules", 9.0), ("card", 8.0), ("outro", 0.6)]
    scenes = [("boot", 0.6), ("hook", 2.6), ("grid", 3.0), ("race", spec["race"]["race_end"]),
              ("finish", 2.2), ("result", 5.0)]
    if spec.get("table"):
        scenes.append(("table", 5.0))
    return scenes + [("card", 7.5), ("outro", 0.6)]


def starts(scenes: list[tuple[str, float]]) -> dict[str, float]:
    out, acc = {}, 0.0
    for name, dur in scenes:
        out[name] = acc
        acc += dur
    return out


def glitches(spec: dict, scenes: list[tuple[str, float]]) -> list[tuple[float, float]]:
    """(time, strength) of each glitch burst: the hook, every race event, the result, and a couple
    at random (seeded, so a re-render matches)."""
    at = starts(scenes)
    total = sum(d for _, d in scenes)
    out = [(at["hook"] + 0.05, 1.0)]
    if "race" in at:
        out += [(at["race"] + e["t"], 0.6) for e in spec["race"]["events"]]
        out.append((at["result"] + 0.02, 0.8))
    rng = np.random.default_rng(spec.get("seed", 0))
    out += [(float(rng.uniform(1.0, total - 1.5)), 0.4) for _ in range(2)]
    return sorted(out)


def sfx(spec: dict, scenes: list[tuple[str, float]]) -> list[tuple[float, str]]:
    at = starts(scenes)
    ev = [(0.0, "boot")]
    ev += [(at["hook"] + 0.1 + i * 0.18, "blip") for i in range(len(spec.get("hook", [])))]
    if "rules" in at:
        ev += [(at["rules"] + 0.3 + i * 0.5, "blip") for i in range(4)]
    if "grid" in at:
        g, gd = at["grid"], dict(scenes)["grid"]
        ev += [(g + 0.6 + i * 0.32, "light") for i in range(5)]
        ev.append((g + gd - 0.35, "go"))
        race = spec["race"]
        ev += [(at["race"] + e["t"], e["kind"]) for e in race["events"]]
        last, prev = -1.0, None
        dist = np.array(race["dist"])
        for k in range(0, len(dist), 3):  # a whoosh on overtakes, at most one every 0.6 s
            order = tuple(np.argsort(-dist[k]))
            t = k / FPS
            if prev is not None and order[:3] != prev[:3] and t - last > 0.6 and t < race["race_end"]:
                ev.append((at["race"] + t, "whoosh"))
                last = t
            prev = order
        ev.append((at["finish"], "flag"))
        ev.append((at["result"], "reveal"))
        ev += [(at["result"] + 0.6 + i * 0.35, "blip") for i in range(4)]
    if "table" in at:
        ev += [(at["table"] + 0.2 + i * 0.08, "blip") for i in range(0, 10, 3)]
    ev.append((at["card"], "card"))
    ev += [(at["card"] + 0.15 + i * 0.07, "blip") for i in range(0, 6, 2)]
    return ev


class Video:
    def __init__(self, spec: dict, record: bool = False):
        self.spec = spec
        self.theme = get_theme(spec["theme"])(spec, record=record)
        self.scenes = timeline(spec)
        self.at = starts(self.scenes)
        self.duration = sum(d for _, d in self.scenes)
        self.n_frames = int(round(self.duration * FPS))
        self.bursts = glitches(spec, self.scenes)

    def scene_at(self, T: float) -> tuple[str, float, float]:
        for name, dur in reversed(self.scenes):
            if T >= self.at[name]:
                return name, T - self.at[name], dur
        return self.scenes[0][0], 0.0, self.scenes[0][1]

    def frame(self, idx: int) -> Image.Image:
        T = idx / FPS
        name, t, dur = self.scene_at(T)
        img = self.theme.frame(name, t, dur)
        if name not in ("boot", "outro"):  # the loop frames stay clean
            for at, strength in self.bursts:
                if at <= T < at + GLITCH_FRAMES / FPS:
                    img = self.theme.glitch(img, strength, seed=idx)
        return img


_WORKER: Video | None = None


def _init(spec_json: str) -> None:
    global _WORKER
    _WORKER = Video(json.loads(spec_json))


def _frame(idx: int) -> bytes:
    assert _WORKER is not None
    return _WORKER.frame(idx).convert("RGB").tobytes()


def render(spec: dict, out_path: str | Path, workers: int | None = None, cover_path: str | Path | None = None) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    video = Video(spec)
    workers = workers or max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4"))))
    t0 = time.time()
    race_span = (video.at["race"], video.at["race"] + spec["race"]["race_end"] + 1.5) if "race" in video.at else None
    audio = sound.mix(video.duration, sfx(spec, video.scenes), video.theme.sound, spec.get("seed", 0),
                      spec.get("race"), race_span)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "sound.wav")
        write_wav(audio, wav)
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-i", wav, "-filter_complex", f"[1:a]loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11,aresample=48000[a]",
               "-map", "0:v", "-map", "[a]",
               "-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "medium"), "-crf", "20",
               "-maxrate", "8M", "-bufsize", "16M",
               "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-g", str(FPS * 2),
               "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
               "-t", f"{video.duration:.3f}", "-movflags", "+faststart", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin
        try:
            if workers == 1:
                _init(json.dumps(spec))
                for i in range(video.n_frames):
                    proc.stdin.write(_frame(i))
            else:
                with mp.get_context("spawn").Pool(workers, _init, (json.dumps(spec),)) as pool:
                    for buf in pool.imap(_frame, range(video.n_frames), chunksize=6):
                        proc.stdin.write(buf)
        finally:
            proc.stdin.close()
            rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited with {rc}")
    if cover_path:  # the race card: what the post is for
        video.frame(int((video.at["card"] + 2.0) * FPS)).convert("RGB").save(cover_path, quality=90)
    return {"duration": round(video.duration, 2), "frames": video.n_frames, "seconds": round(time.time() - t0, 1),
            "theme": spec["theme"], "bytes": out_path.stat().st_size}
