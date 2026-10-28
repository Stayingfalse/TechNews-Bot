"""Mock-up screens for the RACEFAX channel (docs/RACING_PLAN.md). Not app code: a throwaway
sketch of the look, so the plan has pictures. Run: python docs/racing/mockup.py [--clip]

A portrait teletext page: 30 columns x 32 rows of 36x60 px cells (the real 12:20 cell, scaled),
2x3 mosaic "sixels" of 18x20 px, the 8 teletext colours, Bedstead (public domain SAA5050 clone),
then a CRT pass: glitch bands, colour fringing, bloom, scanlines, aperture grille, curvature."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
OUT = HERE / "screens"
FONT = ImageFont.truetype(str(HERE / "Bedstead.otf"), 60)
W, H, CW, CH, COLS, ROWS = 1080, 1920, 36, 60, 30, 32
SW, SH = CW // 2, CH // 3  # sixel

K, R, G, Y, B, M, C, WH = ((0, 0, 0), (255, 0, 0), (0, 255, 0), (255, 255, 0), (0, 0, 255), (255, 0, 255),
                           (0, 255, 255), (255, 255, 255))
CARS = [(1, "RED ROCKET", R), (2, "MEAN GREEN", G), (3, "CUSTARD", Y), (4, "BLUE STREAK", B),
        (5, "HOT PINK", M), (6, "CYANARA", C)]


class Page:
    def __init__(self):
        self.im = Image.new("RGB", (W, H), K)
        self.d = ImageDraw.Draw(self.im)

    def bg(self, c, r, w, h, col):
        self.d.rectangle([c * CW, r * CH, (c + w) * CW - 1, (r + h) * CH - 1], fill=col)

    def px(self, x, y, col, sep=False):
        g = 3 if sep else 0
        self.d.rectangle([x * SW + g, y * SH + g, (x + 1) * SW - 1, (y + 1) * SH - 1], fill=col)

    def text(self, c, r, s, fg=WH, bg=None, dh=False):
        for i, ch in enumerate(s):
            cell = Image.new("RGB", (CW, CH), bg or K)
            if ch != " ":
                ImageDraw.Draw(cell).text((0, 0), ch, font=FONT, fill=fg)
            if dh:
                cell = cell.resize((CW, CH * 2), Image.NEAREST)
            if bg is None:  # transparent: paste glyph pixels only
                mask = cell.convert("L").point(lambda v: 255 if v > 40 else 0)
                self.im.paste(cell, ((c + i) * CW, r * CH), mask)
            else:
                self.im.paste(cell, ((c + i) * CW, r * CH))

    def sprite(self, x, y, rows, pal, sep=False):
        for j, line in enumerate(rows):
            for i, ch in enumerate(line):
                if ch in pal:
                    self.px(x + i, y + j, pal[ch], sep)

    def header(self, page, title="RACEFAX", clock="19:00/07"):
        self.text(0, 3, f"P{page}", WH)
        self.text(5, 3, title, Y, B)
        self.text(5 + len(title), 3, f" {page}", C)
        self.text(17, 3, "WED 28 OCT", WH)
        self.text(17, 4, clock, Y)

    def footer(self):
        """Below the safe area (captions cover it): a chequered strip so the page doesn't look top-heavy."""
        for x in range(60):
            for y in range(78, 84):
                if (x // 2 + y // 2) % 2:
                    self.px(x, y, WH)

    def fastext(self, r=23):
        for c, (label, col) in zip((0, 7, 14, 21), (("RACE", R), ("BETS", G), ("TABLE", Y), ("HELP", C))):
            self.text(c, r, label, col)


# ---- sprites (sixels) ---------------------------------------------------------------------------
SIDE_CAR = [
    "XXXX                                        ",
    "XXXX                  HHH                   ",
    " XX                  HHHHH                  ",
    " XX        XXXXXXXXXXXXXXXXXX               ",
    "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX        ",
    "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX  ",
    "XXXWWWWWWXXXXXXXXXXXXXXXXXXXXXXXWWWWWWXXXXXX",
    "  WWWWWWWW                    WWWWWWWW XXXX ",
    "  WWW  WWW                    WWW  WWW      ",
    "  WWWWWWWW                    WWWWWWWW      ",
    "   WWWWWW                      WWWWWW       ",
]
TOP_CAR = [".XX.", "WXXW", ".XX.", ".XX.", "WXXW", ".XX."]
FLAG = ["WWKKWWKK", "WWKKWWKK", "KKWWKKWW", "KKWWKKWW", "WWKKWWKK", "WWKKWWKK"]


MINI_CAR = ["   XX     ", "XXXXXXXXXX", " W     W  "]


def small_digit(p: Page, x, y, ch, col):
    font = {"1": [".X.", "XX.", ".X.", ".X.", ".X.", ".X.", "XXX"],
            "2": ["XX.", "..X", "..X", ".X.", "X..", "X..", "XXX"],
            "3": ["XX.", "..X", "..X", "XX.", "..X", "..X", "XX."]}[ch]
    for j, line in enumerate(font):
        for i, v in enumerate(line):
            if v == "X":
                p.px(x + i, y + j, col)


def big_digit(p: Page, x, y, ch, col):
    """A digit drawn in sixels, 5x7 font scaled x2 (the way teletext pages faked big type)."""
    font = {"1": ["..X..", ".XX..", "..X..", "..X..", "..X..", "..X..", ".XXX."],
            "2": [".XXX.", "X...X", "....X", "..XX.", ".X...", "X....", "XXXXX"],
            "3": ["XXXX.", "....X", "....X", ".XXX.", "....X", "....X", "XXXX."],
            "4": ["...X.", "..XX.", ".X.X.", "X..X.", "XXXXX", "...X.", "...X."]}[ch]
    for j, line in enumerate(font):
        for i, v in enumerate(line):
            if v == "X":
                for dx in (0, 1):
                    for dy in (0, 1):
                        p.px(x + i * 2 + dx, y + j * 2 + dy, col)


def track(p: Page, top_row: int, scroll: int):
    """A straight seen from above: grass, red/white kerbs, six lanes with blue dashes."""
    y0, y1 = top_row * 3, ROWS * 3
    for y in range(y0, y1):
        for x in list(range(0, 6)) + list(range(46, 60)):
            if (x * 7 + y * 3 + scroll) % 5 < 2:
                p.px(x, y, G, sep=True)
        kerb = R if ((y + scroll) // 2) % 2 else WH
        for x in (6, 7, 44, 45):
            p.px(x, y, kerb)
        if ((y + scroll) // 2) % 3 == 0:
            for lane in range(1, 6):
                p.px(8 + lane * 6, y, B)


def lane_x(lane):
    return 8 + lane * 6 + 1  # sixel x of a car in lane 0-5


# ---- screens ------------------------------------------------------------------------------------
def s1_hook():
    p = Page()
    p.header(301)
    p.bg(0, 6, 30, 2, R)
    p.text(1, 6, "TONIGHT'S RACE", Y, R, dh=True)
    p.text(1, 9, "§48,200", C, dh=True)
    p.text(9, 9, "RIDING ON", WH, dh=True)
    p.text(1, 11, "ONE RACE.", WH, dh=True)
    p.sprite(6, 40, SIDE_CAR, {"X": R, "W": WH, "H": Y})
    for i in range(16):  # speed lines
        p.px(1 + (i % 3), 44 + i // 3 * 1, WH if i % 2 else R)
    p.text(1, 17, "312 PUNTERS", G)
    p.text(13, 17, "6 CARS", Y)
    p.text(1, 18, "ONLY 9 OF YOU", WH)
    p.text(1, 19, "BACKED THE OUTSIDER", WH)
    p.text(1, 21, "OFF IN 3...", M, dh=True)
    p.fastext()
    return p


def s2_grid():
    p = Page()
    p.header(302, clock="19:00/09")
    p.text(1, 6, "RACE 14  3 LAPS", WH)
    p.bg(4, 8, 22, 4, K)
    gantry = 4 * 2
    for i in range(5):  # five red lights, all lit
        x = gantry + 1 + i * 8
        for dx in range(5):
            for dy in range(5):
                if (dx, dy) not in ((0, 0), (4, 0), (0, 4), (4, 4)):
                    p.px(x + dx, 26 + dy, R)
    for x in range(8, 52):
        p.px(x, 24, WH)
        p.px(x, 32, WH)
    p.text(3, 12, "LIGHTS OUT IN", WH)
    p.text(17, 12, "5", R, dh=True)
    track(p, 14, 0)
    for x in range(8, 44):  # chequered start line
        p.px(x, 46, WH if (x // 1) % 2 else K)
        p.px(x, 47, K if (x // 1) % 2 else WH)
    for lane, (n, _, col) in enumerate(CARS):
        y = 49 + (lane % 2) * 7
        p.sprite(lane_x(lane), y, TOP_CAR, {"X": col, "W": WH})
        c = (lane_x(lane) + 1) // 2
        p.bg(c, 21, 1, 1, col)
        p.text(c, 21, str(n), K if col not in (B, R, M) else WH, col)
    return p


def s3_race():
    p = Page()
    p.header(302, clock="19:00/21")
    p.text(1, 6, "LAP 3/3", Y, dh=True)
    order = [3, 1, 6, 4, 2, 5]
    for i, n in enumerate(order):
        col = CARS[n - 1][2]
        p.bg(10 + i * 3, 6, 2, 2, col)
        p.text(10 + i * 3, 6, str(n), K if col not in (B, R, M) else WH, col, dh=True)
    track(p, 9, 2)
    heights = {3: 34, 1: 38, 6: 41, 4: 50, 2: 58, 5: 62}
    for lane, (n, _, col) in enumerate(CARS):
        y = heights[n]
        p.sprite(lane_x(lane), y, TOP_CAR, {"X": col, "W": WH})
        for t in range(1, 4):  # exhaust trail
            if t % 2:
                p.px(lane_x(lane) + 1 + t % 2, y + 6 + t, WH, sep=True)
    for dx in range(4):  # oil slick in lane 5
        for dy in range(3):
            if (dx + dy) % 3:
                p.px(lane_x(4) + dx, 52 + dy, M, sep=True)
    p.bg(1, 19, 24, 2, M)
    p.text(2, 19, "HOT PINK SPINS!", WH, M, dh=True)
    return p


def s4_result():
    p = Page()
    p.header(303, clock="19:00/34")
    p.bg(0, 6, 30, 2, B)
    p.text(1, 6, "RESULT  RACE 14", Y, B, dh=True)
    # podium 2-1-3, each step with its car on top
    for c, top, col, num, digit in ((3, 14, WH, "2", 1), (10, 12, WH, "1", 3), (17, 15, WH, "3", 6)):
        p.bg(c, top, 6, 17 - top, col)
        small_digit(p, c * 2 + 4, top * 3 + 1, num, K)
        p.sprite(c * 2 + 1, top * 3 - 3, MINI_CAR, {"X": CARS[digit - 1][2], "W": WH})
    p.text(1, 8, "WINNER  3 CUSTARD", Y)
    p.text(1, 9, "AT 12/1", WH)
    p.text(1, 10, "2ND 1 RED ROCKET", WH)
    p.text(1, 18, "37 OF 312 BACKED IT", G)
    p.text(1, 19, "BIGGEST WIN", C)
    p.text(13, 19, "@TURBO_TESS", WH)
    p.text(1, 20, "+§2,600", Y, dh=True)
    p.text(10, 20, "ON §200", WH)
    p.text(1, 22, "BUST: 11 PUNTERS", R)
    p.fastext()
    return p


def s5_card():
    p = Page()
    p.header(304, clock="19:00/41")
    p.bg(0, 6, 30, 2, G)
    p.text(1, 6, "BETS OPEN RACE 15", K, G, dh=True)
    p.text(1, 8, "NO CAR         ODDS FORM", C)
    odds = ["2/1", "4/1", "9/2", "6/1", "8/1", "12/1"]
    form = ["21134", "43521", "16236", "32415", "54652", "65163"]
    for i, (n, name, col) in enumerate(CARS):
        r = 9 + i
        p.bg(1, r, 1, 1, col)
        p.text(1, r, str(n), K if col not in (B, R, M) else WH, col)
        p.text(3, r, name, col if col != B else C)
        p.text(15, r, odds[i].rjust(4), WH)
        p.text(20, r, form[i], Y)
    p.bg(0, 16, 30, 4, B)
    p.text(1, 16, "COMMENT CAR + STAKE", WH, B)
    p.text(1, 17, "    4 250", Y, B, dh=True)
    p.text(12, 17, "= §250 ON", WH, B)
    p.text(12, 18, "BLUE STREAK", C, B)
    p.text(1, 20, "NEW HERE? YOU GET §1,000", G)
    p.text(1, 21, "BETS CLOSE 18:00 TOMORROW", WH)
    p.text(1, 22, "PLAY MONEY. NO PRIZES.", M)
    p.fastext()
    return p


def s6_table():
    p = Page()
    p.header(399, clock="19:00/05")
    p.bg(0, 6, 30, 2, Y)
    p.text(1, 6, "LEAGUE TABLE WK 43", B, Y, dh=True)
    rows = [("@TURBO_TESS", "14,820", "+", G), ("@GRAN_PRIX", "9,310", "+", G), ("@PITSTOP_PETE", "7,045", "-", R),
            ("@NANA_NITRO", "5,900", "+", G), ("@SLOWLANE", "4,120", "=", WH), ("@CHEQUERED", "3,775", "+", G),
            ("@DIESELDAVE", "3,010", "-", R), ("@VROOMVROOM", "2,480", "+", G), ("@BRAKEFAST", "2,205", "-", R),
            ("@LAPDANCER99", "1,990", "+", G)]
    p.text(1, 8, "POS PUNTER          §   ", C)
    for i, (name, bal, mv, col) in enumerate(rows):
        r = 9 + i
        fg = Y if i < 3 else WH
        p.text(1, r, f"{i + 1:>2}", fg)
        p.text(4, r, name, fg)
        p.text(18, r, bal.rjust(6), fg)
        p.text(25, r, {"+": "^", "-": "v", "=": "-"}[mv], col)
    p.text(1, 20, "CLIMBER @NANA_NITRO +4,100", G)
    p.text(1, 21, "1,204 PUNTERS  46 BUST", WH)
    p.text(1, 22, "RESETS? NEVER. TABLE SUN.", M)
    p.fastext()
    return p


# ---- CRT ----------------------------------------------------------------------------------------
def crt(img: Image.Image, seed: int, glitch: float = 1.0) -> Image.Image:
    rng = np.random.default_rng(seed)
    a = np.asarray(img).astype(np.float32) / 255
    for _ in range(int(3 * glitch)):  # tearing bands
        y = rng.integers(200, H - 200)
        h = int(rng.integers(6, 40))
        a[y:y + h] = np.roll(a[y:y + h], int(rng.integers(-60, 60) * glitch), axis=1)
    if glitch >= 1:  # one band with the colour split wide open
        y = rng.integers(300, H - 300)
        a[y:y + 24, :, 0] = np.roll(a[y:y + 24, :, 0], 18, axis=1)
        a[y:y + 24, :, 2] = np.roll(a[y:y + 24, :, 2], -18, axis=1)
    a[..., 0] = np.roll(a[..., 0], -3, axis=1)  # fringing
    a[..., 2] = np.roll(a[..., 2], 3, axis=1)
    glow = Image.fromarray((a * 255).astype(np.uint8)).resize((W // 4, H // 4), Image.BILINEAR)
    glow = glow.filter(ImageFilter.GaussianBlur(6)).resize((W, H), Image.BILINEAR)
    a = a * 0.92 + np.asarray(glow).astype(np.float32) / 255 * 0.55
    y = np.arange(H)[:, None, None]
    a *= 0.72 + 0.28 * np.cos(2 * np.pi * y / 6) ** 2  # scanlines, 6 px period
    x = np.arange(W)
    grille = np.full((W, 3), 0.86, np.float32)
    grille[np.arange(W), x % 3] = 1.0
    a *= grille[None]
    bar = (np.arange(H) - rng.integers(0, H)) % H  # slow rolling hum bar
    a *= (1 + 0.06 * np.exp(-((bar - 120) / 90.0) ** 2))[:, None, None]
    a += rng.normal(0, 0.025, a.shape[:2])[..., None]
    # curvature: sample from a barrel-distorted grid
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx, ny = (xx / W - 0.5) * 2, (yy / H - 0.5) * 2
    r2 = nx * nx * 0.55 + ny * ny * 0.3
    sx = ((nx * (1 + 0.06 * r2)) / 2 + 0.5) * (W - 1)
    sy = ((ny * (1 + 0.06 * r2)) / 2 + 0.5) * (H - 1)
    inside = (sx >= 0) & (sx <= W - 1) & (sy >= 0) & (sy <= H - 1)
    a = a[np.clip(sy, 0, H - 1).astype(int), np.clip(sx, 0, W - 1).astype(int)]
    a[~inside] = 0
    vig = 1 - 0.45 * (nx ** 2 * 0.6 + ny ** 2 * 0.4) ** 1.5
    a *= np.clip(vig, 0, 1)[..., None]
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def safe_zone(img: Image.Image) -> Image.Image:
    """The race card with the Reels/Shorts overlays shaded, to check nothing important hides there."""
    o = img.convert("RGBA")
    d = ImageDraw.Draw(o, "RGBA")
    shade = (255, 255, 255, 70)
    d.rectangle([0, 0, W, 4 * CH - 1], fill=shade)
    d.rectangle([0, 24 * CH, W, H], fill=shade)
    d.rectangle([26 * CW, 0, W, H], fill=shade)
    d.text((40, 24 * CH + 40), "caption / buttons", font=FONT, fill=(255, 255, 255, 200))
    return o.convert("RGB")


SCREENS = [("1-hook", s1_hook), ("2-grid", s2_grid), ("3-race", s3_race), ("4-result", s4_result),
           ("5-race-card", s5_card), ("6-league-table", s6_table)]


def main():
    OUT.mkdir(exist_ok=True)
    shots = []
    for i, (name, fn) in enumerate(SCREENS):
        page = fn()
        if name not in ("2-grid", "3-race"):
            page.footer()
        raw = page.im
        shot = crt(raw, seed=i, glitch={"3-race": 1.0, "1-hook": 0.4}.get(name, 0.0))
        shot.save(OUT / f"{name}.jpg", quality=88)
        shots.append(shot)
        if name == "5-race-card":
            safe_zone(shot).save(OUT / "safe-zones.jpg", quality=85)
    tw = 360
    sheet = Image.new("RGB", (tw * 3 + 40, (H * tw // W) * 2 + 30), (20, 20, 20))
    for i, s in enumerate(shots):
        sheet.paste(s.resize((tw, H * tw // W), Image.LANCZOS), (10 + (i % 3) * (tw + 10), 10 + (i // 3) * (H * tw // W + 10)))
    sheet.save(OUT / "contact-sheet.jpg", quality=90)
    if "--clip" in sys.argv:
        clip()


def clip():
    """Four seconds of the race at 30 fps (silent), to judge the motion, glitches and scanlines."""
    frames = HERE / ".frames"
    frames.mkdir(exist_ok=True)
    speed = [1.00, 0.97, 1.03, 0.95, 0.92, 0.99]
    for f in range(120):
        p = Page()
        p.header(302, clock=f"19:00/{21 + f // 30:02d}")
        p.text(1, 6, "LAP 3/3", Y, dh=True)
        track(p, 9, f)
        for lane, (n, _, col) in enumerate(CARS):
            y = int(62 - f * 0.18 * speed[lane] - lane * 2 * (lane % 2)) - (f * speed[lane] * 0.05) % 2
            y = max(29, int(y))
            p.sprite(lane_x(lane), y, TOP_CAR, {"X": col, "W": WH})
        g = 1.0 if f % 37 < 3 else 0.0
        crt(p.im, seed=f, glitch=g).save(frames / f"{f:04d}.png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-i", str(frames / "%04d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", str(OUT / "race-motion-test.mp4")], check=True)
    for fp in frames.iterdir():
        fp.unlink()
    frames.rmdir()


if __name__ == "__main__":
    main()
