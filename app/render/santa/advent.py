"""The raosanta.uk advent calendar: one calendar for the season, drawn in code, that fills up day by
day. Doors 1-24 sit in a shuffled grid (fixed for the year, as on a real calendar) above a big
door 25. A door opened on an earlier day shows its treasure; today's opens in the video.

`calendar(day)` draws the whole board for a day; `treasure(n, size)` draws door n's treasure (25 of
them, all flat shapes in the site's colours). The countdown scene (scenes.AdventScene) films it.
"""
from __future__ import annotations

import math
import random
from datetime import date
from functools import lru_cache

from PIL import Image, ImageDraw

from ..theme import font
from . import look
from .look import DISPLAY, SEMI, C

CAL_W, CAL_H = 1600, 2800
COLS, ROWS = 4, 6
MARGIN, GAP, TITLE_H = 90, 28, 330
CELL_W = (CAL_W - 2 * MARGIN - (COLS - 1) * GAP) // COLS
CELL_H = 300
BIG_H = 380
DOOR_COLOURS = [C.post, C.pine, C.night, C.post_deep, C.pine, C.post, C.night, C.pine]

BROWN = (122, 82, 54)
GINGER = (176, 108, 58)
ORANGE = (232, 134, 42)
PASTRY = (217, 163, 91)


def layout(year: int = 2026) -> dict[int, tuple[int, int, int, int]]:
    """door number -> (x, y, w, h) on the board. 1-24 shuffled once per year; 25 is the big one."""
    order = list(range(1, 25))
    random.Random(year * 7 + 3).shuffle(order)
    out = {}
    for k, n in enumerate(order):
        r, c = divmod(k, COLS)
        out[n] = (MARGIN + c * (CELL_W + GAP), TITLE_H + r * (CELL_H + GAP), CELL_W, CELL_H)
    y25 = TITLE_H + ROWS * (CELL_H + GAP) + 10
    out[25] = (MARGIN, y25, CAL_W - 2 * MARGIN, BIG_H)
    return out


def door_colour(n: int) -> tuple:
    return C.post if n == 25 else DOOR_COLOURS[(n * 5) % len(DOOR_COLOURS)]


# ---------------------------------------------------------------- the 25 treasures (300x300, flat)

def _canvas():
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _star(d, cx, cy, r, fill, inner=0.42, points=5, rot=-90):
    pts = []
    for k in range(points * 2):
        rr = r if k % 2 == 0 else r * inner
        a = math.radians(rot + k * 180 / points)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=fill)


def t_star(d):
    _star(d, 150, 158, 128, C.gold + (255,))
    _star(d, 150, 158, 70, C.gold_soft + (255,))


def t_bauble(d):
    d.line([(150, 18), (150, 62)], fill=C.gold + (255,), width=8)
    d.rectangle((122, 58, 178, 92), fill=C.gold + (255,))
    d.ellipse((40, 80, 260, 300 - 10), fill=C.post + (255,))
    d.arc((40, 120, 260, 220), 20, 160, fill=C.label + (255,), width=16)
    d.ellipse((84, 120, 124, 170), fill=(236, 150, 150, 255))


def t_candy(d):
    pts = [(190, 280 - k * 8) for k in range(20)]
    pts += [(130 + 60 * math.cos(math.radians(a)), 120 - 60 * math.sin(math.radians(a))) for a in range(0, 181, 10)]
    pts += [(70, 120 + k * 8) for k in range(1, 6)]
    for k, (x, y) in enumerate(pts):
        col = C.post if (k // 3) % 2 == 0 else C.label
        d.ellipse((x - 20, y - 20, x + 20, y + 20), fill=col + (255,))


def t_snowman(d):
    d.ellipse((70, 140, 230, 295), fill=C.frost + (255,))
    d.ellipse((95, 52, 205, 160), fill=C.frost + (255,))
    d.rectangle((105, 136, 200, 158), fill=C.post + (255,))
    d.rectangle((180, 150, 205, 200), fill=C.post + (255,))
    d.rectangle((108, 10, 192, 62), fill=C.ink + (255,))
    d.rectangle((88, 56, 212, 70), fill=C.ink + (255,))
    for x in (128, 172):
        d.ellipse((x - 8, 88, x + 8, 104), fill=C.ink + (255,))
    d.polygon([(150, 110), (150, 126), (196, 118)], fill=ORANGE + (255,))
    for y in (190, 225, 260):
        d.ellipse((143, y, 157, y + 14), fill=C.ink + (255,))


def t_mitten(d):
    d.rounded_rectangle((80, 50, 230, 230), radius=70, fill=C.post + (255,))
    d.ellipse((40, 110, 120, 200), fill=C.post + (255,))
    d.rectangle((70, 220, 240, 290), fill=C.label + (255,))
    for x in range(85, 230, 30):
        d.line([(x, 232), (x + 15, 278)], fill=C.gold + (255,), width=6)
    _star(d, 160, 130, 30, C.label + (255,))


def t_robin(d):
    d.ellipse((50, 80, 250, 250), fill=BROWN + (255,))
    d.ellipse((90, 70, 200, 170), fill=BROWN + (255,))
    d.ellipse((110, 120, 220, 230), fill=(214, 74, 60, 255))
    d.ellipse((150, 100, 166, 116), fill=C.ink + (255,))
    d.polygon([(196, 118), (240, 128), (196, 138)], fill=C.gold + (255,))
    d.polygon([(40, 160), (60, 230), (100, 200)], fill=BROWN + (255,))
    for x in (130, 165):
        d.line([(x, 245), (x, 290)], fill=C.gold_ink + (255,), width=6)


def t_ginger(d):
    col = GINGER + (255,)
    d.ellipse((100, 15, 200, 115), fill=col)
    d.rounded_rectangle((90, 100, 210, 220), radius=30, fill=col)
    d.rounded_rectangle((30, 110, 120, 150), radius=20, fill=col)
    d.rounded_rectangle((180, 110, 270, 150), radius=20, fill=col)
    d.rounded_rectangle((90, 200, 140, 290), radius=22, fill=col)
    d.rounded_rectangle((160, 200, 210, 290), radius=22, fill=col)
    for x in (130, 170):
        d.ellipse((x - 8, 50, x + 8, 66), fill=C.label + (255,))
    d.arc((122, 60, 178, 96), 20, 160, fill=C.label + (255,), width=5)
    for y in (130, 165):
        d.ellipse((141, y, 159, y + 18), fill=C.post + (255,))
    for x0 in (40, 230):
        d.line([(x0, 120), (x0 + 15, 140)], fill=C.label + (255,), width=5)


def t_bell(d):
    d.pieslice((70, 40, 230, 200), 180, 360, fill=C.gold + (255,))
    d.polygon([(70, 120), (230, 120), (262, 240), (38, 240)], fill=C.gold + (255,))
    d.rectangle((38, 232, 262, 252), fill=C.gold_ink + (255,))
    d.ellipse((130, 240, 170, 280), fill=C.gold_ink + (255,))
    d.ellipse((100, 18, 150, 58), fill=C.post + (255,))
    d.ellipse((150, 18, 200, 58), fill=C.post + (255,))
    d.arc((96, 90, 150, 200), 100, 200, fill=C.gold_soft + (255,), width=10)


def _leaf(d, cx, cy, ang, col):
    pts = []
    for k in range(9):
        t = k / 8
        x = -90 + 180 * t
        y = (34 if k % 2 else 18) * math.sin(math.pi * t)
        pts.append((x, -y))
    pts += [(x, -y) for x, y in reversed([(-90 + 180 * k / 8, -((34 if k % 2 else 18) * math.sin(math.pi * k / 8))) for k in range(9)])]
    a = math.radians(ang)
    d.polygon([(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)) for x, y in pts], fill=col)


def t_holly(d):
    _leaf(d, 105, 160, -30, C.pine + (255,))
    _leaf(d, 195, 160, 30, (31, 110, 80, 255))
    for x, y in ((130, 120), (170, 120), (150, 90)):
        d.ellipse((x - 26, y - 26, x + 26, y + 26), fill=C.post + (255,))


def t_present(d, box=C.post, ribbon=C.gold):
    d.rectangle((50, 110, 250, 290), fill=box + (255,))
    d.rectangle((38, 90, 262, 140), fill=box + (255,))
    d.rectangle((130, 90, 170, 290), fill=ribbon + (255,))
    d.rectangle((38, 106, 262, 124), fill=ribbon + (255,))
    d.ellipse((70, 30, 150, 100), outline=ribbon + (255,), width=18)
    d.ellipse((150, 30, 230, 100), outline=ribbon + (255,), width=18)


def t_stocking(d):
    d.polygon([(90, 70), (190, 70), (190, 200), (250, 240), (230, 290), (120, 270), (90, 220)], fill=C.post + (255,))
    d.ellipse((90, 220, 170, 290), fill=C.post + (255,))
    d.rounded_rectangle((76, 30, 204, 86), radius=14, fill=C.label + (255,))
    _star(d, 140, 160, 26, C.gold + (255,))


def t_tree(d):
    for k, (w, y) in enumerate(((210, 250), (170, 190), (120, 130))):
        d.polygon([(150 - w / 2, y), (150 + w / 2, y), (150, y - 110)], fill=C.pine + (255,))
    d.rectangle((132, 248, 168, 290), fill=BROWN + (255,))
    _star(d, 150, 30, 30, C.gold + (255,))
    for x, y, c in ((110, 220, C.post), (190, 225, C.gold), (150, 165, C.label), (125, 110, C.post), (178, 150, C.post)):
        d.ellipse((x - 11, y - 11, x + 11, y + 11), fill=c + (255,))


def t_christingle(d):
    d.ellipse((50, 130, 250, 300), fill=ORANGE + (255,))
    d.rectangle((50, 195, 250, 225), fill=C.post + (255,))
    d.rectangle((132, 50, 168, 150), fill=C.label + (255,))
    d.ellipse((136, 8, 164, 56), fill=C.gold + (255,))
    d.ellipse((143, 26, 157, 52), fill=C.gold_soft + (255,))
    for a in (200, 340):
        x = 150 + 95 * math.cos(math.radians(a))
        d.line([(150, 170), (x, 120)], fill=C.ink + (255,), width=4)
        d.ellipse((x - 12, 108, x + 12, 132), fill=C.pine + (255,))


def t_reindeer(d):
    for s in (-1, 1):
        x0 = 150 + s * 40
        d.line([(x0, 90), (x0 + s * 40, 20)], fill=C.gold_ink + (255,), width=12)
        d.line([(x0 + s * 22, 55), (x0 + s * 70, 50)], fill=C.gold_ink + (255,), width=10)
        d.ellipse((150 + s * 85 - 26, 110, 150 + s * 85 + 26, 140), fill=BROWN + (255,))
    d.ellipse((85, 80, 215, 260), fill=BROWN + (255,))
    for x in (125, 175):
        d.ellipse((x - 9, 140, x + 9, 158), fill=C.ink + (255,))
    d.ellipse((128, 205, 172, 249), fill=C.post + (255,))


def t_cracker(d):
    d.rounded_rectangle((90, 120, 210, 180), radius=10, fill=C.post + (255,))
    for s in (-1, 1):
        xe = 150 + s * 60
        d.polygon([(xe, 125), (xe, 175), (xe + s * 45, 200), (xe + s * 45, 100)], fill=C.gold + (255,))
        for k in range(4):
            y = 100 + k * 33
            d.polygon([(xe + s * 45, y), (xe + s * 70, y + 16), (xe + s * 45, y + 33)], fill=C.gold_soft + (255,))
    d.rectangle((140, 120, 160, 180), fill=C.label + (255,))
    _star(d, 150, 150, 14, C.gold + (255,))


def t_mince_pie(d):
    d.ellipse((40, 110, 260, 270), fill=PASTRY + (255,))
    d.ellipse((60, 95, 240, 240), fill=(234, 190, 120, 255))
    _star(d, 150, 168, 52, (120, 58, 40, 255))
    rng = random.Random(17)
    for _ in range(40):
        x, y = rng.uniform(70, 230), rng.uniform(105, 230)
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=C.paper + (255,))


def t_cocoa(d):
    d.rounded_rectangle((70, 110, 220, 285), radius=24, fill=C.label + (255,))
    d.arc((190, 150, 260, 240), 270, 90, fill=C.label + (255,), width=18)
    d.ellipse((70, 95, 220, 135), fill=(110, 66, 42, 255))
    for x, y in ((100, 100), (140, 95), (175, 104)):
        d.rounded_rectangle((x, y, x + 26, y + 22), radius=5, fill=C.paper + (255,))
    for x in (110, 150, 190):
        d.arc((x - 20, 20, x + 20, 90), 100, 260, fill=C.frost_soft + (255,), width=6)
    d.rectangle((70, 200, 220, 220), fill=C.post + (255,))


def t_postcard(d):
    card = look.postcard(250, 180, edge=12, shadow=0)
    stamp = look.stamp(70, 6)
    card = card.copy()
    card.alpha_composite(stamp, (card.width - stamp.width - 18, 16))
    f = font(SEMI, 34)
    ImageDraw.Draw(card).text((30, 100), "Thank you!", font=f, fill=C.post + (255,))
    return card


def t_pudding(d):
    d.pieslice((40, 70, 260, 290), 180, 360, fill=(96, 58, 38, 255))
    d.rectangle((40, 178, 260, 230), fill=(96, 58, 38, 255))
    d.ellipse((40, 200, 260, 260), fill=(96, 58, 38, 255))
    d.polygon([(60, 140), (240, 140), (225, 165), (200, 150), (180, 175), (150, 150), (120, 172), (95, 150), (72, 168)],
              fill=C.paper + (255,))
    d.pieslice((70, 70, 230, 180), 180, 360, fill=C.paper + (255,))
    _leaf(d, 128, 74, -25, C.pine + (255,))
    _leaf(d, 176, 74, 25, C.pine + (255,))
    d.ellipse((136, 56, 164, 84), fill=C.post + (255,))


def t_wreath(d):
    d.ellipse((35, 35, 265, 265), outline=C.pine + (255,), width=58)
    rng = random.Random(5)
    for _ in range(14):
        a = rng.uniform(0, 2 * math.pi)
        x, y = 150 + 101 * math.cos(a), 150 + 101 * math.sin(a)
        d.ellipse((x - 10, y - 10, x + 10, y + 10), fill=C.post + (255,))
    d.polygon([(150, 240), (100, 210), (100, 270)], fill=C.post + (255,))
    d.polygon([(150, 240), (200, 210), (200, 270)], fill=C.post + (255,))
    d.ellipse((136, 226, 164, 254), fill=C.post_deep + (255,))


def t_sleigh(d):
    d.polygon([(40, 130), (60, 210), (230, 210), (260, 150), (230, 120), (210, 160), (90, 160), (80, 120)], fill=C.post + (255,))
    d.arc((20, 200, 290, 280), 0, 180, fill=C.gold + (255,), width=10)
    for x in (90, 200):
        d.line([(x, 210), (x, 240)], fill=C.gold + (255,), width=8)
    d.rectangle((110, 90, 170, 160), fill=C.pine + (255,))
    d.rectangle((136, 90, 146, 160), fill=C.gold + (255,))
    d.rectangle((160, 105, 205, 160), fill=C.gold + (255,))


def t_stamp(d):
    return look.stamp(270, -6)


def t_santa_hat(d):
    d.polygon([(50, 240), (250, 240), (230, 120), (180, 60), (110, 70), (70, 140)], fill=C.post + (255,))
    d.polygon([(180, 60), (240, 90), (262, 150), (230, 120)], fill=C.post + (255,))
    d.rounded_rectangle((36, 222, 264, 286), radius=30, fill=C.paper + (255,))
    d.ellipse((232, 130, 292, 190), fill=C.paper + (255,))


def t_big_present(d):
    t_present(d, box=C.gold, ribbon=C.post)
    for x, y, r in ((40, 40, 16), (262, 52, 12), (28, 200, 10), (272, 230, 14)):
        _star(d, x, y, r, C.gold_soft + (255,))


def t_snowflake(d):
    for k in range(6):
        a = math.radians(k * 60 - 90)
        x, y = 150 + 125 * math.cos(a), 150 + 125 * math.sin(a)
        d.line([(150, 150), (x, y)], fill=C.frost + (255,), width=14)
        for f in (0.45, 0.72):
            bx, by = 150 + 125 * f * math.cos(a), 150 + 125 * f * math.sin(a)
            for s in (-1, 1):
                b = a + s * math.radians(45)
                d.line([(bx, by), (bx + 38 * math.cos(b), by + 38 * math.sin(b))], fill=C.frost + (255,), width=10)
    d.ellipse((128, 128, 172, 172), fill=C.frost_soft + (255,))


def t_padlock(d):
    """November: door 1 is locked. No peeking."""
    d.arc((85, 20, 215, 170), 180, 360, fill=C.frost_soft + (255,), width=26)
    d.line([(98, 95), (98, 140)], fill=C.frost_soft + (255,), width=26)
    d.line([(202, 95), (202, 140)], fill=C.frost_soft + (255,), width=26)
    d.rounded_rectangle((50, 130, 250, 290), radius=28, fill=C.gold + (255,), outline=C.gold_ink + (255,), width=8)
    d.ellipse((128, 178, 172, 222), fill=C.night_deep + (255,))
    d.polygon([(140, 210), (160, 210), (166, 258), (134, 258)], fill=C.night_deep + (255,))


TREASURES = {0: t_padlock, 1: t_star, 2: t_bauble, 3: t_candy, 4: t_snowman, 5: t_mitten, 6: t_robin, 7: t_ginger, 8: t_bell,
             9: t_holly, 10: t_present, 11: t_stocking, 12: t_tree, 13: t_christingle, 14: t_reindeer, 15: t_cracker,
             16: t_mince_pie, 17: t_cocoa, 18: t_postcard, 19: t_pudding, 20: t_wreath, 21: t_sleigh, 22: t_snowflake,
             23: t_stamp, 24: t_santa_hat, 25: t_big_present}


@lru_cache(maxsize=64)
def treasure(n: int, size: int) -> Image.Image:
    img, d = _canvas()
    out = TREASURES[n](d)
    if isinstance(out, Image.Image):  # a ready-made picture (the stamp, the postcard)
        img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        img.alpha_composite(out, ((300 - out.width) // 2, (300 - out.height) // 2))
    return img.resize((size, size), Image.LANCZOS)


# ---------------------------------------------------------------- doors and the board

@lru_cache(maxsize=64)
def door_face(n: int, w: int, h: int) -> Image.Image:
    """A closed door: its colour, a gold frame, the number painted on, a brass knob."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = door_colour(n)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=col + (255,), outline=C.gold + (255,), width=6)
    d.rounded_rectangle((16, 16, w - 17, h - 17), radius=12, outline=tuple(min(255, c + 40) for c in col) + (255,), width=3)
    size = 150 if n < 25 else 220
    num = look.rich(str(n), DISPLAY, size, C.label, C.label, w)
    img.alpha_composite(num, ((w - num.width) // 2, (h - num.height) // 2 - 6))
    if n == 25:
        lab = look.rich("CHRISTMAS DAY", SEMI, 40, C.gold_soft, C.gold_soft, w)
        img.alpha_composite(lab, ((w - lab.width) // 2, h - lab.height - 34))
    d.ellipse((w - 46, h // 2 - 14, w - 18, h // 2 + 14), fill=C.gold_soft + (255,), outline=C.gold_ink + (255,), width=3)
    return img


def recess(n: int, w: int, h: int, with_treasure: bool) -> Image.Image:
    """An opened door's hole: dark, warm-lit, with its treasure (unless it's still to come out)."""
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=18, fill=C.night_deep + (255,), outline=C.gold + (255,), width=6)
    d.ellipse((w * 0.15, h * 0.12, w * 0.85, h * 0.92), fill=(40, 52, 92, 255))
    if with_treasure:
        t = treasure(n, int(min(w, h) * 0.78))
        img.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2))
    # the door hangs open on its left hinge: a thin dark sliver
    d.polygon([(0, 6), (22, 26), (22, h - 26), (0, h - 6)], fill=tuple(max(0, c - 40) for c in door_colour(n)) + (255,))
    return img


@lru_cache(maxsize=8)
def calendar(today: date) -> Image.Image:
    """The board on `today`: doors before today's open (with their treasures); today's and later
    closed (today's opens in the video). Before 1 December, every door is shut."""
    img = Image.new("RGBA", (CAL_W, CAL_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, CAL_W - 1, CAL_H - 1), radius=48, fill=C.night_raised + (255,), outline=C.gold + (255,), width=14)
    d.rounded_rectangle((28, 28, CAL_W - 29, CAL_H - 29), radius=36, outline=C.gold_ink + (255,), width=4)
    rng = random.Random(today.year)
    for _ in range(70):
        x, y, r = rng.uniform(50, CAL_W - 50), rng.uniform(50, CAL_H - 50), rng.uniform(3, 7)
        d.ellipse((x - r, y - r, x + r, y + r), fill=C.gold_soft + (90,))
    title = look.rich("The raosanta.uk *advent calendar*", DISPLAY, 74, C.label, C.gold, CAL_W - 2 * MARGIN)
    img.alpha_composite(title, ((CAL_W - title.width) // 2, 70))
    year = look.rich(str(today.year if today.month >= 8 else today.year - 1), SEMI, 48, C.gold_soft, C.gold_soft, 400)
    img.alpha_composite(year, ((CAL_W - year.width) // 2, 70 + title.height + 4))
    opened = today.day - 1 if today.month == 12 else 0
    for n, (x, y, w, h) in layout(today.year if today.month >= 8 else today.year - 1).items():
        face = recess(n, w, h, True) if n <= opened else door_face(n, w, h)
        img.alpha_composite(face, (x, y))
    return img
