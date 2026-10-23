"""Viewer-picked themes.

A quiz with `ask_theme` ends by asking viewers to comment a theme for next week. The Monday batch
reads those comments (GET /themes/suggestions), picks one and credits the viewer in a quiz with
`picked_by`; once that quiz posts, the viewer gets a reply under their suggestion pointing at it.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from . import store
from .cliffhanger import BLOCKED, norm, read_comments, safe_name
from .config import settings
from .publish import PUBLISHERS
from .spec import QuizSpec

log = logging.getLogger(__name__)

# Comments that are a score or a reaction, not a theme
NOT_A_THEME = re.compile(r"^(\d+\s*(/\s*\d+|out of \d+)?|first|me|yes|no|lol|haha+|wow|nice|cool|love (it|this)|"
                         r"easy|hard|too easy|too hard|great|good|fun)\W*$", re.I)


def _theme_text(text: str) -> str | None:
    t = re.sub(r"@\w[\w.]*", " ", text)  # drop tags of friends
    t = re.sub(r"(?i)\b(theme|next week|please|pls|plz|do|can you|could you|how about|maybe)\b[:!,.]*", " ", t)
    t = " ".join(t.split()).strip(" -:,.!?")
    if not 2 <= len(t) <= 60 or not re.search(r"[A-Za-z]", t) or NOT_A_THEME.match(t):
        return None
    if any(b in t.lower() for b in BLOCKED):
        return None
    return t


def suggestions(days: int = 8) -> dict:
    """Theme suggestions from the comments on the `ask_theme` posts of the last `days` days."""
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    posts, found = [], []
    for job in store.list_jobs(200):
        if (job.get("status") != "done" or job.get("dry_run") or job["id"].startswith("test-")
                or (job.get("published_at") or "") < since):
            continue
        if not QuizSpec.model_validate(job["spec"]).ask_theme:
            continue
        rows, readable, errors = read_comments(job)
        posts.append({"job_id": job["id"], "published_at": job["published_at"], "comments": len(rows),
                      "platforms_read": readable, "errors": errors})
        for c in rows:
            theme, user = _theme_text(c["text"]), safe_name(c["user"])
            if theme and user:
                found.append({"theme": theme, "user": user, "platform": c["platform"], "comment_id": c["id"],
                              "at": c["at"], "job_id": job["id"]})
    groups: dict[str, dict] = {}
    for f in sorted(found, key=lambda f: f["at"]):  # earliest suggester of each theme first
        g = groups.setdefault(norm(f["theme"]), {"theme": f["theme"], "count": 0, "users": [], "first": f})
        if f["user"].lower() not in (u.lower() for u in g["users"]):
            g["count"] += 1
            g["users"].append(f["user"])
    ranked = sorted(groups.values(), key=lambda g: (-g["count"], g["first"]["at"]))
    return {"posts": posts, "groups": ranked, "suggestions": found}


REPLIES = {
    "youtube": "🎉 Your theme won! Today's quiz is the one you picked, with your name on it: {url}",
    "instagram": "🎉 Your theme won! Today's quiz is the one you picked, with your name on it. It's the newest post on our profile 👀",
}


def after_publish(job: dict) -> None:
    """The quiz with a viewer-picked theme is out: reply under the suggestion that picked it."""
    picked = QuizSpec.model_validate(job["spec"]).picked_by
    if (not picked or not settings.next_link_comments or job.get("dry_run")
            or (job.get("picked_reply") or {}).get("ok")):
        return
    res = job.get("results", {}).get(picked.platform, {})
    if not res.get("ok"):  # replying from a platform the quiz didn't go out on would point nowhere
        return
    try:
        PUBLISHERS[picked.platform].reply(picked.comment_id, REPLIES[picked.platform].format(url=res.get("url") or ""))
        job["picked_reply"] = {"ok": True, "user": picked.user}
    except Exception as e:
        log.warning("theme reply to %s: %s", picked.user, e)
        job["picked_reply"] = {"ok": False, "user": picked.user, "error": str(e)[:200]}
