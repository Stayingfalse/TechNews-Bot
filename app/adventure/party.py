"""The party: viewers who join the story. A joiner gets a companion (a story character the server
draws: name, class, look) that travels with the hero with their username on it, while they keep
commenting. Plus the story's credits ("rolled by @name"). docs/VOICES_STORY_PLAN.md §2.

- Places adapt to turnout: about one place for every 4 voters on recent episodes, 2 to 6.
- Open places go to joiners in the order they asked; once a week one place goes to a random joiner
  first, so newcomers get in.
- A member who misses INACTIVE episodes in a row (no comment of any kind) heads home.
- Companions are drawn from fixed lists, seeded by the member, never from anything they wrote. That
  keeps everything the AI writer may see about a companion free of personal data (§5).
- Names need a moderation look before they're shown (dashboard): names already approved go straight
  on; new ones are shown unless removed before the post. Removed names are blocked from the party
  and credits for good.

Stored in DATA_DIR/adventure/party.json. Usernames leave it RETENTION_DAYS after a member leaves or
a credit's episode (privacy policy §5), and on erasure or opt-out at once.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import threading
from datetime import datetime, timedelta, timezone

from ..config import settings

INACTIVE = 3  # episodes in a row without a comment before a companion heads home
MIN_PLACES, MAX_PLACES, VOTERS_PER_PLACE = 2, 6, 4
QUEUE_DAYS = 14  # a join request waits this long for a place
RALLY = ((50, 3), (25, 2), (10, 1))  # voters → bonus on the roll

NAMES = ["Ash", "Brindle", "Moss", "Wren", "Corin", "Tamsin", "Bram", "Isolde", "Fenn", "Mabry", "Rook", "Hester",
         "Odo", "Linnet", "Garrick", "Sable", "Tobin", "Elsbeth", "Pip", "Rowan", "Alder", "Juniper", "Cade", "Merrin",
         "Hollis", "Briar", "Quill", "Nell", "Thorne", "Ivo", "Saffi", "Dunstan", "Wynn", "Maud", "Kestrel", "Bede"]
CLASSES = ["fighter", "rogue", "wizard"]

_lock = threading.RLock()


def _path():
    from .campaign import _dir

    return _dir() / "party.json"


def load() -> dict:
    p = _path()
    s = json.loads(p.read_text()) if p.exists() else {}
    for k, v in {"members": [], "queue": [], "past": [], "credits": [], "turnout": [], "approved": [], "blocked": [],
                 "random_week": None, "updates": {}}.items():
        s.setdefault(k, v)
    return s


def save(s: dict) -> None:
    from .campaign import _write

    _write(_path(), s)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _h(*parts: object) -> int:
    msg = ":".join(str(p) for p in parts).encode()
    return int.from_bytes(hmac.new(settings.api_token.encode(), msg, hashlib.sha256).digest()[:8], "big")


def shown_name(user: str | None) -> str | None:
    """The username as it may appear on screen, or None (too short, offensive, opted out)."""
    from .. import privacy
    from ..cliffhanger import safe_name

    if not user or privacy.is_opted_out(user):
        return None
    return safe_name(user)


def rally(voters: int) -> int:
    return next((bonus for need, bonus in RALLY if voters >= need), 0)


def places_for(turnout: list[int]) -> int:
    """Adaptive: about one place per VOTERS_PER_PLACE voters over the last 3 episodes."""
    recent = turnout[-3:]
    if not recent:
        return 3
    return max(MIN_PLACES, min(MAX_PLACES, math.ceil(sum(recent) / len(recent) / VOTERS_PER_PLACE)))


def _draw(key: str, taken: set[str]) -> dict:
    """A companion for this member: the server's draw, nothing from what they wrote."""
    h = _h("companion", key)
    names = [n for n in NAMES if n not in taken] or NAMES
    return {"name": names[h % len(names)], "cls": CLASSES[(h // 97) % 3], "look": (h // 991) % 3}


def update(ep: int, tally: dict, when: datetime | None = None) -> dict:
    """Apply yesterday's comments (votes on episode ep - 1) before episode `ep` is made: leaves,
    activity, the inactivity rule, joins, places. Safe to repeat for the same episode: the first
    result is kept (a re-render or a retry doesn't move anyone again)."""
    when = when or datetime.now(timezone.utc)
    with _lock:
        s = load()
        done = s["updates"].get(str(ep))
        if done:
            return done
        blocked = set(s["blocked"])
        on = ep - 1  # the episode the comments were on
        left, joined = [], []

        def depart(m: dict, reason: str) -> None:
            s["members"].remove(m)
            s["past"].append({**m, "left_ep": ep, "left_at": _now(), "reason": reason})
            left.append({"name": m["companion"]["name"], "handle": m["user"], "reason": reason})

        for r in tally.get("leaves", []):
            m = next((m for m in s["members"] if m["key"] == r["key"]), None)
            if m:
                depart(m, "left")
            s["queue"] = [q for q in s["queue"] if q["key"] != r["key"]]
        from .. import privacy

        active = {c["key"] for c in tally.get("commenters", [])}
        for m in list(s["members"]):
            if privacy.is_opted_out(m["user"]):
                depart(m, "opted out")
                s["past"][-1].update(key=None, user=None, uid=None)
                left[-1]["handle"] = None
            elif m["key"] in active:
                m["last_ep"] = on
            elif on - m.get("last_ep", on) >= INACTIVE:
                depart(m, "inactive")
        members = {m["key"] for m in s["members"]}
        queued = {q["key"] for q in s["queue"]}
        for r in tally.get("joins", []):
            if r["key"] in members or r["key"] in queued or r["key"] in blocked or not shown_name(r["user"]):
                continue
            s["queue"].append({"key": r["key"], "user": r["user"], "uid": r.get("uid"),
                               "asked": when.isoformat(timespec="seconds"), "asked_ep": on})
            queued.add(r["key"])
        cutoff = (when - timedelta(days=QUEUE_DAYS)).isoformat()
        s["queue"] = [q for q in s["queue"] if q["asked"] >= cutoff and shown_name(q["user"])]

        s["turnout"].append({"ep": on, "voters": len(tally.get("voters", []))})
        s["turnout"] = s["turnout"][-30:]
        places = places_for([t["voters"] for t in s["turnout"]])

        def admit(q: dict, how: str) -> None:
            taken = {m["companion"]["name"] for m in s["members"]}
            m = {"key": q["key"], "user": q["user"], "uid": q.get("uid"), "joined_ep": ep, "last_ep": on,
                 "joined_at": _now(), "how": how, "companion": _draw(q["key"], taken)}
            s["members"].append(m)
            s["queue"].remove(q)
            joined.append({"name": m["companion"]["name"], "handle": m["user"], "how": how})

        week = when.astimezone(settings.tz).strftime("%G-W%V")
        if s["queue"] and len(s["members"]) < places and s["random_week"] != week:
            admit(s["queue"][_h("random", week) % len(s["queue"])], "weekly draw")
            s["random_week"] = week
        while s["queue"] and len(s["members"]) < places:
            admit(s["queue"][0], "first in line")
        out = {"ep": ep, "places": places, "joined": joined, "left": left, "members": len(s["members"]),
               "waiting": len(s["queue"])}
        s["updates"][str(ep)] = out
        s["updates"] = dict(list(s["updates"].items())[-10:])
        save(s)
        return out


def pick_roller(ep: int, voters: list[dict]) -> str | None:
    """A random voter to credit with today's roll (the server still rolls). None if nobody can be shown."""
    s = load()
    blocked = set(s["blocked"])
    names = sorted({v["user"] for v in voters if v.get("user") and v["user"].lower() not in blocked and shown_name(v["user"])})
    return names[_h("roller", ep) % len(names)] if names else None


def credit(ep: int, job_id: str, kind: str, user: str, word: str | None = None) -> None:
    with _lock:
        s = load()
        s["credits"] = [c for c in s["credits"] if not (c["ep"] == ep and c["kind"] == kind and c["key"] == user.lower())]
        s["credits"].append({"ep": ep, "job": job_id, "kind": kind, "user": user, "key": user.lower(), "at": _now(),
                             **({"word": word} if word else {})})
        save(s)


def spec_party(ep: int | None = None) -> list[dict]:
    """The party as the renderer draws it: companions (story data) plus the handle to show."""
    s = load()
    blocked = set(s["blocked"])
    out = []
    for m in s["members"]:
        handle = shown_name(m["user"]) if m["key"] not in blocked else None
        out.append({**m["companion"], "handle": handle, "key": m["key"]})
    return out


def moment_slot(ep: int, size: int) -> int | None:
    """Which companion (slot, from 1) gets a moment in today's story: a random draw on the server,
    never based on what anyone wrote."""
    return _h("moment", ep) % size + 1 if size else None


def story_party(party: list[dict]) -> list[dict]:
    """The same party with nothing about the people: what the AI writer (P2) may be given."""
    return [{"slot": i + 1, "name": c["name"], "cls": c["cls"]} for i, c in enumerate(party)]


# ------------------------------------------------------------------ moderation


def approved(key: str) -> bool:
    return key.lower() in set(load()["approved"])


def approve(key: str) -> None:
    with _lock:
        s = load()
        s["approved"] = sorted(set(s["approved"]) | {key.lower()})
        s["blocked"] = [b for b in s["blocked"] if b != key.lower()]
        save(s)


def block(key: str) -> None:
    """Never show this name again: out of the party, the queue and the credits."""
    key = key.lower()
    with _lock:
        s = load()
        s["blocked"] = sorted(set(s["blocked"]) | {key})
        s["approved"] = [a for a in s["approved"] if a != key]
        for m in [m for m in s["members"] if m["key"] == key]:
            s["members"].remove(m)
            s["past"].append({**m, "user": None, "left_ep": None, "left_at": _now(), "reason": "removed"})
        s["queue"] = [q for q in s["queue"] if q["key"] != key]
        s["credits"] = [c for c in s["credits"] if c["key"] != key]
        save(s)


# ------------------------------------------------------------------ privacy


def erase(key: str) -> int:
    """Erasure / opt-out: the username leaves every party record (companions they had stay in the
    story under their story names). Returns how many records changed."""
    key = key.lower().lstrip("@")
    n = 0
    with _lock:
        s = load()
        for m in [m for m in s["members"] if m["key"] == key]:
            s["members"].remove(m)
            s["past"].append({**m, "key": None, "user": None, "uid": None, "left_ep": None, "left_at": _now(), "reason": "opted out"})
            n += 1
        before = len(s["queue"]) + len(s["credits"])
        s["queue"] = [q for q in s["queue"] if q["key"] != key]
        s["credits"] = [c for c in s["credits"] if c["key"] != key]
        for p in s["past"]:
            if p.get("key") == key:
                p.update(key=None, user=None, uid=None)
                n += 1
        n += before - len(s["queue"]) - len(s["credits"])
        s["approved"] = [a for a in s["approved"] if a != key]
        if n:
            save(s)
    return n


def purge_old(days: int) -> int:
    """Storage limitation: usernames leave past members `days` after they left, and credits `days`
    after they were given."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    with _lock:
        s = load()
        for p in s["past"]:
            if p.get("user") and (p.get("left_at") or "9") < cutoff:
                p.update(key=None, user=None, uid=None)
                n += 1
        before = len(s["credits"])
        s["credits"] = [c for c in s["credits"] if c["at"] >= cutoff]
        n += before - len(s["credits"])
        if n:
            save(s)
    return n


def chronicle() -> dict:
    """What the public /chronicle page shows: the party now, who's waiting, past companions, credits."""
    s = load()
    blocked = set(s["blocked"])
    show = lambda u, k: shown_name(u) if u and k not in blocked else None  # noqa: E731
    return {
        "members": [{**m["companion"], "handle": show(m["user"], m["key"]), "joined_ep": m["joined_ep"]} for m in s["members"]],
        "waiting": len(s["queue"]),
        "past": [{**p["companion"], "handle": show(p.get("user"), p.get("key")), "joined_ep": p.get("joined_ep"),
                  "left_ep": p.get("left_ep"), "reason": p.get("reason")} for p in s["past"][-40:]][::-1],
        "credits": [{"ep": c["ep"], "kind": c["kind"], "handle": show(c["user"], c["key"]), "word": c.get("word")}
                    for c in s["credits"][-90:]][::-1],
        "places": places_for([t["voters"] for t in s["turnout"]]),
    }
