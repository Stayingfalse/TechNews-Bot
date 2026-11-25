"""A raosanta.uk promo, start to finish: the sky, the segments one after another, the brand line,
the carol and the narrator, encoded like the quiz (1080×1920, 30 fps, H.264 + AAC).

The video loops: the last scene clears and the sky eases back to frame 0, so an autoplay replay
runs on without a jump.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from ...santa.spec import PromoSpec
from .. import priority
from ..audio import SR, voice_track, write_sfx_track
from ..draw import blit, ease_in_cubic, ease_in_out_cubic, prog
from ..theme import FPS, H, SAFE_LEFT, SAFE_TOP, W
from . import carols, look
from .look import DISPLAY, C
from .scenes import SAY_AT, SCENES

log = logging.getLogger(__name__)
OUTRO = 0.22
LOOP = 0.45
LOUDNESS = float(os.environ.get("LOUDNESS_LUFS", "-15"))


def seed_of(spec: PromoSpec) -> int:
    return sum(map(ord, spec.id))


class Promo:
    def __init__(self, spec: PromoSpec, voice_lens: dict[int, float] | None = None, images_dir: Path | None = None):
        self.spec = spec
        voice_lens = voice_lens or {}
        self.sky = look.Sky(seed_of(spec))
        self.start_sky = self.sky.render(0.0)
        self.scenes = [SCENES[s.type](s, voice_lens.get(i), images_dir=images_dir) for i, s in enumerate(spec.segments)]
        self.starts, acc = [], 0.0
        for s in self.scenes:
            self.starts.append(acc)
            acc += s.duration
        self.duration = acc
        self.n_frames = int(round(acc * FPS))
        self.brand = self._brand()

    @staticmethod
    def _brand() -> Image.Image:
        st = look.stamp(64)
        txt = look.rich("RAOSANTA.UK", DISPLAY, 30, C.gold_soft, C.gold_soft, 600)
        img = Image.new("RGBA", (st.width + 16 + txt.width, max(st.height, txt.height)), (0, 0, 0, 0))
        img.alpha_composite(st, (0, (img.height - st.height) // 2))
        img.alpha_composite(txt, (st.width + 16, (img.height - txt.height) // 2))
        return img

    def sfx_events(self) -> list[tuple[float, str]]:
        return [(start + t, k) for start, s in zip(self.starts, self.scenes) for t, k in s.sfx() if t < s.duration]

    def say_times(self) -> dict[int, float]:
        return {i: start + SAY_AT for i, start in enumerate(self.starts)}

    def _scene_at(self, T: float) -> int:
        for i in range(len(self.scenes) - 1, -1, -1):
            if T >= self.starts[i]:
                return i
        return 0

    def frame(self, idx: int) -> Image.Image:
        T = idx / FPS
        i = self._scene_at(T)
        scene, t = self.scenes[i], T - self.starts[i]
        frame = self.sky.render(T)
        last = i == len(self.scenes) - 1
        if last:
            out = ease_in_out_cubic(prog(t, scene.duration - LOOP, LOOP - 2 / FPS))
            if out > 0:
                frame = Image.blend(frame, self.start_sky, out)
        else:
            out = ease_in_cubic(prog(t, scene.duration - OUTRO, OUTRO))
        fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        scene.render(fg, t)
        if out > 0:
            blit(frame, fg, 0, -90 * out, anchor="lt", alpha=1 - out)
        else:
            frame.alpha_composite(fg)
        brand_a = 1.0 - (out if last else 0.0)
        blit(frame, self.brand, SAFE_LEFT - 6, SAFE_TOP - 70, anchor="lm", alpha=brand_a)
        return frame


# ---------------------------------------------------------------- parallel render

_WORKER: Promo | None = None


def _init(spec_json: str, lens: dict, images: str | None) -> None:
    global _WORKER
    _WORKER = Promo(PromoSpec.model_validate_json(spec_json), {int(k): v for k, v in lens.items()},
                    Path(images) if images else None)


def _init_pool(*args) -> None:
    priority.lower()
    _init(*args)


def _frame(idx: int) -> bytes:
    assert _WORKER is not None
    return _WORKER.frame(idx).convert("RGB").tobytes()


def render_promo(spec: PromoSpec, out_path: str | Path, *, voice: dict[int, np.ndarray] | None = None,
                 images_dir: Path | None = None, cover_path: str | Path | None = None,
                 workers: int | None = None, max_seconds: float | None = None) -> dict:
    """Render `spec` to `out_path`. `voice`: the narrator's line for each segment that has one
    (mono at SR), already made; without it the video is music and text only. A video that would
    run past `max_seconds` is refused (ValueError) before anything is rendered."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    voice = voice or {}
    lens = {i: len(a) / SR for i, a in voice.items()}
    promo = Promo(spec, lens, images_dir)
    if max_seconds and promo.duration > max_seconds:
        raise ValueError(f"it would run {promo.duration:.1f} s, past the {max_seconds:.0f} s limit: cut a segment or shorten the lines")
    workers = workers or max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4"))))
    t0 = time.time()
    n = int(SR * promo.duration) + SR
    vo = None
    if voice:
        at = promo.say_times()
        vo = voice_track([(at[i], a) for i, a in voice.items()], n)
    bed, track = None, "none"
    if spec.music.startswith("carol"):
        name = spec.music.split(":", 1)[1] if ":" in spec.music else None
        bed, track = carols.carol(promo.duration, seed_of(spec), name)

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "mix.wav")
        write_sfx_track(promo.sfx_events(), promo.duration, wav, bed=bed, voice=vo)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-i", wav, "-filter_complex", f"[1:a]loudnorm=I={LOUDNESS}:TP=-1.5:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "medium"), "-crf", "19",
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1", "-g", str(FPS * 2),
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-t", f"{promo.duration:.3f}", "-movflags", "+faststart", str(out_path),
        ]
        proc = subprocess.Popen(priority.cmd(cmd), stdin=subprocess.PIPE)
        assert proc.stdin
        args = (spec.model_dump_json(), lens, str(images_dir) if images_dir else None)
        try:
            if workers == 1:
                _init(*args)
                for i in range(promo.n_frames):
                    proc.stdin.write(_frame(i))
            else:
                with mp.get_context("spawn").Pool(workers, _init_pool, args) as pool:
                    for buf in pool.imap(_frame, range(promo.n_frames), chunksize=4):
                        proc.stdin.write(buf)
        finally:
            proc.stdin.close()
            rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited with {rc}")

    if cover_path:  # the hook, fully in: the end of the first scene's entrance
        promo.frame(min(promo.n_frames - 1, int(1.2 * FPS))).convert("RGB").save(cover_path, quality=90)
    info = {"duration": round(promo.duration, 2), "frames": promo.n_frames, "render_seconds": round(time.time() - t0, 1),
            "bytes": out_path.stat().st_size, "music": track, "voice_lines": len(voice)}
    log.info("rendered promo %s %s", out_path.name, info)
    return info
