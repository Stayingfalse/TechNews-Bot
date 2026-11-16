"""Render a raosanta.uk promo and send it to Discord, without posting it anywhere.

POST /santa/preview takes a spec (app/santa/spec.py), renders it in the background with its
narrator (when its format is voiced and the budget allows) and sends the video to Discord.
Stored in DATA_DIR/santa/previews/<id>.json; the video is in the media folder, cleared like the
others after KEEP_VIDEOS_DAYS.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
from datetime import datetime
from pathlib import Path

from .. import notify, store
from ..config import settings
from ..render.santa.video import render_promo
from . import voice
from .spec import MAX_SECONDS, PromoSpec

log = logging.getLogger(__name__)
_render_lock = threading.Lock()  # one promo render at a time


def _dir() -> Path:
    d = settings.data_dir / "santa" / "previews"
    d.mkdir(parents=True, exist_ok=True)
    return d


def images_dir() -> Path:
    return settings.data_dir / "santa" / "images"


def save(job: dict) -> None:
    p = _dir() / f"{job['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1, default=str))
    os.replace(tmp, p)


def get(job_id: str) -> dict | None:
    if not re.fullmatch(r"[\w-]+", job_id or ""):
        return None
    p = _dir() / f"{job_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def recent(limit: int = 20) -> list[dict]:
    jobs = [json.loads(p.read_text()) for p in _dir().glob("*.json")]
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)[:limit]


def create(spec: PromoSpec, background: bool = True) -> dict:
    job = {"id": f"santa-{datetime.now(settings.tz):%Y%m%d-%H%M}-{secrets.token_hex(2)}", "kind": "preview",
           "channel": "santa", "status": "queued", "created_at": store.now_iso(), "spec": spec.model_dump()}
    save(job)
    if background:
        threading.Thread(target=run, args=(job,), daemon=True, name=f"santa-{job['id']}").start()
    else:
        run(job)
    return job


def run(job: dict) -> dict:
    spec = PromoSpec.model_validate(job["spec"])
    try:
        with _render_lock:
            job["status"] = "rendering"
            save(job)
            lines, job["voice"] = voice.lines(spec)
            name = f"{job['id']}-{secrets.token_hex(6)}"  # unguessable, as the quiz's
            out = settings.videos_dir / f"{name}.mp4"
            job["render"] = render_promo(spec, out, voice=lines, images_dir=images_dir(),
                                         cover_path=out.with_suffix(".jpg"), max_seconds=MAX_SECONDS)
            job.update(status="done", video=out.name, video_url=f"{settings.public_base_url}/media/{out.name}",
                       finished_at=store.now_iso())
            save(job)
        _notify(job, spec, out)
    except Exception as e:
        log.exception("santa preview %s failed", job["id"])
        job.update(status="failed", error=str(e)[:500])
        save(job)
        notify.send(f":warning: **raosanta.uk** preview `{job['id']}` failed: {str(e)[:300]}")
    return job


def _notify(job: dict, spec: PromoSpec, video: Path) -> None:
    r = job["render"]
    what = spec.format + (f" · {spec.audience}" if spec.audience != "everyone" else "")
    lines = [f":santa: **raosanta.uk** preview `{spec.id}` ({what}), not posted",
             f"{r['duration']} s · music: {r['music']} · voice: {job['voice']} · "
             f"{voice.spent()}/{settings.santa_voice_budget} voice characters used this month"]
    if spec.caption:
        lines.append(f"> {spec.caption[:600]}")
    if video.stat().st_size > notify.MAX_ATTACH:
        lines.append(job["video_url"])
    notify.send("\n".join(lines), attach=video)
