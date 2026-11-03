"""Replies under Farside's posts, sent slowly: COLONY_REPLY_GAP seconds apart and at most
COLONY_REPLY_PER_HOUR an hour, paused for an hour if Instagram pushes back. Nobody blocked or opted
out is replied to, and each comment gets one reply at most.

Stored in DATA_DIR/colony/replies.json."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import notify
from ..config import settings

_lock = threading.RLock()
BLOCKED = ("action is blocked", "temporarily blocked", "spam", "rate limit", "too many")
PAUSE = timedelta(hours=1)


def _path() -> Path:
    d = settings.data_dir / "colony"
    d.mkdir(parents=True, exist_ok=True)
    return d / "replies.json"


def queue() -> dict:
    p = _path()
    return json.loads(p.read_text()) if p.exists() else {"items": [], "sent": [], "paused_until": None}


def _save(q: dict) -> None:
    p = _path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(q, indent=1))
    os.replace(tmp, p)


def add(items: list[dict]) -> int:
    """Queue {comment_id, user, text} replies; a comment already queued or answered is skipped."""
    with _lock:
        q = queue()
        known = {i["comment_id"] for i in q["items"] + q["sent"]}
        n = 0
        for it in items:
            if it.get("comment_id") and it["comment_id"] not in known and it.get("text"):
                q["items"].append({**it, "text": it["text"][:300]})
                known.add(it["comment_id"])
                n += 1
        _save(q)
    return n


def send_due(now: datetime | None = None) -> int:
    from ..privacy import opted_out
    from ..publish import instagram
    from . import state

    now = now or datetime.now(timezone.utc)
    sent = 0
    with _lock:
        q = queue()
        if q.get("paused_until") and datetime.fromisoformat(q["paused_until"]) > now:
            return 0
        skip = opted_out() | set(state.load()["blocked"])
        hour_ago = (now - timedelta(hours=1)).isoformat()
        last = max((i["sent_at"] for i in q["sent"] if i.get("sent_at")), default=None)
        in_hour = sum(1 for i in q["sent"] if (i.get("sent_at") or "") > hour_ago)
        while q["items"] and in_hour < settings.colony_reply_per_hour:
            if last and (now - datetime.fromisoformat(last)).total_seconds() < settings.colony_reply_gap:
                break
            item = q["items"].pop(0)
            if (item.get("user") or "").lstrip("@").lower() in skip:
                continue
            try:
                item["reply_id"] = instagram.reply(item["comment_id"], item["text"])
                item["sent_at"] = now.isoformat()
                q["sent"].append(item)
                sent += 1
                in_hour += 1
                last = item["sent_at"]
            except Exception as e:
                err = str(e)
                if any(k in err.lower() for k in BLOCKED):
                    q["items"].insert(0, item)
                    q["paused_until"] = (now + PAUSE).isoformat()
                    notify.send(f":no_entry: **Farside replies paused for an hour**: Instagram refused a reply ({err[:200]}).")
                    break
                item["error"] = err[:200]
                q["sent"].append(item)
        q["sent"] = q["sent"][-2000:]
        _save(q)
    return sent


def erase(handle: str) -> int:
    h = handle.lstrip("@").lower()
    with _lock:
        q = queue()
        before = len(q["items"]) + len(q["sent"])
        q["items"] = [i for i in q["items"] if (i.get("user") or "").lstrip("@").lower() != h]
        q["sent"] = [i for i in q["sent"] if (i.get("user") or "").lstrip("@").lower() != h]
        _save(q)
        return before - len(q["items"]) - len(q["sent"])
