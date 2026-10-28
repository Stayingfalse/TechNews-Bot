"""What every racing theme gets: the race data turned into positions, order and gaps per frame,
the circuit's shape, and a text helper that remembers where it wrote (for the safe-zone test).

A theme subclasses Theme and implements `draw(scene, t, dur)` for each scene name in SCENES, plus
optionally `glitch`. Everything else (timing, glitch moments, sound, encoding) is the engine's, so
a new look is one new file in this folder, registered in themes/__init__.py.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
# Text must stay inside this box: the Reels/Shorts header is above it, the caption and buttons
# below it, the like/comment buttons to its right.
SAFE = (48, 240, 936, 1440)
SCENES = ("boot", "hook", "rules", "grid", "race", "finish", "result", "table", "card", "outro")
FONTS = Path(__file__).resolve().parents[4] / "assets" / "fonts" / "racing"


@lru_cache(maxsize=64)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    files = {"black": "Inter-Black.otf", "bold": "Inter-ExtraBold.otf", "semi": "Inter-SemiBold.otf",
             "mono": "JetBrainsMono-SemiBold.ttf", "mono-bold": "JetBrainsMono-ExtraBold.ttf"}
    return ImageFont.truetype(str(FONTS / files[name]), size)


def circuit(seed: int, cx: float, cy: float, rx: float, ry: float, n: int = 720) -> np.ndarray:
    """A closed, smooth loop bent by the seed; points are spaced evenly by distance along it, so
    a car's lap fraction maps straight to a point."""
    rng = np.random.default_rng(seed)
    k = [(2, rng.uniform(.06, .11), rng.uniform(0, 6)), (3, rng.uniform(.05, .1), rng.uniform(0, 6)),
         (5, rng.uniform(.02, .045), rng.uniform(0, 6))]
    t = np.linspace(0, 2 * np.pi, 4000, endpoint=False)
    r = 1 + sum(a * np.sin(f * t + p) for f, a, p in k)
    pts = np.stack([cx + rx * r * np.cos(t), cy + ry * r * np.sin(t)], 1)
    seg = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    even = np.linspace(0, s[-1], n, endpoint=False)
    closed = np.vstack([pts, pts[:1]])
    return np.stack([np.interp(even, s, closed[:, 0]), np.interp(even, s, closed[:, 1])], 1)


def point_at(track: np.ndarray, frac: float) -> tuple[float, float, float]:
    """(x, y, heading) at a lap fraction."""
    n = len(track)
    f = (frac % 1) * n
    i = int(f) % n
    a, b = track[i], track[(i + 1) % n]
    u = f - int(f)
    x, y = a + (b - a) * u
    c = track[(i + 4) % n]
    return float(x), float(y), math.atan2(c[1] - a[1], c[0] - a[0])


class Theme:
    name = "base"
    sound: dict = {}  # overrides for app/render/racing/sound.py, e.g. {"bed": "pulse"}

    def __init__(self, spec: dict, record: bool = False):
        self.spec = spec
        self.cars = spec["cars"]
        self.race = spec.get("race")
        self.record = record
        self.boxes: list[tuple[str, tuple[int, int, int, int]]] = []  # (scene, bbox) when recording
        self.scene = ""
        if self.race:
            self.dist = np.array(self.race["dist"])
            self.times = {int(k): v for k, v in self.race["times"].items()}
            self.out_at = {e["car"]: e["t"] for e in self.race["events"] if e["kind"] == "blowup"}

    # ---------------------------------------------------------------- per-frame race state
    def frame_of(self, t: float) -> int:
        return max(0, min(len(self.dist) - 1, int(t * FPS)))

    def laps(self, t: float) -> np.ndarray:
        return self.dist[self.frame_of(t)]

    def standings(self, t: float) -> list[dict]:
        """Running order at race time t: {car, pos, lap, gap (s to the leader, or None), done, out}."""
        d = self.laps(t)
        laps = self.race["laps"]
        rows = []
        for j, car in enumerate(self.cars):
            no = car["no"]
            fin = self.times.get(no)
            done = fin is not None and fin <= t
            out = no in self.out_at and self.out_at[no] <= t
            rows.append({"car": no, "d": float(d[j]), "fin": fin if done else None, "done": done, "out": out})
        rows.sort(key=lambda r: (r["out"], not r["done"], r["fin"] if r["done"] else 0, -r["d"]))
        lead = rows[0]
        speed = laps / max(self.race["winner_time"], 1)
        for i, r in enumerate(rows):
            r["pos"] = i + 1
            r["lap"] = min(laps, int(r["d"]) + 1)
            if i == 0 or r["out"]:
                r["gap"] = None
            elif r["done"] and lead["done"]:
                r["gap"] = r["fin"] - lead["fin"]
            elif lead["done"]:  # still running after the winner is home: its expected finish
                r["gap"] = max(0.0, t + (laps - r["d"]) / speed - lead["fin"])
            else:
                r["gap"] = max(0.0, (lead["d"] - r["d"]) / speed)
        return rows

    def event_at(self, t: float, within: float = 2.0) -> dict | None:
        """The latest spin, turbo or blow-up in the last `within` seconds of race time."""
        ev = [e for e in self.race["events"] if e["t"] <= t < e["t"] + within]
        return ev[-1] if ev else None

    def car(self, no: int) -> dict:
        return self.cars[no - 1]

    # ---------------------------------------------------------------- drawing helpers
    def text(self, d: ImageDraw.ImageDraw, xy, s: str, fnt, fill, anchor: str = "la", record: bool = True) -> tuple:
        d.text(xy, s, font=fnt, fill=fill, anchor=anchor)
        box = d.textbbox(xy, s, font=fnt, anchor=anchor)
        if self.record and record and s.strip():
            self.boxes.append((self.scene, tuple(int(v) for v in box)))
        return box

    def fit(self, s: str, name: str, size: int, width: int) -> ImageFont.FreeTypeFont:
        """The largest size up to `size` at which `s` fits in `width`."""
        while size > 20 and font(name, size).getlength(s) > width:
            size -= 2
        return font(name, size)

    # ---------------------------------------------------------------- the theme's job
    def draw(self, scene: str, t: float, dur: float) -> Image.Image:
        raise NotImplementedError

    def glitch(self, img: Image.Image, amount: float, seed: int) -> Image.Image:
        return img

    def frame(self, scene: str, t: float, dur: float) -> Image.Image:
        self.scene = scene
        return self.draw(scene, t, dur)
