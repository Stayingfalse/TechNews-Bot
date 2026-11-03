"""Farside's endpoints for the Claude Code routines (docs/COLONY_ROUTINE_PROMPT.md and
docs/COLONY_DAILY_PROMPT.md). Mounted by main.py behind the API token."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, HTTPException, Query

from ..config import settings
from ..render.colony import kit
from . import plan, today

router = APIRouter(prefix="/colony", tags=["colony"])


def _day(d: str) -> date:
    if not d:
        return datetime.now(settings.tz).date()
    try:
        return date.fromisoformat(d)
    except ValueError:
        raise HTTPException(400, "date: YYYY-MM-DD")


@router.get("/schema")
def colony_schema():
    """The episode format, the kit, and the limits, for writing a plan or a day."""
    return {"episode": plan.__doc__, "kit": kit.current(), "draw": today.draw_guide(), "crew": today.CREW_NOTES, "events": plan.EVENTS,
            "slots": plan.SLOTS, "caption_line": plan.LINE_CHARS, "say_line": plan.SAY_CHARS,
            "target_seconds": plan.TARGET_SECONDS, "max_seconds": plan.MAX_SECONDS}


@router.post("/week")
def colony_week(week: dict = Body(...), replace: bool = False):
    """The weekly plan: {"week_start": "YYYY-MM-DD", "episodes": [7 episodes], "spares": [2]}.
    422 lists every problem; fix them all and send it again."""
    probs = today.save_week(week, replace=replace)
    if probs:
        raise HTTPException(422, {"problems": probs})
    notes = {ep.get("date"): n for ep in week.get("episodes", []) if (n := plan.length_note(ep))}
    return {"ok": True, "week_start": week["week_start"], "notes": notes}


@router.get("/week")
def colony_week_get(date_: str = Query(default="", alias="date")):
    day = _day(date_)
    ep, source = today.planned(day)
    return {"date": day.isoformat(), "planned": ep, "from": source}


@router.get("/today")
def colony_today(date_: str = Query(default="", alias="date")):
    """Today's planned episode, the colony, the story so far, and the people with new comments
    (their sheets, looks and comments), with the cut-off for sending today's episode."""
    return today.context(_day(date_))


@router.post("/today")
def colony_today_post(ep: dict = Body(...), date_: str = Query(default="", alias="date")):
    """Today's episode, adapted to what people asked for. 422 lists every problem; 409 after the
    cut-off (the plan stands)."""
    day = _day(date_ or ep.get("date", ""))
    try:
        probs = today.accept(day, ep)
    except today.TooLate as e:
        raise HTTPException(409, str(e))
    if probs:
        raise HTTPException(422, {"problems": probs})
    return {"ok": True, "date": day.isoformat(), "deadline": today.deadline(day).isoformat(),
            "note": plan.length_note(ep), "new_parts": [f"{p['slot']}/{p['id']}" for p in ep.get("parts") or []]}


# ------------------------------------------------------------------ running the channel


@router.post("/start", status_code=202)
def colony_start(date_: str = Query(default="", alias="date"), at: str = "", restart: bool = False):
    """Start the daily schedule from `date` (default: today if its slot is over an hour away, else
    tomorrow). `at` (HH:MM today, local, or an ISO time) posts the first episode then instead,
    with every day after at COLONY_POST_TIME. `restart=true` books it again while nothing has
    posted. Needs COLONY_ENABLED, PUBLISH_ENABLED and @farside.colony connected
    (/oauth/instagram/start?channel=colony)."""
    import re

    from . import jobs

    if not settings.colony_enabled:
        raise HTTPException(409, "Farside is switched off: set COLONY_ENABLED=true")
    when = None
    if at:
        if re.fullmatch(r"\d{1,2}:\d{2}", at):
            h, m = (int(x) for x in at.split(":"))
            when = datetime.now(settings.tz).replace(hour=h, minute=m, second=0, microsecond=0)
        else:
            try:
                when = datetime.fromisoformat(at)
            except ValueError:
                raise HTTPException(400, "at: HH:MM (today, local) or an ISO date-time")
            when = when if when.tzinfo else when.replace(tzinfo=settings.tz)
    try:
        return jobs.start(date.fromisoformat(date_) if date_ else None, at=when, restart=restart)
    except jobs.NotConnected as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/state")
def colony_state():
    """The channel (started, next post), the colony (followers, built, building) and recent days."""
    from . import inbox, jobs, replies, state

    s = state.load()
    q = replies.queue()
    return {"channel": jobs.channel_state(), "enabled": settings.colony_enabled, "can_publish": jobs.can_publish(),
            "colony": {"day": s["day"], "followers": s["followers"], "settlers": len(s["settlers"]), "built": s["built"],
                       "building": s["building"], "stock": s["stock"], "blocked": len(s["blocked"])},
            "inbox": {"comments": len(inbox.load()["comments"]),
                      "unsorted": sum(1 for c in inbox.load()["comments"].values() if not c.get("kind"))},
            "replies": {"queued": len(q["items"]), "sent": len(q["sent"]), "paused_until": q.get("paused_until")},
            "jobs": [{k: v for k, v in j.items() if k not in ("episode",)} for j in jobs.recent(7)]}


@router.post("/block")
def colony_block(user: str = "", part: str = "", date_: str = Query(default="", alias="date")):
    """Block a person (out of the colony for good, never shown or replied to) or a drawn part
    (`part=pet/dragon`: never drawn again). Today's episode renders again if there's time."""
    from ..render.colony import custom
    from . import jobs, state

    if not user and not part:
        raise HTTPException(400, "give user=@name or part=slot/id")
    done = []
    if user:
        state.block(user)
        done.append(f"user {user}")
    if part:
        slot, _, pid = part.partition("/")
        if not custom.block(slot, pid):
            raise HTTPException(404, f"no drawn part {part!r}")
        done.append(f"part {part}")
    day = _day(date_).isoformat()
    job = jobs.rerender(day)
    return {"blocked": done, "day": day, "status": (job or {}).get("status")}


@router.post("/preview", status_code=202)
def colony_preview(date_: str = Query(default="", alias="date")):
    """Render a day's episode as it stands now and send it to Discord. Nothing is posted or saved."""
    from . import jobs

    return jobs.preview(_day(date_) if date_ else None)


@router.post("/jobs/{day}/retry", status_code=202)
def colony_retry(day: str):
    from . import jobs

    try:
        return jobs.retry(day)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/jobs/{day}")
def colony_cancel(day: str):
    """Don't post a day's episode (it's marked cancelled; the next day is booked as usual)."""
    from . import jobs

    job = jobs.get(day)
    if not job or job["status"] not in ("booked", "scheduled", "failed", "missed"):
        raise HTTPException(409, "only a day that hasn't posted (and isn't posting) can be cancelled")
    job["status"] = "cancelled"
    jobs.save(job)
    jobs.book(date.fromisoformat(day) + timedelta(days=1))
    return job
