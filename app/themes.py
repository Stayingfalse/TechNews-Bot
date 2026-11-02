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


# Words that make a comment a sentence about the quiz rather than a topic ("I would never have
# guessed shining", "can't decide if I prefer...", "had no clue for round 4")
SENTENCE = re.compile(r"(?i)\b(i|i'?m|i'?ve|i'?d|my|me|we|our|you|your|it'?s|this|that|was|were|is|are|am|would|should|"
                      r"can'?t|didn'?t|don'?t|won'?t|wasn'?t|isn'?t|got|get|guess(ed)?|knew|know|think|thought|"
                      r"prefer|had|have|has|never|clue|answer|round|question|wrong|right|score|voice|video|videos)\b")
MAX_WORDS = 5


# Words that end a theme named inside a sentence, read backwards from "theme": "we need a *Halloween* theme"
_BEFORE_THEME = {"a", "an", "the", "some", "any", "another", "more", "next", "new", "different", "great", "good",
                 "fun", "cool", "nice", "proper", "full", "whole", "for", "of", "to", "with", "like", "and", "or",
                 "need", "needs", "want", "wants", "have", "do", "try", "should", "could", "would", "please", "pls",
                 "plz", "what", "how", "about", "maybe", "then", "also", "but", "so", "on", "in", "be"}
MAX_THEME_WORDS = 4


def _clean_words(words: list[str]) -> str | None:
    t = " ".join(w.strip("'\".,!?:;()") for w in words).strip()
    return t if t and not SENTENCE.search(t) else None


def _theme_in_sentence(text: str) -> str | None:
    """A theme named inside a longer comment, as viewers answer "How many did you get? Comment a
    theme": "4 this time, I think we need a Halloween theme", "we should have an anime theme next",
    "Anime would be a great theme", "next theme should be Pixar"."""
    t = re.sub(r"@\w[\w.]*", " ", text)
    for clause in re.split(r"[.!?;\n]+|,\s*(?=\D)", t):
        # "theme should be Pixar", "theme idea: Pixar"
        m = re.search(r"(?i)\bthemes?\b\s*(?:idea|suggestion|request)?\s*(?:should be|could be|would be|is|=|:|-)\s*(.+)$", clause)
        if m:
            words = [w for w in m.group(1).split() if w.lower() not in ("a", "an", "the", "next", "please", "pls", "plz")]
            if found := _clean_words(words[:MAX_THEME_WORDS]):
                return found
        # "Anime would be a great theme", "Pixar is a good theme"
        m = re.match(r"(?i)^\s*(.+?)\s+(?:would|could|will|'d|might)?\s*(?:be|is|makes?)\s+(?:a|an)?\s*"
                     r"(?:\w+\s+)?themes?\b", clause)
        if m and len(m.group(1).split()) <= MAX_THEME_WORDS:
            if found := _clean_words(m.group(1).split()):
                return found
        # "we need a Halloween theme", "an anime theme next": the words just before "theme"
        m = re.search(r"(?i)^(.*?)\bthemes?\b", clause)
        if m:
            words = m.group(1).split()
            picked: list[str] = []
            for w in reversed(words):
                bare = w.strip("'\".,!?:;()").lower()
                if not bare or bare in _BEFORE_THEME or SENTENCE.fullmatch(bare) or bare.isdigit():
                    break
                picked.insert(0, w)
                if len(picked) == MAX_THEME_WORDS:
                    break
            if picked and (found := _clean_words(picked)):
                return found
    return None


def _theme_text(text: str) -> str | None:
    """The theme a comment suggests, or None if it reads as a reaction, an answer or a sentence."""
    inner = _theme_in_sentence(text)
    if inner and inner.lower() != text.strip().lower():
        return _theme_text(inner)  # the same checks as a bare suggestion (length, reactions, rude words)
    t = re.sub(r"@\w[\w.]*", " ", text)  # drop tags of friends
    t = re.sub(r"(?i)\b(theme|next week|please|pls|plz|do|can you|could you|how about|maybe|what about)\b[:!,.?]*", " ", t)
    t = " ".join(t.split()).strip(" -:,.!?")
    t = re.sub(r"(?i)^(a|an|the|some)\s+(?=\S+\s)", "", t)  # "a Harry Potter one" -> "Harry Potter one"
    t = re.sub(r"(?i)\s+(one|quiz|round|edition|special)$", "", t).strip()
    if not 2 <= len(t) <= 40 or not re.search(r"[A-Za-z]", t) or NOT_A_THEME.match(t):
        return None
    if len(t.split()) > MAX_WORDS or SENTENCE.search(t) or t.count(",") > 1:
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
                              "text": " ".join(c["text"].split())[:120], "at": c["at"], "job_id": job["id"]})
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
