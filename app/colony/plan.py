"""The episode format the routines write and the server checks (docs/COLONY_PLAN.md §5a-5b).

An episode is a list of beats that play in order, plus the post's caption. The weekly plan's
episodes stand on their own (the founding crew, and slots code fills); the daily adaptation adds
the people: their looks, sheets, lines, replies.

Beats:
  {"type": "slot", "slot": "arrivals" | "people" | "granted" | "build" | "next" | "ask"}   filled by code
      ("granted": everyone whose look changed today walks past, named: the "granted today" parade)
  {"type": "caption", "lines": [...], "secs": 2.5}
  {"type": "say", "who": WHO, "text": "LINE ONE|LINE TWO", "secs": 2.5}
  {"type": "feature", "who": WHO, "lines": [...], "secs": 2.5}                      a settler's moment
  {"type": "event", "event": EVENT, "lines": [...], "secs": 3}
  {"type": "decision", "who": WHO, "lines": [...], "choices": [["A", "OPEN IT"], ["B", "LEAVE IT"]]}

WHO is a crew name (MAREN, TOLU, BASK, IKO), a settler's @handle, or "$1"-"$4": the day's featured
settlers in order (newcomers first), which code fills; a beat whose "$n" has nobody is left out.
"""
from __future__ import annotations

import re
from datetime import date

from ..render.colony import kit, pixfont

CREW = ("MAREN", "TOLU", "BASK", "IKO")
SLOTS = ("arrivals", "people", "granted", "build", "next", "ask")
EVENTS = ("dust_storm", "signal", "aurora", "meteors", "quake", "night")
BEATS = ("slot", "caption", "say", "feature", "event", "decision")
SLOT_SECS = {"arrivals": 9.1, "people": 7.8, "granted": 7.4, "build": 8.0, "next": 3.6, "ask": 3.0}  # the most each can take
LINE_CHARS = 24  # a caption line (the font fits 24 small or 12 big)
SAY_CHARS = 18  # a speech-bubble line
MAX_SECONDS = 34  # the whole episode at its longest (most run 20-28 s)
LINK = re.compile(r"https?://|www\.|\.(com|net|org|io|ly|gg|co)\b", re.I)
# a short backstop; the writer is told the rules, and the preview has a human last look
BLOCKLIST = re.compile(r"\b(fuck|shit|cunt|nigg|fag|retard|kill yourself|kys|nazi|porn|sex)\w*", re.I)


def _text_problems(where: str, text: str, limit: int, handles: set[str]) -> list[str]:
    probs = []
    if len(text) > limit:
        probs.append(f"{where}: {len(text)} characters, at most {limit}: {text!r}")
    if LINK.search(text):
        probs.append(f"{where}: no links")
    if BLOCKLIST.search(text):
        probs.append(f"{where}: not teen-friendly: {text!r}")
    for m in re.findall(r"@([a-z0-9._]*[a-z0-9_])", text, re.I):
        if m.lower() not in handles:
            probs.append(f"{where}: @{m} isn't a settler (only name people who live here)")
    missing = {ch for ch in text.upper().replace("*", "") if ch not in pixfont.GLYPHS}
    if missing:
        probs.append(f"{where}: the font has no {''.join(sorted(missing))!r}")
    return probs


def _who_ok(who: str, handles: set[str]) -> bool:
    return who in CREW or re.fullmatch(r"\$[1-4]", who or "") is not None or who.lstrip("@").lower() in handles


def check_episode(ep: dict, handles: set[str], adapted: bool = False) -> list[str]:
    """Every problem with an episode, as short sentences (empty list = fine)."""
    probs = []
    beats = ep.get("beats")
    if not isinstance(beats, list) or not beats:
        return ["beats: a non-empty list is needed"]
    secs = 0.0
    decisions = 0
    for i, b in enumerate(beats):
        w = f"beats[{i}]"
        t = b.get("type")
        if t not in BEATS:
            probs.append(f"{w}: type must be one of {', '.join(BEATS)}")
            continue
        if t == "slot":
            if b.get("slot") not in SLOTS:
                probs.append(f"{w}: slot must be one of {', '.join(SLOTS)}")
            secs += SLOT_SECS.get(b.get("slot"), 0)
            continue
        s = float(b.get("secs", 2.6))
        if not 1.0 <= s <= 6.0:
            probs.append(f"{w}: secs between 1 and 6")
        secs += s
        if t in ("say", "feature", "decision"):
            who = str(b.get("who", ""))
            if not _who_ok(who, handles):
                probs.append(f"{w}: who {who!r} must be a crew name ({', '.join(CREW)}), a settler's @handle or $1-$4")
        if t == "say":
            lines = str(b.get("text", "")).split("|")
            if not 1 <= len(lines) <= 3:
                probs.append(f"{w}: text is 1-3 lines split by |")
            for j, line in enumerate(lines):
                probs += _text_problems(f"{w}.text line {j + 1}", line, SAY_CHARS, handles)
        if t in ("caption", "feature", "event", "decision"):
            lines = b.get("lines") or []
            if t != "event" and not 1 <= len(lines) <= 3:
                probs.append(f"{w}: lines is 1-3 lines")
            for j, line in enumerate(lines):
                probs += _text_problems(f"{w}.lines[{j}]", str(line), LINE_CHARS, handles)
        if t == "event" and b.get("event") not in EVENTS:
            probs.append(f"{w}: event must be one of {', '.join(EVENTS)}")
        if t == "decision":
            decisions += 1
            ch = b.get("choices") or []
            if not 2 <= len(ch) <= 3 or any(len(c) != 2 for c in ch):
                probs.append(f"{w}: choices is 2-3 pairs like [\"A\", \"OPEN IT\"]")
            else:
                if [c[0] for c in ch] != ["A", "B", "C"][:len(ch)]:
                    probs.append(f"{w}: choices are lettered A, B, C in order")
                for c in ch:
                    probs += _text_problems(f"{w}.choice {c[0]}", str(c[1]), 10, handles)
    if decisions > 1:
        probs.append("at most one decision an episode")
    secs = estimate(ep)
    if secs > MAX_SECONDS:
        probs.append(f"about {secs:.0f} s long, at most {MAX_SECONDS} s: cut a beat or shorten secs")
    cap = str(ep.get("caption", ""))
    if not cap or len(cap) > 600:
        probs.append("caption: the post's caption, 1-600 characters")
    elif LINK.search(cap) or BLOCKLIST.search(cap):
        probs.append("caption: no links, teen-friendly")
    if adapted:
        from .picks import GRANT_MAX
        if len(ep.get("settlers") or {}) > GRANT_MAX:
            probs.append(f"settlers: at most {GRANT_MAX} changed a day ({len(ep['settlers'])} given)")
        for h, info in (ep.get("settlers") or {}).items():
            if h.lstrip("@").lower() not in handles:
                probs.append(f"settlers: {h} isn't a settler")
                continue
            for p in kit.validate(info.get("look") or {}):
                probs.append(f"settlers.{h}.look: {p}")
            tr = info.get("traits") or []
            if len(tr) > 3 or any(not re.fullmatch(r"[a-z][a-z -]{1,15}", str(x)) for x in tr):
                probs.append(f"settlers.{h}.traits: up to 3 short lower-case words")
            sheet = str(info.get("sheet", ""))
            if len(sheet) > 300:
                probs.append(f"settlers.{h}.sheet: at most 300 characters")
            if LINK.search(sheet) or BLOCKLIST.search(sheet):
                probs.append(f"settlers.{h}.sheet: no links, teen-friendly")
        seen = set()
        for i, r in enumerate(ep.get("replies") or []):
            if not r.get("comment_id"):
                probs.append(f"replies[{i}]: comment_id is needed")
            if r.get("comment_id") in seen:
                probs.append(f"replies[{i}]: one reply per comment")
            seen.add(r.get("comment_id"))
            probs += _text_problems(f"replies[{i}]", str(r.get("text", "")), 150, handles)
        for i, w in enumerate(ep.get("wanted") or []):
            if len(str(w)) > 80:
                probs.append(f"wanted[{i}]: at most 80 characters")
    return probs


def estimate(ep: dict) -> float:
    """The longest the episode can run, in seconds (slots at their fullest; a decision is 6 s)."""
    t = 0.0
    beats = ep.get("beats") or []
    if ep.get("settlers") and not any(b.get("slot") == "granted" for b in beats):
        t += SLOT_SECS["granted"]  # the parade is added for everyone whose look changed
    for b in beats:
        if b.get("type") == "slot":
            t += SLOT_SECS.get(b.get("slot"), 0)
        elif b.get("type") == "decision":
            t += 6.0
        else:
            t += float(b.get("secs", 2.6))
    return t


def check_week(week: dict, handles: set[str]) -> list[str]:
    """The weekly plan: 7 dated episodes from week_start, and 2 spares that fit any day."""
    probs = []
    try:
        start = date.fromisoformat(str(week.get("week_start")))
    except ValueError:
        return ["week_start: a date, YYYY-MM-DD"]
    eps = week.get("episodes") or []
    if len(eps) != 7:
        probs.append(f"episodes: 7 needed, {len(eps)} given")
    for i, ep in enumerate(eps):
        want = date.fromordinal(start.toordinal() + i).isoformat()
        if ep.get("date") != want:
            probs.append(f"episodes[{i}].date: should be {want}")
        if not any(b.get("type") == "slot" and b.get("slot") == "arrivals" for b in ep.get("beats") or []):
            probs.append(f"episodes[{i}]: needs an arrivals slot (newcomers come first)")
        probs += [f"episodes[{i}]: {p}" for p in check_episode(ep, handles)]
    spares = week.get("spares") or []
    if len(spares) != 2:
        probs.append(f"spares: 2 needed, {len(spares)} given")
    for i, ep in enumerate(spares):
        probs += [f"spares[{i}]: {p}" for p in check_episode(ep, handles)]
    return probs
