"""The spec the renderer draws from: built from race records, settlement and the league table.
Plain JSON, so it can be stored with the job and re-rendered (or rendered in another theme) later."""
from __future__ import annotations

from datetime import datetime

from ..config import settings
from . import commentary, hooks, races, sim


def format_part(fmt: str) -> dict:
    F = sim.FORMATS[fmt]
    return {"key": fmt, "name": F["name"], "laps": F["laps"], "pits": bool(F.get("pits")),
            "wear": bool(F["wear"]), "launch": bool(F.get("launch")), "cross": bool(F.get("cross"))}


def race_part(race: dict) -> dict:
    """The race as the renderer needs it: per-frame distances (already in video time) plus the result."""
    res = race["result"]
    scale = res["scale"]
    win = str(res["order"][0])
    gaps = {no: round(t - res["times"][win], 3) for no, t in res["times"].items() if t is not None and no != win}
    out = {"no": race["no"], "format": format_part(race["format"]), "track": race["track"], "laps": res["laps"],
           "dist": res["dist"], "times": res["times"],
           "vtimes": {no: (round(t / scale, 3) if t is not None else None) for no, t in res["times"].items()},
           "events": res["events"], "order": res["order"], "dnf": res["dnf"], "margin": res["margin"],
           "winner_time": res["winner_time"], "scale": scale, "race_end": round((len(res["dist"]) - 1) / sim.FPS, 3),
           "gaps": gaps}
    for k in ("wear", "pit", "reaction"):
        if k in res:
            out[k] = res[k]
    out["commentary"] = commentary.lines(out, int(race["seal"][:8], 16))
    return out


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
    return {"no": race["no"], "format": format_part(race["format"]), "track": race["track"], "odds": race["odds"],
            "form": {str(k): v for k, v in races.form(race["no"], fmt=race["format"]).items()}, "seal": race["seal"],
            "closes": closes.strftime("%a %H:%M").upper()}


def schedule_part(card_race: dict, days: int = 5) -> list[dict]:
    """The coming races, from the card's race on: what runs on which day."""
    out = []
    for k, row in enumerate(races.upcoming(card_race["closes_at"], days)):
        day = datetime.fromisoformat(row["date"])
        fmt = card_race["format"] if k == 0 else row["format"]
        out.append({"day": "TOMORROW" if k == 0 else day.strftime("%a %d").upper(), "format": format_part(fmt),
                    "no": card_race["no"] + k, "open": k == 0})
    return out


def spec(theme: str, card_race: dict, ran: dict | None = None, settled: dict | None = None,
         table: dict | None = None, bust: int = 0, intro: str = "classic") -> dict:
    """A race video (ran = the race just run), or the launch video (ran None: rules then the card).
    `intro` picks the race video's opening (app/render/racing/engine.py INTROS)."""
    out = {"theme": theme, "intro": intro, "cars": sim.CARS, "domain": settings.racing_domain, "card": card_part(card_race),
           "schedule": schedule_part(card_race), "seed": int(card_race["seal"][:8], 16)}
    if ran is None:
        out.update(launch=True, hook=hooks.LAUNCH)
        return out
    out.update(race=race_part(ran), result=result_part(ran, settled, bust), hook=hooks.choose(ran, settled))
    if table:
        out["table"] = table
    return out
