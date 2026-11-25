"""When the raosanta.uk channel posts (docs/SANTA_PLAN.md §2).

One post every SANTA_CADENCE_HOURS (22), counted from a fixed starting point (the anchor), so each
post lands two hours earlier in the day than the one before and the times walk round the day:
21:30, 19:30, 17:30, ... 07:30. A step that would land before SANTA_WINDOW opens (07:00) goes to
SANTA_ANCHOR (21:30) that evening instead and the walk starts again; one that lands after the window
closes goes to the next morning's opening time. Moving a step moves the ones after it too.

Each slot is then checked against the other channels (app/slots.py): a clash nudges that one post
by 15-minute steps, nearest first and later before earlier, up to SANTA_NUDGE_MAX_MINUTES and
inside the window. A nudge doesn't move the slots after it, so one busy evening doesn't shift the
whole pattern. A slot with no free time near it is skipped, with the reason.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone

from .. import channels, slots, store
from ..config import settings

STATE = "santa/state.json"
STEP = timedelta(minutes=15)


def now() -> datetime:
    return datetime.now(timezone.utc)


def _hm(hhmm: str) -> time:
    h, m = (int(x) for x in hhmm.split(":"))
    return time(h, m)


def _local_at(day, hhmm: str) -> datetime:
    t = _hm(hhmm)
    return datetime(day.year, day.month, day.day, t.hour, t.minute, tzinfo=settings.tz).astimezone(timezone.utc)


def in_window(t: datetime) -> bool:
    local = t.astimezone(settings.tz).strftime("%H:%M")
    return settings.santa_window[0] <= local <= settings.santa_window[1]


def state() -> dict:
    return store._read(STATE, {})


def set_anchor(at: datetime) -> dict:
    """The first slot of the pattern; every later one follows from it."""
    if not in_window(at):
        raise ValueError(f"the anchor must be inside SANTA_WINDOW ({'-'.join(settings.santa_window)}, local)")
    s = state() | {"anchor": at.astimezone(timezone.utc).isoformat(), "anchor_set_at": store.now_iso()}
    (settings.data_dir / "santa").mkdir(parents=True, exist_ok=True)
    store._write(STATE, s)
    return s


def default_anchor(t: datetime | None = None) -> datetime:
    """Without a saved anchor: SANTA_ANCHOR this evening, or tomorrow's once it has passed."""
    t = t or now()
    day = t.astimezone(settings.tz).date()
    at = _local_at(day, settings.santa_anchor)
    return at if at > t else _local_at(day + timedelta(days=1), settings.santa_anchor)


def anchor() -> datetime:
    """The pattern's first slot. Saved the first time it's needed, so the pattern stays put: unsaved,
    "the next 21:30" would move on every evening and start a second pattern beside the first. With
    bookings already made, it's the earliest one's planned slot, so they stay on the pattern."""
    a = state().get("anchor")
    if a:
        return datetime.fromisoformat(a)
    first = _earliest_booking()
    at = first or default_anchor()
    s = state() | {"anchor": at.astimezone(timezone.utc).isoformat(), "anchor_set_at": store.now_iso(),
                   "anchor_from": "first booking" if first else "default"}
    (settings.data_dir / "santa").mkdir(parents=True, exist_ok=True)
    store._write(STATE, s)
    return at


def _earliest_booking() -> datetime | None:
    d = settings.data_dir / "santa" / "jobs"
    planned = []
    for p in d.glob("*.json") if d.exists() else []:
        try:
            planned.append(datetime.fromisoformat(json.loads(p.read_text())["planned"]))
        except (ValueError, KeyError):
            continue
    return min(planned) if planned else None


def _next_nominal(prev: datetime) -> datetime:
    cand = prev + timedelta(hours=settings.santa_cadence_hours)
    local = cand.astimezone(settings.tz)
    hm = local.strftime("%H:%M")
    if hm < settings.santa_window[0]:  # too early: this evening's anchor instead
        return _local_at(local.date(), settings.santa_anchor)
    if hm > settings.santa_window[1]:  # too late: tomorrow's opening time
        return _local_at(local.date() + timedelta(days=1), settings.santa_window[0])
    return cand


def nominal(after: datetime, count: int, start: datetime | None = None) -> list[datetime]:
    """The pattern's next `count` times from `after` on (before any nudging)."""
    t = start or anchor()
    out = []
    for _ in range(100000):
        if len(out) >= count:
            break
        if t >= after:
            out.append(t)
        t = _next_nominal(t)
    return out


def _place(t: datetime, others: list[slots.Busy]) -> tuple[datetime | None, list[slots.Busy]]:
    """The free time nearest `t` (t itself if it's free), and what `t` clashed with."""
    def hits(x):
        return slots.clashes(x, channels.SANTA, settings.santa_buffer_minutes, settings.santa_render_lead_minutes, others)

    first = hits(t)
    if not first:
        return t, []
    for k in range(1, settings.santa_nudge_max_minutes // 15 + 1):
        for cand in (t + STEP * k, t - STEP * k):
            if in_window(cand) and cand > now() and not hits(cand):
                return cand, first
    return None, first


def upcoming(count: int = 14, after: datetime | None = None, start: datetime | None = None) -> list[dict]:
    """The next `count` slots: when each would post (`at`, UTC and local), where the pattern put it
    (`planned`), and why it moved (`nudged`, with what it avoided) or was skipped (`skipped`)."""
    after = after or now()
    times = nominal(after, count, start)
    if not times:
        return []
    others = slots.busy(times[0] - timedelta(hours=4), times[-1] + timedelta(hours=4), exclude=channels.SANTA)
    out = []
    for t in times:
        at, hit = _place(t, others)
        row = {"planned": t.isoformat(), "planned_local": _local(t)}
        if at is None:
            row |= {"skipped": True, "reason": "no free time within "
                    f"{settings.santa_nudge_max_minutes} minutes: " + ", ".join(sorted({b.label for b in hit}))}
        else:
            row |= {"at": at.isoformat(), "local": _local(at)}
            if hit:
                row |= {"nudged": int((at - t).total_seconds() // 60), "avoided": sorted({b.label for b in hit})}
        out.append(row)
    return out


def _local(t: datetime) -> str:
    return t.astimezone(settings.tz).strftime("%a %d %b %H:%M")
