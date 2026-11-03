"""Render on the render worker (app/render_worker.py), or say why not so the caller renders here.

The worker is this same code (same image, built from the same branch) started with
APP=app.render_worker:app on another host. It only draws and encodes: it has no schedule, no
accounts and no ElevenLabs key. This server sends a zip (request.json plus every file the render
reads that only lives here: host lines, narration, an uploaded music track) and gets a zip back
(summary.json, video.mp4 and, for some kinds, cover.jpg).

`render()` never raises: any failure (worker down, busy, slow, out of date, a bad zip) is logged,
reported to Discord once an hour at most, and returns None, and the caller renders locally as before.
"""
from __future__ import annotations

import io
import json
import logging
import threading
import time
import zipfile
from pathlib import Path

import httpx

from ..config import settings

log = logging.getLogger(__name__)
KINDS = ("quiz", "racing", "adventure", "colony")
FILE_ARG = "@file:"  # in `args`, a file sent with the request (the worker swaps in its own path)

_warned = {"at": 0.0}
_warn_lock = threading.Lock()


def enabled() -> bool:
    return bool(settings.render_url and settings.render_token)


def pack(meta_name: str, meta: dict, files: dict[str, Path] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # video and mp3s don't compress further
        z.writestr(meta_name, json.dumps(meta))
        for name, path in (files or {}).items():
            z.write(path, name)
    return buf.getvalue()


def safe_name(name: str) -> bool:
    """A zip member that stays inside the folder it's unpacked to."""
    p = Path(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and "\\" not in name


def file_args(args: list[str]) -> tuple[list[str], dict[str, Path]]:
    """Renderer arguments with each local file swapped for a placeholder, and the files to send."""
    out, files = [], {}
    for a in args:
        p = Path(a)
        if p.is_absolute() and p.is_file():
            name = f"files/{len(files)}-{p.name}"
            files[name] = p
            out.append(FILE_ARG + name)
        else:
            out.append(a)
    return out, files


def _warn(why: str, kind: str) -> None:
    log.warning("render worker: %s; rendering the %s video here instead", why, kind)
    with _warn_lock:
        if time.time() - _warned["at"] < 3600:
            return
        _warned["at"] = time.time()
    from .. import notify  # here, not at the top: notify imports nothing from render, but keep the worker lean
    notify.error(f"render worker failed ({why[:300]}); rendering here instead. "
                 "Further failures in the next hour are only logged.")


def render(kind: str, spec: dict, out: Path, cover: Path | None = None, *, options: dict | None = None,
           files: dict[str, Path] | None = None) -> dict | None:
    """The render summary, with the video at `out` (and the cover at `cover`), or None: render here."""
    if not enabled():
        return None
    t0 = time.time()
    meta = {"kind": kind, "spec": spec, "options": options or {}, "cover": cover is not None}
    try:
        body = pack("request.json", meta, files)
        r = httpx.post(f"{settings.render_url}/render", content=body,
                       headers={"Authorization": f"Bearer {settings.render_token}", "Content-Type": "application/zip"},
                       timeout=httpx.Timeout(settings.render_timeout, connect=20))
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            summary = json.loads(z.read("summary.json"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read("video.mp4"))
            if cover is not None:
                if "cover.jpg" not in z.namelist():
                    raise RuntimeError("no cover in the reply")
                cover.write_bytes(z.read("cover.jpg"))
    except Exception as e:
        for p in (out, cover):
            if p is not None:
                p.unlink(missing_ok=True)
        _warn(f"{type(e).__name__}: {e}" if str(e) else type(e).__name__, kind)
        return None
    summary["rendered_by"] = "worker"
    summary["round_trip_seconds"] = round(time.time() - t0, 1)
    log.info("render worker made %s in %.0fs", out.name, time.time() - t0)
    return summary


# ------------------------------------------------------------------ one per kind of video

def quiz(spec, out: Path, cover: Path, *, brand: str, music_dir: Path, bundled_music: bool,
         reveal: dict | None, voice) -> dict | None:
    """A quiz (app/render/engine.py). The music is picked and the host lines made here, so the
    worker needs neither the music library on /data nor the ElevenLabs key."""
    if not enabled():
        return None
    from . import music
    from . import voice as host
    from .engine import Video, seed_of

    files: dict[str, Path] = {}
    opts: dict = {"brand": brand, "reveal": reveal}
    track = music.pick(spec.music, music_dir, seed_of(spec), bundled_music)
    if isinstance(track, Path):
        if music.is_bundled(track):
            opts["track"] = {"bundled": track.name}
        else:
            files[f"music/{track.name}"] = track
            opts["track"] = {"file": f"music/{track.name}"}
    else:
        opts["track"] = track  # "synth" or None
    if getattr(spec, "voice", False) and voice:
        opts["voice"] = {"voice_id": voice.voice_id, "model": voice.model}
        try:
            for p in host.fetch_all(Video(spec, brand, reveal), voice):
                files[f"voice/{p.name}"] = p
        except Exception as e:  # as a local render does: the video goes out without the voice-over
            log.warning("voice-over failed, rendering without it: %s", e)
            opts["voice_error"] = str(e)[:200]
    return render("quiz", json.loads(spec.model_dump_json()), out, cover, options=opts, files=files)


def racing(spec: dict, out: Path, cover: Path) -> dict | None:
    """A racing video (app/render/racing/engine.py): everything it draws is in the spec."""
    return render("racing", spec, out, cover)


def adventure(spec: dict, out: Path, args: list[str]) -> dict | None:
    """An adventure video (the Node renderer in adventure/); `args` = its narration arguments."""
    if not enabled():
        return None
    sent, files = file_args(args)
    return render("adventure", spec, out, options={"args": sent}, files=files)


def colony(spec: dict, out: Path, cover: Path, voice: list | None = None) -> dict | None:
    """A Farside episode (app/render/colony/video.py); `voice` = its lines as (time, samples)."""
    if not enabled():
        return None
    import tempfile

    import numpy as np

    files, opts = {}, {}
    with tempfile.TemporaryDirectory() as d:
        if voice:
            npz = Path(d) / "voice.npz"
            np.savez(npz, times=np.array([t for t, _ in voice], np.float64),
                     **{f"line{i}": np.asarray(a, np.float32) for i, (_, a) in enumerate(voice)})
            files["files/voice.npz"] = npz
            opts["voice"] = "files/voice.npz"
        return render("colony", spec, out, cover, options=opts, files=files)
