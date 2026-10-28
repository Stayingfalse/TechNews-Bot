"""The race: a seeded simulation on the race's own track, odds from running it many times, and the
seal that proves a race wasn't changed after the bets came in.

How a car goes round: every car has a speed profile for the track (`profile`), the fastest it can
take each point: its top speed caps it on the straights, its grip caps it in the corners
(speed² ≤ grip × 22 m/s² ÷ curvature), its acceleration decides how quickly it gets back up to
speed, and everyone brakes alike. So each format favours different cars by itself: ovals and drag
strips reward top speed and acceleration, rally stages reward grip, endurance rewards tyres and
reliability. On top of that each car's pace wanders (less for consistent cars), and things
happen: spins (mostly in corners), slipstreaming on straights, punctures, blown engines, pit stops
for tyres in endurance races, tangles at the figure 8's crossing, jump starts at the drag strip.

One model runs both ways: `run(rng, ...)` simulates n races side by side. The real race is n=1
from the race's own secret seed; the odds are many runs from a public seed. Anyone can re-run a
race from its revealed seed with this file and get the same result.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

import numpy as np

from . import tracks

CARS = [
    {"no": 1, "name": "RED ROCKET", "colour": "red"},
    {"no": 2, "name": "MEAN GREEN", "colour": "green"},
    {"no": 3, "name": "CUSTARD", "colour": "yellow"},
    {"no": 4, "name": "BLUE STREAK", "colour": "blue"},
    {"no": 5, "name": "HOT PINK", "colour": "magenta"},
    {"no": 6, "name": "CYANARA", "colour": "cyan"},
]
N = len(CARS)
FPS = 30
MARGIN = 0.05  # the book's overround: implied chances add up to 105%
MC_RUNS = 12000

# laps: race length · video: seconds the race takes on screen (the race is sped up or slowed to
# fit) · spin: how loose the surface is · wear: tyre wear per lap · dnf: chance a car with average
# reliability breaks down over the whole race
FORMATS = {
    "oval": {"name": "Oval", "laps": 10, "video": 16.0, "spin": 0.5, "wear": 0.0, "dnf": 0.02, "draft": True},
    "gp": {"name": "Grand Prix", "laps": 5, "video": 18.0, "spin": 1.0, "wear": 0.06, "dnf": 0.02, "draft": True},
    "rally": {"name": "Rally", "laps": 2, "video": 18.0, "spin": 2.6, "wear": 0.15, "dnf": 0.04, "puncture": 0.05},
    "figure8": {"name": "Figure 8", "laps": 8, "video": 17.0, "spin": 0.9, "wear": 0.0, "dnf": 0.02, "cross": True},
    "endurance": {"name": "Endurance", "laps": 24, "video": 22.0, "spin": 0.7, "wear": 0.085, "dnf": 0.06,
                  "pits": True, "puncture": 0.01, "draft": True},
    "drag": {"name": "Drag", "laps": 1, "video": 7.0, "spin": 0.0, "wear": 0.0, "dnf": 0.0, "launch": True},
}
STATS = ("speed", "accel", "grip", "tyres", "consistency", "reliability")

VMAX = 84.0  # m/s for speed 1.0
LATERAL = 22.0  # m/s² of cornering for grip 1.0
ACCEL = 11.0  # m/s² from standstill for accel 1.0
BRAKE = 26.0
SPIN_LOSS, TANGLE_LOSS = 3.5, 3.0  # seconds a spin or a tangle costs
PIT_TIME, PIT_FUMBLE = 24.0, 7.0
PUNCTURE_LOSS = 14.0
DAY_FORM = 0.011  # spread of each car's pace on the day
TANGLE_CHANCE = 0.3


def initial_stats(seed: int = 2026) -> list[dict]:
    """Starting stats: each car has a strength, so each format has its own favourite.
    1 top speed · 2 grip · 3 all-rounder · 4 acceleration · 5 tyres and reliability · 6 grip + accel."""
    rng = np.random.default_rng(seed)
    base = [
        {"speed": 1.014, "accel": 1.0, "grip": 0.988, "tyres": 0.97, "consistency": 0.5, "reliability": 0.78},
        {"speed": 0.996, "accel": 0.995, "grip": 1.018, "tyres": 1.0, "consistency": 0.55, "reliability": 0.8},
        {"speed": 1.003, "accel": 1.002, "grip": 1.003, "tyres": 1.0, "consistency": 0.7, "reliability": 0.82},
        {"speed": 1.005, "accel": 1.022, "grip": 0.992, "tyres": 0.96, "consistency": 0.5, "reliability": 0.78},
        {"speed": 0.998, "accel": 0.993, "grip": 0.998, "tyres": 1.06, "consistency": 0.62, "reliability": 0.9},
        {"speed": 0.993, "accel": 1.012, "grip": 1.012, "tyres": 0.99, "consistency": 0.55, "reliability": 0.8},
    ]
    return [{k: round(float(v + rng.normal(0, 0.003 if k in ("speed", "accel", "grip", "tyres") else 0.01)),
                       4 if k in ("speed", "accel", "grip", "tyres") else 3) for k, v in s.items()} for s in base]


@lru_cache(maxsize=32)
def _track(kind: str, seed: int) -> tracks.Track:
    return tracks.generate(kind, seed)


def profile(track: tracks.Track, stats: list[dict]) -> np.ndarray:
    """(N, POINTS) the fastest each car can take each point of the lap, in m/s."""
    p = len(track.pts)
    ds = track.length / p
    vmax = np.array([VMAX * s["speed"] for s in stats])
    lat = np.array([LATERAL * s["grip"] for s in stats])
    acc = np.array([ACCEL * s["accel"] for s in stats])
    vlim = np.minimum(vmax[:, None], np.sqrt(lat[:, None] / np.maximum(track.curv[None, :], 1e-6)))
    v = vlim.copy()
    if not track.closed:  # a drag strip: from a standstill, flat out
        cur = np.full(N, 1.0)
        for i in range(p):
            a = acc * (1 - cur / vmax) + 0.6
            cur = np.minimum(vmax, np.sqrt(cur ** 2 + 2 * a * ds))
            v[:, i] = cur
        return v
    for _ in range(2):  # twice round, so the start of the lap knows how fast the end was
        for i in range(p):  # accelerating out of each corner
            prev = v[:, i - 1]
            a = acc * (1 - prev / vmax) + 0.6
            v[:, i] = np.minimum(v[:, i], np.sqrt(prev ** 2 + 2 * a * ds))
        for i in range(p - 1, -1, -1):  # braking into the next one
            nxt = v[:, (i + 1) % p]
            v[:, i] = np.minimum(v[:, i], np.sqrt(nxt ** 2 + 2 * BRAKE * ds))
    return v


def lap_times(track: tracks.Track, stats: list[dict]) -> np.ndarray:
    v = profile(track, stats)
    return (track.length / len(track.pts) / v).sum(axis=1)


@dataclass
class Batch:
    """n races simulated together. dist[k, i, j]: laps covered by car j of race i at step k."""
    t: np.ndarray  # (steps,) race time in seconds at each recorded step
    dist: np.ndarray
    finish: np.ndarray  # (n, N) seconds when each car crossed the line, inf if it didn't
    events: list[list[dict]]
    wear: np.ndarray | None = None  # (steps, N) for race 0, when frames are kept
    pit: np.ndarray | None = None  # (steps, N) bool
    reaction: np.ndarray | None = None  # (n, N) drag starts

    def order(self, i: int = 0) -> list[int]:
        f, d = self.finish[i], self.dist[-1, i]
        return sorted(range(N), key=lambda j: (f[j], -d[j]))


def run(rng: np.random.Generator, stats: list[dict], fmt: str, track: tracks.Track, n: int = 1,
        keep_frames: bool = True) -> Batch:
    F = FORMATS[fmt]
    laps = F["laps"]
    prof = profile(track, stats)
    P = prof.shape[1]
    est_lap = float(np.median(lap_times(track, stats)))
    per_lap = 400 if F.get("launch") else min(150, 2400 / laps)
    dt = est_lap / per_lap
    steps = int(laps * per_lap * 1.6) + 50
    cons = np.array([s["consistency"] for s in stats])
    rel = np.array([s["reliability"] for s in stats])
    tyres = np.array([s["tyres"] for s in stats])
    sigma = 0.045 * (1.25 - cons)
    rho = math.exp(-dt / max(est_lap * 0.12, 0.3))
    curv_w = track.curv / max(track.curv.mean(), 1e-9) if track.closed else np.zeros(P)
    spin_per_lap = 0.07 * F["spin"] * (1.6 - cons)
    dnf_per_lap = F["dnf"] * (1 - rel) * 5 / laps
    wear_per_lap = F["wear"] / tyres
    pit_at = 0.78 + 0.12 * (tyres - 1)  # how worn a car's tyres get before it comes in

    dist = np.zeros((n, N))
    wander = np.zeros((n, N))
    lost = np.zeros((n, N))  # seconds still to sit out (spin, pit stop, puncture)
    wear = np.zeros((n, N))
    dead = np.zeros((n, N), bool)
    finish = np.full((n, N), np.inf)
    in_pit = np.zeros((n, N), bool)
    events: list[list[dict]] = [[] for _ in range(n)]
    reaction = None
    start = np.zeros((n, N))
    if F.get("launch"):  # the lights: reaction times, and the odd jump start (disqualified)
        rt = 0.17 + rng.standard_normal((n, N)) * 0.05 * (1.3 - cons)
        reaction = np.clip(rt, 0.06, 0.6)
        jump = rng.random((n, N)) < 0.02 * (1.2 - cons)
        start = reaction
        dead |= jump
        for i, j in zip(*np.nonzero(jump)):
            events[i].append({"t": 0.0, "car": int(j), "kind": "jumpstart"})
    # form on the day (set-up, conditions, luck): the reason favourites lose
    day = 1 + rng.standard_normal((n, N)) * DAY_FORM
    times = [0.0]
    frames = [dist.copy()] if keep_frames else []
    wears = [wear[0].copy()] if keep_frames else []
    pits = [in_pit[0].copy()] if keep_frames else []

    def log(kind, mask, t, **extra):
        for i, j in zip(*np.nonzero(mask)):
            events[i].append({"t": round(t, 3), "car": int(j), "kind": kind,
                              **{k: round(float(v[i, j]), 1) for k, v in extra.items()}})

    for k in range(steps):
        t = (k + 1) * dt
        racing = ~dead & np.isinf(finish)
        if not racing.any():
            break
        # five draws per step, always in this order, so one seed always means one race
        noise, u_spin, u_dnf, u_event, u_pit = (rng.standard_normal((n, N)), rng.random((n, N)), rng.random((n, N)),
                                                rng.random((n, N)), rng.random((n, N)))
        wander = rho * wander + math.sqrt(1 - rho * rho) * noise * sigma
        if track.closed:
            idx = np.minimum((np.mod(dist, 1) * P).astype(int), P - 1)
        else:
            idx = np.minimum((dist * P).astype(int), P - 1)
        moving = racing & (lost <= 0) & (t > start)
        base_v = prof[np.arange(N)[None, :], idx]
        lap_part = base_v * dt / track.length  # share of a lap each car would cover this step

        spin = moving & (u_spin < spin_per_lap * curv_w[idx] * lap_part)
        lost = np.where(spin, SPIN_LOSS, lost)
        log("spin", spin, t)
        blow = racing & (u_dnf < dnf_per_lap * lap_part)
        dead |= blow
        log("blowup", blow, t)
        if F.get("puncture"):
            punct = moving & ~spin & (u_event < F["puncture"] * (0.5 + wear) * lap_part)
            if F.get("pits"):
                wear = np.where(punct, 1.0, wear)  # limps on to its stop
            else:
                lost = np.where(punct, PUNCTURE_LOSS, lost)
            log("puncture", punct, t)
        if F.get("cross"):  # the figure 8's crossing: two cars there at once can tangle
            frac = np.mod(dist, 1)
            ca, cb = track.crossing
            near_a = np.minimum(np.abs(frac - ca), 1 - np.abs(frac - ca)) < 0.02
            near_b = np.abs(frac - cb) < 0.02
            at_a, at_b = moving & near_a, moving & near_b
            both = at_a.any(axis=1) & at_b.any(axis=1)
            hit = both[:, None] & (at_a | at_b) & (u_event < TANGLE_CHANCE * lap_part / 0.02)
            lost = np.where(hit, TANGLE_LOSS, lost)
            log("tangle", hit, t)

        speed = base_v * day * (1 + wander) * (1 - 0.18 * wear ** 1.5)
        if F.get("draft"):  # slipstream: right behind another car on a straight
            gap = dist[:, None, :] - dist[:, :, None]  # [i, a, b]: how far b is ahead of a
            close = ((gap > 0.0005) & (gap < 0.008)).any(axis=2)
            speed = speed * np.where(close & (curv_w[idx] < 0.3), 1.03, 1.0)
        speed = np.where(moving, np.maximum(speed, 1.0), 0.0)

        before = dist.copy()
        dist = dist + speed * dt / track.length
        wear = wear + wear_per_lap * (dist - before)
        lost = np.maximum(lost - dt, 0)
        if F.get("pits"):  # in for tyres at the end of a lap once they're worn
            new_lap = np.floor(dist) > np.floor(before)
            stop = racing & new_lap & (wear >= pit_at) & (dist < laps)
            dur = PIT_TIME + (u_pit - 0.5) * 3 + np.where(u_pit < 0.06, PIT_FUMBLE, 0)
            lost = np.where(stop, dur, lost)
            wear = np.where(stop, 0.0, wear)
            in_pit = (in_pit | stop) & (lost > 0)
            log("pit", stop, t, dur=dur)
        crossed = racing & (dist >= laps)
        if crossed.any():  # the exact crossing time within the step, so photo finishes are fair
            frac = (laps - before[crossed]) / np.maximum(dist[crossed] - before[crossed], 1e-9)
            finish[crossed] = t - dt + frac * dt
            dist[crossed] = laps
        if keep_frames:
            times.append(t)
            frames.append(dist.copy())
            wears.append(wear[0].copy())
            pits.append(in_pit[0].copy())
    if keep_frames:
        return Batch(np.array(times), np.array(frames), finish, events, np.array(wears), np.array(pits), reaction)
    return Batch(np.array([0.0]), dist[None], finish, events, reaction=reaction)


def setup(fmt: str, track_seed: int) -> tracks.Track:
    """The race's track: every format has its own kind, generated from the public track seed."""
    return _track(fmt, track_seed)


def win_chances(stats: list[dict], fmt: str, track_seed: int, runs: int | None = None, seed: int = 0) -> list[float]:
    """Each car's chance of winning, from `runs` races (the seed is public: anyone can check)."""
    runs = runs or MC_RUNS
    track = setup(fmt, track_seed)
    wins = np.zeros(N)
    done = 0
    rng = np.random.default_rng(seed)
    while done < runs:
        n = min(1000, runs - done)
        b = run(rng, stats, fmt, track, n, keep_frames=False)
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
    return best


def odds(stats: list[dict], fmt: str, track_seed: int, seed: int = 0) -> list[str]:
    return [price(c) for c in win_chances(stats, fmt, track_seed, seed=seed)]


def payout(stake: int, frac: str) -> int:
    """What a winning bet returns: the stake back plus the winnings."""
    return stake + int(stake * Fraction(frac))


def drift(stats: list[dict], seed: int) -> list[dict]:
    """Stats after a race: a small seeded random walk, pulled gently back towards each car's
    starting stats so no car runs away for good (or loses its character)."""
    rng = np.random.default_rng(seed)
    home = initial_stats()
    out = []
    for s, h in zip(stats, home):
        d = {}
        for k in STATS:
            v = s.get(k, h[k])
            if k in ("consistency", "reliability"):
                d[k] = round(float(np.clip(v + rng.normal(0, 0.025) - 0.06 * (v - h[k]), 0.15, 0.97)), 3)
            else:
                d[k] = round(float(np.clip(v + rng.normal(0, 0.004) - 0.06 * (v - h[k]), 0.93, 1.08)), 4)
        out.append(d)
    return out


# ------------------------------------------------------------------ the seal


def new_seed() -> str:
    import secrets

    return secrets.token_hex(16)


def seal_text(race_no: int, seed: str, fmt: str, track_seed: int, stats: list[dict]) -> str:
    return f"{race_no}|{seed}|{fmt}|{track_seed}|{json.dumps(stats, sort_keys=True, separators=(',', ':'))}"


def seal(race_no: int, seed: str, fmt: str, track_seed: int, stats: list[dict]) -> str:
    """Published before betting opens; the seed is revealed after the race. sha256 of
    "race_no|seed|format|track_seed|stats as compact sorted JSON"."""
    return hashlib.sha256(seal_text(race_no, seed, fmt, track_seed, stats).encode()).hexdigest()


def race(race_no: int, seed: str, stats: list[dict], fmt: str, track_seed: int) -> Batch:
    """The real race for a revealed seed: numpy's default generator seeded with
    int(sha256("race_no|seed")), then `run` with n=1 on the race's track."""
    key = int(hashlib.sha256(f"{race_no}|{seed}".encode()).hexdigest(), 16)
    return run(np.random.default_rng(key), stats, fmt, setup(fmt, track_seed), 1)


def summary(b: Batch, fmt: str) -> dict:
    """The result, plus the race resampled for the video: the winner crosses the line 1.4 s before
    the race's on-screen time is up, so a 30-minute endurance race is sped up and a drag race slowed."""
    F = FORMATS[fmt]
    order = b.order(0)
    fin = b.finish[0]
    win_t = float(fin[order[0]]) if np.isfinite(fin[order[0]]) else float(b.t[-1])
    scale = win_t / (F["video"] - 1.4)  # race seconds per video second
    n_frames = int(F["video"] * FPS) + 1
    vt = np.arange(n_frames) / FPS * scale
    dist = np.stack([np.interp(vt, b.t, b.dist[:, 0, j]) for j in range(N)], 1)
    out = {
        "format": fmt, "laps": F["laps"], "scale": round(scale, 4),
        "order": [CARS[j]["no"] for j in order],
        "times": {str(CARS[j]["no"]): (round(float(fin[j]), 3) if np.isfinite(fin[j]) else None) for j in range(N)},
        "margin": round(float(fin[order[1]] - fin[order[0]]), 3) if np.isfinite(fin[order[1]]) else None,
        "winner_time": round(win_t, 3),
        "events": [{**e, "real_t": e["t"], "t": round(e["t"] / scale, 3), "car": CARS[e["car"]]["no"]} for e in b.events[0]],
        "dnf": [CARS[j]["no"] for j in range(N) if not np.isfinite(fin[j])],
        "dist": np.round(dist, 4).tolist(),
    }
    if F["wear"]:
        out["wear"] = np.round(np.stack([np.interp(vt, b.t, b.wear[:, j]) for j in range(N)], 1), 2).tolist()
    if F.get("pits"):
        idx = np.clip(np.searchsorted(b.t, vt), 0, len(b.t) - 1)
        out["pit"] = b.pit[idx].astype(int).tolist()
    if b.reaction is not None:
        out["reaction"] = {str(CARS[j]["no"]): round(float(b.reaction[0, j]), 3) for j in range(N)}
    return out
