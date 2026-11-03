"""The colony on the far side of a moon, side-on: sky with a ringed planet above, the surface and
its buildings in the middle, the colony's tunnels below. `draw(spec, t)` gives one frame; the spec
says who lives there, what's built, who arrives, where the camera looks and what the captions say.

Three layers: the sky (screen-fixed, a little parallax), the ridges (parallax), and the world
(WW wide, panned by the camera). UI is drawn on the screen last."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from . import pixfont
from .art import BAYER, CAPSULE, CRATE, H, P, SAFE, SKINS, SUITS, W, Canvas, barrel_elder, settler

WW = 260  # world width
GROUND = 176  # the surface line
POD_X = 32
DOME = (102, 22)  # habitat dome: centre x, radius
GREEN = (166, 19)  # greenhouse
BEACON_X = 228
OUTSIDE_MAX = 16  # settlers drawn outside; the rest are lit windows and heads in the dome


def _rng(*key) -> np.random.Generator:
    return np.random.default_rng(abs(hash(("colony",) + key)) % (2 ** 32))


def ground_y(x: float) -> int:
    return GROUND + int(round(1.2 * math.sin(x * 0.07) + 0.8 * math.sin(x * 0.19 + 1.3)))


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


# ------------------------------------------------------------------ still layers (cached)


@lru_cache(maxsize=2)
def _sky(seed: int):
    sw = W + 40
    c = Canvas(sw, H)
    bands = ["sky0", "sky1", "sky2", "sky3", "sky4", "sky5", "sky6", "sky7", "sky8"]
    bottom = GROUND - 12
    for y in range(H):
        f = np.clip(y / bottom, 0, 0.999) ** 1.35 * (len(bands) - 1)
        i = int(f)
        use_hi = np.tile(BAYER[y % 4], sw // 4 + 1)[:sw] < (f - i)
        c.rgb[y] = np.where(use_hi[:, None], P[bands[min(i + 1, len(bands) - 1)]], P[bands[i]])
    cx, cy, r = 128, 122, 25
    yy, xx = np.mgrid[0:H, 0:sw]
    tilt = (xx - cx) * 0.2
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    body = d <= r
    ring = np.abs(((xx - cx) / 42.0) ** 2 + ((yy - cy + tilt) / 6.0) ** 2 - 1) < 0.2
    c.mask(ring & ~body & (yy < cy - tilt), 0, 0, P["ring"] * 0.8, world=False)
    band = ((yy - cy + tilt) / r * 5 + 10).astype(int) % 4
    for i, k in enumerate(["planet0", "planet1", "planet2", "planet3"]):
        c.mask(body & (band == i), 0, 0, P[k], world=False)
    shade = (xx - cx + (yy - cy) * 0.3) / r
    bg = np.tile(BAYER, (H // 4 + 1, sw // 4 + 1))[:H, :sw]
    for lvl, a in ((0.15, 0.55), (0.5, 0.95)):
        c.mask(body & (shade > lvl) & (bg < a), 0, 0, P["sky1"], world=False)
    c.mask(ring & (yy >= cy - tilt), 0, 0, P["ring"], world=False)
    glow, gx, gy = c.disc(26, GROUND - 22, 11)  # the far sun, setting
    c.dither_mask(glow, gx, gy, P["sky8"], 0.5, world=False)
    m, x0, y0 = c.disc(26, GROUND - 22, 4)
    c.mask(m, x0, y0, P["sun"], world=False)
    rng = np.random.default_rng(seed)
    stars = [(int(rng.integers(0, sw)), int(rng.integers(0, GROUND - 50)), float(rng.random())) for _ in range(90)]
    return c, stars


@lru_cache(maxsize=2)
def _ridges():
    out = []
    for k, base, amp, freq, ph, par in (("ridge0", GROUND - 30, 10, 0.045, 0.4, 0.3),
                                        ("ridge1", GROUND - 16, 7, 0.08, 2.0, 0.55),
                                        ("ridge2", GROUND - 6, 4, 0.14, 4.1, 0.8)):
        c = Canvas(WW, H)
        for x in range(WW):
            top = int(base + amp * math.sin(x * freq + ph) + amp * 0.5 * math.sin(x * freq * 2.7 + ph * 3))
            c.rect(x, top, 1, GROUND + 8 - top, P[k])
        out.append((c, par))
    return out


@lru_cache(maxsize=2)
def _ground(seed: int) -> Canvas:
    c = Canvas(WW, H)
    rng = np.random.default_rng(seed)
    strata = ["soil0", "soil1", "soil2", "soil3", "soil4"]
    for x in range(WW):
        gy = ground_y(x)
        c.rect(x, gy, 1, H - gy, P["soil0"])
        for i, k in enumerate(strata):
            yb = gy + 5 + i * 17 + int(2 * math.sin(x * 0.06 + i))
            c.rect(x, yb, 1, H - yb, P[k])
        c.rect(x, gy, 1, 2, P["grass1"])
        c.px(x, gy, P["grass0"])
    for _ in range(50):
        x, y = rng.integers(0, WW), rng.integers(GROUND + 8, H)
        c.rect(x, y, rng.integers(2, 4), 1, P["rock"])
    # under the colony: the pod's shaft, the store room, a corridor to the dome's cellar
    c.rect(POD_X - 2, GROUND + 1, 5, 24, P["tunnel"])
    for i in range(0, 24, 3):
        c.rect(POD_X - 2, GROUND + 2 + i, 5, 1, P["metal3"])
    c.rect(POD_X - 14, GROUND + 22, 44, 14, P["tunnel"])  # store room
    c.rect(POD_X - 14, GROUND + 36, 44, 1, P["metal3"])
    for x, y in ((POD_X - 11, 31), (POD_X - 5, 31), (POD_X - 8, 26), (POD_X + 16, 31), (POD_X + 22, 31)):
        c.sprite(CRATE, x, GROUND + y)
    c.rect(POD_X + 30, GROUND + 29, DOME[0] - POD_X - 30, 7, P["tunnel"])  # corridor
    c.rect(DOME[0] - 14, GROUND + 18, 30, 18, P["tunnel"])  # cellar under the dome
    c.rect(DOME[0] - 14, GROUND + 36, 30, 1, P["metal3"])
    for i, (x, hgt) in enumerate(((DOME[0] - 11, 5), (DOME[0] - 7, 7), (DOME[0] - 3, 4), (DOME[0] + 2, 6),
                                  (DOME[0] + 6, 5), (DOME[0] + 10, 7))):  # mushroom beds
        c.rect(x, GROUND + 36 - hgt, 1, hgt, P["soil0"])
        c.rect(x - 1, GROUND + 36 - hgt - 1, 3, 2, P["crys1"] if i % 2 else P["crys0"])
    # a fossil, for later
    for dx, dy in ((0, 0), (2, -1), (4, -1), (6, 0), (8, 1), (3, 1), (5, 2)):
        c.px(200 + dx, GROUND + 52 + dy, P["rock"] * 1.4)
    for _ in range(34):  # glowing crystals on the surface
        x = int(rng.integers(3, WW - 3))
        if abs(x - POD_X) < 20 or abs(x - DOME[0]) < DOME[1] + 3 or abs(x - GREEN[0]) < GREEN[1] + 3 or abs(x - BEACON_X) < 6:
            continue
        k = ["crys0", "crys1", "crys2"][int(rng.integers(0, 3))]
        hgt = int(rng.integers(2, 6))
        gy = ground_y(x)
        c.rect(x, gy - hgt, 1, hgt, P[k])
        if hgt > 3:
            c.px(x - 1, gy - hgt + 1, P[k])
            c.px(x + 1, gy - hgt + 2, P[k])
    return c


# ------------------------------------------------------------------ buildings


def draw_pod(c: Canvas, t: float):
    x, gy = POD_X, GROUND
    c.rect(x - 13, gy - 19, 26, 17, P["metal1"])
    c.rect(x - 11, gy - 22, 22, 3, P["metal0"])
    c.rect(x - 8, gy - 25, 16, 3, P["metal0"])
    c.rect(x - 13, gy - 19, 26, 1, P["metal0"])
    c.rect(x - 13, gy - 3, 26, 2, P["metal2"])
    for fx in (x - 16, x + 13):
        c.rect(fx, gy - 6, 3, 6, P["metal3"])
    m, x0, y0 = c.disc(x - 5, gy - 12, 3)
    c.mask(m, x0, y0, P["metal3"])
    m, x0, y0 = c.disc(x - 5, gy - 12, 2)
    c.mask(m, x0, y0, P["warm0"])
    c.rect(x + 2, gy - 15, 7, 12, P["warm1"])  # open door
    c.rect(x + 9, gy - 2, 7, 1, P["metal2"])  # ramp
    c.rect(x - 1, gy - 34, 1, 9, P["metal2"])  # antenna
    if int(t * 1.5) % 2 == 0:
        c.px(x - 1, gy - 35, P["crys1"], world=False)


def draw_dome(c: Canvas, cx: int, r: int, fill: float = 1.0, inside: str = "home", t: float = 0.0, heads: int = 0):
    """A glass dome; `fill` < 1 is one still being built (frame first, then panels)."""
    gy = GROUND
    yy, xx = np.mgrid[-r:1, -r:r + 1]
    d = np.sqrt(xx ** 2 + yy ** 2)
    shell = d <= r
    edge = shell & (d > r - 1.2)
    ang = np.degrees(np.arctan2(-yy, xx))  # 0 right … 180 left
    struts = shell & ((np.abs((ang % 36) - 18) > 16.6) | (np.abs(((r - d) % 7) - 3.5) > 3.0))
    x0, y0 = cx - r, gy - r
    if fill > 0:
        panels = shell & (ang <= 180 * min(1, fill) + 0.01)
        if inside == "green":
            c.mask(panels & (yy > -r * 0.4), x0, y0, P["grass2"])
            for i in range(-r + 3, r - 2, 4):
                hgt = 3 + (i * 7) % 5
                if panels[r - 1, i + r]:
                    c.rect(cx + i, gy - hgt, 1, hgt, P["crys2"] * 0.85)
                    c.px(cx + i - 1, gy - hgt + 1, P["crys2"])
                    c.px(cx + i + 1, gy - hgt, P["crys2"])
        else:
            c.mask(panels, x0, y0, P["warm1"] * 0.6)
            c.rect(cx - r + 4, gy - 5, r * 2 - 8, 1, P["wood1"])
            rng = _rng("heads", cx)
            for i in range(heads):  # people inside, as heads in helmets over the table
                hx = cx - r + 6 + (i * 37) % (2 * r - 11)
                c.rect(hx, gy - 9 - (i % 2), 3, 3, P["rim"])
                c.px(hx + 1, gy - 8 - (i % 2), P["warm0"])
        c.dither_mask(panels, x0, y0, P["glass"], 0.4)
        hi = panels & (xx < -r * 0.35) & (yy < -r * 0.45) & (d > r - 4) & (d < r - 2.5)
        c.mask(hi, x0, y0, P["hi"])
    frame = edge | struts
    if fill < 1:
        frame = frame & (ang <= 180 * min(1, fill + 0.3))
    c.mask(frame, x0, y0, P["rim"] if fill >= 1 else P["metal1"])
    c.rect(cx - r, gy - 1, 2 * r + 1, 2, P["metal2"])
    if fill < 1:  # scaffold and welding sparks
        for sx in range(cx - r, cx + r + 1, 8):
            c.rect(sx, gy - r - 3, 1, r + 3, P["wood1"])
        c.rect(cx - r, gy - r - 3, 2 * r + 1, 1, P["wood1"])
        a = math.radians(180 * min(1, fill))
        wx, wy = cx + r * math.cos(a), gy - r * math.sin(a)
        rng = _rng("spark", int(t * 12))
        for _ in range(4):
            c.px(wx + rng.integers(-3, 4), wy + rng.integers(-3, 3), P["warm0"], world=False)
        return (wx, wy)
    return None


def draw_heater(c: Canvas, x: int, t: float):
    gy = ground_y(x)
    c.rect(x - 1, gy - 4, 3, 4, P["metal3"])
    c.rect(x - 3, gy - 6, 7, 2, P["metal2"])
    flick = 0.5 + 0.5 * math.sin(t * 17) * math.sin(t * 5.3)
    c.rect(x - 2, gy - 6, 5, 1, P["coil"] if flick > 0.3 else P["warm2"], world=False)


def draw_beacon_ghost(c: Canvas, t: float):
    x, gy = BEACON_X, ground_y(BEACON_X)
    on = int(t * 4) % 2 == 0
    for y in range(gy - 40, gy, 2):
        if on or y % 4 == 0:
            c.px(x - 3, y, P["gold"], world=False)
            c.px(x + 3, y, P["gold"], world=False)
    for xx in range(x - 3, x + 4, 2):
        c.px(xx, gy - 40, P["gold"], world=False)
    if on:
        c.px(x, gy - 44, P["gold"], world=False)


# ------------------------------------------------------------------ people


def pingpong(v: float, lo: float, hi: float) -> tuple[float, bool]:
    span = hi - lo
    p = v % (2 * span)
    return (lo + p, False) if p < span else (hi - (p - span), True)


def crowd(spec: dict) -> list[dict]:
    """Everyone already living there, with a deterministic wander."""
    rng = _rng("crowd", spec.get("seed", 1))
    out = []
    for s in spec["settlers"]:
        lo = float(rng.uniform(10, WW - 60))
        out.append({**s, "suit": s.get("suit") or SUITS[int(rng.integers(0, len(SUITS)))],
                    "skin": s.get("skin") or SKINS[int(rng.integers(0, len(SKINS)))],
                    "lo": lo, "hi": lo + float(rng.uniform(16, 50)), "speed": float(rng.uniform(3, 8)),
                    "phase": float(s.get("phase", rng.uniform(0, 100))), "pause": float(rng.uniform(0, 1))})
    return out


def draw_person(c: Canvas, p: dict, x: float, t: float, walking: bool, flip: bool, carry: bool = False) -> float:
    gy = ground_y(x)
    if p.get("look") == "barrel":
        spr = barrel_elder()
        hop = round(abs(math.sin(t * 6)) * 2) if walking else 0
        c.sprite(spr, round(x) - 4, gy - spr.h - hop, flip=flip)
        return gy - spr.h - hop
    spr = settler(int(t * 6) if walking else 0, p["suit"], p["skin"])
    c.sprite(spr, round(x) - 3, gy - spr.h, flip=flip)
    if carry:
        c.sprite(CRATE, round(x) - 2, gy - spr.h - 5)
        return gy - spr.h - 5
    return gy - spr.h


# ------------------------------------------------------------------ UI (screen coordinates)


def fit_scale(text: str, max_w: int = SAFE[2] - SAFE[0]) -> int:
    return 2 if pixfont.width(text, 2) <= max_w else 1


def caption(c: Canvas, lines: list[str], t: float, t0: float):
    k = min(1.0, (t - t0) / 0.18)
    scale = min(fit_scale(l.replace("*", "")) for l in lines)
    lh = 9 * scale
    y = 238 - (len(lines) - 1) * lh + int((1 - k) * 4)
    for i, line in enumerate(lines):
        words = line.split(" ")
        text = " ".join(w.strip("*") for w in words)
        x = (SAFE[0] + SAFE[2]) // 2 - pixfont.width(text, scale) // 2
        for w in words:
            col = P["gold"] if w.startswith("*") else P["ui"]
            w = w.strip("*")
            c.text(w, x, y + i * lh, col, scale=scale)
            x += pixfont.width(w + " ", scale)


def title(c: Canvas, count: int, bump: float):
    mid = (SAFE[0] + SAFE[2]) // 2
    c.text("FARSIDE", mid, 40, P["gold"], scale=3, center=True)
    c.text(f"{count} LIVE HERE", mid, 66 - int(bump * 2), P["ui"], scale=2, center=True)


class Tags:
    """Name tags and speech bubbles, moved up when they'd overlap each other."""

    def __init__(self, c: Canvas):
        self.c, self.boxes = c, []

    def _place(self, x0, y0, w, h):
        def free(x, y):
            return not any(x < bx + bw + 1 and bx < x + w + 1 and y < by + bh + 1 and by < y + h + 1
                           for bx, by, bw, bh in self.boxes)

        def clamp(x):
            return int(min(max(x, SAFE[0]), SAFE[2] - w))

        best = (clamp(x0), y0)
        for dy in range(0, 4 * (h + 1), h + 1):  # sideways first, then up a row
            for dx in (0, w // 2 + 2, -(w // 2 + 2), w + 2, -(w + 2)):
                x, y = clamp(x0 + dx), y0 - dy
                if free(x, y):
                    best = (x, y)
                    break
            else:
                continue
            break
        self.boxes.append((best[0], best[1], w, h))
        return best

    def tag(self, name: str, x: float, y: float, col=None):
        w = pixfont.width(name) + 4
        x0, y0 = self._place(x - w // 2, y - 10, w, 9)
        self.c.rect(x0, y0, w, 9, P["ink"], world=False)
        self.c.text(name, x0 + 2, y0 + 1, P["ui"] if col is None else col, outline=False)

    def bubble(self, text: str, x: float, y: float):
        lines = text.split("|")
        w = max(pixfont.width(l) for l in lines) + 6
        h = len(lines) * 9 + 3
        x0, y0 = self._place(x - w // 2, y - h - 4, w, h)
        c = self.c
        c.rect(x0 - 1, y0 - 1, w + 2, h + 2, P["ink"], world=False)
        c.rect(x0, y0, w, h, P["ui"], world=False)
        if y0 + h + 4 >= y - 4:
            c.rect(int(x) - 1, y0 + h, 3, 2, P["ui"], world=False)
            c.px(int(x), y0 + h + 2, P["ui"], world=False)
        for i, l in enumerate(lines):
            c.text(l, x0 + 3, y0 + 2 + i * 9, P["ink"], outline=False)


def progress(c: Canvas, label: str, frac: float, right: str):
    x0, y0, w = SAFE[0] + 6, 86, SAFE[2] - SAFE[0] - 12
    c.text(label, x0, y0, P["ui"])
    c.text(right, x0 + w - pixfont.width(right), y0, P["gold"])
    c.rect(x0 - 1, y0 + 9, w + 2, 7, P["ink"], world=False)
    c.rect(x0, y0 + 10, w, 5, P["barbg"], world=False)
    c.rect(x0, y0 + 10, int(w * max(0, min(1, frac))), 5, P["bar"], world=False)
    for i in range(0, int(w * frac), 3):
        c.px(x0 + i, y0 + 10, P["ui"], world=False)


# ------------------------------------------------------------------ the frame


def camera(spec: dict, t: float) -> int:
    keys = spec.get("camera", [(0, 0)])
    if t <= keys[0][0]:
        return int(keys[0][1])
    for (ta, xa), (tb, xb) in zip(keys, keys[1:]):
        if t <= tb:
            return int(round(xa + (xb - xa) * _ease((t - ta) / max(0.01, tb - ta))))
    return int(keys[-1][1])


def draw(spec: dict, t: float) -> Canvas:
    seed = spec.get("seed", 1)
    cam = max(0, min(WW - W, camera(spec, t)))
    sky, stars = _sky(seed)
    scr = Canvas()
    sox = int(cam * 0.15)
    scr.rgb[:] = sky.rgb[:, sox:sox + W]
    for (sx, sy, ph) in stars:
        x = sx - sox
        if 0 <= x < W and 0.5 + 0.5 * math.sin(t * (1.5 + ph * 3) + ph * 40) > 0.35:
            scr.px(x, sy, P["star"] if ph > 0.3 else P["star2"], world=False)
    for layer, par in _ridges():
        scr.paste(layer, int(cam * par))

    wc = Canvas(WW, H)
    g = _ground(seed)
    wc.rgb[:], wc.world[:], wc.alpha[:] = g.rgb, g.world, g.alpha
    lights = [(POD_X - 5, GROUND - 12, 20, 0.55), (POD_X + 5, GROUND - 9, 24, 0.5), (POD_X + 4, GROUND + 30, 34, 0.6),
              (DOME[0], GROUND + 28, 24, 0.45)]
    draw_pod(wc, t)
    people = crowd(spec)
    outside, inside = people[:OUTSIDE_MAX], people[OUTSIDE_MAX:]
    sparks = None
    for b in spec.get("buildings", []):
        if b["kind"] == "dome":
            draw_dome(wc, *DOME, fill=1.0, inside="home", t=t, heads=min(10, len(inside)))
            lights.append((DOME[0], GROUND - 8, 34, 0.7))
        elif b["kind"] == "greenhouse":
            f0, f1, ta, tb = b.get("from", 1.0), b.get("to", 1.0), b.get("t0", 0), b.get("t1", 1)
            fill = f0 + (f1 - f0) * _ease((t - ta) / max(0.01, tb - ta))
            sparks = draw_dome(wc, *GREEN, fill=fill, inside="green", t=t)
            lights.append((GREEN[0], GROUND - 6, 26, 0.3 + 0.3 * fill))
    if sparks and spec.get("building_now", (0, 0))[0] <= t <= spec.get("building_now", (0, 0))[1]:
        lights.append((sparks[0], sparks[1], 12, 0.6))
    for hx in spec.get("heaters", []):
        draw_heater(wc, hx, t)
        lights.append((hx, GROUND - 6, 18, 0.75 + 0.08 * math.sin(t * 13)))

    heads: dict[str, tuple[float, float]] = {}
    for p in outside:
        if p.get("job") == "carry":
            x, back = pingpong(p["phase"] + t * 14, POD_X + 16, GREEN[0] - GREEN[1] - 4)
            top = draw_person(wc, p, x, t, True, flip=back, carry=not back)
        elif p.get("job") == "sit":
            x = p["x"]
            top = draw_person(wc, p, x, t, False, flip=p.get("flip", False))
        else:
            v = p["phase"] + t * p["speed"]
            walking = math.sin(v * 0.13 + p["pause"] * 6) > -0.4
            x, back = pingpong(v if walking else p["phase"], p["lo"], p["hi"])
            top = draw_person(wc, p, x, t, walking, flip=back)
        heads[p["name"]] = (x, top)

    count, bump = spec["count"], 0.0
    for a in spec.get("arrivals", []):
        tl, x = a["land"], a["x"]
        gy = ground_y(x)
        if t < tl - 1.3:
            continue
        if t < tl:  # falling, with a trail and a flame
            k = (t - (tl - 1.3)) / 1.3
            y = -16 + (gy - CAPSULE.h + 16) * (k ** 1.7)
            for i in range(1, 12):
                wc.px(x + 2 - i * 0.5, y - i * 2, P["warm1"] if i < 4 else P["sky7"], world=False)
            wc.sprite(CAPSULE, x - 4, y)
            wc.rect(x - 1, y + CAPSULE.h, 2, 2, P["warm0"], world=False)
            lights.append((x, y + 5, 18, 0.7))
            continue
        wc.sprite(CAPSULE, x - 4, gy - CAPSULE.h)
        lights.append((x, gy - 4, 12, 0.4))
        dt = t - tl
        if dt < 0.5:
            r = int(2 + dt * 18)
            for i in range(-r, r + 1, 2):
                wc.px(x + i, gy - 1 - abs(i) // 5, P["metal1"], world=False)
        count += 1
        bump = max(bump, max(0.0, 1 - dt * 3))
        if dt > 0.4:
            walk = a.get("walk", 16)
            walk_x = x + min(abs(walk), (dt - 0.4) * 10) * (1 if walk > 0 else -1)
            moving = (dt - 0.4) * 10 < abs(walk)
            p = {"name": a["name"], "look": a.get("look"), "suit": a.get("suit", SUITS[1]), "skin": a.get("skin", SKINS[1])}
            heads[a["name"]] = (walk_x, draw_person(wc, p, walk_x, t, moving, flip=walk < 0))
    if spec.get("beacon_ghost") and spec["beacon_ghost"][0] <= t <= spec["beacon_ghost"][1]:
        draw_beacon_ghost(wc, t)

    scr.paste(wc, cam)
    scr.light([(lx - cam, ly, r, s) for (lx, ly, r, s) in lights], spec.get("ambient", 0.6))

    tags = Tags(scr)
    for b in spec.get("bubbles", []):
        if b["t0"] <= t <= b["t1"] and b["who"] in heads:
            hx, hy = heads[b["who"]]
            tags.bubble(b["text"], hx - cam, hy - 1)
    for a in spec.get("arrivals", []):
        if a["name"] in heads and 0.4 < t - a["land"] < 4.5:
            hx, hy = heads[a["name"]]
            tags.tag("@" + a["name"], hx - cam, hy - 1, P["gold"])
    for name, (t0, t1) in spec.get("tags", {}).items():
        if t0 <= t <= t1 and name in heads:
            hx, hy = heads[name]
            tags.tag(name if name.isupper() else "@" + name, hx - cam, hy - 1)
    title(scr, count, bump)
    for pb in spec.get("progress", []):
        if pb["t0"] <= t <= pb["t1"]:
            k = _ease((t - pb["t0"] - 0.3) / max(0.01, pb.get("fill_s", 3.0)))
            frac = pb["from"] + (pb["to"] - pb["from"]) * k
            progress(scr, pb["label"], frac, pb["right"].replace("{pct}", f"{int(round(frac * 100))}%"))
    for cap in spec.get("captions", []):
        if cap["t0"] <= t <= cap["t1"]:
            caption(scr, cap["lines"], t, cap["t0"])
    return scr
