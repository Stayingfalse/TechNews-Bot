"""Timeline + frame compositor + ffmpeg encoder."""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

from ..spec import QuizSpec
from . import music
from .audio import write_sfx_track
from .background import Background
from .draw import blit, clamp, disc, ease_in_cubic, ease_in_out_cubic, ink_text, prog
from .scenes import IntroScene, RoundScene, build_scenes
from .theme import FPS, H, PALETTES, SAFE_LEFT, SAFE_RIGHT, SAFE_TOP, W

log = logging.getLogger(__name__)

OUTRO = 0.22  # seconds each scene spends leaving
LOOP = 0.45  # the last scene clears and the stage eases back to frame 0, so an autoplay replay loops seamlessly
MUSIC_GAIN = float(os.environ.get("MUSIC_GAIN", "0.32"))  # library tracks, after loudness normalisation
LOUDNESS = float(os.environ.get("LOUDNESS_LUFS", "-15"))  # final mix target, about what Reels/Shorts play at


def seed_of(spec: QuizSpec) -> int:
    return sum(map(ord, spec.id))


class Video:
    def __init__(self, spec: QuizSpec, brand: str = "", reveal: dict | None = None):
        self.spec = spec
        self.pal = PALETTES[spec.palette]
        self.bg = Background(self.pal, seed=seed_of(spec))
        self.scenes = build_scenes(spec, self.pal, seed_of(spec), reveal)
        self.starts = []
        acc = 0.0
        for s in self.scenes:
            self.starts.append(acc)
            acc += s.duration
        self.duration = acc
        self.n_frames = int(round(acc * FPS))
        self.brand = ink_text(brand, "sign", 28, self.pal.paper, self.pal.ink, 0, 3, 1) if brand else None
        self.lamp_on = disc(11, self.pal.sign + (255,), self.pal.ink, 4, 3)
        self.lamp_off = disc(11, self.pal.stage + (255,), self.pal.ink, 4, 3)
        self.start_bg = self.bg.render(0.0)

    def sfx_events(self) -> list[tuple[float, str]]:
        ev = []
        for start, s in zip(self.starts, self.scenes):
            ev += [(start + t, k) for t, k in s.sfx() if t < s.duration]
        return ev

    def _scene_at(self, T: float) -> int:
        for i in range(len(self.scenes) - 1, -1, -1):
            if T >= self.starts[i]:
                return i
        return 0

    def frame(self, idx: int) -> Image.Image:
        T = idx / FPS
        i = self._scene_at(T)
        scene = self.scenes[i]
        t = T - self.starts[i]

        energy = max((clamp(1 - (t - p) / 0.6) ** 2 for p in scene.pulses() if t >= p and (i or p)), default=0.0)
        frame = self.bg.render(T, energy)

        last = i == len(self.scenes) - 1
        if last:  # fully cleared two frames before the end, so the final frames match frame 0
            out_p = ease_in_out_cubic(prog(t, scene.duration - LOOP, LOOP - 2 / FPS))
        else:
            out_p = ease_in_cubic(prog(t, scene.duration - OUTRO, OUTRO))
        if last and out_p > 0:
            frame = Image.blend(frame, self.start_bg, out_p)

        fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        scene.render(fg, t)
        if out_p > 0:
            blit(frame, fg, 0, -90 * out_p, anchor="lt", alpha=1 - out_p)
        else:
            frame.alpha_composite(fg)

        self._chrome(frame, T, looping=last and out_p > 0.5)
        return frame

    def _chrome(self, frame: Image.Image, T: float, looping: bool = False) -> None:
        # Brand top-left; one lamp per round top-right, lit once that round has started
        y = SAFE_TOP - 70
        if self.brand:
            blit(frame, self.brand, SAFE_LEFT - 6, y, anchor="lm")
        rounds = [k for k, s in enumerate(self.scenes) if isinstance(s, RoundScene)]
        step = 34
        x0 = SAFE_RIGHT - (len(rounds) - 1) * step - 10
        for k, si in enumerate(rounds):
            lamp = self.lamp_on if T >= self.starts[si] and not looping else self.lamp_off
            blit(frame, lamp, x0 + k * step, y)


# ---------------------------------------------------------------- parallel render

_WORKER: Video | None = None


def _init_worker(spec_json: str, brand: str, reveal: dict | None = None) -> None:
    global _WORKER
    _WORKER = Video(QuizSpec.model_validate_json(spec_json), brand, reveal)


def _render_frame(idx: int) -> bytes:
    assert _WORKER is not None
    return _WORKER.frame(idx).convert("RGB").tobytes()


def render_video(spec: QuizSpec, out_path: str | Path, *, brand: str = "", workers: int | None = None,
                 cover_path: str | Path | None = None, music_dir: Path | None = None,
                 reveal: dict | None = None) -> dict:
    """`reveal` = yesterday's cliffhanger ({answer, note, shoutouts}) to show before the outro."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    video = Video(spec, brand, reveal)
    workers = workers or max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4"))))
    t0 = time.time()
    track = music.pick(spec.music, music_dir or Path("/nonexistent"), seed_of(spec))

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "sfx.wav")
        bed = music.synth(video.duration, seed_of(spec)) if track == "synth" else None
        write_sfx_track(video.sfx_events(), video.duration, wav, enabled=spec.sfx, bed=bed)
        audio_in = ["-i", wav]
        master = f"loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11,aresample=48000"
        graph = f"[1:a]{master}[a]"
        if isinstance(track, Path):
            fade = max(0.0, video.duration - 1.5)
            audio_in += ["-stream_loop", "-1", "-i", str(track)]
            graph = (
                f"[2:a]loudnorm=I=-16:TP=-1.5,aresample=48000,volume={MUSIC_GAIN},"
                f"afade=t=in:d=0.3,afade=t=out:st={fade:.2f}:d=1.5[m];"
                f"[1:a][m]amix=inputs=2:duration=first:normalize=0,{master}[a]"
            )
        audio_map = ["-filter_complex", graph, "-map", "0:v", "-map", "[a]"]
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            *audio_in, *audio_map,
            "-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "medium"), "-crf", "19",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-g", str(FPS * 2),
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-t", f"{video.duration:.3f}", "-movflags", "+faststart",
            str(out_path),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin
        try:
            if workers == 1:
                _init_worker(spec.model_dump_json(), brand, reveal)
                for i in range(video.n_frames):
                    proc.stdin.write(_render_frame(i))
            else:
                ctx = mp.get_context("spawn")  # safe inside the threaded web server
                with ctx.Pool(workers, _init_worker, (spec.model_dump_json(), brand, reveal)) as pool:
                    for buf in pool.imap(_render_frame, range(video.n_frames), chunksize=4):
                        proc.stdin.write(buf)
        finally:
            proc.stdin.close()
            rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited with {rc}")

    if cover_path:
        # Cover = end of the title card; with no card, round 1's clue under the title banner (never an answer).
        first = video.scenes[0]
        at = first.duration - OUTRO - 0.1 if isinstance(first, IntroScene) else 1.8
        cover_idx = min(video.n_frames - 1, int(at * FPS))
        video.frame(cover_idx).convert("RGB").save(cover_path, quality=90)

    info = {
        "duration": round(video.duration, 2),
        "frames": video.n_frames,
        "render_seconds": round(time.time() - t0, 1),
        "bytes": out_path.stat().st_size,
        "music": track.name if isinstance(track, Path) else (track or "none"),
    }
    log.info("rendered %s %s", out_path.name, info)
    return info
