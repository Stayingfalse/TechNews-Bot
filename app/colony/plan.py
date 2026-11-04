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
TARGET_SECONDS = 30  # what to aim for: people watch 8-12 s, and shorter parts get pushed further
MAX_SECONDS = 40  # the most an episode may run: for big days (a surge, lots of newcomers, a decision)
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


# ------------------------------------------------------------------ the shape (JSON types)

REQUEST_SCHEMA = """POST /colony/today body (JSON object):
  date      "YYYY-MM-DD" (optional; today if left out, or ?date=)
  beats     [beat, ...]  1 or more; each an object, see the beat types above
  caption   "..."        the post's caption, 1-600 characters
  summary   "..."        optional, the story so far in one line, at most 200 characters
  settlers  {"@handle": {"look": {slot: part, ...}, "traits": ["word", ...], "sheet": "..."}, ...}
  replies   [{"comment_id": "...", "text": "..."}, ...]   ({"<comment_id>": "<text>"} is accepted too)
  parts     [{"slot": "...", "id": "...", "rows": ["..."], "frames": [["..."]], "colors": {"x": "name"}}, ...]
  wanted    ["...", ...]  things the kit can't draw (not parts), each at most 80 characters"""

_BEAT_TYPES = {"type": str, "slot": str, "who": str, "text": str, "event": str}


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def shape(ep, adapted: bool = False) -> tuple[dict, list[str], list[str]]:
    """Check the JSON types of an episode before anything reads it. Returns (a copy with the bad
    items left out, so the other checks can still look at the rest; the problems; notes on
    anything converted). Never raises on any JSON value."""
    if not isinstance(ep, dict):
        return {}, [f"the episode must be a JSON object, not {type(ep).__name__}"], []
    probs, notes, out = [], [], dict(ep)
    beats = ep.get("beats")
    if beats is not None and not isinstance(beats, list):
        probs.append("beats: a list of beat objects is needed")
        out["beats"] = []
    else:
        good = []
        for i, b in enumerate(beats or []):
            w = f"beats[{i}]"
            if not isinstance(b, dict):
                probs.append(f"{w}: must be an object, like {{\"type\": \"slot\", \"slot\": \"arrivals\"}}")
                good.append(None)  # a gap, so the other checks still name beats by their place in the list
                continue
            bad = [k for k, t in _BEAT_TYPES.items() if k in b and not isinstance(b[k], t)]
            if "secs" in b and not _is_num(b["secs"]):
                bad.append("secs")
            if "lines" in b and not (isinstance(b["lines"], list) and all(isinstance(x, str) for x in b["lines"])):
                bad.append("lines")
            if "choices" in b and not (isinstance(b["choices"], list) and all(
                    isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) for x in c) for c in b["choices"])):
                bad.append("choices")
            if bad:
                for k in bad:
                    want = {"secs": "a number", "lines": "a list of strings",
                            "choices": 'a list of pairs like ["A", "OPEN IT"]'}.get(k, "a string")
                    probs.append(f"{w}.{k}: {want} is needed")
                good.append(None)
                continue
            good.append(b)
        out["beats"] = good
    for key, limit in (("caption", None), ("summary", None)):
        if key in ep and ep[key] is not None and not isinstance(ep[key], str):
            probs.append(f"{key}: a string is needed")
            out[key] = ""
    if "date" in ep and ep["date"] is not None:
        if not isinstance(ep["date"], str):
            probs.append("date: a string, YYYY-MM-DD")
            out.pop("date")
        else:
            try:
                date.fromisoformat(ep["date"])
            except ValueError:
                probs.append("date: a date, YYYY-MM-DD")
                out.pop("date")
    if not adapted:
        return out, probs, notes
    # settlers: {"@handle": {"look": {...}, "traits": [...], "sheet": "..."}}
    st = ep.get("settlers")
    if st is not None and not isinstance(st, dict):
        probs.append('settlers: an object is needed, {"@handle": {"look": {...}, "traits": [...], "sheet": "..."}}')
        out["settlers"] = {}
    else:
        good = {}
        for h, info in (st or {}).items():
            w = f"settlers.{h}"
            if not isinstance(info, dict):
                probs.append(f'{w}: an object is needed, {{"look": {{...}}, "traits": [...], "sheet": "..."}}')
                continue
            bad = False
            look = info.get("look")
            if look is not None and not (isinstance(look, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in look.items())):
                probs.append(f'{w}.look: an object of slot to part, like {{"hat": "crown"}}')
                bad = True
            tr = info.get("traits")
            if tr is not None and not (isinstance(tr, list) and all(isinstance(x, str) for x in tr)):
                probs.append(f"{w}.traits: a list of strings is needed")
                bad = True
            if info.get("sheet") is not None and not isinstance(info["sheet"], str):
                probs.append(f"{w}.sheet: a string is needed")
                bad = True
            if not bad:
                good[h] = info
        out["settlers"] = good
    # replies: [{"comment_id": "...", "text": "..."}]; {"<comment_id>": "<text>"} is converted
    rp = ep.get("replies")
    if isinstance(rp, dict):
        if all(isinstance(k, str) and isinstance(v, str) for k, v in rp.items()):
            rp = [{"comment_id": k, "text": v} for k, v in rp.items()]
            notes.append('replies: converted from {comment_id: text} to [{"comment_id", "text"}]')
        else:
            probs.append('replies: a list of {comment_id, text} is needed (or {"<comment_id>": "<text>"})')
            rp = []
    if rp is not None and not isinstance(rp, list):
        probs.append("replies: a list of {comment_id, text} is needed")
        rp = []
    good = []
    for i, r in enumerate(rp or []):
        if not (isinstance(r, dict) and isinstance(r.get("comment_id"), (str, int)) and not isinstance(r.get("comment_id"), bool)
                and isinstance(r.get("text"), str)):
            probs.append(f'replies[{i}]: an object {{"comment_id": "...", "text": "..."}} is needed')
            continue
        good.append({**r, "comment_id": str(r["comment_id"])})
    out["replies"] = good
    # parts: [{"slot", "id", "rows", "frames", "colors"}]
    pt = ep.get("parts")
    if pt is not None and not isinstance(pt, list):
        probs.append("parts: a list of part objects is needed")
        pt = []
    good = []
    for i, part in enumerate(pt or []):
        w = f"parts[{i}]"
        if not isinstance(part, dict):
            probs.append(f'{w}: an object is needed, {{"slot", "id", "rows", "colors"}}')
            continue
        bad = [k for k in ("slot", "id") if not isinstance(part.get(k), str)]
        if not (isinstance(part.get("rows"), list) and all(isinstance(r, str) for r in part["rows"])):
            bad.append("rows")
        if "frames" in part and not (isinstance(part["frames"], list) and all(
                isinstance(f, list) and all(isinstance(r, str) for r in f) for f in part["frames"])):
            bad.append("frames")
        if not (isinstance(part.get("colors"), dict) and all(isinstance(k, str) and isinstance(v, str)
                                                              for k, v in part["colors"].items())):
            bad.append("colors")
        if bad:
            probs += [f"{w}.{k}: " + {"rows": "a list of strings", "frames": "a list of lists of strings",
                                       "colors": "an object of character to colour name"}.get(k, "a string") + " is needed"
                      for k in bad]
            continue
        good.append(part)
    out["parts"] = good
    wt = ep.get("wanted")
    if wt is not None and not (isinstance(wt, list) and all(isinstance(x, str) for x in wt)):
        probs.append("wanted: a list of strings is needed")
        out["wanted"] = []
    return out, probs, notes


def check_episode(ep: dict, handles: set[str], adapted: bool = False) -> list[str]:
    """Every problem with an episode, as short sentences (empty list = fine). Wrong JSON types
    are reported first; the other checks run on the rest."""
    ep, probs, _ = shape(ep, adapted)
    if not isinstance(ep, dict) or not ep and probs:
        return probs
    beats = ep.get("beats")
    if not isinstance(beats, list) or not beats:
        return probs + (["beats: a non-empty list is needed"] if not any(p.startswith("beats") for p in probs) else [])
    ep = {**ep, "beats": [b for b in beats if b is not None]}  # for the length estimate
    secs = 0.0
    decisions = 0
    for i, b in enumerate(beats):
        if b is None:  # wrong shape, reported above
            continue
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
        probs.append(f"about {secs:.0f} s long, at most {MAX_SECONDS} s (aim for {TARGET_SECONDS}): cut a beat or shorten secs")
    cap = str(ep.get("caption") or "")
    if any(p.startswith("caption") for p in probs):
        pass
    elif not cap or len(cap) > 600:
        probs.append("caption: the post's caption, 1-600 characters")
    elif LINK.search(cap) or BLOCKLIST.search(cap):
        probs.append("caption: no links, teen-friendly")
    if adapted:
        from .picks import GRANT_MAX
        if len(ep.get("settlers") or {}) > GRANT_MAX:
            probs.append(f"settlers: at most {GRANT_MAX} changed a day ({len(ep['settlers'])} given)")
        from ..render.colony import custom
        parts = ep.get("parts") or []
        if len(parts) > custom.MAX_NEW_A_DAY:
            probs.append(f"parts: at most {custom.MAX_NEW_A_DAY} new parts a day ({len(parts)} given)")
        taken = set(custom.all_parts())
        new = set()
        for part in parts:
            probs += custom.check(part, kit.KIT, taken | new)
            new.add((part.get("slot"), part.get("id")))
        for h, info in (ep.get("settlers") or {}).items():
            if h.lstrip("@").lower() not in handles:
                probs.append(f"settlers: {h} isn't a settler")
                continue
            look = {k: v for k, v in (info.get("look") or {}).items() if (k, v) not in new}  # drawn today: fine
            for p in kit.validate(look):
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
    beats = [b for b in (ep.get("beats") if isinstance(ep.get("beats"), list) else []) if isinstance(b, dict)]
    if ep.get("settlers") and not any(b.get("slot") == "granted" for b in beats):
        t += SLOT_SECS["granted"]  # the parade is added for everyone whose look changed
    for b in beats:
        if b.get("type") == "slot":
            t += SLOT_SECS.get(b.get("slot"), 0) if isinstance(b.get("slot"), str) else 0
        elif b.get("type") == "decision":
            t += 6.0
        else:
            t += float(b["secs"]) if _is_num(b.get("secs")) else 2.6
    return t


def length_note(ep: dict) -> str | None:
    """A nudge (not a problem) when an episode is over the target."""
    if not isinstance(ep, dict):
        return None
    secs = estimate(ep)
    if secs > TARGET_SECONDS:
        return (f"about {secs:.0f} s at its longest: fine for a big day, but aim for {TARGET_SECONDS} s "
                "(cut crew lines and captions first)")
    return None


def check_week(week: dict, handles: set[str]) -> list[str]:
    """The weekly plan: 7 dated episodes from week_start, and 2 spares that fit any day."""
    probs = []
    if not isinstance(week, dict):
        return ["the week must be a JSON object"]
    try:
        start = date.fromisoformat(str(week.get("week_start")))
    except ValueError:
        return ["week_start: a date, YYYY-MM-DD"]
    for key in ("episodes", "spares"):
        if not isinstance(week.get(key) or [], list):
            probs.append(f"{key}: a list of episodes is needed")
            week = {**week, key: []}
    eps = week.get("episodes") or []
    if len(eps) != 7:
        probs.append(f"episodes: 7 needed, {len(eps)} given")
    for i, ep in enumerate(eps):
        want = date.fromordinal(start.toordinal() + i).isoformat()
        if not isinstance(ep, dict):
            probs.append(f"episodes[{i}]: must be an object")
            continue
        if ep.get("date") != want:
            probs.append(f"episodes[{i}].date: should be {want}")
        if not any(isinstance(b, dict) and b.get("type") == "slot" and b.get("slot") == "arrivals"
                   for b in (ep.get("beats") if isinstance(ep.get("beats"), list) else [])):
            probs.append(f"episodes[{i}]: needs an arrivals slot (newcomers come first)")
        probs += [f"episodes[{i}]: {p}" for p in check_episode(ep, handles)]
    spares = week.get("spares") or []
    if len(spares) != 2:
        probs.append(f"spares: 2 needed, {len(spares)} given")
    for i, ep in enumerate(spares):
        if not isinstance(ep, dict):
            probs.append(f"spares[{i}]: must be an object")
            continue
        probs += [f"spares[{i}]: {p}" for p in check_episode(ep, handles)]
    return probs
