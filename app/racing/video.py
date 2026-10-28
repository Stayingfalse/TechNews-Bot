"""The spec the renderer draws from: built from race records, settlement and the league table.
Plain JSON, so it can be stored with the job and re-rendered (or rendered in another theme) later."""
from __future__ import annotations

from datetime import datetime

from ..config import settings
from . import hooks, races, sim

FPS = sim.FPS


def race_part(race: dict) -> dict:
    """The race as the renderer needs it: per-frame distances plus the result."""
    res = race["result"]
    dist = res["dist"]
    end = min(len(dist) / FPS, res["winner_time"] + 1.4)
    win_t = res["times"][str(res["order"][0])] if str(res["order"][0]) in res["times"] else res["winner_time"]
    gaps = {str(no): round(t - win_t, 3) for no, t in ((int(k), v) for k, v in res["times"].items())
            if t is not None and no != res["order"][0]}
    return {"no": race["no"], "circuit": race["circuit"], "laps": sim.LAPS, "dist": dist,
            "times": res["times"], "events": res["events"], "order": res["order"], "dnf": res["dnf"],
            "margin": res["margin"], "winner_time": res["winner_time"], "race_end": round(end, 3), "gaps": gaps}


def result_part(race: dict, settled: dict | None, bust: int) -> dict:
    bets = [b for b in (settled or {}).get("bets", []) if not b.get("refused")]
    win = race["result"]["order"][0]
    winners = [b for b in bets if b["car"] == win]
    biggest = max(winners, key=lambda b: b["returned"] - b["stake"], default=None)
    return {"odds": race["odds"][win - 1], "bettors": len({b["pid"] for b in bets}),
            "backers": len({b["pid"] for b in winners}), "staked": sum(b["stake"] for b in bets),
            "biggest": {"name": biggest["name"], "won": biggest["returned"] - biggest["stake"], "stake": biggest["stake"]}
            if biggest else None, "bust": bust}


def card_part(race: dict) -> dict:
    closes = datetime.fromisoformat(race["closes_at"]).astimezone(settings.tz)
    return {"no": race["no"], "circuit": race["circuit"], "odds": race["odds"],
            "form": {str(k): v for k, v in races.form(race["no"]).items()}, "seal": race["seal"],
            "closes": closes.strftime("%a %H:%M").upper()}


def spec(theme: str, card_race: dict, ran: dict | None = None, settled: dict | None = None,
         table: dict | None = None, bust: int = 0) -> dict:
    """A race video (ran = the race just run), or the launch video (ran None: rules then the card)."""
    out = {"theme": theme, "cars": sim.CARS, "domain": settings.racing_domain, "card": card_part(card_race),
           "seed": int(card_race["seal"][:8], 16)}
    if ran is None:
        out.update(launch=True, hook=hooks.LAUNCH)
        return out
    out.update(race=race_part(ran), result=result_part(ran, settled, bust), hook=hooks.choose(ran, settled))
    if table:
        out["table"] = table
    return out
