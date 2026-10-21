"""Render → publish → notify, one job at a time."""
from __future__ import annotations

import logging
import queue
import secrets
import tempfile
import threading
import time
from pathlib import Path

from . import notify, store
from .config import settings
from .images import fetch_images
from .publish import instagram, tiktok
from .render.engine import render_video
from .spec import StorySpec

log = logging.getLogger(__name__)
_queue: "queue.Queue[str]" = queue.Queue()


def submit(spec: StorySpec, dry_run: bool = False) -> dict:
    job = {
        "id": f"{spec.id}-{secrets.token_hex(3)}",
        "spec": spec.model_dump(),
        "dry_run": dry_run,
        "status": "queued",
        "created_at": store.now_iso(),
        "results": {},
    }
    store.save_job(job)
    _queue.put(job["id"])
    return job


def media_url(name: str) -> str:
    return f"{settings.public_base_url}/media/{name}"


def _run(job_id: str) -> None:
    job = store.get_job(job_id)
    if not job:
        return
    spec = StorySpec.model_validate(job["spec"])
    stem = f"{spec.id}-{secrets.token_urlsafe(8)}"  # unguessable public URL
    video = settings.videos_dir / f"{stem}.mp4"
    cover = settings.videos_dir / f"{stem}.jpg"

    job["status"] = "fetching_images"
    store.save_job(job)
    with tempfile.TemporaryDirectory() as tmp:
        image_paths, image_errors = fetch_images(spec, Path(tmp))
        job.update(status="rendering", image_errors=image_errors)
        store.save_job(job)
        info = render_video(spec, video, brand=settings.brand_handle, cover_path=cover, image_paths=image_paths)
    job.update(status="rendered", render=info, video=video.name, video_url=media_url(video.name),
               cover_url=media_url(cover.name))
    store.save_job(job)

    publish = settings.publish_enabled and not job["dry_run"]
    results = job["results"]
    if publish and settings.tiktok_enabled:
        try:
            results["tiktok"] = {"ok": True, **tiktok.upload_draft(video)}
        except Exception as e:
            log.exception("tiktok upload failed")
            results["tiktok"] = {"ok": False, "error": str(e)[:500]}
    if publish and settings.instagram_enabled and settings.instagram_mode == "auto":
        try:
            results["instagram"] = {"ok": True, **instagram.publish_reel(job["video_url"], spec.full_caption(), job["cover_url"])}
        except Exception as e:
            log.exception("instagram publish failed")
            results["instagram"] = {"ok": False, "error": str(e)[:500]}

    if not job["dry_run"]:
        store.add_history({
            "date": store.now_iso(),
            "id": spec.id,
            "topic_key": spec.topic_key,
            "category": spec.category,
            "palette": spec.palette,
            "title": next((b.text for b in spec.beats if b.type in ("title", "hook")), spec.id),
            "sources": spec.sources,
            "job_id": job_id,
        })

    job["status"] = "done"
    store.save_job(job)
    _notify(job, spec, video)


def _notify(job: dict, spec: StorySpec, video: Path) -> None:
    r = job["results"]
    lines = []
    if "tiktok" in r:
        lines.append("**TikTok:** " + ("in your drafts/inbox, add a sound and post" if r["tiktok"]["ok"] else f"failed: {r['tiktok']['error']}"))
    if "instagram" in r:
        lines.append("**Instagram:** " + ("published" if r["instagram"]["ok"] else f"failed: {r['instagram']['error']}"))
    if settings.instagram_mode != "auto" or "instagram" not in r:
        lines.append("**Instagram:** save the video below, post it as a Reel and add the sound")
    if job.get("image_errors"):
        lines.append("**Images skipped:** " + ", ".join(f"`{k}` ({v})" for k, v in job["image_errors"].items()))
    if not settings.publish_enabled or job["dry_run"]:
        lines.insert(0, "_Publishing is off; nothing was uploaded._")

    embed = {
        "title": f"New short ready: {spec.id}",
        "url": job["video_url"],
        "color": 0x8B6CFF,
        "fields": [
            {"name": "Suggested sound", "value": spec.suggested_sound or "(none)", "inline": False},
            {"name": "Sources", "value": "\n".join(spec.sources)[:1000], "inline": False},
            {"name": "Length", "value": f"{job['render']['duration']} s", "inline": True},
            *([{"name": "Image credits", "inline": False, "value": "\n".join(
                f"{i.credit} ({i.license or 'licence not stated'}): {i.url}" for i in spec.images)[:1000]}]
              if spec.images else []),
        ],
    }
    content = "\n".join(lines) + f"\n\n**Caption** (copy):\n```\n{spec.full_caption()[:1500]}\n```"
    notify.send(content, embed, attach=video)


def _worker() -> None:
    while True:
        job_id = _queue.get()
        try:
            _run(job_id)
        except Exception as e:
            log.exception("job %s failed", job_id)
            job = store.get_job(job_id) or {"id": job_id}
            job.update(status="failed", error=str(e)[:1000])
            store.save_job(job)
            notify.error(f"job `{job_id}` failed: {e}")


def _maintenance() -> None:
    """Twice a day: keep OAuth tokens fresh and delete old videos."""
    while True:
        for name, fn in (("tiktok", tiktok.refresh_if_needed), ("instagram", instagram.refresh_if_needed)):
            try:
                fn()
            except Exception as e:
                log.exception("%s token refresh failed", name)
                notify.error(f"{name} token refresh failed ({e}); reconnect via /oauth/{name}/start")
        cutoff = time.time() - settings.keep_videos_days * 86400
        for f in settings.videos_dir.glob("*"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        time.sleep(12 * 3600)


def start_background() -> None:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_worker, daemon=True, name="render-worker").start()
    threading.Thread(target=_maintenance, daemon=True, name="maintenance").start()
