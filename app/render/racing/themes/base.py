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


def fit_track(pts, box: tuple[float, float, float, float]) -> np.ndarray:
    """The race's track (points in a unit box) scaled into a screen box (x0, y0, x1, y1), centred,
    keeping its shape."""
    x0, y0, x1, y1 = box
    p = np.array(pts, float)
    size = min(x1 - x0, y1 - y0)
    return np.stack([x0 + (x1 - x0 - size) / 2 + p[:, 0] * size, y0 + (y1 - y0 - size) / 2 + p[:, 1] * size], 1)


def point_at(track: np.ndarray, frac: float, closed: bool = True) -> tuple[float, float, float]:
    """(x, y, heading) at a lap fraction (along the strip, for an open track)."""
    n = len(track)
    f = (frac % 1) * n if closed else min(max(frac, 0.0), 0.9999) * (n - 1)
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
            r = self.race
            self.fmt = r["format"]
            self.dist = np.array(r["dist"])
            self.times = {int(k): v for k, v in r["times"].items()}  # race seconds
            self.vtimes = {int(k): v for k, v in r["vtimes"].items()}  # when each car finishes on screen
            self.out_at = {e["car"]: e["t"] for e in r["events"] if e["kind"] in ("blowup", "jumpstart")}
            self.wear = np.array(r["wear"]) if r.get("wear") else None
            self.pit = np.array(r["pit"], bool) if r.get("pit") else None
            self.lap_time = r["winner_time"] / max(r["laps"], 1)  # race seconds a lap, roughly

    # ---------------------------------------------------------------- per-frame race state
    def frame_of(self, t: float) -> int:
        return max(0, min(len(self.dist) - 1, int(t * FPS)))

    def laps(self, t: float) -> np.ndarray:
        return self.dist[self.frame_of(t)]

    def standings(self, t: float) -> list[dict]:
        """Running order at video time t: {car, pos, lap, gap (race seconds to the leader, or None),
        done, out, pit, wear}. Gaps are in real race seconds, whatever the playback speed."""
        k = self.frame_of(t)
        d = self.dist[k]
        laps = self.race["laps"]
        real_t = t * self.race["scale"]
        rows = []
        for j, car in enumerate(self.cars):
            no = car["no"]
            vfin = self.vtimes.get(no)
            done = vfin is not None and vfin <= t
            out = no in self.out_at and self.out_at[no] <= t
            rows.append({"car": no, "d": float(d[j]), "fin": self.times[no] if done else None, "done": done, "out": out,
                         "pit": bool(self.pit[k, j]) if self.pit is not None else False,
                         "wear": float(self.wear[k, j]) if self.wear is not None else None})
        rows.sort(key=lambda r: (r["out"], not r["done"], r["fin"] if r["done"] else 0, -r["d"]))
        lead = rows[0]
        for i, r in enumerate(rows):
            r["pos"] = i + 1
            r["lap"] = min(laps, int(r["d"]) + 1)
            if i == 0 or r["out"]:
                r["gap"] = None
            elif r["done"] and lead["done"]:
                r["gap"] = r["fin"] - lead["fin"]
            elif lead["done"]:  # still running after the winner is home: its expected finish
                r["gap"] = max(0.0, real_t + (laps - r["d"]) * self.lap_time - lead["fin"])
            else:
                r["gap"] = max(0.0, (lead["d"] - r["d"]) * self.lap_time)
        return rows

    def event_at(self, t: float, within: float = 2.0) -> dict | None:
        """The latest event in the last `within` seconds of video time."""
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
