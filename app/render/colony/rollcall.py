"""Roll call: everyone living on Farside, in a grid, each settler in their full look (pet, hat,
ride, costume), named, with where they stand on the image so they can be tagged there.

Slides are 1080×1350 (4:5, the tallest a feed image goes). Art is drawn at 108×135 and scaled ×10;
text is drawn at 360×450 and scaled ×3, so names stay readable at that size. The first slide is a
title card; the rest hold PER_SLIDE settlers each."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import kit, pixfont
from .art import BAYER, Canvas, P

AW, AH, AS = 108, 135, 10  # art
TW, TH, TS = 360, 450, 3  # text
COLS, ROWS = 3, 3
PER_SLIDE = COLS * ROWS
CELL = 36  # art pixels
ZOOM = 2  # settlers drawn twice as big as in the videos, so you can see your look
TOP = 27  # the header band


def _sky(c: Canvas, top="sky1", bottom="sky6"):
    bands = ["sky0", "sky1", "sky2", "sky3", "sky4", "sky5", "sky6", "sky7", "sky8"]
    i0, i1 = bands.index(top), bands.index(bottom)
    for y in range(c.h):
        f = (y / c.h) * (i1 - i0) + i0
        i = int(f)
        hi = np.tile(BAYER[y % 4], c.w // 4 + 1)[:c.w] < (f - i)
        c.rgb[y] = np.where(hi[:, None], P[bands[min(i + 1, len(bands) - 1)]], P[bands[i]])


def _stars(c: Canvas, seed: int, n: int, below: int):
    rng = np.random.default_rng(seed)
    for _ in range(n):
        c.px(int(rng.integers(0, c.w)), int(rng.integers(0, below)), P["star"], world=False)


def _planet(c: Canvas, cx, cy, r):
    yy, xx = np.mgrid[0:c.h, 0:c.w]
    t = (xx - cx) * 0.2
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    body = d <= r
    ring = np.abs(((xx - cx) / (r * 1.7)) ** 2 + ((yy - cy + t) / (r * 0.25)) ** 2 - 1) < 0.18
    c.mask(ring & ~body & (yy < cy - t), 0, 0, P["ring"] * 0.8, world=False)
    band = ((yy - cy + t) / r * 5 + 10).astype(int) % 4
    for i, k in enumerate(["planet0", "planet1", "planet2", "planet3"]):
        c.mask(body & (band == i), 0, 0, P[k], world=False)
    sh = (xx - cx + (yy - cy) * 0.3) / r
    bg = np.tile(BAYER, (c.h // 4 + 1, c.w // 4 + 1))[:c.h, :c.w]
    c.mask(body & (sh > 0.2) & (bg < 0.7), 0, 0, P["sky1"], world=False)
    c.mask(ring & (yy >= cy - t), 0, 0, P["ring"], world=False)


def _text(t: Canvas, s: str, cx: int, y: int, col, scale=1, max_w: int | None = None):
    s = s.upper()
    while max_w and len(s) > 3 and pixfont.width(s, scale) > max_w:
        s = s[:-2] + "…" if s.endswith("…") else s[:-1] + "…"
    if "…" in s and "…" not in pixfont.GLYPHS:
        s = s.replace("…", ".")
    t.text(s, cx, y, col, scale=scale, center=True)


def _zoom(spr):
    """A sprite with every pixel doubled."""
    from .art import Sprite

    z = Sprite.__new__(Sprite)
    z.cols = spr.cols
    z.layers = {k: m.repeat(ZOOM, 0).repeat(ZOOM, 1) for k, m in spr.layers.items()}
    z.h, z.w, z.top = spr.h * ZOOM, spr.w * ZOOM, spr.top * ZOOM
    return z


def _compose(art: Canvas, text: Canvas) -> Image.Image:
    big = np.clip(art.rgb, 0, 255).astype("uint8").repeat(AS, 0).repeat(AS, 1)
    tx = np.clip(text.rgb, 0, 255).astype("uint8").repeat(TS, 0).repeat(TS, 1)
    a = text.alpha.repeat(TS, 0).repeat(TS, 1)
    big[a] = tx[a]
    return Image.fromarray(big)


def cover(count: int, shown: int, day_label: str) -> Image.Image:
    art, text = Canvas(AW, AH), Canvas(TW, TH)
    _sky(art, "sky1", "sky7")
    _stars(art, 11, 60, 90)
    _planet(art, 54, 58, 26)
    for x in range(AW):  # the horizon, with the colony's lights
        gy = 112 + int(round(1.5 * math.sin(x * 0.12)))
        art.rect(x, gy, 1, AH - gy, P["soil1"])
        art.px(x, gy, P["grass0"])
    rng = np.random.default_rng(3)
    for _ in range(26):
        art.px(int(rng.integers(4, AW - 4)), int(rng.integers(114, 124)), P["warm0"], world=False)
    _text(text, "FARSIDE", TW // 2, 24, P["gold"], scale=4)
    _text(text, "ROLL CALL", TW // 2, 64, P["ui"], scale=3)
    _text(text, f"{count:,} SETTLERS LIVE HERE", TW // 2, 362, P["ui"], scale=2)
    _text(text, "SWIPE TO FIND YOURSELF" if shown > 1 else "FIND YOURSELF", TW // 2, 392, P["gold"], scale=1)
    _text(text, day_label, TW // 2, 412, P["ui"], scale=1)
    return _compose(art, text)


def grid(people: list[dict], page: int, pages: int) -> tuple[Image.Image, list[dict]]:
    """One slide of up to PER_SLIDE people ({handle, look, rank}); returns it and their tag spots."""
    art, text = Canvas(AW, AH), Canvas(TW, TH)
    _sky(art, "sky1", "sky5")
    _stars(art, 20 + page, 30, TOP)
    _text(text, "FARSIDE ROLL CALL", TW // 2, 22, P["gold"], scale=2)
    _text(text, f"{page}/{pages}", TW // 2, 52, P["ui"])
    spots = []
    for i, p in enumerate(people[:PER_SLIDE]):
        col, row = i % COLS, i // COLS
        x0, y0 = col * CELL, TOP + row * CELL
        art.rect(x0 + 1, y0 + 1, CELL - 2, CELL - 2, P["sky2"] * 0.9)
        art.rect(x0 + 1, y0 + 1, CELL - 2, 1, P["rim"] * 0.45)
        ground = y0 + CELL - 9
        art.rect(x0 + 2, ground, CELL - 4, 1, P["grass0"])
        art.rect(x0 + 2, ground + 1, CELL - 4, 1, P["grass1"])
        look = kit.full(p.get("look") or {})
        spr = _zoom(kit.compose(look, 0))
        cx = x0 + CELL // 2 + (4 if look["pet"] != "none" else 0)
        art.sprite(spr, cx - (kit.OX + 3) * ZOOM - 1, ground - spr.h)
        pet = kit.pet_sprite(look["pet"], 0)
        if pet:
            pz = _zoom(pet)
            art.sprite(pz, cx - 9 - pz.w, ground - pz.h)
        tx = (x0 + CELL // 2) * TW // AW
        ty = (ground + 2) * TH // AH
        _text(text, "@" + p["handle"], tx, ty, P["ui"], max_w=CELL * TW // AW - 4)
        if p.get("rank") and p["rank"] != "newcomer":
            _text(text, p["rank"], tx, ty + 9, P["gold"])
        spots.append({"username": p["handle"], "x": round((x0 + CELL / 2) / AW, 3),
                      "y": round((ground - 10) / AH, 3)})
    return _compose(art, text), spots
