"""Tracks: a new one for every race, generated from a public seed and the race's format.

A track is a closed loop (or, for a drag race, a straight) as evenly spaced points in a unit box,
with its length in metres and the curvature at every point. The curvature is what makes formats
differ: a car's corner speed is capped by its grip over the curvature, so twisty tracks reward
grip and long straights reward top speed (see sim.profile).

Kinds: oval (two straights, two long banked turns), gp (fast straights and a mix of corners),
rally (corner after corner), figure8 (crosses itself in the middle), endurance (a long gp-style
lap) and drag (a straight quarter mile).
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

POINTS = 600  # points per lap


@dataclass
class Track:
    kind: str
    name: str
    seed: int
    pts: np.ndarray  # (POINTS, 2) in [0, 1] x [0, 1], y down
    length: float  # metres
    curv: np.ndarray = field(repr=False)  # 1/m at each point
    crossing: tuple[float, float] | None = None  # figure 8: the two lap fractions at the crossing
    closed: bool = True
    n_corners: int = 0

    def public(self) -> dict:
        """What the race card and the renderer get (and anyone can rebuild from kind + seed)."""
        return {"kind": self.kind, "name": self.name, "seed": self.seed, "length": round(self.length),
                "pts": np.round(self.pts, 4).tolist(), "crossing": self.crossing, "closed": self.closed,
                "corners": self.n_corners}


def _resample(raw: np.ndarray, closed: bool = True, n: int = POINTS) -> np.ndarray:
    """Evenly spaced by distance along the line."""
    loop = np.vstack([raw, raw[:1]]) if closed else raw
    seg = np.linalg.norm(np.diff(loop, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    even = np.linspace(0, s[-1], n, endpoint=not closed)
    return np.stack([np.interp(even, s, loop[:, 0]), np.interp(even, s, loop[:, 1])], 1)


def _fit(pts: np.ndarray, margin: float = 0.06) -> np.ndarray:
    """Scaled into the unit box, keeping its shape, centred."""
    lo, hi = pts.min(0), pts.max(0)
    size = (hi - lo).max()
    out = (pts - lo) / size * (1 - 2 * margin) + margin
    return out + (1 - (out.max(0) + out.min(0))) / 2


def _curvature(pts: np.ndarray, length: float, closed: bool) -> np.ndarray:
    n = len(pts)
    ds = length / n
    k = 4  # look a few points either side so the number is smooth
    if closed:
        a, b, c = np.roll(pts, k, 0), pts, np.roll(pts, -k, 0)
    else:
        idx = np.arange(n)
        a, b, c = pts[np.clip(idx - k, 0, n - 1)], pts, pts[np.clip(idx + k, 0, n - 1)]
    h1 = np.arctan2(*(b - a).T[::-1])
    h2 = np.arctan2(*(c - b).T[::-1])
    turn = np.abs((h2 - h1 + np.pi) % (2 * np.pi) - np.pi)
    curv = turn / (k * ds)
    return np.convolve(np.concatenate([curv[-5:], curv, curv[:5]]) if closed else np.pad(curv, 5, mode="edge"),
                       np.ones(11) / 11, mode="valid")


def _intersects(pts: np.ndarray) -> bool:
    """Does the closed line cross itself? (Checked on a coarse copy, which is plenty.)"""
    p = pts[::6]
    m = len(p)
    segs = [(p[i], p[(i + 1) % m]) for i in range(m)]

    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    for i in range(m):
        for j in range(i + 2, m):
            if i == 0 and j == m - 1:
                continue
            a, b = segs[i]
            c, d = segs[j]
            if ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d):
                return True
    return False


def _fillet(poly: np.ndarray, radii: list[float]) -> np.ndarray:
    """A closed path along the polygon's sides (the straights) with each corner rounded off by a
    circular arc of its own radius (a hairpin where the turn is sharp and the radius small)."""
    m = len(poly)
    out = []
    for i in range(m):
        a, p, b = poly[i - 1], poly[i], poly[(i + 1) % m]
        u, v = (p - a) / np.linalg.norm(p - a), (b - p) / np.linalg.norm(b - p)
        turn = math.acos(float(np.clip(u @ v, -1, 1)))
        if turn < 1e-3:
            out.append(p)
            continue
        t = min(radii[i] * math.tan(turn / 2), 0.45 * np.linalg.norm(p - a), 0.45 * np.linalg.norm(b - p))
        r = t / math.tan(turn / 2)
        start, end = p - u * t, p + v * t
        side = 1 if u[0] * v[1] - u[1] * v[0] > 0 else -1
        normal = np.array([-u[1], u[0]]) * side
        centre = start + normal * r
        a0 = math.atan2(*(start - centre)[::-1])
        a1 = math.atan2(*(end - centre)[::-1])
        sweep = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        for k in np.linspace(0, 1, max(4, int(abs(sweep) * 12))):
            ang = a0 + sweep * k
            out.append(centre + r * np.array([math.cos(ang), math.sin(ang)]))
    return np.array(out)


def _circuit(rng: random.Random, n_ctrl: tuple[int, int], wobble: float, radius: tuple[float, float]) -> np.ndarray:
    """A random polygon around an ellipse, its corners rounded with random radii (as a share of the
    track's size). Retried until the loop doesn't cross itself."""
    for _ in range(80):
        n = rng.randint(*n_ctrl)
        step = 2 * math.pi / n  # evenly spread with jitter: a star-shaped polygon never crosses itself
        angles = [i * step + rng.uniform(-0.35, 0.35) * step for i in range(n)]
        poly = np.array([(math.cos(a) * (1 + rng.uniform(-wobble, wobble)),
                          math.sin(a) * 1.25 * (1 + rng.uniform(-wobble, wobble))) for a in angles])
        pts = _resample(_fillet(poly, [rng.uniform(*radius) for _ in range(n)]))
        if not _intersects(pts):
            return pts
    return _resample(np.stack([np.cos(np.linspace(0, 2 * np.pi, 200, endpoint=False)),
                               0.8 * np.sin(np.linspace(0, 2 * np.pi, 200, endpoint=False))], 1))


def _oval(rng: random.Random) -> np.ndarray:
    """A stadium (two straights joined by half circles), sometimes a tri-oval."""
    straight, r = rng.uniform(1.2, 2.0), 1.0
    pts = []
    for t in np.linspace(0, 1, 800, endpoint=False):
        s = t * (2 * straight + 2 * math.pi * r)
        if s < straight:
            x, y = -straight / 2 + s, -r
        elif s < straight + math.pi * r:
            a = (s - straight) / r
            x, y = straight / 2 + r * math.sin(a), -r * math.cos(a)
        elif s < 2 * straight + math.pi * r:
            x, y = straight / 2 - (s - straight - math.pi * r), r
        else:
            a = (s - 2 * straight - math.pi * r) / r
            x, y = -straight / 2 - r * math.sin(a), r * math.cos(a)
        pts.append((x, y))
    pts = np.array(pts)
    return np.stack([pts[:, 1], pts[:, 0]], 1)  # stood up, to fit a portrait map


def _figure8(rng: random.Random) -> tuple[np.ndarray, tuple[float, float]]:
    w, h = rng.uniform(0.55, 0.8), 1.0
    t = np.linspace(0, 2 * np.pi, 1200, endpoint=False)
    pts = np.stack([w * np.sin(2 * t) / 2 * (1 + 0.15 * rng.uniform(-1, 1) * np.cos(t)), h * np.sin(t)], 1)
    return pts, (0.0, 0.5)  # the line crosses itself at t=0 and t=pi


LENGTHS = {"oval": (2200, 2800), "gp": (4200, 5200), "rally": (3200, 4000), "figure8": (1300, 1800),
           "endurance": (5200, 6200), "drag": (402.3, 402.3)}

PLACES = ["Kestrel", "Harbour", "Moorside", "Glass Lake", "Copper Hill", "Old Aerodrome", "Ironbridge", "Saltmarsh",
          "Ashford Vale", "Blackwater", "Highcliff", "Larkspur", "Redmoor", "Stonegate", "Wexham", "Fallow Down",
          "Northgate", "Brackenridge", "Silverdale", "Thornbury"]
SUFFIX = {"oval": ["Motor Speedway", "Superspeedway", "Speedway"], "gp": ["Circuit", "Grand Prix Circuit", "Park"],
          "rally": ["Forest Stage", "Hill Stage", "Gravel Stage"], "figure8": ["Figure 8", "Crossroads Raceway"],
          "endurance": ["Endurance Ring", "Long Circuit"], "drag": ["Dragway", "Strip"]}


def generate(kind: str, seed: int) -> Track:
    rng = random.Random(f"{kind}:{seed}")
    crossing = None
    closed = True
    if kind == "oval":
        raw = _resample(_oval(rng))
    elif kind == "gp":
        raw = _circuit(rng, (8, 12), 0.4, (0.07, 0.35))
    elif kind == "endurance":
        raw = _circuit(rng, (6, 9), 0.3, (0.08, 0.45))
    elif kind == "rally":
        raw = _circuit(rng, (14, 20), 0.42, (0.04, 0.12))
    elif kind == "figure8":
        fig, crossing = _figure8(rng)
        raw = _resample(fig)
    elif kind == "drag":
        raw = np.stack([np.full(POINTS, 0.5), np.linspace(1, 0, POINTS)], 1)  # bottom to top
        closed = False
    else:
        raise ValueError(f"unknown track kind {kind!r}")
    pts = raw if kind == "drag" else _fit(raw)
    length = rng.uniform(*LENGTHS[kind])
    name = f"{rng.choice(PLACES)} {rng.choice(SUFFIX[kind])}"
    curv = np.zeros(POINTS) if kind == "drag" else _curvature(pts, length, closed)
    track = Track(kind, name, seed, pts, length, curv, crossing, closed)
    track.n_corners = corners(track)
    if kind == "oval":
        track.curv = np.minimum(curv, 1 / 420)  # banking: the turns are taken flat out
    return track


def corners(track: Track) -> int:
    """How many corners a lap has (runs of real curvature), for the race card."""
    if not track.closed:
        return 0
    bent = track.curv > 1 / 400
    edges = np.sum(bent & ~np.roll(bent, 1))
    return int(edges)
