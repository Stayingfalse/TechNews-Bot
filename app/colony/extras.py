"""Farside extras: a standalone video posted outside the daily cycle (a catch-up, a teaser).

POST /colony/extra takes an episode in the same format as POST /colony/today (beats and a
caption). It renders straight away from the colony as it stands, with a quiet day (nobody
arriving, nothing built), sends a Discord preview with the video, and posts as soon as it's
ready, or at `at`. Nothing about the colony changes: no settlers, no replies, no new parts,
and the day's own episode still posts at its slot. Comments on an extra are read like any
other post's, so people who comment there still get a settler.

Stored in DATA_DIR/colony/extras/<id>.json. Run by the same schedule loop as the days.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import channels, notify, store
from ..config import settings
from ..publish import instagram
from . import episode, plan, rules, state

log = logging.getLogger(__name__)
_mine: set[str] = set()
STALE = timedelta(minutes=20)
NOT_ALLOWED = ("settlers", "replies", "parts")  # an extra changes nobody and answers nobody
READ_FOR = timedelta(days=3)  # comments on an extra are read for this long after it posts


def _dir() -> Path:
    d = settings.data_dir / "colony" / "extras"
    d.mkdir(parents=True, exist_ok=True)
    return d


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


def recent(limit: int = 30) -> list[dict]:
    jobs = [json.loads(p.read_text()) for p in _dir().glob("*.json")]
    return sorted(jobs, key=lambda j: j["created_at"], reverse=True)[:limit]


def posted_media(t: datetime | None = None) -> list[tuple[str, str]]:
    """(extra id, media id) of extras posted lately, whose comments are still read."""
    t = t or datetime.now(timezone.utc)
    out = []
    for j in recent(20):
        ig = (j.get("results") or {}).get("instagram") or {}
        if ig.get("ok") and j.get("published_at") and t - datetime.fromisoformat(j["published_at"]) < READ_FOR:
            out.append((j["id"], ig["media_id"]))
    return out


def parse_at(at: str, now: datetime | None = None) -> datetime | None:
    """`at`: "" (as soon as it's rendered), HH:MM (today, local) or an ISO date-time (local if no
    offset). A "+" in a query string arrives as a space, so a trailing " 00:00" offset is read as
    "+00:00"; a space between the date and the time is left alone."""
    if not at:
        return None
    now = now or datetime.now(timezone.utc)
    at = at.strip()
    if re.fullmatch(r"\d{1,2}:\d{2}", at):
        h, m = (int(x) for x in at.split(":"))
        when = now.astimezone(settings.tz).replace(hour=h, minute=m, second=0, microsecond=0)
    else:
        at = re.sub(r"(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?) (\d{2}:?\d{2})$", r"\1+\2", at)
        try:
            when = datetime.fromisoformat(at)
        except ValueError:
            raise ValueError("at: HH:MM (today, local) or an ISO date-time")
        when = when if when.tzinfo else when.replace(tzinfo=settings.tz)
    if when < now:
        raise ValueError(f"at: {when.isoformat()} has already passed")
    return when.astimezone(timezone.utc)


def check(ep) -> tuple[list[str], dict]:
    """The problems with an extra's episode, and the checked copy."""
    if not isinstance(ep, dict):
        return ["the episode must be a JSON object"], {}
    probs = [f"{k}: an extra can't {what}" for k, what in
             (("settlers", "change settlers"), ("replies", "send replies"), ("parts", "add parts")) if ep.get(k)]
    s = state.load()
    handles = {st["handle"].lower() for st in s["settlers"].values()}
    probs += plan.check_episode(ep, handles, adapted=True)
    shaped, _, _ = plan.shape(ep, adapted=True)
    return probs, shaped if isinstance(shaped, dict) else {}


def create(ep, at: datetime | None = None) -> dict:
    """Check the episode, keep it, and start rendering. Raises ValueError with the problems."""
    probs, ep = check(ep)
    if probs:
        raise ValueError(probs)
    ep = {k: v for k, v in ep.items() if k not in NOT_ALLOWED}
    local_now = datetime.now(settings.tz)
    job = {"id": f"farside-extra-{local_now:%Y%m%d-%H%M}-{secrets.token_hex(2)}", "kind": "extra",
           "date": local_now.date().isoformat(), "channel": channels.COLONY,
           "publish_at": at.isoformat() if at else None, "status": "queued", "created_at": store.now_iso(),
           "ep": ep, "results": {}}
    save(job)
    _spawn(prepare, job)
    return job


def _quiet_report(s: dict) -> dict:
    """A day where nothing happens: nobody arrives, nothing is built, nobody is featured."""
    return {"day": s.get("day") or datetime.now(settings.tz).date().isoformat(), "arrived": [], "jobs": [],
            "ranked_up": [], "recruits": [], "left": 0, "joined": 0, "unlocked": [], "gained": {},
            "featured": [], "next": rules.next_goal(s)}


def prepare(job: dict) -> None:
    from . import jobs

    try:
        with jobs._render_lock:
            job["status"] = "preparing"
            save(job)
            s = state.load()  # a copy: nothing here is saved back
            spec = episode.build(s, _quiet_report(s), job["ep"])
            spec, lines = jobs._voice(job, spec, s)
            job["caption"] = spec["caption"]
            job["status"] = "rendering"
            save(job)
            jobs._render(job, spec, persist=False, voice=lines)
            job["status"] = "scheduled"
            save(job)
            _preview(job)
    except Exception as e:
        _fail(job, e, "preparing")


def _when(job: dict) -> str:
    if not job.get("publish_at"):
        return "now"
    return datetime.fromisoformat(job["publish_at"]).astimezone(settings.tz).strftime("%a %d %b %H:%M")


def _preview(job: dict) -> None:
    v = job.get("voice") or {}
    lines = [f":ringed_planet: **Farside extra** `{job['id']}` posts {_when(job)} unless cancelled",
             f"{job['render']['duration']:.0f}s · " + (f"voiced ({v.get('lines')} lines, {v.get('chars')} chars)"
                                                     if v.get("on") else f"NO VOICE: {v.get('why', 'off')}"),
             f"Caption: {job.get('caption', '')[:300]}",
             f"Cancel: `DELETE /colony/extras/{job['id']}`"]
    notify.send("\n".join(lines), attach=settings.videos_dir / job["video"])


def post(job: dict) -> None:
    try:
        with channels.use(channels.COLONY):
            try:
                res = {"ok": True, **instagram.publish_reel(job["video_url"], job["caption"], job.get("cover_url"))}
            except Exception as e:
                log.exception("farside extra post failed")
                res = {"ok": False, "error": str(e)[:500]}
        job["results"]["instagram"] = res
        ok = res["ok"]
        job.update(status="done" if ok else "failed", finished_at=store.now_iso())
        if ok:
            job["published_at"] = store.now_iso()
        else:
            job["error"] = res["error"]
        save(job)
        notify.send(f":ringed_planet: **Farside extra {'posted' if ok else 'post FAILED'}** `{job['id']}`: "
                    + (str(res.get("url") or res.get("media_id")) if ok else
                       f"{res['error']}\nRetry with POST /colony/extras/{job['id']}/retry"))
    except Exception as e:
        _fail(job, e, "publishing")


def _fail(job: dict, e: Exception, step: str) -> None:
    log.exception("farside extra %s failed during %s", job["id"], step)
    job.update(status="failed", error=f"{step}: {e}"[:1000])
    save(job)
    notify.send(f":warning: **Farside extra** `{job['id']}` failed during {step}: {e}\n"
                f"Retry with POST /colony/extras/{job['id']}/retry")


def retry(job_id: str) -> dict:
    job = get(job_id)
    if not job:
        raise LookupError(f"no extra {job_id}")
    if job["status"] != "failed":
        raise ValueError("only a failed extra can be retried")
    job.update(error=None, results={})
    if job.get("video") and (settings.videos_dir / job["video"]).exists():
        job["status"] = "publishing"
        save(job)
        _spawn(post, job)
    else:
        job["status"] = "queued"
        save(job)
        _spawn(prepare, job)
    return job


def cancel(job_id: str) -> dict:
    job = get(job_id)
    if not job:
        raise LookupError(f"no extra {job_id}")
    if job["status"] in ("publishing", "done", "cancelled"):
        raise ValueError(f"can't cancel an extra that is {job['status']}")
    job["status"] = "cancelled"
    save(job)
    return job


def _spawn(target, job: dict) -> None:
    _mine.add(job["id"])

    def run():
        try:
            target(job)
        finally:
            _mine.discard(job["id"])

    threading.Thread(target=run, daemon=True, name=job["id"]).start()


def tick(t: datetime | None = None) -> None:
    """Post what's due, and pick up extras a restart left half-done."""
    t = t or datetime.now(timezone.utc)
    cutoff = time.time() - STALE.total_seconds()
    for job in recent(20):
        st = job["status"]
        if job["id"] in _mine:
            continue
        stale = (_dir() / f"{job['id']}.json").stat().st_mtime < cutoff
        if st in ("queued", "preparing", "rendering") and stale:
            job["status"] = "queued"
            save(job)
            _spawn(prepare, job)
        elif st == "publishing" and stale:
            job.update(status="failed", error="the server restarted while posting")
            save(job)
            notify.send(f":warning: **Farside**: the server restarted while posting extra `{job['id']}`; check "
                        f"@{settings.colony_handle} before retrying.")
        elif st == "scheduled" and (not job.get("publish_at") or t >= datetime.fromisoformat(job["publish_at"])):
            job["status"] = "publishing"
            save(job)
            _spawn(post, job)
