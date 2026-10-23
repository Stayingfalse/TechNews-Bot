"""Per-post performance numbers from every platform, for the dashboard and the weekly review.

Each posted quiz is snapshotted at about 1 hour, 24 hours and 7 days old, and its latest numbers
are refreshed every few hours until it is 14 days old. Stored in metrics.json on the /data volume.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from . import store
from .config import settings
from .publish import PUBLISHERS
from .spec import QuizSpec

log = logging.getLogger(__name__)
_lock = threading.Lock()

SNAPSHOTS = {"1h": 1, "24h": 24, "7d": 168}  # name -> hours after posting
REFRESH_HOURS = 4
TRACK_DAYS = 14


def _age_hours(published_at: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(published_at)).total_seconds() / 3600


def posted_jobs() -> list[dict]:
    """Quizzes that went out to at least one platform, newest first."""
    jobs = [j for j in store.list_jobs(200)
            if j.get("status") == "done" and not j.get("dry_run") and j.get("published_at")
            and any(r.get("ok") for r in j.get("results", {}).values())]
    return sorted(jobs, key=lambda j: j["published_at"], reverse=True)


def tags_for(job: dict) -> dict[str, str]:
    """Labels to compare posts by: the routine's own experiment tags plus ones read off the quiz."""
    spec = QuizSpec.model_validate(job["spec"])
    types = sorted({r.type for r in spec.rounds})
    posted = datetime.fromisoformat(job.get("publish_at") or job["published_at"]).astimezone(settings.tz)
    secs = job.get("render", {}).get("duration") or 0
    auto = {
        "theme": spec.theme or "General mix",
        "rounds": str(len(spec.rounds)),
        "format": f"all {types[0]}" if len(types) == 1 else "mixed",
        "slot": posted.strftime("%H:%M"),
        "weekday": posted.strftime("%a"),
        "length": "under 30 s" if secs < 30 else "30-45 s" if secs < 45 else "45 s+",
        "palette": spec.palette,
        "music": str(job.get("render", {}).get("music") or spec.music),
        "test": "yes" if job["id"].startswith("test-") else "no",
        "intro": spec.intro,
        "cliffhanger": "yes" if spec.rounds[-1].cliffhanger else "no",
        "reveals_yesterday": "yes" if job.get("reveal") else "no",
        "ask_comment": "yes" if any(r.ask_comment for r in spec.rounds) else "no",
        "pause_hint": "yes" if spec.pause_hint else "no",
    }
    return {**auto, **spec.tags}


def _fetch(platform: str, job: dict) -> dict:
    res = job["results"][platform]
    mod = PUBLISHERS[platform]
    if platform == "instagram":
        return mod.metrics(res["media_id"])
    if platform == "youtube":
        return mod.metrics(res["video_id"], job["published_at"])
    return {"error": "metrics not supported yet"}


def collect(force: bool = False) -> int:
    """Take the snapshots that are due. Returns how many platform posts were updated."""
    data = store._read("metrics.json", {})
    updated = 0
    for job in posted_jobs():
        age = _age_hours(job["published_at"])
        if age > TRACK_DAYS * 24 and not force:
            continue
        entry = data.setdefault(job["id"], {})
        for platform, res in job["results"].items():
            if not res.get("ok") or platform not in PUBLISHERS or not PUBLISHERS[platform].configured():
                continue
            rec = entry.setdefault(platform, {"snapshots": {}})
            due = [name for name, h in SNAPSHOTS.items() if age >= h and name not in rec["snapshots"]]
            last = rec.get("latest", {}).get("at")
            stale = not last or _age_hours(last) >= REFRESH_HOURS
            if not (force or due or stale):
                continue
            try:
                m = _fetch(platform, job)
            except Exception as e:  # one platform failing must not stop the rest
                log.warning("metrics %s %s: %s", job["id"], platform, e)
                m = {"error": str(e)[:200]}
            m["at"] = store.now_iso()
            m["age_h"] = round(age, 1)
            rec["latest"] = m
            for name in due:
                rec["snapshots"][name] = m
            updated += 1
    with _lock:
        store._write("metrics.json", data)
    return updated


def _derived(m: dict, duration: float) -> dict:
    views = m.get("views") or 0
    acts = sum(m.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
    out = {}
    if views:
        out["engagement_per_1k"] = round(acts / views * 1000, 1)
        out["comments_per_1k"] = round((m.get("comments") or 0) / views * 1000, 1)
    if m.get("avg_watch_s") and duration:
        out["watched_pct"] = round(min(100.0, m["avg_watch_s"] / duration * 100), 1)
    elif m.get("avg_view_pct"):
        out["watched_pct"] = round(m["avg_view_pct"], 1)
    return out


def report() -> list[dict]:
    """Every posted quiz with its tags, answers and per-platform numbers (latest + snapshots)."""
    data = store._read("metrics.json", {})
    out = []
    for job in posted_jobs():
        spec = QuizSpec.model_validate(job["spec"])
        duration = job.get("render", {}).get("duration") or 0
        platforms = {}
        for p, res in job["results"].items():
            if not res.get("ok"):
                continue
            rec = data.get(job["id"], {}).get(p, {})
            latest = rec.get("latest", {})
            platforms[p] = {"url": res.get("url"), "latest": {**latest, **_derived(latest, duration)},
                            "snapshots": {k: {**v, **_derived(v, duration)} for k, v in rec.get("snapshots", {}).items()}}
        out.append({
            "job_id": job["id"], "published_at": job["published_at"], "slot": job.get("slot"),
            "title": spec.title.replace("*", ""), "duration_s": duration,
            "rounds": [{"type": r.type, "answer": r.answer_text()} for r in spec.rounds],
            "tags": tags_for(job), "platforms": platforms,
        })
    return out


def run_forever() -> None:
    while True:
        try:
            n = collect()
            if n:
                log.info("metrics: updated %d platform posts", n)
        except Exception:
            log.exception("metrics collection failed")
        time.sleep(15 * 60)
