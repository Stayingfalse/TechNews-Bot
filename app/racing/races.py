"""Race records: one JSON file per race in DATA_DIR/racing/races.

A race is opened (seed drawn, seal and odds published), takes bets while its card is up, then is
run and settled. The seed stays secret until the race has run; nothing outside this module reads
it before then.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import settings
from . import sim

PUBLIC = ("no", "format", "track", "seal", "odds", "opened_at", "closes_at", "status", "post", "result", "bets",
          "revealed")
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _dir() -> Path:
    d = settings.data_dir / "racing" / "races"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(race: dict) -> None:
    p = _dir() / f"{race['no']:05d}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(race, indent=1))
    os.replace(tmp, p)


def get(no: int) -> dict | None:
    p = _dir() / f"{no:05d}.json"
    return json.loads(p.read_text()) if p.exists() else None


def all_races() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_dir().glob("*.json"))]


def latest() -> dict | None:
    files = sorted(_dir().glob("*.json"))
    return json.loads(files[-1].read_text()) if files else None


def public(race: dict) -> dict:
    """What anyone may see: never the seed before the race has run, never the hidden stats."""
    out = {k: race[k] for k in PUBLIC if k in race}
    if race.get("status") == "run":
        out["seed"] = race["seed"]
        out["stats"] = race["stats"]
    return out


def format_on(day) -> str:
    """The calendar's format for a date (RACING_CALENDAR). "a|b" alternates by ISO week."""
    options = settings.racing_calendar.get(DAYS[day.weekday()], "gp").split("|")
    fmt = options[day.isocalendar()[1] % len(options)].strip()
    return fmt if fmt in sim.FORMATS else "gp"


def format_for(closes_at: str) -> str:
    """The format for a race, from the day its video posts (bets close the same day)."""
    from datetime import datetime

    return format_on(datetime.fromisoformat(closes_at).astimezone(settings.tz).date())


def upcoming(closes_at: str, days: int = 5) -> list[dict]:
    """The calendar from a race's video day on: [{date, format}], the first being that race."""
    from datetime import datetime, timedelta

    first = datetime.fromisoformat(closes_at).astimezone(settings.tz).date()
    return [{"date": (first + timedelta(days=k)).isoformat(), "format": format_on(first + timedelta(days=k))}
            for k in range(days)]


def open_race(no: int, stats: list[dict], opened_at: str, closes_at: str, fmt: str | None = None) -> dict:
    """A new race, saved: see draft()."""
    race = draft(no, stats, opened_at, closes_at, fmt)
    save(race)
    return race


def draft(no: int, stats: list[dict], opened_at: str, closes_at: str, fmt: str | None = None) -> dict:
    """A new race: its format from the calendar, a brand-new track, a secret seed, the seal and the odds."""
    import secrets

    fmt = fmt or format_for(closes_at)
    seed = sim.new_seed()
    track_seed = secrets.randbelow(10 ** 9)  # public: the track is on the race card
    track = sim.setup(fmt, track_seed)
    race = {"no": no, "format": fmt, "track": track.public(), "seed": seed, "stats": stats,
            "seal": sim.seal(no, seed, fmt, track_seed, stats),
            "odds": sim.odds(stats, fmt, track_seed, seed=no),  # the odds' own seed is public: the race number
            "opened_at": opened_at, "closes_at": closes_at, "status": "open", "bets": []}
    return race


def run(race: dict) -> dict:
    """Run a race from its secret seed (the result plus the video's frames)."""
    return sim.summary(sim.race(race["no"], race["seed"], race["stats"], race["format"], race["track"]["seed"]),
                       race["format"])


def form(before: int, n: int = 5, fmt: str | None = None) -> dict[int, str]:
    """Each car's last n finishing positions (in this format, if given), most recent last ("21134");
    "-" for no race, "X" for out."""
    done = [r for r in all_races() if r["no"] < before and r.get("status") == "run"
            and (fmt is None or r.get("format") == fmt)][-n:]
    out = {}
    for car in sim.CARS:
        s = ""
        for r in done:
            res = r["result"]
            s += "X" if car["no"] in res["dnf"] else str(res["order"].index(car["no"]) + 1)
        out[car["no"]] = s.rjust(n, "-")
    return out


def streak(car: int, before: int) -> int:
    """How many races in a row a car has won, up to `before`."""
    k = 0
    for r in reversed([r for r in all_races() if r["no"] < before and r.get("status") == "run"]):
        if r["result"]["order"][0] != car:
            break
        k += 1
    return k


def scrub(pids: set[str], names_only: bool = False) -> None:
    """Privacy: take players out of race records (erasure), or only their names (anonymising)."""
    if not pids:
        return
    from .ledger import anon_name

    for race in all_races():
        changed = False
        for key in ("bets", "commenters"):
            rows = race.get(key) or []
            if key == "bets":
                if names_only:
                    for b in rows:
                        if b["pid"] in pids and b.get("name"):
                            b["name"], changed = anon_name(b["pid"]), True
                else:
                    keep = [b for b in rows if b["pid"] not in pids]
                    changed |= len(keep) != len(rows)
                    race[key] = keep
            elif not names_only:
                keep = [p for p in rows if p not in pids]
                changed |= len(keep) != len(rows)
                race[key] = keep
        if changed:
            save(race)
