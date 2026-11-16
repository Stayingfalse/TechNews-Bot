"""raosanta.uk endpoints (docs/SANTA_PLAN.md), and the all-channel busy list. Mounted by main.py
behind the API token. Nothing here posts yet: the channel's schedule, and previews to Discord."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import ValidationError

from .. import channels, slots
from ..config import settings
from . import previews, schedule, source, spec as promo

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


@router.get("/santa/schema")
def santa_schema():
    """The promo format: the spec's JSON schema, which formats are voiced, the narrators and the
    length to aim for."""
    return {"spec": promo.PromoSpec.model_json_schema(), "about": promo.__doc__, "voiced": list(promo.VOICED),
            "voices": list(settings.santa_voices), "placeholders": promo.PLACEHOLDERS,
            "target_seconds": promo.TARGET_SECONDS,
            "max_seconds": promo.MAX_SECONDS}


@router.post("/santa/preview", status_code=202)
def santa_preview(body: dict = Body(...)):
    """Render a promo spec (GET /santa/schema) and send it to Discord. Nothing is posted.
    422 lists every problem with the spec. Poll GET /santa/previews/{id}."""
    try:
        spec = promo.PromoSpec.model_validate(body)
    except ValidationError as e:
        raise HTTPException(422, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()])
    job = previews.create(spec)
    return {"id": job["id"], "status": job["status"]}


@router.get("/santa/previews")
def santa_previews(limit: int = Query(default=20, ge=1, le=100)):
    return {"previews": [{k: j.get(k) for k in ("id", "status", "created_at", "voice", "render", "video_url", "error")}
                         | {"spec_id": j["spec"]["id"], "format": j["spec"]["format"]} for j in previews.recent(limit)]}


@router.get("/santa/previews/{job_id}")
def santa_preview_job(job_id: str):
    job = previews.get(job_id)
    if not job:
        raise HTTPException(404, "no such preview")
    return job


@router.get("/santa/stats")
def santa_stats():
    """raosanta.uk's figures as the next video would quote them (each placeholder and its text), and
    the site's answer. Placeholders missing from `values` have no figure right now."""
    stats = source.fetch()
    return {"connected": bool(settings.raosanta_api_token), "source": settings.raosanta_api_url,
            "values": source.values(stats), "stats": stats}
