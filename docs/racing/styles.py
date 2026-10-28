"""Four non-teletext design directions for Sixel Speedway v1 (docs/RACING_PLAN.md §5). Not app code:
each style draws the same moment (lap 3 of race 14) and the same race card, so they compare
like for like. Run: python docs/racing/styles.py  → docs/racing/styles/*.jpg"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
OUT = HERE / "styles"
W, H = 1080, 1920
CARS = [(1, "RED ROCKET"), (2, "MEAN GREEN"), (3, "CUSTARD"), (4, "BLUE STREAK"), (5, "HOT PINK"), (6, "CYANARA")]
ODDS = ["2/1", "4/1", "9/2", "6/1", "8/1", "12/1"]
FORM = ["21134", "43521", "16236", "32415", "54652", "65163"]
ORDER = [3, 1, 6, 4, 2, 5]  # running order on lap 3
PROGRESS = {3: 0.71, 1: 0.69, 6: 0.655, 4: 0.60, 2: 0.56, 5: 0.47}  # share of the lap


def font(name, size):
    paths = {"inter": "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
             "inter-md": "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf",
             "mono": "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-SemiBold.ttf",
             "mono-xb": "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-ExtraBold.ttf",
             "bungee": str(HERE.parent.parent / "assets/fonts/Bungee-Regular.ttf")}
    return ImageFont.truetype(paths[name], size)


def circuit(cx, cy, rx, ry, n=600, seed=14):
    """A closed, smooth, procedurally bent loop (the real renderer would seed this per season)."""
    rng = np.random.default_rng(seed)
    k = [(2, rng.uniform(.06, .1), rng.uniform(0, 6)), (3, rng.uniform(.05, .09), rng.uniform(0, 6)),
         (5, rng.uniform(.02, .04), rng.uniform(0, 6))]
    pts = []
    for i in range(n):
        t = i / n * 2 * math.pi
        r = 1 + sum(a * math.sin(f * t + p) for f, a, p in k)
        pts.append((cx + rx * r * math.cos(t), cy + ry * r * math.sin(t)))
    return pts


def at(pts, frac):
    i = int(frac % 1 * len(pts))
    (x0, y0), (x1, y1) = pts[i], pts[(i + 3) % len(pts)]
    return pts[i], math.atan2(y1 - y0, x1 - x0)


def glow(layer: Image.Image, radii=(4, 12, 30), gains=(1.0, .8, .6)) -> Image.Image:
    out = layer.copy()
    for r, g in zip(radii, gains):
        b = layer.filter(ImageFilter.GaussianBlur(r))
        out = ImageChops.add(out, Image.eval(b, lambda v, g=g: int(v * g)))
    return out


# ================================================================================================
# A. VECTOR: 1979 vector-arcade monitor. Glowing lines on black, wireframe everything.
# ================================================================================================
VEC = [(255, 60, 60), (60, 255, 120), (255, 230, 60), (80, 150, 255), (255, 80, 220), (60, 240, 255)]


def vec_car(d: ImageDraw.ImageDraw, x, y, ang, col, s=40):
    shape = [(1.0, 0), (-.7, .55), (-.4, 0), (-.7, -.55)]
    pts = [(x + s * (px * math.cos(ang) - py * math.sin(ang)), y + s * (px * math.sin(ang) + py * math.cos(ang)))
           for px, py in shape]
    d.line(pts + [pts[0]], fill=col, width=4, joint="curve")


def vector_race():
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    f, fb = font("mono", 44), font("mono-xb", 92)
    d.text((70, 250), "LAP 3/3", font=fb, fill=(255, 255, 255))
    d.text((70, 360), "RACE 14", font=f, fill=(120, 200, 255))
    outer, inner = circuit(540, 900, 430, 420), circuit(540, 900, 330, 320)
    d.line(outer + [outer[0]], fill=(60, 200, 255), width=4)
    d.line(inner + [inner[0]], fill=(60, 200, 255), width=4)
    mid = [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(outer, inner)]
    for i in range(0, len(mid), 20):  # dashed centre line
        d.line([mid[i], mid[(i + 8) % len(mid)]], fill=(30, 90, 140), width=2)
    d.line([outer[0], inner[0]], fill=(255, 255, 255), width=6)
    for n, frac in PROGRESS.items():
        lane = (n - 1) % 3 - 1
        (x, y), ang = at(mid, frac)
        x += lane * 26 * -math.sin(ang)
        y += lane * 26 * math.cos(ang)
        vec_car(d, x, y, ang, VEC[n - 1])
        for t in range(1, 6):  # beam trail
            (tx, ty), _ = at(mid, frac - t * .008)
            d.point((tx + lane * 26 * -math.sin(ang), ty + lane * 26 * math.cos(ang)), fill=VEC[n - 1])
    for i, n in enumerate(ORDER):  # running order as a vector list
        y = 1370 - (5 - i) * 0
        d.text((70 + i * 140, 1380), f"{n}", font=fb, fill=VEC[n - 1])
        d.line([(70 + i * 140, 1490), (130 + i * 140, 1490)], fill=VEC[n - 1], width=4)
    d.text((70, 1520), "HOT PINK SPUN OUT  T4", font=f, fill=VEC[4])
    im = glow(im)
    return jitter(im)


def vector_card():
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    f, fb, fs = font("mono", 50), font("mono-xb", 88), font("mono", 36)
    d.text((70, 250), "BETS OPEN", font=fb, fill=(255, 255, 255))
    d.text((70, 360), "RACE 15 · 18:00 TOMORROW", font=fs, fill=(120, 200, 255))
    for i, (n, name) in enumerate(CARS):
        y = 470 + i * 120
        d.rectangle([70, y, 150, y + 90], outline=VEC[i], width=4)
        d.text((95, y + 12), str(n), font=f, fill=VEC[i])
        d.text((180, y + 4), name, font=f, fill=VEC[i])
        d.text((180, y + 58), "FORM " + FORM[i], font=fs, fill=(90, 140, 190))
        d.text((760, y + 12), ODDS[i].rjust(4), font=f, fill=(255, 255, 255))
    d.rectangle([70, 1220, 930, 1420], outline=(255, 255, 255), width=4)
    d.text((110, 1245), "COMMENT  CAR + STAKE", font=fs, fill=(255, 255, 255))
    d.text((110, 1300), "4 250", font=fb, fill=VEC[3])
    d.text((460, 1325), "= §250 ON 4", font=f, fill=(255, 255, 255))
    d.text((70, 1440), "PLAY MONEY · NO PRIZES · RACE.ONLYDAN.UK", font=fs, fill=(150, 150, 150))
    return jitter(glow(im))


def jitter(im):
    """Beam wobble: a couple of rows nudged sideways, faint phosphor ghost, no scanlines."""
    a = np.asarray(im).astype(np.float32)
    ghost = np.roll(a, 4, axis=1) * .18
    a = np.maximum(a, ghost)
    for y in (812, 1306):
        a[y:y + 10] = np.roll(a[y:y + 10], 9, axis=1)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# ================================================================================================
# B. HANDHELD LCD: a 1980s Game-&-Watch-style handheld. Fixed segments, visible ghosts, printed
# colour overlay behind the glass, 7-segment digits.
# ================================================================================================
LCD_BG, LCD_ON, LCD_GHOST = (174, 184, 160), (34, 40, 34), (160, 170, 147)
PRINT = [(214, 64, 52), (60, 150, 80), (230, 180, 40), (50, 100, 190), (210, 80, 150), (40, 170, 190)]
SEG = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc",
       "8": "abcdefg", "9": "abcdfg", "/": "", " ": "", "-": "g"}


def seven(d, x, y, ch, h=90, on=LCD_ON, ghost=LCD_GHOST, wdt=12):
    w = h * .55
    segs = {"a": [(x, y), (x + w, y)], "b": [(x + w, y), (x + w, y + h / 2)], "c": [(x + w, y + h / 2), (x + w, y + h)],
            "d": [(x, y + h), (x + w, y + h)], "e": [(x, y + h / 2), (x, y + h)], "f": [(x, y), (x, y + h / 2)],
            "g": [(x, y + h / 2), (x + w, y + h / 2)]}
    for k, line in segs.items():
        d.line(line, fill=on if k in SEG.get(ch, "") else ghost, width=wdt)
    if ch == "/":
        d.line([(x + w * .1, y + h), (x + w * .9, y)], fill=on, width=wdt)


def lcd_frame(title_y=200):
    im = Image.new("RGB", (W, H), (28, 26, 30))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([20, 120, W - 20, H - 120], 60, fill=(196, 40, 40))  # the plastic shell
    d.rounded_rectangle([50, 150, W - 50, H - 150], 40, fill=(240, 226, 196))  # printed faceplate
    d.text((90, 185), "SIXEL SPEEDWAY", font=font("bungee", 66), fill=(196, 40, 40))
    d.text((92, 270), "GAME & BET  ·  6 CAR", font=font("inter", 32), fill=(40, 40, 40))
    d.rounded_rectangle([80, 330, W - 80, 1460], 24, fill=(60, 60, 64))
    d.rectangle([110, 360, W - 110, 1430], fill=LCD_BG)
    return im, d


def lcd_race():
    im, d = lcd_frame()
    lanes_x = [150 + i * 135 for i in range(6)]
    rows = [1300 - r * 105 for r in range(9)]  # 9 fixed segment positions per lane
    pos = {3: 8, 1: 7, 6: 7, 4: 6, 2: 5, 5: 3}
    for lane, (n, _) in enumerate(CARS):
        for r, y in enumerate(rows):
            on = pos[n] == r
            col = LCD_ON if on else LCD_GHOST
            x = lanes_x[lane]
            d.rectangle([x + 20, y, x + 80, y + 70], outline=col, width=8)  # body
            for wy in (y + 6, y + 50):
                d.rectangle([x + 4, wy, x + 18, wy + 18], fill=col)
                d.rectangle([x + 82, wy, x + 96, wy + 18], fill=col)
        d.ellipse([lanes_x[lane] + 25, 1395, lanes_x[lane] + 75, 1445], fill=PRINT[lane])  # printed lane colour
        d.text((lanes_x[lane] + 38, 1398), str(n), font=font("inter", 34), fill=(255, 255, 255))
    d.text((140, 375), "LAP", font=font("inter", 34), fill=LCD_ON)
    seven(d, 230, 375, "3", h=60, wdt=9)
    seven(d, 290, 375, "/", h=60, wdt=9)
    seven(d, 350, 375, "3", h=60, wdt=9)
    d.text((620, 375), "SPIN!", font=font("inter", 50), fill=LCD_ON)  # icon segment, lit
    d.text((140, 1500), "● ● ●  BEEP  BEEP  BEEP", font=font("inter", 34), fill=(120, 110, 100))
    return lcd_glitch(im, seed=1)


def lcd_card():
    im, d = lcd_frame()
    d.text((140, 380), "BETS OPEN  RACE 15", font=font("inter", 50), fill=LCD_ON)
    for i, (n, name) in enumerate(CARS):
        y = 480 + i * 140
        d.ellipse([140, y + 10, 220, y + 90], fill=PRINT[i])
        d.text((165, y + 22), str(n), font=font("inter", 46), fill=(255, 255, 255))
        d.text((250, y + 25), name, font=font("inter", 44), fill=LCD_ON)
        num, den = ODDS[i].split("/")
        x = 720
        for ch in num.rjust(2) + "/" + den:
            seven(d, x, y + 10, ch, h=72, wdt=10)
            x += 52
    d.text((140, 1350), "COMMENT  CAR + STAKE  →  4 250", font=font("inter", 40), fill=LCD_ON)
    d.text((140, 1500), "PLAY MONEY · NO PRIZES · RACE.ONLYDAN.UK", font=font("inter-md", 30), fill=(90, 80, 70))
    return lcd_glitch(im, seed=2)


def lcd_glitch(im, seed):
    """LCD 'glitches' are slow-pixel smears and a dying-battery fade, not CRT tearing."""
    a = np.asarray(im).astype(np.float32)
    lcd = a[360:1430, 110:W - 110]
    smear = np.roll(lcd, 10, axis=0) * .12 + lcd * .88  # slow-response ghost trail
    a[360:1430, 110:W - 110] = smear
    rng = np.random.default_rng(seed)
    y = int(rng.integers(500, 1300))
    a[y:y + 40, 110:W - 110] = a[y:y + 40, 110:W - 110] * .9 + np.array(LCD_BG) * .1
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


# ================================================================================================
# C. PIT WALL: a TV timing screen. Dark navy, timing tower, live track map with dots and gaps.
# ================================================================================================
NAVY, PANEL = (10, 14, 30), (22, 28, 52)
TEAM = [(232, 52, 52), (40, 200, 110), (250, 205, 40), (60, 120, 255), (240, 80, 190), (30, 210, 230)]


def pit_race():
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    fi, fm, fb = font("inter", 40), font("mono", 38), font("inter", 70)
    d.text((60, 240), "LAP 3 / 3", font=fb, fill=(255, 255, 255))
    d.text((60, 325), "RACE 14 · SIXEL SPEEDWAY", font=font("inter-md", 32), fill=(140, 150, 190))
    d.rounded_rectangle([700, 245, 950, 315], 14, fill=(250, 205, 40))
    d.text((725, 254), "YELLOW", font=fi, fill=NAVY)
    trk = circuit(540, 760, 400, 330, seed=7)
    d.line(trk + [trk[0]], fill=(60, 70, 110), width=46, joint="curve")
    d.line(trk + [trk[0]], fill=(150, 160, 200), width=6, joint="curve")
    for s, colr in ((0, (180, 80, 255)), (1, (40, 200, 110)), (2, (250, 205, 40))):  # sector colours
        seg = trk[s * 200:(s + 1) * 200]
        d.line(seg, fill=colr, width=10)
    (sx, sy), ang = at(trk, 0)
    d.line([(sx - 30 * math.sin(ang), sy + 30 * math.cos(ang)), (sx + 30 * math.sin(ang), sy - 30 * math.cos(ang))],
           fill=(255, 255, 255), width=8)
    for n, frac in PROGRESS.items():
        (x, y), _ = at(trk, frac)
        d.ellipse([x - 28, y - 28, x + 28, y + 28], fill=TEAM[n - 1], outline=(255, 255, 255), width=4)
        d.text((x - 10, y - 22), str(n), font=font("inter", 34), fill=NAVY if n in (2, 3, 6) else (255, 255, 255))
    gaps = ["LEADER", "+0.21", "+0.64", "+1.90", "+2.44", "+4.87"]
    for i, n in enumerate(ORDER):  # timing tower
        y = 1200 + i * 52 - 0
        d.rectangle([60, y, 940, y + 46], fill=PANEL if i % 2 else (28, 36, 66))
        d.text((76, y + 2), f"{i + 1}", font=fm, fill=(255, 255, 255))
        d.rectangle([126, y + 6, 136, y + 40], fill=TEAM[n - 1])
        d.text((156, y + 2), CARS[n - 1][1], font=font("inter", 34), fill=(255, 255, 255))
        d.text((720, y + 2), gaps[i].rjust(7), font=fm, fill=(180, 80, 255) if i == 2 else (200, 205, 230))
    d.rectangle([60, 1140, 940, 1190], fill=(240, 80, 190))
    d.text((80, 1143), "5 HOT PINK · SPIN AT TURN 4", font=font("inter", 36), fill=(255, 255, 255))
    return dropout(im, seed=3)


def pit_card():
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    fm = font("mono", 40)
    d.text((60, 240), "BETS OPEN", font=font("inter", 80), fill=(255, 255, 255))
    d.text((60, 335), "RACE 15 · CLOSES 18:00 TOMORROW", font=font("inter-md", 34), fill=(140, 150, 190))
    d.text((60, 420), "CAR", font=font("inter-md", 28), fill=(120, 130, 170))
    d.text((640, 420), "ODDS   FORM", font=font("inter-md", 28), fill=(120, 130, 170))
    for i, (n, name) in enumerate(CARS):
        y = 470 + i * 112
        d.rounded_rectangle([60, y, 940, y + 96], 16, fill=PANEL)
        d.rounded_rectangle([60, y, 84, y + 96], 8, fill=TEAM[i])
        d.text((110, y + 20), f"{n}  {name}", font=font("inter", 44), fill=(255, 255, 255))
        d.text((640, y + 24), ODDS[i].rjust(4), font=fm, fill=(250, 205, 40))
        for j, c in enumerate(FORM[i]):  # form as little position chips
            d.rounded_rectangle([780 + j * 30, y + 30, 804 + j * 30, y + 66], 5,
                                fill=(180, 80, 255) if c == "1" else (60, 70, 110))
            d.text((785 + j * 30, y + 30), c, font=font("inter-md", 26), fill=(255, 255, 255))
    d.rounded_rectangle([60, 1180, 940, 1400], 24, fill=(250, 205, 40))
    d.text((100, 1205), "COMMENT CAR + STAKE", font=font("inter", 40), fill=NAVY)
    d.text((100, 1265), "4 250", font=font("inter", 110), fill=NAVY)
    d.text((470, 1300), "= §250 on\nBLUE STREAK", font=font("inter", 40), fill=NAVY)
    d.text((60, 1430), "Play money · no prizes · race.onlydan.uk", font=font("inter-md", 32), fill=(140, 150, 190))
    return dropout(im, seed=4)


def dropout(im, seed):
    """Broadcast glitch: a block of the picture freezes/offsets like a dropped satellite feed."""
    a = np.asarray(im).copy()
    rng = np.random.default_rng(seed)
    for _ in range(3):
        y, x = int(rng.integers(300, 1500)), int(rng.integers(0, 800))
        h, w = int(rng.integers(16, 40)), int(rng.integers(160, 400))
        a[y:y + h, x:x + w] = np.roll(a[y:y + h, x:x + w], int(rng.integers(20, 60)), axis=1)
        blk = a[y:y + h, x:x + w].astype(np.int16)
        a[y:y + h, x:x + w] = np.clip(blk // 16 * 16 + 20, 0, 255).astype(np.uint8)  # macroblocking
    return Image.fromarray(a)


# ================================================================================================
# D. 16-BIT: top-down pixel-art racer (Super Sprint / Micro Machines vintage). Native 180x320, x6.
# ================================================================================================
PX = [(224, 56, 56), (56, 184, 72), (248, 208, 48), (56, 96, 232), (232, 88, 184), (56, 208, 224)]


def sprite_car(d, x, y, col, sc=2):
    body = [".XXX.", "XWWWX", "XXXXX", "KXXXK", "KXXXK", "XXXXX", "XXXXX", "KXXXK", ".XXX."]
    pal = {"X": col, "W": (200, 230, 255), "K": (20, 20, 20)}
    for j, line in enumerate(body):
        for i, c in enumerate(line):
            if c in pal:
                d.rectangle([x + i * sc, y + j * sc, x + i * sc + sc - 1, y + j * sc + sc - 1], fill=pal[c])


def bit_race():
    im = Image.new("RGB", (180, 320), (72, 152, 56))
    d = ImageDraw.Draw(im)
    for y in range(0, 320, 2):  # grass dither
        for x in range((y // 2) % 4, 180, 4):
            d.point((x, y), fill=(60, 132, 48))
    d.rectangle([30, 40, 150, 320], fill=(88, 88, 96))
    for y in range(40, 320, 6):
        d.rectangle([26, y, 29, y + 2], fill=(224, 56, 56))
        d.rectangle([26, y + 3, 29, y + 5], fill=(240, 240, 240))
        d.rectangle([151, y, 154, y + 2], fill=(224, 56, 56))
        d.rectangle([151, y + 3, 154, y + 5], fill=(240, 240, 240))
    for y in range(40, 320, 16):
        for lane in range(1, 6):
            d.rectangle([30 + lane * 20, y, 30 + lane * 20, y + 7], fill=(150, 150, 160))
    for x in range(30, 150, 2):  # tyre wall top + crowd
        d.ellipse([x, 30, x + 4, 34], fill=(30, 30, 30))
    for x in range(0, 180, 3):
        d.point((x, 22 + (x * 7) % 5), fill=PX[x % 6])
    ys = {3: 120, 1: 132, 6: 141, 4: 170, 2: 196, 5: 236}
    for lane, (n, _) in enumerate(CARS):
        sprite_car(d, 35 + lane * 20, ys[n], PX[lane])
    d.ellipse([120, 228, 140, 240], fill=(30, 20, 40))  # oil
    for i in range(6):
        d.point((128 + i, 247 + i % 2), fill=(200, 200, 200))  # skid smoke
    big = im.resize((W, H), Image.NEAREST)
    bd = ImageDraw.Draw(big)
    hud = ImageFont.load_default_imagefont()
    hudim = Image.new("RGBA", (180, 320), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hudim)
    hd.rectangle([0, 0, 180, 20], fill=(16, 16, 40, 255))
    hd.text((4, 4), "LAP 3/3", font=hud, fill=(248, 208, 48))
    for i, n in enumerate(ORDER):
        hd.rectangle([70 + i * 18, 4, 84 + i * 18, 16], fill=PX[n - 1] + (255,))
        hd.text((75 + i * 18, 5), str(n), font=hud, fill=(0, 0, 0))
    hd.rectangle([20, 250, 160, 266], fill=(232, 88, 184, 255))
    hd.text((40, 253), "HOT PINK SPINS!", font=hud, fill=(255, 255, 255))
    hudim = hudim.resize((W, H), Image.NEAREST)
    big.paste(hudim, (0, 0), hudim)
    return soft_crt(big)


def bit_card():
    im = Image.new("RGB", (180, 320), (24, 24, 56))
    d = ImageDraw.Draw(im)
    hud = ImageFont.load_default_imagefont()
    d.rectangle([0, 40, 180, 58], fill=(248, 208, 48))
    d.text((8, 44), "BETS OPEN - RACE 15", font=hud, fill=(24, 24, 56))
    for i, (n, name) in enumerate(CARS):
        y = 66 + i * 22
        sprite_car(d, 8, y + 2, PX[i], sc=1)
        d.text((20, y + 6), f"{n} {name}", font=hud, fill=(255, 255, 255))
        d.text((128, y + 6), ODDS[i].rjust(4), font=hud, fill=(248, 208, 48))
        d.line([(8, y + 19), (172, y + 19)], fill=(48, 48, 96))
    d.rectangle([8, 204, 172, 236], fill=(56, 96, 232))
    d.text((14, 208), "COMMENT CAR + STAKE", font=hud, fill=(255, 255, 255))
    d.text((14, 221), "e.g.  4 250", font=hud, fill=(248, 208, 48))
    d.text((8, 242), "PLAY MONEY. NO PRIZES.", font=hud, fill=(232, 88, 184))
    return soft_crt(im.resize((W, H), Image.NEAREST))


def soft_crt(im):
    """A lighter touch than the teletext pass: faint 6 px scanlines and a little bloom only."""
    a = np.asarray(im).astype(np.float32)
    y = np.arange(H)[:, None, None]
    a *= .82 + .18 * (np.cos(2 * np.pi * y / 6) ** 2)
    b = np.asarray(im.filter(ImageFilter.GaussianBlur(10))).astype(np.float32)
    return Image.fromarray(np.clip(a * .95 + b * .25, 0, 255).astype(np.uint8))


STYLES = [("a-vector", "Vector arcade", vector_race, vector_card),
          ("b-lcd", "Handheld LCD", lcd_race, lcd_card),
          ("c-pitwall", "Pit wall", pit_race, pit_card),
          ("d-16bit", "16-bit top-down", bit_race, bit_card)]


def main():
    OUT.mkdir(exist_ok=True)
    tw, th = 300, 533
    sheet = Image.new("RGB", (len(STYLES) * (tw * 2 + 30) + 10, th + 90), (18, 18, 18))
    sd = ImageDraw.Draw(sheet)
    for i, (slug, label, race, card) in enumerate(STYLES):
        x0 = 10 + i * (tw * 2 + 30)
        sd.text((x0, 18), label.upper(), font=font("inter", 34), fill=(255, 255, 255))
        for j, fn in enumerate((race, card)):
            img = fn()
            img.save(OUT / f"{slug}-{'race' if j == 0 else 'card'}.jpg", quality=88)
            sheet.paste(img.resize((tw, th), Image.LANCZOS), (x0 + j * (tw + 10), 70))
    sheet.save(OUT / "styles-sheet.jpg", quality=90)


if __name__ == "__main__":
    main()
