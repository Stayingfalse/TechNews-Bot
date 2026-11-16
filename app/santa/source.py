"""Live figures from raosanta.uk (its GET /api/promo/stats, in the rast3 repo), filled into a promo
when it's rendered, so a video quotes the numbers of that hour.

The site only ever gives rounded, site-wide counts ("1,200+"; under 10 is null). A spec quotes them
with placeholders such as {allTime.gifts} (the list: spec.PLACEHOLDERS). On screen they appear as
given; in a narrator line "1,200+" is read as "over 1,200".

When the site can't be reached, the last good answer is used for up to STALE_AFTER. A placeholder
with no value leaves out what it's in: a figure without a number is dropped, and so is any other
segment (and a figures segment with nothing left), or caption sentence. The `end` card is never
dropped.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

import httpx

from ..config import settings
from .spec import PLACEHOLDER, PromoSpec

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(hours=12)
_ROUNDED = re.compile(r"^(\d[\d,]*)\+$")


def _cache_path():
    p = settings.data_dir / "santa" / "stats.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch() -> dict | None:
    """The site's figures now, else the last good copy if it's recent, else None."""
    if settings.raosanta_api_token:
        try:
            r = httpx.get(f"{settings.raosanta_api_url}/api/promo/stats", timeout=15,
                          headers={"Authorization": f"Bearer {settings.raosanta_api_token}"})
            r.raise_for_status()
            stats = r.json()
            _cache_path().write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "stats": stats}))
            return stats
        except Exception as e:  # never log the token: only the error's kind and status
            log.warning("raosanta stats unavailable: %s %s", type(e).__name__, getattr(getattr(e, "response", None), "status_code", ""))
    p = _cache_path()
    if p.exists():
        saved = json.loads(p.read_text())
        if datetime.now(timezone.utc) - datetime.fromisoformat(saved["fetched_at"]) < STALE_AFTER:
            return saved["stats"]
    return None


def _day(ymd: str | None) -> str | None:
    if not ymd:
        return None
    d = date.fromisoformat(ymd)
    return f"{d.day} {d:%B}"


def values(stats: dict | None) -> dict[str, str]:
    """placeholder name -> text, for the placeholders that have a value."""
    if not stats:
        return {}
    out: dict[str, str] = {}
    for group in ("allTime", "thisSeason", "groups"):
        for k, v in (stats.get(group) or {}).items():
            if isinstance(v, str) and v:
                out[f"{group}.{k}"] = v
    season = stats.get("season") or {}
    if season.get("year"):
        out["season.year"] = str(season["year"])
    for k in ("opensOn", "closesOn", "lastOrderOn"):
        if (d := _day(season.get(k))):
            out[f"season.{k}"] = d
    for k in ("daysToOpen", "daysToClose", "daysToLastOrder"):
        if isinstance(season.get(k), int):
            out[f"season.{k}"] = str(season[k])
    return out


def _spoken(v: str) -> str:
    m = _ROUNDED.match(v)
    return f"over {m.group(1)}" if m else v


def _fill(text: str, vals: dict[str, str], spoken: bool = False) -> str | None:
    """`text` with its placeholders filled, or None if one has no value."""
    missing = False

    def sub(m):
        nonlocal missing
        v = vals.get(m.group(1))
        if v is None:
            missing = True
            return ""
        return _spoken(v) if spoken else v

    out = PLACEHOLDER.sub(sub, text)
    return None if missing else out


def _fill_any(value, vals: dict[str, str], key: str = ""):
    """A dumped segment (or part) filled; raises KeyError when a placeholder has no value."""
    if isinstance(value, str):
        out = _fill(value, vals, spoken=key == "say")
        if out is None:
            raise KeyError(key)
        return out
    if isinstance(value, dict):
        return {k: _fill_any(v, vals, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill_any(v, vals, key) for v in value]
    return value


def uses_figures(spec: PromoSpec) -> bool:
    return bool(PLACEHOLDER.search(spec.model_dump_json()))


def fill(spec: PromoSpec, stats: dict | None) -> tuple[PromoSpec, list[str]]:
    """The spec with live figures in, and what was left out (and why)."""
    if not uses_figures(spec):
        return spec, []
    vals = values(stats)
    dumped = spec.model_dump()
    kept, notes = [], []
    for i, seg in enumerate(dumped["segments"]):
        if seg["type"] == "figures":
            figs = []
            for f in seg["figures"]:
                try:
                    figs.append(_fill_any(f, vals))
                except KeyError:
                    notes.append(f"segment {i}: left out the figure {f['value']!r} (no value)")
            if not figs:
                notes.append(f"segment {i}: left out (no figures had a value)")
                continue
            seg = seg | {"figures": figs}
        try:
            kept.append(_fill_any(seg, vals))
        except KeyError as e:
            if seg["type"] == "end":
                raise ValueError(f"the end card's {e.args[0]} has a placeholder with no value")
            notes.append(f"segment {i} ({seg['type']}): left out, {e.args[0]} has a figure with no value")
    if len(kept) < 2:
        raise ValueError("too little left once the missing figures were taken out: " + "; ".join(notes))
    caption = []
    for sentence in re.split(r"(?<=[.!?])\s+", dumped["caption"]):
        filled = _fill(sentence, vals)
        if filled is None:
            notes.append(f"caption: left out {sentence!r}")
        elif filled:
            caption.append(filled)
    return PromoSpec.model_validate(dumped | {"segments": kept, "caption": " ".join(caption)}), notes
