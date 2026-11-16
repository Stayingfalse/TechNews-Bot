"""raosanta.uk endpoints (docs/SANTA_PLAN.md), and the all-channel busy list. Mounted by main.py
behind the API token. Nothing here renders or posts yet: this is the channel's schedule."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query

from .. import channels, slots
from ..config import settings
from . import schedule

router = APIRouter(tags=["santa"])


def _settings() -> dict:
    return {"enabled": settings.santa_enabled, "handle": settings.santa_handle, "platforms": settings.santa_platforms,
            "cadence_hours": settings.santa_cadence_hours, "window": "-".join(settings.santa_window),
            "anchor_time": settings.santa_anchor, "buffer_minutes": settings.santa_buffer_minutes,
            "nudge_max_minutes": settings.santa_nudge_max_minutes,
            "render_lead_minutes": settings.santa_render_lead_minutes}


@router.get("/santa/state")
def santa_state():
    """The channel's settings, its anchor (the pattern's first slot) and the next few slots."""
    s = schedule.state()
    return {"settings": _settings(), "anchor": schedule.anchor().isoformat(), "anchor_saved": bool(s.get("anchor")),
            "next": schedule.upcoming(3)}


@router.get("/santa/slots")
def santa_slots(count: int = Query(default=14, ge=1, le=60)):
    """The next `count` posting slots, each checked against every other channel's posts and renders:
    `at`/`local` (when it would post), `planned` (where the 22-hour pattern put it), `nudged` (minutes
    moved, with what it `avoided`) or `skipped` (with the `reason`)."""
    return {"slots": schedule.upcoming(count)}


@router.put("/santa/anchor")
def santa_anchor(at: str = Query(..., description="YYYY-MM-DDTHH:MM, local time (or with an offset)")):
    """Set the pattern's first slot; every later one follows from it. Must be inside SANTA_WINDOW."""
    try:
        t = datetime.fromisoformat(at)
    except ValueError:
        raise HTTPException(400, "at: YYYY-MM-DDTHH:MM")
    t = t if t.tzinfo else t.replace(tzinfo=settings.tz)
    try:
        schedule.set_anchor(t)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return santa_state()


@router.get("/slots/busy")
def busy_slots(hours: int = Query(default=48, ge=1, le=24 * 14), channel: str = ""):
    """Every running channel's posts and render windows over the next `hours` (the times other
    channels must keep clear of). `channel` leaves that channel out."""
    if channel and channel not in channels.registry():
        raise HTTPException(422, f"unknown channel {channel!r}")
    start = datetime.now(timezone.utc)
    return {"busy": [b.as_dict() for b in slots.busy(start, start + timedelta(hours=hours), exclude=channel or None)]}
