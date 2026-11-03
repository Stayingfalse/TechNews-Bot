"""The week plan and each day's adaptation (docs/COLONY_PLAN.md §5b). The server never calls
Claude: the weekly routine POSTs the plan, the daily routine GETs today's context and POSTs
today's episode. Whatever has been accepted by the cut-off is what plays; otherwise the plan.

Stored in DATA_DIR/colony/weeks/<week_start>.json and DATA_DIR/colony/days/<date>.json."""
from __future__ import annotations

import copy
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ..config import settings
from ..render.colony import kit
from . import inbox, picks, plan, rules, state

SO_FAR = 10  # episodes of the story so far handed to the routine
MAX_PEOPLE = 40  # settlers with new comments handed over a day (the grants first)
MAX_COMMENTS = 3  # per settler
CREW_NOTES = {
    "MAREN": "the commander, calm, the colony's voice of reason; white suit, white hair",
    "TOLU": "pilot, cheerful, always has a cap on; orange suit",
    "BASK": "hauler, never stops carrying crates; teal suit",
    "IKO": "engineer, fixes everything with a wrench; red suit, hair in a bun",
}


def draw_guide() -> dict:
    """How to draw a part the kit hasn't got (for the routine)."""
    from ..render.colony import custom
    return {
        "how": ("Draw it as rows of characters, '.' for empty, each other character mapped in `colors` to a palette "
                "name (or #rrggbb, which is snapped to the nearest house colour). Facing right, the bottom row on the "
                "ground. 1 pixel is small: a settler is 7 wide and 12 tall. Give it a dark outline (ink or metal3) and "
                "2-4 colours. An optional second frame in `frames` animates it (pets walk, wings flap)."),
        "boxes": {slot: {"max_width": w, "max_height": h} for slot, (w, h) in custom.BOX.items()},
        "where": {"hat": "centred on the head, its bottom row on top of the helmet",
                  "held": "in the front hand: its bottom row at the hand, drawn from the hand outwards",
                  "back": "behind the body, its right edge at the back",
                  "carrier": "something to ride or sit in: the settler sits two rows into its top, centred",
                  "pet": "walks beside the settler",
                  "costume": "replaces the whole settler (a ghost, a robot, a dragon): feet on the bottom row"},
        "palette": custom.palette_names(), "max_new_a_day": custom.MAX_NEW_A_DAY,
        "example": {"slot": "pet", "id": "dragon", "colors": {"g": "crys2", "d": "grass2", "w": "crys1", "e": "eye"},
                    "rows": ["....ww....", "...dwwd.ge", "..dgggggg.", "dgggggg...", "...g..g..."],
                    "frames": [["...w.w....", "...dwd..ge", "..dgggggg.", "dgggggg...", "..g....g.."]]},
    }


class TooLate(Exception):
    pass


def _dir(name: str) -> Path:
    d = settings.data_dir / "colony" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(p: Path, data) -> None:
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    os.replace(tmp, p)


def deadline(day: date) -> datetime:
    """The cut-off for `day`'s adaptation: COLONY_CUTOFF_MINUTES before the post, as UTC."""
    h, m = (int(x) for x in settings.colony_post_time.split(":"))
    post = datetime(day.year, day.month, day.day, h, m, tzinfo=settings.tz)
    return (post - timedelta(minutes=settings.colony_cutoff_minutes)).astimezone(timezone.utc)


# ------------------------------------------------------------------ the week


def save_week(week: dict, replace: bool = False) -> list[str]:
    """Check and keep the weekly plan; returns the problems (nothing kept if there are any)."""
    s = state.load()
    handles = {st["handle"].lower() for st in s["settlers"].values()}
    probs = plan.check_week(week, handles)
    p = _dir("weeks") / f"{week.get('week_start')}.json"
    if not probs and p.exists() and not replace:
        probs = [f"a plan for the week of {week['week_start']} exists: send replace=true to change it"]
    if not probs:
        _write(p, week)
    return probs


def _weeks() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_dir("weeks").glob("*.json"))]


def planned(day: date) -> tuple[dict | None, str]:
    """The planned episode for `day` and where it came from: "plan", "spare" or "none"."""
    iso = day.isoformat()
    weeks = _weeks()
    for w in reversed(weeks):
        for ep in w.get("episodes", []):
            if ep.get("date") == iso:
                return ep, "plan"
    if weeks:  # no plan for today: a spare, taking turns
        spares = weeks[-1].get("spares") or []
        if spares:
            return {**copy.deepcopy(spares[day.toordinal() % len(spares)]), "date": iso}, "spare"
    return None, "none"


# ------------------------------------------------------------------ the day


# Reads the account's follower count right now, or None. Set when the channel's account is
# connected (the scheduler, M3); until then the preview keeps yesterday's count.
live_followers = None


def _preview(day: date, followers: int | None = None) -> tuple[dict, dict, list[dict]]:
    """The colony as it would be today, from the comments so far and (if known) today's follower
    count (nothing saved)."""
    s = state.load()
    after = deadline(day - timedelta(days=1)).isoformat()
    cut = deadline(day).isoformat()
    comments = [c for c in inbox.since(after) if c["at"] <= cut and c.get("kind") != "not_ok"]
    older = [c for c in inbox.waiting(after) if c.get("kind") != "not_ok"]
    if s["day"] == day.isoformat():  # today's already been applied (a re-run after the post was made)
        return s, s["days"][s["day"]], older + comments
    s2, report = rules.apply_day(s, day, comments, followers)
    return s2, report, older + comments


def context(day: date, now: datetime | None = None, followers: int | None = None) -> dict:
    """What the daily routine is given (GET /colony/today)."""
    now = now or datetime.now(timezone.utc)
    if followers is None and live_followers:
        try:
            followers = live_followers()
        except Exception:
            followers = None
    s, report, comments = _preview(day, followers)
    big = rules.surge(report, s["followers"])
    ep, source = planned(day)
    by_settler: dict[str, list[dict]] = {}
    for c in comments:
        by_settler.setdefault(c["settler"], []).append(c)
    requests = [c for c in comments if c.get("kind") in ("request", None)]
    choice = picks.choose(s, requests, set(report["arrived"]), day)
    granted = [r["key"] for r in choice["grant"]]
    order = granted + [k for k in report["featured"] if k not in granted]
    order += [k for k in by_settler if k not in order]
    people = []
    for k in order[:MAX_PEOPLE]:
        st = s["settlers"].get(k)
        if not st:
            continue
        people.append({
            "handle": "@" + st["handle"], "new": k in report["arrived"], "rank": st["rank"], "job": st["job"],
            "streak": st["streak"], "look": st.get("look") or {}, "traits": st.get("traits") or [],
            "sheet": st.get("sheet") or "",
            "comments": [{"id": c["id"], "kind": c.get("kind") or "unsorted", "text": c["text"][:300]}
                         for c in by_settler.get(k, [])[-MAX_COMMENTS:]],
        })
    so_far = []
    for d in sorted(_dir("days").glob("*.json"))[-SO_FAR:]:
        e = json.loads(d.read_text())
        so_far.append({"date": e.get("date"), "summary": e.get("summary", "")})
    return {
        "date": day.isoformat(), "deadline": deadline(day).isoformat(), "open": now < deadline(day),
        # a big day (a surge of followers) opens on the planet and may run longer: the new people
        # are likely to come back, so give the spotlights their moments
        "big_day": big, "new_followers": report.get("joined", 0),
        "aim_seconds": plan.MAX_SECONDS - 2 if big else plan.TARGET_SECONDS,
        "planned": ep, "planned_from": source,
        "featured": {f"${i + 1}": "@" + s["settlers"][k]["handle"] for i, k in enumerate(report["featured"]) if k in s["settlers"]},
        "colony": {"followers": s["followers"], "built": s["built"], "building": s["building"],
                   "next": report.get("next"), "settlers": len(s["settlers"])},
        "story_so_far": so_far, "people": people, "crew": CREW_NOTES,
        "kit": kit.current(), "draw": draw_guide(), "limits": {"caption_line": plan.LINE_CHARS, "say_line": plan.SAY_CHARS,
                                   "target_seconds": plan.TARGET_SECONDS, "max_seconds": plan.MAX_SECONDS, "beats": plan.BEATS, "events": plan.EVENTS,
                                   "slots": plan.SLOTS},
        "unsorted": sum(1 for c in comments if not c.get("kind")),
        # whose requests: three spotlights get a moment on screen, the rest of `grant` walk in the
        # "granted today" parade, and `queue` is everyone else's place in line (for their reply)
        "spotlights": [{"handle": r["handle"], "comment_id": r["comment_id"], "why": r["why"], "likes": r["likes"],
                        "waited_days": r["waited"]} for r in choice["spotlights"]],
        "grant": [{"handle": r["handle"], "comment_ids": r["comment_ids"]} for r in choice["grant"]],
        "queue": choice["queue"],
    }


def accept(day: date, ep: dict, now: datetime | None = None) -> list[str]:
    """Check and keep today's adapted episode (POST /colony/today); returns the problems."""
    now = now or datetime.now(timezone.utc)
    if now >= deadline(day):
        raise TooLate(f"too late: the cut-off for {day} was {deadline(day).isoformat()}; the plan stands")
    s, report, _ = _preview(day)
    handles = {st["handle"].lower() for st in s["settlers"].values()}
    probs = plan.check_episode(ep, handles, adapted=True)
    if ep.get("date") not in (None, day.isoformat()):
        probs.append(f"date: should be {day.isoformat()}")
    if len(str(ep.get("summary", ""))) > 200:
        probs.append("summary: one line of the story so far, at most 200 characters")
    if not probs:
        _write(_dir("days") / f"{day.isoformat()}.json", {**ep, "date": day.isoformat(), "accepted_at": now.isoformat()})
        from ..render.colony import custom
        for part in ep.get("parts") or []:  # drawn today: into the kit, with a picture for the preview
            by = next((h for h, info in (ep.get("settlers") or {}).items()
                       if (info.get("look") or {}).get(part["slot"]) == part["id"]), None)
            custom.save(part, by, day.isoformat())
            custom.preview(part, _dir("kit-previews") / f"{part['slot']}-{part['id']}.png")
        # what this episode answers: comments it replied to, and the comments of everyone it changed
        _, _, comments = _preview(day)
        changed = {h.lstrip("@").lower() for h in (ep.get("settlers") or {})}
        ids = {r["comment_id"] for r in ep.get("replies") or []}
        ids |= {c["id"] for c in comments if c["user"].lstrip("@").lower() in changed}
        inbox.mark_answered(ids, day.isoformat())
    return probs


def adapted(day: date) -> dict | None:
    p = _dir("days") / f"{day.isoformat()}.json"
    return json.loads(p.read_text()) if p.exists() else None


def episode_for(day: date) -> tuple[dict | None, str]:
    """What plays on `day`: the adaptation, else the plan, else a spare, else the default beats."""
    a = adapted(day)
    if a:
        return a, "adapted"
    return planned(day)


def commit(s: dict, ep: dict | None, report: dict | None = None) -> dict:
    """Keep what today's adaptation said about people (looks, traits, sheets) once it has posted,
    and who had a moment on screen (so the spotlight moves on to others)."""
    if not ep:
        return s
    by = {st["handle"].lower(): k for k, st in s["settlers"].items()}
    on = ep.get("date") or (report or {}).get("day")
    for b in ep.get("beats") or []:
        if b.get("type") in ("feature", "say", "decision") and on:
            who = str(b.get("who", ""))
            if who.startswith("$") and report:
                i = int(who[1:]) - 1
                k = report["featured"][i] if i < len(report["featured"]) else None
            else:
                k = by.get(who.lstrip("@").lower())
            if k and k in s["settlers"]:
                st = s["settlers"][k]
                st["featured_on"] = sorted(set(st.get("featured_on") or []) | {on})[-10:]
    for h, info in (ep.get("settlers") or {}).items():
        k = by.get(h.lstrip("@").lower())
        if not k:
            continue
        st = s["settlers"][k]
        if info.get("look"):
            st["look"] = {**(st.get("look") or {}), **info["look"]}
        if "traits" in info:
            st["traits"] = list(info["traits"])[:3]
        if info.get("sheet"):
            st["sheet"] = str(info["sheet"])[:300]
    return s
