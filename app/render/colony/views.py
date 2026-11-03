"""The colony's other three views, in the same palette, font and sprites as the side-on scene:

- top-down: the colony at scale, a tile map with domes, roads, farms and crowds
- inside: a cut-away room, drawn at twice the pixel size (a close-up), where personal scenes play
- planet: the whole moon turning, every settler a light on the night side

Each `draw_*(spec, t)` returns a screen Canvas (180×320, ×6 on output)."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from . import pixfont
from . import kit
from .art import BAYER, CRATE, H, P, SAFE, SKINS, SUITS, W, Canvas, hexc
from .scene import Tags, caption, progress, title


def _rng(*key) -> np.random.Generator:
    return np.random.default_rng(abs(hash(("colony-views",) + key)) % (2 ** 32))


def _bayer(h, w, oy=0, ox=0):
    return BAYER[(np.arange(h) + oy) % 4][:, (np.arange(w) + ox) % 4]


def _noise(xx, yy, seed=0):
    s = 0.0
    for i, (f, a) in enumerate(((0.045, 1.0), (0.11, 0.5), (0.23, 0.25))):
        s = s + a * np.sin(xx * f + seed * 1.7 + i) * np.cos(yy * f * 1.13 - seed + i * 2.1)
    return s / 1.75


# ------------------------------------------------------------------ top-down

TD_W, TD_H = 360, 420  # the map; the camera shows 180×320 of it


def _road_pts():
    return [[(30, 210), (120, 210), (180, 150), (270, 150), (330, 120)],
            [(120, 210), (150, 300), (250, 330)],
            [(180, 150), (175, 60)],
            [(120, 210), (60, 300)]]


DOMES_TD = [(120, 180, 15, "home"), (88, 232, 12, "home"), (205, 125, 16, "home"), (250, 175, 12, "home"),
            (150, 270, 13, "home"), (290, 110, 10, "home"), (60, 160, 10, "home"), (215, 330, 12, "work")]
FARMS_TD = [(195, 205, 46, 22), (205, 232, 40, 18), (40, 255, 30, 20), (260, 260, 44, 26)]
PAD_TD = (300, 205, 16)


def _seg_points(pts, step=1.0):
    out = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(x1 - x0, y1 - y0) / step))
        out += [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n)]
    return out


@lru_cache(maxsize=2)
def _td_map(seed: int) -> Canvas:
    c = Canvas(TD_W, TD_H)
    yy, xx = np.mgrid[0:TD_H, 0:TD_W].astype(np.float32)
    n = _noise(xx * 0.6, yy * 0.6, seed) + 0.12 * _bayer(TD_H, TD_W)
    for lvl, k in ((-9, "grass2"), (-0.15, "grass1"), (0.5, "grass0")):
        c.mask(n > lvl, 0, 0, P[k] * 0.92)
    rng = np.random.default_rng(seed)
    for _ in range(9):  # craters
        cx, cy, r = int(rng.integers(0, TD_W)), int(rng.integers(0, TD_H)), int(rng.integers(6, 18))
        d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        c.mask((d < r) & (d > r - 2) & (yy < cy), 0, 0, P["grass0"] * 1.15)
        c.mask((d < r) & (d > r - 2) & (yy >= cy), 0, 0, P["soil1"])
        c.mask(d < r - 2, 0, 0, P["soil0"])
    for _ in range(70):  # crystal clusters
        x, y = int(rng.integers(0, TD_W)), int(rng.integers(0, TD_H))
        k = ["crys0", "crys1", "crys2"][int(rng.integers(0, 3))]
        for dx, dy in ((0, 0), (1, -1), (-1, 0), (0, 1)):
            if rng.random() < 0.8:
                c.px(x + dx, y + dy, P[k])
    for pts in _road_pts():  # roads
        for (x, y) in _seg_points(pts, 0.5):
            c.rect(x - 2, y - 2, 5, 5, P["soil1"])
        for (x, y) in _seg_points(pts, 0.5):
            c.rect(x - 1, y - 1, 3, 3, P["soil0"] * 1.25)
    for (x, y, w, h) in FARMS_TD:  # greenhouse rows
        c.rect(x, y, w, h, P["metal3"])
        for i in range(y + 1, y + h - 1, 3):
            c.rect(x + 1, i, w - 2, 2, P["crys2"] * 0.7)
            for j in range(x + 2, x + w - 2, 4):
                c.px(j, i, P["crys2"])
        c.dither_mask(np.ones((h, w), bool), x, y, P["glass"], 0.3)
    px, py, pr = PAD_TD  # landing pad
    d = np.sqrt((xx - px) ** 2 + (yy - py) ** 2)
    c.mask(d < pr, 0, 0, P["metal2"])
    c.mask((d < pr - 2) & (d > pr - 3.2), 0, 0, P["gold"])
    c.rect(px - 4, py - 1, 9, 3, P["metal1"])
    c.rect(px - 1, py - 4, 3, 9, P["metal1"])
    return c


def _dome_td(c: Canvas, cx, cy, r, kind):
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    d = np.sqrt(xx ** 2 + yy ** 2)
    disc = d <= r
    c.mask(disc, cx - r, cy - r, P["metal3"])
    c.mask(d <= r - 1, cx - r, cy - r, P["warm1"] * 0.6 if kind == "home" else P["metal2"])
    if kind == "home":  # furniture seen through the glass
        rng = _rng("td-dome", cx, cy)
        for _ in range(r // 2):
            a, rr = rng.uniform(0, 6.28), rng.uniform(0, r - 4)
            c.rect(cx + rr * math.cos(a), cy + rr * math.sin(a), 2, 2, P["wood1"])
    ang = np.degrees(np.arctan2(yy, xx))
    struts = disc & ((np.abs((ang % 45) - 22.5) > 21.2) | (np.abs(d - r * 0.55) < 0.5))
    c.dither_mask(d <= r - 1, cx - r, cy - r, P["glass"], 0.45)
    c.mask(struts, cx - r, cy - r, P["rim"] * 0.75)
    c.mask(disc & (d > r - 1), cx - r, cy - r, P["rim"])
    hi = disc & (xx < 0) & (yy < 0) & (np.abs(d - r * 0.75) < 0.7) & (ang < -110) & (ang > -160)
    c.mask(hi, cx - r, cy - r, P["hi"])


def _walker_td(c: Canvas, x, y, suit, t, phase):
    step = int((t * 6 + phase) % 2)
    c.rect(x, y, 2, 1, P["rim"])
    c.rect(x, y + 1, 2, 2, suit)
    c.px(x - 1 + 3 * step, y + 2, suit * 0.7)


def draw_topdown(spec: dict, t: float) -> Canvas:
    seed = spec.get("seed", 7)
    cam = spec.get("camera", [(0, (90, 60))])
    (ta, (ax, ay)), (tb, (bx, by)) = (cam[0], cam[-1]) if len(cam) > 1 else (cam[0], cam[0])
    k = max(0.0, min(1.0, (t - ta) / max(0.01, tb - ta)))
    k = k * k * (3 - 2 * k)
    ox, oy = int(ax + (bx - ax) * k), int(ay + (by - ay) * k)
    m = _td_map(seed)
    wc = Canvas(TD_W, TD_H)
    wc.rgb[:], wc.world[:], wc.alpha[:] = m.rgb, m.world, m.alpha
    lights = []
    for (cx, cy, r, kind) in DOMES_TD:
        _dome_td(wc, cx, cy, r, kind)
        lights.append((cx, cy, r * 2.2, 0.55))
    for pts in _road_pts():  # lamps along the roads
        for i, (x, y) in enumerate(_seg_points(pts, 22)):
            wc.px(x + 3, y + 3, P["warm0"], world=False)
            lights.append((x + 3, y + 3, 10, 0.35))
    # the crowd: walkers on the roads, the rest as lit windows
    rng = _rng("td-crowd", seed)
    roads = [_seg_points(p, 1.0) for p in _road_pts()]
    named = {}
    for i in range(spec.get("walkers", 140)):
        road = roads[i % len(roads)]
        v = (rng.uniform(0, len(road)) + t * rng.uniform(3, 9) * (1 if i % 2 else -1)) % len(road)
        x, y = road[int(v)]
        side = rng.integers(-2, 3)
        suit = hexc(SUITS[int(rng.integers(0, len(SUITS)))])
        _walker_td(wc, x + side, y + side * 0.5, suit, t, i)
        if i < len(spec.get("named", [])):
            named[spec["named"][i]] = (x + side, y + side * 0.5)
    for (fx, fy, fw, fh) in FARMS_TD:  # farmers in the rows
        for j in range(4):
            _walker_td(wc, fx + 4 + ((j * 11 + t * 4) % (fw - 8)), fy + 2 + j * 4 % (fh - 4), hexc(SUITS[7]), t, j)
    if spec.get("site"):  # a planned building, blinking
        sx, sy, sr = spec["site"]
        if int(t * 3) % 2 == 0:
            yy, xx = np.mgrid[-sr:sr + 1, -sr:sr + 1]
            d = np.sqrt(xx ** 2 + yy ** 2)
            ring = (np.abs(d - sr) < 0.6) & ((np.degrees(np.arctan2(yy, xx)) % 30) < 18)
            wc.mask(ring, sx - sr, sy - sr, P["gold"], world=False)
    scr = Canvas()
    sub = Canvas(TD_W, H)
    sub.rgb[:H] = wc.rgb[oy:oy + H]
    sub.world[:H] = wc.world[oy:oy + H]
    sub.alpha[:H] = wc.alpha[oy:oy + H]
    scr.paste(sub, ox)
    scr.light([(lx - ox, ly - oy, r, s) for (lx, ly, r, s) in lights], spec.get("ambient", 0.55))
    tags = Tags(scr)
    for name, (x, y) in named.items():
        tags.tag("@" + name, x - ox, y - oy - 1)
    for name, (x, y) in spec.get("labels", {}).items():
        tags.tag(name, x - ox, y - oy, P["gold"])
    if spec.get("title", True):
        title(scr, spec["count"], 0)
    for cap in spec.get("captions", []):
        if cap["t0"] <= t <= cap["t1"]:
            caption(scr, cap["lines"], t, cap["t0"])
    return scr


# ------------------------------------------------------------------ inside (a close-up, pixels ×2)

IW, IH = W // 2, H // 2  # 90×160, drawn twice as big


def _seal(c: Canvas, x, y, letter, word, col):
    m, x0, y0 = c.disc(x, y, 7)
    c.mask(m, x0 + 1, y0 + 1, P["ink"], world=False)
    c.mask(m, x0, y0, col, world=False)
    m2, x1, y1 = c.disc(x, y, 5)
    c.mask(m2, x1, y1, col * 0.8, world=False)
    c.text(letter, x - 2, y - 3, P["ui"], outline=False)
    c.text(word, x + 11, y - 3, P["ui"], scale=1)


def draw_inside(spec: dict, t: float) -> Canvas:
    FLOOR = 104  # close-up pixels; ×2 on screen
    c = Canvas(IW, IH)
    c.rgb[:] = P["sky1"]
    rng = _rng("inside-stars")
    for _ in range(26):  # outside, through the curved glass: stars and the ringed planet
        c.px(int(rng.integers(0, IW)), int(rng.integers(20, 60)), P["star"], world=False)
    pm, px0, py0 = c.disc(68, 40, 9)
    c.mask(pm, px0, py0, P["planet1"], world=False)
    c.mask(pm & (np.arange(pm.shape[0])[:, None] % 5 < 2), px0, py0, P["planet0"], world=False)
    c.dither_mask(pm & (np.arange(pm.shape[1])[None, :] > 10), px0, py0, P["sky1"], 0.6, world=False)
    c.rect(54, 40, 29, 1, P["ring"], world=False)
    for x in range(8, IW, 18):  # the glass wall's struts
        c.rect(x, 18, 1, 44, P["rim"] * 0.55)
    c.rect(0, 18, IW, 1, P["rim"] * 0.55)
    c.rect(0, 40, IW, 1, P["rim"] * 0.4)
    c.dither_mask(np.ones((44, IW), bool), 0, 18, P["glass"], 0.25)
    c.rect(0, 0, IW, 18, P["metal3"])  # ceiling
    c.rect(0, 62, IW, FLOOR - 62, P["metal2"])  # back wall
    for x in range(0, IW, 10):
        c.rect(x, 62, 1, FLOOR - 62, P["metal3"])
    c.rect(0, 62, IW, 2, P["metal1"])
    c.rect(0, FLOOR, IW, IH - FLOOR, P["wood1"])
    for x in range(0, IW, 6):
        c.rect(x, FLOOR, 1, IH - FLOOR, P["wood0"] * 0.8)
    for _ in range(30):  # frost in the draughty corner
        c.px(int(rng.integers(74, IW)), int(rng.integers(20, 62)), P["rim"])
    # a shelf on the right wall
    c.rect(66, 74, 20, 1, P["wood0"])
    c.sprite(CRATE, 68, 69)
    c.rect(77, 70, 3, 4, P["crys1"])
    # the sealed door in the left wall: a round hatch with glowing seams
    door = (14, 84, 10)
    dm, dx0, dy0 = c.disc(*door)
    c.mask(dm, dx0, dy0, P["metal3"])
    dm2, dx1, dy1 = c.disc(door[0], door[1], door[2] - 2)
    c.mask(dm2, dx1, dy1, P["metal1"] * 0.8)
    glow = 0.6 + 0.4 * math.sin(t * 3)
    seam = P["crys0"] * glow + P["metal1"] * (1 - glow)
    c.rect(door[0] - 7, door[1], 15, 1, seam, world=False)
    c.rect(door[0], door[1] - 7, 1, 15, seam, world=False)
    c.rect(door[0] - 2, door[1] - 2, 5, 5, P["iron"])
    lamp_x = 50
    c.rect(lamp_x, 0, 1, 50, P["metal3"])
    c.rect(lamp_x - 3, 50, 7, 2, P["metal2"])
    c.rect(lamp_x - 2, 52, 5, 1, P["warm0"], world=False)
    c.rect(40, FLOOR - 11, 22, 2, P["wood0"])  # the table
    c.rect(42, FLOOR - 9, 2, 9, P["wood1"])
    c.rect(58, FLOOR - 9, 2, 9, P["wood1"])
    c.rect(45, FLOOR - 14, 2, 3, P["ui"] * 0.85)
    heads = {}
    from .scene import BARREL_ELDER, look_of
    people = list(spec.get("people", []))
    if spec.get("elder"):
        people.append({"name": spec["elder"], "x": 82, "flip": True, "look": BARREL_ELDER})
    for p in people:
        if isinstance(p, (list, tuple)):  # (name, x, flip, suit, skin)
            p = {"name": p[0], "x": p[1], "flip": p[2], "suit": p[3], "skin": p[4]}
        look = kit.full(look_of(p))
        spr = kit.compose(look, 0)
        bob = round(abs(math.sin(t * 2))) if look["carrier"] != "none" else 0
        c.sprite(spr, p["x"] - kit.OX - 3, FLOOR - spr.h - bob, flip=p.get("flip", False))
        pet = kit.pet_sprite(look["pet"], int(t * 3))
        if pet:
            c.sprite(pet, p["x"] + (5 if p.get("flip") else -9), FLOOR - pet.h, flip=p.get("flip", False))
        heads[p["name"]] = (p["x"], FLOOR - spr.h - bob + spr.top)
    c.light([(lamp_x, 56, 40, 0.75 + 0.03 * math.sin(t * 9)), (door[0], door[1], 14, 0.25 * glow)],
            spec.get("ambient", 0.5), warm=P["warm1"])
    scr = Canvas()
    scr.rgb[:] = c.rgb.repeat(2, 0).repeat(2, 1)
    tags = Tags(scr)
    for b in spec.get("bubbles", []):
        if b["t0"] <= t <= b["t1"] and b["who"] in heads:
            hx, hy = heads[b["who"]]
            tags.bubble(b["text"], hx * 2, hy * 2 - 2)
    for name, (hx, hy) in heads.items():
        if name in spec.get("tags", []):
            tags.tag(("@" if not name.isupper() else "") + name, hx * 2, hy * 2 - 1)
    q = spec.get("question")
    if q and q["t0"] <= t:
        mid = (SAFE[0] + SAFE[2]) // 2
        for i, line in enumerate(q["lines"]):
            scale = min(2 if pixfont.width(l.replace("*", ""), 2) <= SAFE[2] - SAFE[0] else 1 for l in q["lines"])
            scr.text(line.replace("*", ""), mid, 42 + i * 9 * scale, P["gold"] if line.startswith("*") else P["ui"],
                     scale=scale, center=True)
        x = SAFE[0] + 4
        for i, (letter, word) in enumerate(q["choices"]):
            _seal(scr, x + 7, 238, letter, word, P["coil"] if i == 0 else hexc("3f7fd6"))
            x += 22 + pixfont.width(word) + 4
    for cap in spec.get("captions", []):
        if cap["t0"] <= t <= cap["t1"]:
            caption(scr, cap["lines"], t, cap["t0"])
    return scr


# ------------------------------------------------------------------ planet


@lru_cache(maxsize=1)
def _lights_on_globe(n: int, seed: int):
    """Settlers' homes as (lon, lat) points in districts that spread from the landing site."""
    rng = np.random.default_rng(seed)
    districts = [(0.3, 0.2, 0.18), (0.75, 0.35, 0.12), (-0.2, -0.15, 0.14), (1.2, -0.3, 0.1), (0.5, -0.45, 0.08)]
    pts = []
    for i in range(n):
        lon0, lat0, spread = districts[min(len(districts) - 1, int(rng.exponential(1.1)))]
        pts.append((lon0 + rng.normal(0, spread), lat0 + rng.normal(0, spread * 0.7)))
    return np.array(pts, dtype=np.float32)


def draw_planet(spec: dict, t: float) -> Canvas:
    c = Canvas()
    c.rgb[:] = P["sky0"]
    rng = _rng("planet-stars")
    for _ in range(110):
        x, y = int(rng.integers(0, W)), int(rng.integers(0, H))
        if 0.5 + 0.5 * math.sin(t * 2 + x * 0.3 + y) > 0.3:
            c.px(x, y, P["star"] if (x + y) % 3 else P["star2"], world=False)
    # the gas giant far behind
    gm, gx, gy = c.disc(146, 100, 11)
    c.mask(gm, gx, gy, P["planet1"], world=False)
    c.mask(gm & (np.arange(gm.shape[0])[:, None] % 6 < 2), gx, gy, P["planet2"], world=False)
    c.dither_mask(gm & (np.arange(gm.shape[1])[None, :] < 9), gx, gy, P["sky0"], 0.55, world=False)
    c.rect(128, 100, 37, 1, P["ring"] * 0.8, world=False)
    # the moon
    cx, cy, r = 90, 168, 64
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = (xx - cx) / r, (yy - cy) / r
    rr = nx ** 2 + ny ** 2
    disc = rr <= 1
    nz = np.sqrt(np.clip(1 - rr, 0, 1))
    rot = t * spec.get("spin", 0.12) + spec.get("lon0", 0.0)
    lon = np.arctan2(nx, nz) + rot
    lat = np.arcsin(np.clip(-ny, -1, 1))
    tex = (np.sin(lon * 3.1) * np.cos(lat * 4.3) + 0.6 * np.sin(lon * 7.7 + 1) * np.sin(lat * 6.1 + 2)
           + 0.35 * np.sin(lon * 17 + lat * 13))
    bay = _bayer(H, W)
    for lvl, k in ((-9, "grass2"), (-0.35, "grass1"), (0.45, "grass0")):
        c.mask(disc & (tex + 0.3 * bay > lvl), 0, 0, P[k])
    craters = (np.sin(lon * 11) * np.sin(lat * 9 + 1) > 0.86)
    c.mask(disc & craters, 0, 0, P["soil0"])
    light = nx * -0.9 + ny * -0.2 + nz * 0.25  # sun from the left: the right half is night
    night = disc & (light + 0.2 * (bay - 0.5) < 0.05)
    dusk = disc & ~night & (light + 0.2 * (bay - 0.5) < 0.22)
    c.mask(night, 0, 0, P["sky1"] * 1.2)
    c.dither_mask(dusk, 0, 0, P["sky2"], 0.5)
    rim = disc & (rr > 0.93)
    c.mask(rim & ~night, 0, 0, P["rim"] * 0.6)
    # settlers' homes: lights on the night side, roofs on the day side
    pts = _lights_on_globe(spec.get("lights", 1200), spec.get("seed", 7))
    plon, plat = pts[:, 0] - rot, pts[:, 1]
    px_ = np.cos(plat) * np.sin(plon)
    pz = np.cos(plat) * np.cos(plon)
    py_ = -np.sin(plat)
    vis = pz > 0.08
    sx = (cx + px_ * r).astype(int)
    sy = (cy + py_ * r).astype(int)
    for x, y, v, lz in zip(sx, sy, vis, pz):
        if not v or not (0 <= x < W and 0 <= y < H):
            continue
        if night[y, x] or dusk[y, x]:
            c.px(x, y, P["warm0"] if (x * 7 + y) % 5 else P["warm1"], world=False)
        else:
            c.px(x, y, P["grass2"] * 0.8, world=False)
    if spec.get("title", True):
        title(c, spec["count"], 0)
    for cap in spec.get("captions", []):
        if cap["t0"] <= t <= cap["t1"]:
            caption(c, cap["lines"], t, cap["t0"])
    return c
