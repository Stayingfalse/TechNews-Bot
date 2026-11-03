"""An episode's shots → mp4: each shot drawn by its view, a quick pixel iris between shots, synth
sound across the whole, and the last half second fading into the first frame so a replay loops."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from . import scene, sound, views

FPS = 30
VIEWS = {"side": scene.draw, "topdown": views.draw_topdown, "inside": views.draw_inside, "planet": views.draw_planet}


def frame_at(ep: dict, t: float) -> np.ndarray:
    t0 = 0.0
    for shot in ep["shots"]:
        if t < t0 + shot["dur"] or shot is ep["shots"][-1]:
            return VIEWS[shot["view"]](shot["spec"], min(t - t0, shot["dur"] - 1e-3)).frame()
        t0 += shot["dur"]
    raise ValueError("no shots")


def _iris(f: np.ndarray, k: float) -> np.ndarray:
    blk = int((1 - k) * 40) * 6 + 6
    return f[::blk, ::blk].repeat(blk, 0).repeat(blk, 1)[:1920, :1080]


def render(ep: dict, path: str | Path, audio: str | Path | None = None) -> None:
    path = Path(path)
    n = int(ep["duration"] * FPS)
    first = frame_at(ep, 0.0).astype(np.float32)
    wav = path.with_suffix(".wav")
    sound.write({"duration": ep["duration"], "sfx": ep.get("sfx", [])}, wav)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
           "-r", str(FPS), "-i", "-", "-i", str(audio or wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(path)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    cuts = np.cumsum([s["dur"] for s in ep["shots"]])[:-1]
    blend = int(0.5 * FPS)
    try:
        for i in range(n):
            t = i / FPS
            f = frame_at(ep, t)
            near = min((abs(t - c) for c in cuts), default=9)
            if near < 0.25:
                f = _iris(f, near / 0.25)
            if i >= n - blend:
                k = (i - (n - blend) + 1) / blend
                f = (f * (1 - k) + first * k).astype(np.uint8)
            ff.stdin.write(np.ascontiguousarray(f).tobytes())
    finally:
        ff.stdin.close()
        rc = ff.wait()
        wav.unlink(missing_ok=True)
    if rc:
        raise RuntimeError(f"ffmpeg exited with {rc}")
