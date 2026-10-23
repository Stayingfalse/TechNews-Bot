"""The cliffhanger loop.

A quiz whose last round is a `cliffhanger` posts without that round's answer and asks viewers to
comment theirs. When the next quiz is rendered (shortly before it posts), the comments on the
cliffhanger post are read from Instagram and YouTube, judged, and the first correct commenters
get a shout-out in the video next to the revealed answer. Once that quiz is posted, each of them
gets a reply under their comment pointing at the new video.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

from . import store
from .publish import PUBLISHERS
from .spec import QuizSpec

log = logging.getLogger(__name__)

MAX_SHOUTOUTS = 5
LOOKBACK = timedelta(days=4)  # a cliffhanger older than this is dropped rather than revealed
# Names shown on screen must be safe for a public video; anything matching these is skipped.
BLOCKED = ("fuck", "shit", "cunt", "nigg", "fag", "slut", "whore", "bitch", "dick", "cock", "porn", "sex",
           "nazi", "rape", "pussy", "wank", "twat", "retard", "kill")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    return " ".join(text.split())


def _matches(comment: str, target: str) -> bool:
    """Forgiving match: the answer appears in the comment, or the comment is a close misspelling of it."""
    c, t = norm(comment), norm(target)
    if not t:
        return False
    if re.search(rf"(^| ){re.escape(t)}( |$)", c):
        return True
    words, n = c.split(), len(t.split())
    windows = [" ".join(words[i:i + n]) for i in range(max(1, len(words) - n + 1))] or [c]
    return max(SequenceMatcher(None, w, t).ratio() for w in windows) >= 0.8


def is_correct(rnd, text: str) -> bool:
    if rnd.type == "true_false":
        words = set(norm(text).split())
        yes, no = bool(words & {"real", "true", "yes"}), bool(words & {"fake", "false", "no"})
        return (yes and not no) if rnd.answer else (no and not yes)
    if rnd.type in ("choice", "odd_one_out"):
        options = rnd.options if rnd.type == "choice" else rnd.items
        right = rnd.correct if rnd.type == "choice" else rnd.odd
        letter = re.fullmatch(r"\W*\(?([a-d])\)?\W*", text.strip().lower())
        if letter and rnd.type == "choice":
            return "abcd".index(letter.group(1)) == right
        hits = [i for i, o in enumerate(options) if _matches(text, o)]
        if hits:
            return hits == [right] or (right in hits and any(_matches(text, a) for a in rnd.accept))
        return any(_matches(text, a) for a in rnd.accept)
    return any(_matches(text, t) for t in rnd.correct_texts())


def reveal_text(rnd) -> tuple[str, str]:
    """(the answer as shown on the podium, a short note under it)."""
    if rnd.type == "true_false":
        return ("Real" if rnd.answer else "Fake"), rnd.explanation
    if rnd.type == "choice":
        return rnd.options[rnd.correct], rnd.note
    if rnd.type == "odd_one_out":
        return rnd.items[rnd.odd], rnd.reason
    return rnd.answer, getattr(rnd, "note", "")


def safe_name(user: str) -> str | None:
    plain = unicodedata.normalize("NFKD", user).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9._-]", "", plain)[:28]
    if len(name) < 2 or any(b in name.lower() for b in BLOCKED):
        return None
    return name


def pending_for(job: dict) -> dict | None:
    """The most recent posted cliffhanger, not yet revealed, posted before this job's slot."""
    before = datetime.fromisoformat(job.get("publish_at") or datetime.now(timezone.utc).isoformat())
    best = None
    for j in store.list_jobs(200):
        if j.get("status") != "done" or j.get("dry_run") or j["id"] == job["id"] or j.get("cliff_revealed_by"):
            continue
        if j["id"].startswith("test-") or not j.get("published_at"):
            continue
        posted = datetime.fromisoformat(j["published_at"])
        if not (before - LOOKBACK < posted < before):
            continue
        spec = QuizSpec.model_validate(j["spec"])
        if spec.rounds[-1].cliffhanger and (best is None or j["published_at"] > best["published_at"]):
            best = j
    return best


def collect(cliff_job: dict) -> dict:
    """Judge the comments on a cliffhanger post. shoutouts = None when no platform's comments could be read."""
    rnd = QuizSpec.model_validate(cliff_job["spec"]).rounds[-1]
    answer, note = reveal_text(rnd)
    found, readable, errors = [], 0, []
    for platform, res in cliff_job.get("results", {}).items():
        if not res.get("ok") or platform not in ("instagram", "youtube") or not PUBLISHERS[platform].configured():
            continue
        mod = PUBLISHERS[platform]
        try:
            if platform == "instagram":
                own = mod.own_name().lower()
                rows = [dict(c, platform=platform) for c in mod.comments(res["media_id"]) if c["user"].lower() != own]
            else:
                own = mod.connected_identity()
                rows = [dict(c, platform=platform) for c in mod.comments(res["video_id"]) if c.get("channel") != own]
            readable += 1
            found += rows
        except Exception as e:
            errors.append(f"{platform}: {e}"[:200])
            log.warning("cliffhanger comments %s: %s", platform, e)
    found.sort(key=lambda c: c["at"])
    winners, seen = [], set()
    for c in found:
        name = safe_name(c["user"])
        if not name or name.lower() in seen or not is_correct(rnd, c["text"]):
            continue
        seen.add(name.lower())
        winners.append({"platform": c["platform"], "comment_id": c["id"], "user": name, "at": c["at"]})
        if len(winners) == MAX_SHOUTOUTS:
            break
    return {
        "from_job": cliff_job["id"], "answer": answer, "note": note,
        "shoutouts": [w["user"] for w in winners] if readable else None,
        "winners": winners, "comments_read": len(found), "errors": errors, "collected_at": store.now_iso(),
    }


def prepare(job: dict) -> dict | None:
    """Called just before a scheduled quiz is rendered: the reveal for yesterday's cliffhanger, if any."""
    if job.get("dry_run") or not job.get("slot"):
        return None
    cliff = pending_for(job)
    return collect(cliff) if cliff else None


REPLIES = {
    "youtube": ["✅ You got it! You're in today's quiz: {url}", "🎉 Correct, and you made today's shout-outs: {url}",
                "✅ Nailed it, find your name in today's quiz: {url}"],
    "instagram": ["✅ You got it! You're in today's quiz 👀 It's the newest post on our profile.",
                  "🎉 Correct, and you made today's shout-outs! Check our latest quiz 👀",
                  "✅ Nailed it! Find your name in today's quiz, top of our profile."],
}


def after_publish(job: dict) -> None:
    """The quiz carrying the reveal is out: mark the cliffhanger revealed and reply to each winner."""
    reveal = job.get("reveal")
    if not reveal or job.get("dry_run") or not any(r.get("ok") for r in job.get("results", {}).values()):
        return
    cliff = store.get_job(reveal["from_job"])
    if cliff:
        cliff["cliff_revealed_by"] = job["id"]
        store.save_job(cliff)
    replies = []
    for i, w in enumerate(reveal.get("winners", [])):
        res = job["results"].get(w["platform"], {})
        if not res.get("ok"):
            continue
        text = REPLIES[w["platform"]][i % 3].format(url=res.get("url") or "")
        try:
            PUBLISHERS[w["platform"]].reply(w["comment_id"], text)
            replies.append({"user": w["user"], "platform": w["platform"], "ok": True})
        except Exception as e:
            replies.append({"user": w["user"], "platform": w["platform"], "ok": False, "error": str(e)[:200]})
    reveal["replies"] = replies
    store.save_job(job)
