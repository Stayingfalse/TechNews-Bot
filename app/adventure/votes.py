"""Reading A/B/C votes out of comments, and deciding the winner.

A comment is a vote when it clearly picks one option: a lone letter ("B", "b!", "(c)"), a letter
leading a short comment ("B - the lock"), "option b" / "I pick c" / "team a", or one option's name
("goblins"). Anything naming two options, or a letter inside ordinary prose ("what a twist"), is not.
Each account's first vote counts. Ties are broken by a keyed hash, so nobody (us included) can steer
them; no votes at all means the post's stated default."""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata

from ..config import settings

LETTERS = "abc"
STOP = {"the", "and", "for", "with", "your", "this", "that", "into", "from", "another", "way", "old"}
_LEAD = re.compile(r"^\(?([abc])\)?(?:[\s.,:;!?)\-–—]|$)")
_PHRASE = re.compile(r"\b(?:option|choice|pick|picking|vote|voting|choose|choosing|go(?:ing)? with|team|letter|i say|my vote is)\s+\(?([abc])\b")


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"@\w+|https?://\S+", " ", text)  # mentions and links aren't votes
    return " ".join(text.split())


def _stem(w: str) -> str:
    return w[:-1] if len(w) > 4 and w.endswith("s") else w


def _keywords(label: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]+", _norm(label)) if len(w) >= 4 and w not in STOP}


def parse(text: str, options: list[str]) -> int | None:
    """The option (0-2) a comment votes for, or None."""
    t = _norm(text)
    bare = re.sub(r"[^a-z0-9 ]+", " ", t).split()
    letters = [w for w in bare if len(w) == 1 and w in LETTERS[: len(options)]]
    if len(bare) == 1 and letters:
        return LETTERS.index(letters[0])
    if len(set(letters)) > 1:
        return None  # "a or b", "B and C"
    found: set[int] = set()
    m = _LEAD.match(t)
    if m and len(bare) <= 8:
        found.add(LETTERS.index(m.group(1)))
    found |= {LETTERS.index(x) for x in _PHRASE.findall(t)}
    words = {_stem(w) for w in bare}
    named = {i for i, label in enumerate(options) if _keywords(label) & words}
    if not found and len(named) == 1:
        found = named
    elif found and named and not named <= found:
        return None  # "B, the goblins... no wait, skeletons": names a different option too
    found = {i for i in found if i < len(options)}
    return found.pop() if len(found) == 1 else None


WAYS = ("bold", "sly", "wise")  # how the hero does it: the winning way picks the check's skill
WAY_WORDS = {"bold": 0, "boldly": 0, "sly": 1, "slyly": 1, "wise": 2, "wisely": 2}
_WAY = re.compile(r"\b(bold|boldly|sly|slyly|wise|wisely)\b")
_JOIN = re.compile(r"^(?:#?join|i(?:'ll| will)? join|join (?:the |your )?party|count me in|i'?m in)\b")
_LEAVE = re.compile(r"^(?:#?leave|leave (?:the |your )?party|i(?:'m| am) out)\b")


def way_of(text: str) -> int | None:
    """The way (0 bold, 1 sly, 2 wise) a comment names, if it names exactly one."""
    found = {WAY_WORDS[m] for m in _WAY.findall(_norm(text))}
    return found.pop() if len(found) == 1 else None


def party_word(text: str) -> str | None:
    """"join" or "leave" when a short comment asks to join or leave the party ("join", "A sly join")."""
    t = re.sub(r"[^a-z0-9#' ]+", " ", _norm(text)).split()
    if not t or len(t) > 8:
        return None
    for start in range(len(t)):  # after a vote and a way: "a sly join"
        rest = " ".join(t[start:])
        if _LEAVE.match(rest):
            return "leave"
        if _JOIN.match(rest):
            return "join"
        if t[start] not in ("a", "b", "c", *WAYS, "bold", "boldly", "slyly", "wisely", "and", "+", "&"):
            break
    return None


def tally(comments: list[dict], options: list[str]) -> dict:
    """Count each account's first vote and first way, and who asked to join or leave the party.
    comments: oldest first, each {user, uid?, text, ...}. Only the totals are kept in the episode's
    record; `voters`, `joins`, `leaves` and `commenters` (names) are for the party and credits
    (app/adventure/party.py) and aren't stored with the votes."""
    counts, voters, seen = [0] * len(options), [], set()
    ways, way_seen = [0, 0, 0], set()
    joins, leaves, commenters, asked = [], [], [], set()
    for c in comments:
        who = (c.get("user") or "").lower() or (f"id:{c['uid']}" if c.get("uid") else "")
        if not who:
            continue
        text = c.get("text") or ""
        if who not in {x["key"] for x in commenters}:
            commenters.append({"key": who, "user": c.get("user"), "uid": c.get("uid")})
        if who not in way_seen and (w := way_of(text)) is not None:
            way_seen.add(who)
            ways[w] += 1
        if who not in asked and (pw := party_word(text)):
            asked.add(who)
            (joins if pw == "join" else leaves).append({"key": who, "user": c.get("user"), "uid": c.get("uid"), "at": c.get("at")})
        if who in seen:
            continue
        pick = parse(text, options)
        if pick is None:
            continue
        seen.add(who)
        counts[pick] += 1
        voters.append({"user": c.get("user"), "pick": pick})
    return {"counts": counts, "voters": voters, "comments": len(comments), "ways": ways,
            "joins": joins, "leaves": leaves, "commenters": commenters}


def top_way(ways: list[int]) -> int | None:
    """The winning way, or None when nobody named one or it's a tie (then the node's own skill is used)."""
    top = max(ways) if ways else 0
    return ways.index(top) if top and ways.count(top) == 1 else None


def decide(counts: list[int], default: int, key: str) -> tuple[int, str]:
    """(winning option, how it was decided). Ties broken by HMAC(API_TOKEN, key)."""
    top = max(counts) if counts else 0
    if top == 0:
        return default, "default"
    tied = [i for i, n in enumerate(counts) if n == top]
    if len(tied) == 1:
        return tied[0], "votes"
    digest = hmac.new(settings.api_token.encode(), f"tie:{key}".encode(), hashlib.sha256).digest()
    return tied[int.from_bytes(digest[:8], "big") % len(tied)], "tie-break"
