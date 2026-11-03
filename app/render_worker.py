"""The render worker: this same image on another host, started with APP=app.render_worker:app.

It only turns specs into videos, for the main server (RENDER_URL there points here; both share
RENDER_TOKEN). No schedule, no accounts, no /data to keep: each request carries everything the
render needs and gets the finished video back (app/render/remote.py has the format). One render at
a time; a second request while one runs gets 503, and the main server renders that one itself.
"""
from __future__ import annotations

import hmac
import io
import json
import logging
import os
import tempfile
import threading
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .render import remote

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN = os.environ.get("RENDER_TOKEN", "")
MAX_REQUEST = 200 * 1024 * 1024  # host lines, narration and at most one music track
_busy = threading.Lock()



@asynccontextmanager
async def lifespan(_: FastAPI):
    if not TOKEN:
        raise RuntimeError("RENDER_TOKEN must be set")
    yield


app = FastAPI(title="Render worker", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "worker": True, "busy": _busy.locked()}


def _unpack(body: bytes, into: Path) -> dict:
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            req = json.loads(z.read("request.json"))
            for name in z.namelist():
                if name == "request.json":
                    continue
                if not remote.safe_name(name):
                    raise ValueError(f"bad file name {name!r}")
                dest = into / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        raise HTTPException(400, f"bad request: {e}")
    if req.get("kind") not in remote.KINDS:
        raise HTTPException(400, f"unknown kind {req.get('kind')!r}")
    return req


def _quiz(req: dict, tmp: Path, out: Path, cover: Path | None) -> dict:
    from .render import music
    from .render.engine import render_video
    from .render.voice import VoiceConfig
    from .spec import QuizSpec

    spec = QuizSpec.model_validate(req["spec"])
    opts = req["options"]
    track = opts.get("track")
    if isinstance(track, dict):
        name = track.get("bundled") or track.get("file") or ""
        path = (music.BUNDLED if "bundled" in track else tmp) / name
        if not remote.safe_name(name) or not path.is_file():
            raise HTTPException(409, f"music track {name!r} isn't here (worker out of date?)")
        track = path
    v = opts.get("voice")
    # No API key: every line comes from the files sent along (render/voice.py _fetch)
    vcfg = VoiceConfig("", v["voice_id"], v["model"], tmp / "voice") if v else None
    info = render_video(spec, out, brand=opts.get("brand", ""), cover_path=cover, reveal=opts.get("reveal"),
                        voice=vcfg, track=track)
    if opts.get("voice_error"):  # the main server couldn't make the lines: say why, as a local render would
        info["voice"] = f"failed: {opts['voice_error']}"[:200]
    return info


def _racing(req: dict, out: Path, cover: Path | None) -> dict:
    from .render.racing.engine import render

    return render(req["spec"], out, cover_path=cover)


def _adventure(req: dict, tmp: Path, out: Path) -> dict:
    from .adventure.jobs import _node

    spec_file = tmp / "spec.json"
    spec_file.write_text(json.dumps(req["spec"]))
    args = []
    for a in req["options"].get("args", []):
        if a.startswith(remote.FILE_ARG):
            name = a[len(remote.FILE_ARG):]
            if not remote.safe_name(name) or not (tmp / name).is_file():
                raise HTTPException(400, f"missing file {name!r}")
            a = str(tmp / name)
        args.append(a)
    workers = str(max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4")))))
    return _node(str(spec_file), "--out", str(out), "--workers", workers, *args)


@app.post("/render")
async def render(request: Request, authorization: str = Header(default="")) -> Response:
    if not TOKEN or not hmac.compare_digest(authorization.encode(), f"Bearer {TOKEN}".encode()):
        raise HTTPException(401, "bad token")
    if int(request.headers.get("content-length") or 0) > MAX_REQUEST:
        raise HTTPException(413, "too large")
    body = await request.body()
    if len(body) > MAX_REQUEST:
        raise HTTPException(413, "too large")
    if not _busy.acquire(blocking=False):
        raise HTTPException(503, "busy with another render")
    try:
        return await run_in_threadpool(_run, body)
    finally:
        _busy.release()


def _run(body: bytes) -> Response:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        req = _unpack(body, tmp)
        out = tmp / "out" / "video.mp4"
        out.parent.mkdir()
        cover = tmp / "out" / "cover.jpg" if req.get("cover") else None
        kind = req["kind"]
        log.info("rendering a %s video", kind)
        try:
            if kind == "quiz":
                info = _quiz(req, tmp, out, cover)
            elif kind == "racing":
                info = _racing(req, out, cover)
            else:
                info = _adventure(req, tmp, out)
        except HTTPException:
            raise
        except Exception as e:  # the main server renders it itself; the reason goes in its log
            log.exception("render failed")
            raise HTTPException(500, f"render failed: {type(e).__name__}: {e}"[:400])
        files = {"video.mp4": out}
        if cover is not None:
            files["cover.jpg"] = cover
        return Response(remote.pack("summary.json", info, files), media_type="application/zip")
