"""Farside's endpoints for the Claude Code routines (docs/COLONY_ROUTINE_PROMPT.md and
docs/COLONY_DAILY_PROMPT.md). Mounted by main.py behind the API token."""
from __future__ import annotations

from datetime import date, datetime

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
