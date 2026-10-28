"""The race: a seeded simulation, odds from running it many times, and the seal that proves a race
wasn't changed after the bets came in.

One model runs both ways: `run(rng, stats, n)` simulates n races side by side. The real race is
n=1 from the race's own secret seed; the odds are n=20,000 from a public seed. So a 9/2 car really
wins about as often as its odds say (less the margin). Anyone can re-run a race from its revealed
seed with this file and get the same result.

Stats per car: pace (top speed, ~1.0), consistency (0-1, steadier and fewer spins when high) and
reliability (0-1, fewer blown engines). They drift a little after every race (`drift`).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

CARS = [
    {"no": 1, "name": "RED ROCKET", "colour": "red"},
    {"no": 2, "name": "MEAN GREEN", "colour": "green"},
    {"no": 3, "name": "CUSTARD", "colour": "yellow"},
    {"no": 4, "name": "BLUE STREAK", "colour": "blue"},
    {"no": 5, "name": "HOT PINK", "colour": "magenta"},
    {"no": 6, "name": "CYANARA", "colour": "cyan"},
]
N = len(CARS)
LAPS = 3
FPS = 30
DT = 1 / FPS
BASE_SPEED = LAPS / 15.0  # laps per second: a race lasts about 15 s
MAX_T = 30.0  # stop simulating after this; anyone not home is classified by distance
MARGIN = 0.05  # the book's overround: implied chances add up to 105%
MC_RUNS = 20000

# Event chances per second of racing (scaled by the car's stats)
SPIN_RATE = 0.022  # a spin costs about 1.2 s
TURBO_RATE = 0.03  # a turbo adds speed for 1.5 s
BLOWUP_RATE = 0.0017  # a blown engine ends the race
SIGMA = 0.16  # speed wander, scaled down for consistent cars
RHO = 0.97  # how slowly the wander changes frame to frame (slow swings make real overtakes)


def initial_stats(seed: int = 2026) -> list[dict]:
    """The roster's starting stats: close enough that any car can win, different enough to have favourites."""
    rng = np.random.default_rng(seed)
    pace = 1 + np.array([0.012, 0.006, 0.002, -0.003, -0.008, -0.012]) + rng.normal(0, 0.002, N)
    cons = np.clip(0.55 + rng.normal(0, 0.12, N), 0.2, 0.9)
    rel = np.clip(0.8 + rng.normal(0, 0.08, N), 0.5, 0.97)
    return [{"pace": round(float(p), 4), "consistency": round(float(c), 3), "reliability": round(float(r), 3)}
            for p, c, r in zip(pace, cons, rel)]


@dataclass
class Batch:
    """n races simulated together. dist[k, i, j] = laps covered by car j of race i at frame k."""
    dist: np.ndarray
    finish: np.ndarray  # (n, N) time each car crossed the line, inf if it didn't
    events: list[list[dict]]  # per race: {t, car, kind}

    def order(self, i: int = 0) -> list[int]:
        """Finishing order of race i (car indexes): finishers by time, then the rest by distance."""
        f, d = self.finish[i], self.dist[-1, i]
        return sorted(range(N), key=lambda j: (f[j], -d[j]))


def run(rng: np.random.Generator, stats: list[dict], n: int = 1, keep_frames: bool = True) -> Batch:
    pace = np.array([s["pace"] for s in stats])
    cons = np.array([s["consistency"] for s in stats])
    rel = np.array([s["reliability"] for s in stats])
    steps = int(MAX_T * FPS)
    sigma = SIGMA * (1.15 - cons)  # how much a car's speed wanders

    dist = np.zeros((n, N))
    wander = np.zeros((n, N))
    slow = np.zeros((n, N))  # seconds of spin left
    boost = np.zeros((n, N))  # seconds of turbo left
    dead = np.zeros((n, N), bool)
    finish = np.full((n, N), np.inf)
    frames = [dist.copy()] if keep_frames else []
    events: list[list[dict]] = [[] for _ in range(n)]
    p_spin = SPIN_RATE * DT * (1.6 - cons)
    p_turbo = TURBO_RATE * DT
    p_blow = BLOWUP_RATE * DT * (1 - rel) * 4
    for k in range(steps):
        t = (k + 1) * DT
        racing = ~dead & np.isinf(finish)
        if not racing.any():
            break
        # four draws per frame, always in this order, so one seed always means one race
        noise, u_spin, u_turbo, u_blow = (rng.standard_normal((n, N)), rng.random((n, N)),
                                          rng.random((n, N)), rng.random((n, N)))
        wander = RHO * wander + np.sqrt(1 - RHO ** 2) * noise * sigma
        spin = racing & (slow <= 0) & (u_spin < p_spin)
        turbo = racing & (boost <= 0) & (slow <= 0) & (u_turbo < p_turbo)
        blow = racing & (u_blow < p_blow)
        slow[spin], boost[turbo] = 1.2, 1.5
        dead |= blow
        for kind, mask in (("spin", spin), ("turbo", turbo), ("blowup", blow)):
            for i, j in zip(*np.nonzero(mask)):
                events[i].append({"t": round(t, 3), "car": int(j), "kind": kind})
        speed = BASE_SPEED * pace * (1 + wander) * np.where(slow > 0, 0.25, 1) * np.where(boost > 0, 1.12, 1)
        speed = np.where(racing, np.maximum(speed, 0.02), 0)
        before = dist.copy()
        dist = dist + speed * DT
        crossed = racing & (dist >= LAPS)
        if crossed.any():  # exact crossing time within the frame, so photo finishes are fair
            frac = (LAPS - before[crossed]) / (dist[crossed] - before[crossed])
            finish[crossed] = t - DT + frac * DT
            dist[crossed] = LAPS
        slow, boost = slow - DT, boost - DT
        if keep_frames:
            frames.append(dist.copy())
    if keep_frames:
        arr = np.array(frames)
    else:
        arr = dist[None]
    return Batch(arr, finish, events)


def win_chances(stats: list[dict], runs: int = MC_RUNS, seed: int = 0) -> list[float]:
    """Each car's chance of winning, from `runs` races (the seed is public: anyone can check)."""
    wins = np.zeros(N)
    done = 0
    rng = np.random.default_rng(seed)
    while done < runs:
        n = min(1000, runs - done)
        b = run(rng, stats, n, keep_frames=False)
        winner = np.where(np.isinf(b.finish).all(axis=1), b.dist[-1].argmax(axis=1), b.finish.argmin(axis=1))
        wins += np.bincount(winner, minlength=N)
        done += n
    return [float(w / runs) for w in wins]


# The usual bookmaker ladder; prices are rounded down to the nearest step (never in the punter's favour)
LADDER = ["1/5", "1/4", "2/7", "1/3", "2/5", "4/9", "1/2", "8/15", "4/7", "8/13", "4/6", "8/11", "4/5",
          "5/6", "10/11", "1/1", "11/10", "6/5", "5/4", "11/8", "6/4", "13/8", "7/4", "15/8", "2/1", "9/4",
          "5/2", "11/4", "3/1", "10/3", "7/2", "4/1", "9/2", "5/1", "11/2", "6/1", "13/2", "7/1", "15/2", "8/1",
          "9/1", "10/1", "11/1", "12/1", "14/1", "16/1", "20/1", "25/1", "33/1", "40/1", "50/1", "66/1", "100/1"]


def price(chance: float, margin: float = MARGIN) -> str:
    """Fractional odds for a chance, with the margin, e.g. 0.18 → "9/2"."""
    fair = 1 / max(chance * (1 + margin), 1e-6) - 1
    best = LADDER[0]
    for step in LADDER:
        if Fraction(step) <= fair:
            best = step
    return "1/1" if best == "1/1" and fair < 0.2 else best


def odds(stats: list[dict], seed: int = 0) -> list[str]:
    return [price(c) for c in win_chances(stats, seed=seed)]


def payout(stake: int, frac: str) -> int:
    """What a winning bet returns: the stake back plus the winnings."""
    return stake + int(stake * Fraction(frac))


def drift(stats: list[dict], seed: int) -> list[dict]:
    """Stats after a race: a small seeded random walk, pulled gently back towards the middle so no
    car runs away for good."""
    rng = np.random.default_rng(seed)
    out = []
    for s in stats:
        pace = s["pace"] + rng.normal(0, 0.006) - 0.05 * (s["pace"] - 1)
        cons = s["consistency"] + rng.normal(0, 0.03) - 0.05 * (s["consistency"] - 0.55)
        rel = s["reliability"] + rng.normal(0, 0.02) - 0.05 * (s["reliability"] - 0.8)
        out.append({"pace": round(float(np.clip(pace, 0.93, 1.07)), 4),
                    "consistency": round(float(np.clip(cons, 0.15, 0.95)), 3),
                    "reliability": round(float(np.clip(rel, 0.5, 0.98)), 3)})
    return out


# ------------------------------------------------------------------ the seal


def new_seed() -> str:
    import secrets

    return secrets.token_hex(16)


def seal(race_no: int, seed: str, stats: list[dict]) -> str:
    """Published before betting opens; the seed is revealed after the race. sha256 of
    "race_no|seed|stats as compact sorted JSON"."""
    body = f"{race_no}|{seed}|{json.dumps(stats, sort_keys=True, separators=(',', ':'))}"
    return hashlib.sha256(body.encode()).hexdigest()


def race(race_no: int, seed: str, stats: list[dict]) -> Batch:
    """The real race for a revealed seed."""
    return run(np.random.default_rng(int(seed, 16) ^ race_no), stats, 1)


def summary(b: Batch) -> dict:
    """What the rest of the system needs from a race: order, times, events, and the track data
    for the video (distance per car per frame, rounded)."""
    order = b.order(0)
    fin = b.finish[0]
    win_t = float(fin[order[0]]) if np.isfinite(fin[order[0]]) else float(len(b.dist) * DT)
    return {
        "order": [CARS[j]["no"] for j in order],
        "times": {str(CARS[j]["no"]): (round(float(fin[j]), 3) if np.isfinite(fin[j]) else None) for j in range(N)},
        "margin": round(float(fin[order[1]] - fin[order[0]]), 3) if np.isfinite(fin[order[1]]) else None,
        "winner_time": round(win_t, 3),
        "events": [{**e, "car": CARS[e["car"]]["no"]} for e in b.events[0]],
        "dnf": [CARS[j]["no"] for j in range(N) if not np.isfinite(fin[j])],
        "dist": np.round(b.dist[:, 0, :], 4).tolist(),
    }
