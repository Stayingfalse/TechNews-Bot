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

CIRCUITS = [  # fictional circuits, one per race in turn; the seed bends each into its own shape
    {"name": "Sixel Park", "seed": 7},
    {"name": "Kestrel Ring", "seed": 21},
    {"name": "Harbour Loop", "seed": 33},
    {"name": "Moorside", "seed": 48},
    {"name": "Glass Lake", "seed": 55},
    {"name": "Copper Hill", "seed": 61},
    {"name": "Old Aerodrome", "seed": 74},
]
PUBLIC = ("no", "seal", "odds", "circuit", "opened_at", "closes_at", "status", "post", "result", "bets",
          "stats_hash", "revealed")


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


def open_race(no: int, stats: list[dict], opened_at: str, closes_at: str) -> dict:
    seed = sim.new_seed()
    race = {"no": no, "seed": seed, "stats": stats, "seal": sim.seal(no, seed, stats),
            "odds": sim.odds(stats, seed=no),  # the odds' own seed is public: the race number
            "circuit": CIRCUITS[(no - 1) % len(CIRCUITS)], "opened_at": opened_at, "closes_at": closes_at,
            "status": "open", "bets": [], "replied": []}
    save(race)
    return race


def form(before: int, n: int = 5) -> dict[int, str]:
    """Each car's last n finishing positions, most recent last ("21134"); "-" for no race, "X" for out."""
    done = [r for r in all_races() if r["no"] < before and r.get("status") == "run"][-n:]
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
