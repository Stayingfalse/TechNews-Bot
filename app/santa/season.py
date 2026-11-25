"""raosanta.uk's season plan: every promo for the season, written ahead in one file
(santa_season/<year>.json), instead of a routine writing them week by week.

Each item is a promo spec with an optional date window (`from`, `until`, UK dates, both
included). The server books from the plan a few days ahead (SANTA_BOOK_AHEAD_DAYS): each free
slot of the 22-hour pattern takes the first promo, in file order, whose window includes that
slot's day. So:
- a promo never goes out outside its window (no "gifting opens Friday" after it's opened);
- an edit to the file reaches every promo not yet booked, once it's deployed;
- a promo whose window passes before a slot fits it is left out, and listed as expired;
- items with no window are fillers, used wherever nothing dated fits.
Nothing is booked after the plan's `ends` date. Ids are never reused, so a promo is never booked twice, and nothing is booked unless
SANTA_ENABLED is on. GET /santa/season shows where every item stands.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from ..config import settings
from . import jobs, source
from .spec import PromoSpec

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2] / "santa_season"


def path(year: int | None = None) -> Path:
    if settings.santa_season_file:
        return Path(settings.santa_season_file)
    year = year or _season_year(datetime.now(timezone.utc))
    return ROOT / f"{year}.json"


def _season_year(t: datetime) -> int:
    """The season a moment belongs to: August to July, named by the year it starts."""
    local = t.astimezone(settings.tz)
    return local.year if local.month >= 8 else local.year - 1


def ends(p: Path | None = None) -> date | None:
    """The plan's last day (UK date): nothing is booked after it."""
    try:
        e = json.loads((p or path()).read_text()).get("ends")
        return date.fromisoformat(e) if e else None
    except (OSError, ValueError):
        return None


def load(p: Path | None = None) -> tuple[list[dict], list[str]]:
    """The plan's items ({spec, from, until}) and every problem with it. An item with a problem is
    left out; the rest still run."""
    p = p or path()
    if not p.exists():
        return [], [f"no season plan at {p.name}"]
    try:
        raw = json.loads(p.read_text())
    except ValueError as e:
        return [], [f"{p.name} isn't valid JSON: {e}"]
    items, probs, seen = [], [], set()
    if raw.get("ends"):
        try:
            date.fromisoformat(raw["ends"])
        except ValueError:
            probs.append("ends must be YYYY-MM-DD")
    for k, it in enumerate(raw.get("items") or []):
        where = f"items[{k}]"
        try:
            spec = PromoSpec.model_validate(it.get("spec"))
        except ValidationError as e:
            probs += [f"{where}.{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
            continue
        try:
            start = date.fromisoformat(it["from"]) if it.get("from") else None
            end = date.fromisoformat(it["until"]) if it.get("until") else None
        except ValueError:
            probs.append(f"{where} ({spec.id}): from/until must be YYYY-MM-DD")
            continue
        if start and end and end < start:
            probs.append(f"{where} ({spec.id}): until is before from")
            continue
        if spec.id in seen:
            probs.append(f"{where}: id {spec.id!r} is used twice")
            continue
        seen.add(spec.id)
        items.append({"spec": spec, "from": start, "until": end})
    return items, probs


def _used_ids() -> dict[str, dict]:
    """Ids already booked or posted (a cancelled booking frees its id)."""
    return {j["spec"]["id"]: j for j in jobs.all_jobs() if j["status"] != "cancelled"}


def _fits(item: dict, day: date) -> bool:
    return (item["from"] is None or item["from"] <= day) and (item["until"] is None or day <= item["until"])


def sync(t: datetime | None = None) -> list[dict]:
    """Book the plan into the free slots up to SANTA_BOOK_AHEAD_DAYS ahead. Returns what it booked."""
    t = t or jobs.now()
    items, probs = load()
    if probs:
        log.warning("santa season plan problems: %s", probs)
    used = _used_ids()
    waiting = [it for it in items if it["spec"].id not in used]
    if not waiting:
        return []
    horizon = t + timedelta(days=settings.santa_book_ahead_days)
    last = ends()
    pairs = []
    for row in jobs.free_slots(40, t):
        at = datetime.fromisoformat(row["at"])
        day = at.astimezone(settings.tz).date()
        if at > horizon or (last and day > last):
            break
        dated = (it for it in waiting if (it["from"] or it["until"]) and _fits(it, day))
        fillers = (it for it in waiting if not it["from"] and not it["until"])
        pick = next(dated, None) or next(fillers, None)
        if pick:
            waiting.remove(pick)
            pairs.append((pick["spec"], row))
    return jobs.book_into(pairs, "season plan")


def substitute(day: date, exclude: str = "") -> PromoSpec | None:
    """A promo for `day` that quotes no figures, for a slot whose own promo has none to show
    (the site hides counts under 10, or the last order day isn't set). Dated ones that fit come
    first, then fillers; never one already booked."""
    items, _ = load()
    used = _used_ids()
    free = [it for it in items if it["spec"].id not in used and it["spec"].id != exclude and not source.uses_figures(it["spec"])]
    dated = (it for it in free if (it["from"] or it["until"]) and _fits(it, day))
    fillers = (it for it in free if not it["from"] and not it["until"])
    pick = next(dated, None) or next(fillers, None)
    return pick["spec"] if pick else None


def finished(t: datetime | None = None) -> bool:
    """True when every item is booked or posted, or its window has passed."""
    today = (t or jobs.now()).astimezone(settings.tz).date()
    last = ends()
    if last and today > last:
        return True
    items, _ = load()
    used = _used_ids()
    return all(it["spec"].id in used or (it["until"] and it["until"] < today) for it in items)


def report(t: datetime | None = None) -> dict:
    """Every item and where it stands: posted, booked (when), waiting (its window), expired."""
    t = t or jobs.now()
    today = t.astimezone(settings.tz).date()
    items, probs = load()
    used = _used_ids()
    rows = []
    for it in items:
        s, j = it["spec"], used.get(it["spec"].id)
        row = {"id": s.id, "format": s.format, "audience": s.audience,
               "from": it["from"].isoformat() if it["from"] else None,
               "until": it["until"].isoformat() if it["until"] else None}
        if j:
            row |= {"status": "posted" if j["status"] == "done" else j["status"], "at": jobs._local(j["publish_at"]),
                    "job": j["id"]}
        elif (it["until"] and it["until"] < today) or ((last := ends()) and today > last):
            row["status"] = "expired"
        else:
            row["status"] = "waiting"
        rows.append(row)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"file": path().name, "ends": ends().isoformat() if ends() else None, "problems": probs, "counts": counts, "items": rows,
            "book_ahead_days": settings.santa_book_ahead_days, "enabled": settings.santa_enabled}
