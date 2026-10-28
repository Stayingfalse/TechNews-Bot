"""Viewers' personal data: opt-outs, erasure and automatic anonymising.

The only personal data the quiz handles is what viewers post publicly in comments (username, the
comment's text and id, its time). The public policy is app/legal/privacy.html; this module makes
its promises true in code:
  - opt-out: a list of usernames the bot never reads, shows, credits or replies to
  - erase(): removes a username from every stored record (and opts them out)
  - anonymise_old(): names in post records are removed RETENTION_DAYS after the post
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from . import store

RETENTION_DAYS = 90


def _key(user: str) -> str:
    return re.sub(r"^@", "", user.strip()).lower()


def opted_out() -> set[str]:
    return set(store._read("optout.json", []))


def opt_out(user: str) -> None:
    with store._lock:
        names = opted_out() | {_key(user)}
        store._write("optout.json", sorted(names))


def is_opted_out(user: str) -> bool:
    return _key(user) in opted_out()


def _scrub(job: dict, user: str | None = None) -> bool:
    """Remove viewer data from a job record: one user's, or (user=None) everyone's. True if changed."""
    changed = False
    rv = job.get("reveal") or {}
    keep = lambda name: user is not None and _key(name) != user  # noqa: E731
    if rv.get("winners"):
        before = len(rv["winners"])
        rv["winners"] = [w for w in rv["winners"] if keep(w["user"])]
        changed |= len(rv["winners"]) != before
    if rv.get("shoutouts"):
        before = len(rv["shoutouts"])
        rv["shoutouts"] = [n for n in rv["shoutouts"] if keep(n)]
        changed |= len(rv["shoutouts"]) != before
    if rv.get("replies"):
        rv["replies"] = [r for r in rv["replies"] if keep(r["user"])]
    picked = (job.get("spec") or {}).get("picked_by")
    if picked and not keep(picked["user"]):
        job["spec"]["picked_by"] = None
        job.pop("picked_reply", None)
        changed = True
    return changed


def erase(user: str) -> int:
    """Article 17: delete a viewer's data from every stored post record, and opt them out so it isn't
    collected again. Returns how many records changed. (Their name in videos already posted stays on
    the platforms until those posts are removed there.)"""
    key = _key(user)
    opt_out(key)
    n = 0
    with store._lock:
        jobs = store._read("jobs.json", {})
        for job in jobs.values():
            if _scrub(job, key):
                n += 1
        store._write("jobs.json", jobs)
    from .racing import ledger

    n += ledger.erase(key)  # their racing balance and every bet
    return n


def anonymise_old(days: int = RETENTION_DAYS) -> int:
    """Storage limitation: strip viewer names from records of posts older than `days`."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    with store._lock:
        jobs = store._read("jobs.json", {})
        for job in jobs.values():
            if (job.get("published_at") or "9") < cutoff and not job.get("anonymised"):
                _scrub(job)
                job["anonymised"] = True
                n += 1
        if n:
            store._write("jobs.json", jobs)
    return n

