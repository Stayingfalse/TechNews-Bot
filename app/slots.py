"""Every channel's upcoming posts and renders in one place, so a channel can find a time that
doesn't clash with any other (docs/SANTA_PLAN.md §2).

Each channel keeps its own schedule; this module only reads them. A channel is busy:
- at each post it has booked (quiz bookings, adventure parts, Farside days and extras), and
- every day at its usual time while it's running (the quiz's POST_TIME, the adventure's, Farside's,
  racing's when switched on, Farside's roll call), because those are booked a day or a week at a
  time and tomorrow's isn't always in yet. The quiz's weekly carousel counts too.

Each post also has a render window before it (that channel's render lead, lasting
SLOT_RENDER_MINUTES). `clashes()` checks a proposed post against all of it: no post within
`buffer` minutes of another channel's post, and no render overlapping another channel's render.
The santa channel uses it to place every post; nobody else has to give way to it.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

from . import channels
from .config import settings

log = logging.getLogger(__name__)
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class Busy:
    channel: str
    what: str  # "post" or "render"
    start: datetime  # UTC
    end: datetime  # UTC; a post is a moment (start == end)
    label: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["start"], d["end"] = self.start.isoformat(), self.end.isoformat()
        d["local"] = self.start.astimezone(settings.tz).strftime("%a %d %b %H:%M")
        return d


def _at(day: date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=settings.tz).astimezone(timezone.utc)


def _post(channel: str, when: datetime, lead_minutes: int | None, label: str) -> list[Busy]:
    out = [Busy(channel, "post", when, when, label)]
    if lead_minutes:
        start = when - timedelta(minutes=lead_minutes)
        out.append(Busy(channel, "render", start, start + timedelta(minutes=settings.slot_render_minutes), label))
    return out


def _daily(channel: str, hhmm: str, lead: int | None, label: str, start: datetime, end: datetime) -> list[Busy]:
    out = []
    day = start.astimezone(settings.tz).date() - timedelta(days=1)
    while _at(day, hhmm) <= end + timedelta(days=1):
        out += _post(channel, _at(day, hhmm), lead, label)
        day += timedelta(days=1)
    return out


def _parse(iso: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def _quiz(start: datetime, end: datetime) -> list[Busy]:
    from . import pipeline

    lead = settings.render_lead_minutes
    out = _daily(channels.MAIN, settings.post_time, lead, "daily quiz", start, end)
    for job in pipeline.scheduled_jobs():
        if (job.get("channel") or channels.MAIN) == channels.MAIN and (t := _parse(job.get("publish_at"))):
            out += _post(channels.MAIN, t, lead, f"quiz {job['id']}")
    if settings.instagram_carousels and settings.carousel_day in WEEKDAYS:
        day = start.astimezone(settings.tz).date() - timedelta(days=1)
        while _at(day, settings.carousel_time) <= end + timedelta(days=1):
            if WEEKDAYS[day.weekday()] == settings.carousel_day:
                out += _post(channels.MAIN, _at(day, settings.carousel_time), None, "weekly quiz carousel")
            day += timedelta(days=1)
    return out


def _adventure(start: datetime, end: datetime) -> list[Busy]:
    from .adventure import jobs

    lead = int(jobs.RENDER_LEAD.total_seconds() // 60)
    out = _daily(channels.ADVENTURE, settings.adventure_post_time, lead, "dungeon crawl", start, end)
    for job in jobs.recent(30):
        if job.get("status") in ("booked", "preparing", "scheduled") and (t := _parse(job.get("publish_at"))):
            out += _post(channels.ADVENTURE, t, lead, f"adventure {job['id']}")
    return out


def _colony(start: datetime, end: datetime) -> list[Busy]:
    from .colony import extras, jobs

    lead = settings.colony_render_lead_minutes
    out = _daily(channels.COLONY, settings.colony_post_time, lead, "Farside", start, end)
    for job in jobs.recent(10):
        if job.get("status") in ("booked", "preparing", "scheduled") and (t := _parse(job.get("publish_at"))):
            out += _post(channels.COLONY, t, lead, f"Farside {job.get('date')}")
    for job in extras.recent(20):
        if job.get("status") not in ("done", "failed", "cancelled", "missed") and (t := _parse(job.get("publish_at"))):
            out += _post(channels.COLONY, t, None, f"Farside extra {job['id']}")
    if settings.colony_rollcall_days > 0:  # every few days; counted daily to be safe
        out += _daily(channels.COLONY, settings.colony_rollcall_time, None, "Farside roll call", start, end)
    return out


def _racing(start: datetime, end: datetime) -> list[Busy]:
    return _daily(channels.RACING, settings.racing_post_time, settings.racing_close_minutes, "Sixel Speedway", start, end)


SOURCES = {channels.MAIN: _quiz, channels.ADVENTURE: _adventure, channels.COLONY: _colony, channels.RACING: _racing}


def busy(start: datetime, end: datetime, exclude: str | None = None) -> list[Busy]:
    """Everything the running channels (except `exclude`) have between `start` and `end`, by time.
    A source that fails is logged and left out rather than stopping the others."""
    out: list[Busy] = []
    for cid in channels.active():
        if cid == exclude or cid not in SOURCES:
            continue
        try:
            out += SOURCES[cid](start, end)
        except Exception:
            log.exception("couldn't read %s's schedule", cid)
    seen, unique = set(), []
    for b in sorted(out, key=lambda b: (b.start, b.channel, b.what)):
        key = (b.channel, b.what, b.start)
        if key not in seen and b.end >= start and b.start <= end:
            seen.add(key)
            unique.append(b)
    return unique


def clashes(when: datetime, channel: str, buffer_minutes: int, render_lead_minutes: int | None,
            others: list[Busy] | None = None) -> list[Busy]:
    """What a post by `channel` at `when` would clash with: another channel's post closer than
    `buffer_minutes`, or another channel's render overlapping this post's render."""
    buf = timedelta(minutes=buffer_minutes)
    if render_lead_minutes:
        r0 = when - timedelta(minutes=render_lead_minutes)
        r1 = r0 + timedelta(minutes=settings.slot_render_minutes)
    if others is None:
        others = busy(when - timedelta(hours=3), when + timedelta(hours=3), exclude=channel)
    out = []
    for b in others:
        if b.channel == channel:
            continue
        if b.what == "post" and abs(b.start - when) < buf:
            out.append(b)
        elif b.what == "render" and render_lead_minutes and b.start < r1 and r0 < b.end:
            out.append(b)
    return out
