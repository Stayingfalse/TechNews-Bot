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

from ..spec import StorySpec
from .audio import write_sfx_track
from .background import Background
from .draw import blit, clamp, ease_in_cubic, glow, prog, rounded_rect, text_sprite
from .scenes import SCENES
from .theme import FPS, H, PALETTES, SAFE_BOTTOM, SAFE_CX, SAFE_LEFT, SAFE_TOP, SAFE_W, W

log = logging.getLogger(__name__)

OUTRO = 0.22  # seconds each scene spends leaving


def _usable_beats(spec: StorySpec, imgs: dict) -> list:
    """Drop image beats whose image failed to download; strip missing images from other beats."""
    beats = []
    for b in spec.beats:
        ref = getattr(b, "image", None)
        if ref and ref not in imgs:
            if b.type == "image":
                continue
            b = b.model_copy(update={"image": None})
        beats.append(b)
    return beats


class Video:
    def __init__(self, spec: StorySpec, brand: str = "", image_paths: dict[str, str] | None = None):
        self.spec = spec
        self.pal = PALETTES[spec.palette]
        self.bg = Background(self.pal, seed=sum(map(ord, spec.id)))
        credits = {i.id: i.credit for i in spec.images}
        imgs = {k: (Image.open(p).convert("RGB"), credits.get(k, "")) for k, p in (image_paths or {}).items()}
        self.scenes = [SCENES[b.type](b, self.pal, imgs) for b in _usable_beats(spec, imgs)]
        self.starts = []
        acc = 0.0
        for s in self.scenes:
            self.starts.append(acc)
            acc += s.duration
        self.duration = acc
        self.n_frames = int(round(acc * FPS))
        self.brand = text_sprite(brand, "bold", 30, self.pal.text, 2) if brand else None
        self.source = text_sprite(spec.source_label, "medium", 30, self.pal.muted) if spec.source_label else None

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

        energy = 0.0 if i == 0 else clamp(1 - t / 0.6) ** 2
        frame = self.bg.render(T, energy)

        last = i == len(self.scenes) - 1
        out_p = 0.0 if last else ease_in_cubic(prog(t, scene.duration - OUTRO, OUTRO))
        scene.backdrop(frame, t, 1 - out_p)

        fg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        scene.render(fg, t)
        frame.alpha_composite(glow(fg, 22, 0.75 * (1 - out_p)))
        if out_p > 0:
            blit(frame, fg, 0, -90 * out_p, anchor="lt", alpha=1 - out_p)
        else:
            frame.alpha_composite(fg)

        self._chrome(frame, T)
        return frame

    def _chrome(self, frame: Image.Image, T: float) -> None:
        # Story-style progress segments
        n = len(self.scenes)
        gap = 10
        seg_w = (SAFE_W - gap * (n - 1)) / n
        y = SAFE_TOP - 50
        for k in range(n):
            x = SAFE_LEFT + k * (seg_w + gap)
            frame.alpha_composite(rounded_rect(int(seg_w), 6, 3, self.pal.text + (50,)), (int(x), y))
            fill = clamp((T - self.starts[k]) / self.scenes[k].duration)
            if fill > 0:
                frame.alpha_composite(rounded_rect(max(6, int(seg_w * fill)), 6, 3, self.pal.accent + (255,)), (int(x), y))
        if self.brand:
            blit(frame, self.brand, SAFE_LEFT, y + 30, anchor="lt", alpha=0.8)
        if self.source:
            blit(frame, self.source, SAFE_CX, SAFE_BOTTOM + 10, anchor="mt", alpha=0.75)


# ---------------------------------------------------------------- parallel render

_WORKER: Video | None = None


def _init_worker(spec_json: str, brand: str, image_paths: dict[str, str]) -> None:
    global _WORKER
    _WORKER = Video(StorySpec.model_validate_json(spec_json), brand, image_paths)


def _render_frame(idx: int) -> bytes:
    assert _WORKER is not None
    return _WORKER.frame(idx).convert("RGB").tobytes()


def render_video(spec: StorySpec, out_path: str | Path, *, brand: str = "", workers: int | None = None,
                 cover_path: str | Path | None = None, image_paths: dict[str, str] | None = None) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image_paths = image_paths or {}
    video = Video(spec, brand, image_paths)
    workers = workers or max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4"))))
    t0 = time.time()

    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "sfx.wav")
        write_sfx_track(video.sfx_events(), video.duration, wav, enabled=spec.sfx)
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
            "-i", wav,
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
                _init_worker(spec.model_dump_json(), brand, image_paths)
                for i in range(video.n_frames):
                    proc.stdin.write(_render_frame(i))
            else:
                ctx = mp.get_context("spawn")  # safe inside the threaded web server
                with ctx.Pool(workers, _init_worker, (spec.model_dump_json(), brand, image_paths)) as pool:
                    for buf in pool.imap(_render_frame, range(video.n_frames), chunksize=4):
                        proc.stdin.write(buf)
        finally:
            proc.stdin.close()
            rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"ffmpeg exited with {rc}")

    if cover_path:
        # Cover = end of the first scene, when the hook is fully on screen.
        cover_idx = min(video.n_frames - 1, int((video.scenes[0].duration - OUTRO - 0.1) * FPS))
        video.frame(cover_idx).convert("RGB").save(cover_path, quality=90)

    info = {
        "duration": round(video.duration, 2),
        "frames": video.n_frames,
        "render_seconds": round(time.time() - t0, 1),
        "bytes": out_path.stat().st_size,
    }
    log.info("rendered %s %s", out_path.name, info)
    return info
