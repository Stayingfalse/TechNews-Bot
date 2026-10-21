"""Render → (wait for the slot) → publish → notify.

One worker thread runs renders and publishes in order. A scheduler thread hands each scheduled
job to the worker when its slot arrives. Job state lives in jobs.json, so a restart picks up
where it left off.
"""
from __future__ import annotations

import logging
import queue
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import notify, store
from .config import settings
from .publish import LABELS, PUBLISHERS, refreshers
from .render.engine import render_video
from .spec import QuizSpec

log = logging.getLogger(__name__)
_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()  # (action, job_id); action: render | publish

ACTIVE = ("queued", "rendering", "scheduled", "publishing")  # still going to post
MISSED_AFTER = timedelta(hours=6)  # a slot more than this late (e.g. server was down) is skipped


def now() -> datetime:
    return datetime.now(timezone.utc)


def slot_time(day: date) -> datetime:
    """The UTC publish time for a local calendar day."""
    h, m = (int(x) for x in settings.post_time.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=settings.tz).astimezone(timezone.utc)


def today_local() -> date:
    return now().astimezone(settings.tz).date()


def media_url(name: str) -> str:
    return f"{settings.public_base_url}/media/{name}"


def submit(spec: QuizSpec, dry_run: bool = False, slot: date | None = None) -> dict:
    job = {
        "id": f"{spec.id}-{secrets.token_hex(3)}",
        "spec": spec.model_dump(),
        "dry_run": dry_run,
        "status": "queued",
        "created_at": store.now_iso(),
        "slot": slot.isoformat() if slot else None,
        "publish_at": slot_time(slot).isoformat() if slot else None,
        "results": {},
    }
    store.save_job(job)
    _queue.put(("render", job["id"]))
    return job


def scheduled_jobs() -> list[dict]:
    """Jobs holding a slot that hasn't been posted yet, earliest slot first."""
    jobs = [j for j in store.list_jobs(200) if j.get("slot") and j["status"] in ACTIVE]
    return sorted(jobs, key=lambda j: j["slot"])


def booked_jobs() -> list[dict]:
    """Jobs that hold their slot: still to be posted, or already posted."""
    return [j for j in store.list_jobs(200) if j.get("slot") and j["status"] in ACTIVE + ("done",)]


def cancel(job: dict, reason: str = "cancelled") -> None:
    job.update(status="cancelled", error=reason)
    store.save_job(job)


# ------------------------------------------------------------------ render

def _render(job: dict) -> None:
    spec = QuizSpec.model_validate(job["spec"])
    stem = f"{spec.id}-{secrets.token_urlsafe(8)}"  # unguessable public URL
    video = settings.videos_dir / f"{stem}.mp4"
    cover = settings.videos_dir / f"{stem}.jpg"
    job["status"] = "rendering"
    store.save_job(job)
    info = render_video(spec, video, brand=settings.brand_handle, cover_path=cover, music_dir=settings.music_dir)
    job.update(render=info, video=video.name, video_url=media_url(video.name), cover_url=media_url(cover.name))

    publish_at = datetime.fromisoformat(job["publish_at"]) if job.get("publish_at") else None
    if publish_at and publish_at > now():
        job["status"] = "scheduled"
        store.save_job(job)
        _notify_scheduled(job, spec, video)
    else:
        store.save_job(job)
        _publish(job)


# ------------------------------------------------------------------ publish

def _publish(job: dict) -> None:
    spec = QuizSpec.model_validate(job["spec"])
    video = settings.videos_dir / job.get("video", "")
    if not job.get("video") or not video.exists():  # never rendered, or the file was cleaned up
        job["publish_at"] = None  # publish straight after this render
        _render(job)
        return
    job["status"] = "publishing"
    store.save_job(job)

    results = job["results"]
    if settings.publish_enabled and not job["dry_run"]:
        for name in settings.platforms:
            if results.get(name, {}).get("ok"):
                continue  # already posted there (resuming after a restart)
            mod = PUBLISHERS[name]
            if not mod.configured():
                results[name] = {"ok": False, "error": "not configured (missing app credentials)"}
                continue
            try:
                results[name] = {"ok": True, **mod.publish(video, spec, job)}
            except Exception as e:
                log.exception("%s publish failed", name)
                results[name] = {"ok": False, "error": str(e)[:500]}
            store.save_job(job)  # record each platform as it completes

    if not job["dry_run"]:
        store.add_history({
            "date": store.now_iso(),
            "slot": job.get("slot"),
            "id": spec.id,
            "theme": spec.theme,
            "palette": spec.palette,
            "title": spec.title.replace("*", ""),
            "round_types": [r.type for r in spec.rounds],
            "answers": spec.answer_keys(),
            "music": job.get("render", {}).get("music"),
            "platforms": {k: v.get("ok") for k, v in results.items()},
            "job_id": job["id"],
        })
    job.update(status="done", published_at=store.now_iso())
    store.save_job(job)
    _notify_published(job, spec, video)


# ------------------------------------------------------------------ Discord

def _answers_field(spec: QuizSpec) -> dict:
    return {"name": "Answers", "inline": False, "value": "\n".join(
        f"{i}. {r.type}: {r.answer_text()}" for i, r in enumerate(spec.rounds, 1))[:1000]}


def _when(job: dict) -> str:
    return datetime.fromisoformat(job["publish_at"]).astimezone(settings.tz).strftime("%a %d %b, %H:%M")


def _notify_scheduled(job: dict, spec: QuizSpec, video: Path) -> None:
    embed = {
        "title": f"Scheduled for {_when(job)}: {spec.title.replace('*', '')}",
        "url": job["video_url"],
        "color": 0xFFC22E,
        "fields": [_answers_field(spec),
                   {"name": "Length", "value": f"{job['render']['duration']} s", "inline": True},
                   {"name": "Music", "value": job["render"].get("music", "?"), "inline": True},
                   {"name": "Platforms", "value": ", ".join(settings.platforms) or "(none)", "inline": True}],
    }
    notify.send(f"Preview of the {_when(job)} quiz. To pull it: `DELETE /schedule/{job['slot']}`", embed, attach=video)


def _notify_published(job: dict, spec: QuizSpec, video: Path) -> None:
    lines = []
    if not settings.publish_enabled or job["dry_run"]:
        lines.append("_Publishing is off; nothing was uploaded._")
    for name, res in job["results"].items():
        if not res["ok"]:
            lines.append(f"**{LABELS[name]}:** failed: {res['error']}")
        elif name == "tiktok" and res.get("mode") == "draft":
            lines.append("**TikTok:** in your inbox; open it and tap post")
        else:
            lines.append(f"**{LABELS[name]}:** posted {res.get('url') or res.get('privacy') or ''}".rstrip())
    embed = {
        "title": f"Posted: {spec.title.replace('*', '')}",
        "url": job["video_url"],
        "color": 0xFF5A3C,
        "fields": [_answers_field(spec)],
    }
    content = "\n".join(lines) + f"\n\n**Caption:**\n```\n{spec.full_caption()[:1500]}\n```"
    # scheduled posts already had the video attached to their preview
    notify.send(content, embed, attach=None if job.get("slot") else video)


# ------------------------------------------------------------------ threads

def _worker() -> None:
    while True:
        action, job_id = _queue.get()
        job = store.get_job(job_id)
        if not job or job["status"] in ("cancelled", "done"):
            continue
        try:
            if action == "render":
                _render(job)
            else:
                _publish(job)
        except Exception as e:
            log.exception("job %s failed", job_id)
            job = store.get_job(job_id) or {"id": job_id}
            job.update(status="failed", error=str(e)[:1000])
            store.save_job(job)
            when = f" (slot {job['slot']})" if job.get("slot") else ""
            notify.error(f"job `{job_id}`{when} failed during {action}: {e}")


_warned: set[str] = set()


def tick() -> None:
    """Hand due jobs to the worker; warn about an empty day and a short runway."""
    t = now()
    for job in scheduled_jobs():
        if job["status"] != "scheduled":
            continue
        due = datetime.fromisoformat(job["publish_at"])
        if due > t:
            continue
        if t - due > MISSED_AFTER:
            job.update(status="missed", error=f"server was not running at {due.isoformat()}")
            store.save_job(job)
            notify.error(f"skipped the {job['slot']} quiz `{job['id']}`: its slot passed while the server was down")
            continue
        job["status"] = "publishing"  # claim it so the next tick doesn't queue it twice
        store.save_job(job)
        _queue.put(("publish", job["id"]))

    today = today_local()
    if t >= slot_time(today) and today.isoformat() not in _warned:
        _warned.add(today.isoformat())
        held = [j for j in store.list_jobs(200) if j.get("slot") == today.isoformat() and j["status"] != "cancelled"]
        if not held:
            notify.error(f"nothing was scheduled for today ({today}); no quiz posted")
        ahead = [j for j in scheduled_jobs() if j["slot"] > today.isoformat()]
        if len(ahead) < 2:
            notify.error(f"only {len(ahead)} quiz(zes) scheduled after today; is the weekly routine running?")


def _scheduler() -> None:
    while True:
        try:
            tick()
        except Exception:
            log.exception("scheduler tick failed")
        time.sleep(30)


def _maintenance() -> None:
    """Twice a day: keep OAuth tokens fresh and delete old videos (never ones still to be posted)."""
    while True:
        for name, fn in refreshers():
            try:
                fn()
            except Exception as e:
                log.exception("%s token refresh failed", name)
                notify.error(f"{name} token refresh failed ({e}); reconnect via /oauth/{name}/start")
        keep = {Path(j["video"]).stem for j in scheduled_jobs() if j.get("video")}
        cutoff = time.time() - settings.keep_videos_days * 86400
        for f in settings.videos_dir.glob("*"):
            if f.stat().st_mtime < cutoff and f.stem not in keep:
                f.unlink(missing_ok=True)
        time.sleep(12 * 3600)


def _recover() -> None:
    """After a restart, re-queue unfinished work. Publishing resumes with the platforms not yet done."""
    for job in sorted(store.list_jobs(200), key=lambda j: j.get("created_at", "")):
        if job["status"] in ("queued", "rendering"):
            _queue.put(("render", job["id"]))
        elif job["status"] == "publishing":
            _queue.put(("publish", job["id"]))


def start_background() -> None:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    _recover()
    threading.Thread(target=_worker, daemon=True, name="worker").start()
    threading.Thread(target=_scheduler, daemon=True, name="scheduler").start()
    threading.Thread(target=_maintenance, daemon=True, name="maintenance").start()
