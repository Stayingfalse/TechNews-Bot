"""Building blocks for tests: posted and booked jobs written straight into the store."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

from app import store


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def posted(job_id: str, spec: dict, hours_ago: float, results: dict | None = None, **extra) -> dict:
    job = {"id": job_id, "spec": copy.deepcopy(spec), "status": "done", "dry_run": False,
           "created_at": ago(hours_ago + 1), "published_at": ago(hours_ago),
           "results": results if results is not None else {
               "instagram": {"ok": True, "media_id": f"M-{job_id}", "url": f"https://instagram.com/reel/{job_id}"},
               "youtube": {"ok": True, "video_id": f"V-{job_id}", "url": f"https://youtube.com/shorts/{job_id}"}},
           **extra}
    store.save_job(job)
    return job


def comment(cid: str, user: str, text: str, minute: int, channel: str = "") -> dict:
    return {"id": cid, "user": user, "text": text, "at": f"2026-10-23T12:{minute:02d}:00Z", "channel": channel}
