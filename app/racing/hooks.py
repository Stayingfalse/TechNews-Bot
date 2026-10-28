"""The hook: the video's first line, picked from templates filled with the race's own numbers.

We already know the result when the video is rendered, so a hook can set up the payoff, but every
template is true whichever way the race went: it never claims an outcome. *Starred* words are
highlighted. Each hook is 2-3 short lines.
"""
from __future__ import annotations

import random
from fractions import Fraction

from . import races


def candidates(race: dict, settled: dict | None) -> list[tuple[int, list[str]]]:
    """(priority, lines) for every hook that fits this race."""
    bets = [b for b in (settled or {}).get("bets", []) if not b.get("refused")]
    staked = sum(b["stake"] for b in bets)
    bettors = len({b["pid"] for b in bets})
    res = race["result"]
    win = res["order"][0]
    win_odds = Fraction(race["odds"][win - 1])
    backers = len({b["pid"] for b in bets if b["car"] == win})
    out: list[tuple[int, list[str]]] = []
    if bettors >= 3 and win_odds >= 6:
        out.append((5, [f"Only *{backers}* of you", "backed the", "outsider"]))
    if staked >= 1000 and bettors >= 3:
        out.append((4, [f"*§{staked:,}*", "riding on", "one race"]))
    allin = len({b["pid"] for b in bets if b.get("asked") == "all"})
    if allin >= 2:
        out.append((4, [f"*{allin}* of you", "went all in"]))
    big = sorted(bets, key=lambda b: -b["stake"])
    if len(big) >= 2 and big[0]["car"] != big[1]["car"] and big[1]["stake"] >= 200:
        a, b = big[0], big[1]
        out.append((3, [f"@{a['name']}", "vs", f"@{b['name']}"] if len(a["name"]) + len(b["name"]) < 24
                    else [f"*§{a['stake'] + b['stake']:,}*", "on rival cars"]))
    for car in range(1, 7):
        k = races.streak(car, race["no"])
        if k >= 2:
            from .sim import CARS

            out.append((3, [CARS[car - 1]["name"].title(), f"has won *{k}*", "in a row"]))
    m = res.get("margin")
    if m is not None and m < 0.1:
        out.append((2, ["Too close", "to *call*?"]))
    if bettors:
        out.append((1, [f"*{bettors}* punters", "one winner"]))
    out.append((0, [f"Race *{race['no']}*", race["circuit"]["name"], "lights out"]))
    return out


def choose(race: dict, settled: dict | None) -> list[str]:
    """The best-fitting hook; ties broken by the race's seed so it varies but re-renders match."""
    cands = candidates(race, settled)
    top = max(p for p, _ in cands)
    best = [lines for p, lines in cands if p == top]
    return random.Random(race["seed"]).choice(best)


LAUNCH = ["Bet on a *race*", "every day"]
