"""Pit wall: a TV timing screen. Dark navy, a live track map with numbered car dots, a timing tower
that reorders on overtakes, flags, and broadcast dropouts for glitches. Motorsport TV in feel,
with no real series' names, logos, fonts or colours.

Every format is drawn on the race's own generated track. Drag races get a lane view with a
"tree" of start lights, reaction times and elapsed times; endurance races get a pit lane, tyre
wear bars and a speed-up badge; figure 8s mark the crossing."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .base import FPS, H, SAFE, W, Theme, fit_track, font, point_at

NAVY, PANEL, PANEL2 = (10, 14, 30), (22, 28, 52), (28, 36, 66)
MUTED, DIM, WHITE = (140, 150, 190), (60, 70, 110), (255, 255, 255)
YELLOW, PURPLE, GREEN, RED, AMBER = (250, 205, 40), (180, 80, 255), (40, 200, 110), (232, 52, 52), (255, 150, 30)
COLOURS = {"red": (232, 52, 52), "green": (40, 200, 110), "yellow": (250, 205, 40), "blue": (60, 120, 255),
           "magenta": (240, 80, 190), "cyan": (30, 210, 230)}
DARK_TEXT = {"green", "yellow", "cyan"}  # colours that need dark type on them
X0, X1 = SAFE[0] + 12, SAFE[2] - 6  # text column
MAP_BOX = (110, 390, 970, 1090)  # where the track map goes
TOWER_Y, ROW = 1150, 48
LANES_Y = (1060, 420)  # drag strip: start line, finish line
EVENTS = {"spin": "SPINS!", "blowup": "ENGINE FAILURE", "puncture": "PUNCTURE", "tangle": "TANGLE AT THE CROSSING",
          "jumpstart": "JUMP START · OUT", "pit": "PITS"}
YELLOW_FLAG = {"spin", "blowup", "puncture", "tangle"}


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def lane_x(j: int) -> float:
    return 255 + j * 114


class PitWall(Theme):
    name = "pitwall"
    sound = {"bed": "pulse", "blip": 1800}

    def __init__(self, spec: dict, record: bool = False):
        super().__init__(spec, record)
        self.bg = self._background()
        if self.race:
            self.drag = self.race["format"]["launch"]
            self.closed = self.race["track"].get("closed", True)
            self.track = fit_track(self.race["track"]["pts"], MAP_BOX)
            self.map = self._strip() if self.drag else self._map()

    # ---------------------------------------------------------------- static layers
    def _background(self) -> Image.Image:
        im = Image.new("RGB", (W, H), NAVY)
        d = ImageDraw.Draw(im)
        for y in range(0, H, 60):  # faint broadcast grid
            d.line([(0, y), (W, y)], fill=(14, 19, 40), width=1)
        for x in range(0, W, 60):
            d.line([(x, 0), (x, H)], fill=(14, 19, 40), width=1)
        return im

    def _map(self) -> Image.Image:
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        draw_track(d, self.track, full=True)
        fmt = self.race["format"]
        x, y, a = point_at(self.track, 0)
        nx, ny = -math.sin(a), math.cos(a)
        if fmt["pits"]:  # the pit lane, inside the start straight
            p0, p1 = point_at(self.track, -0.035), point_at(self.track, 0.035)
            off = 40
            d.line([(p0[0] + off * -math.sin(p0[2]), p0[1] + off * math.cos(p0[2])),
                    (p1[0] + off * -math.sin(p1[2]), p1[1] + off * math.cos(p1[2]))], fill=(90, 100, 140), width=8)
        if fmt["cross"]:  # the crossing (where the lap starts, too)
            cx, cy, _ = point_at(self.track, 0.0)
            d.ellipse([cx - 44, cy - 44, cx + 44, cy + 44], outline=RED, width=5)
        d.line([(x - 34 * nx, y - 34 * ny), (x + 34 * nx, y + 34 * ny)], fill=WHITE, width=10)
        return im

    def _strip(self) -> Image.Image:
        """A drag strip: six lanes from the start (bottom) to the finish (top)."""
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        y0, y1 = LANES_Y
        d.rectangle([lane_x(0) - 57, y1 - 20, lane_x(5) + 57, y0 + 20], fill=(30, 36, 64))
        for j in range(7):
            x = lane_x(0) - 57 + j * 114
            for y in range(y1, y0, 40):
                d.line([(x, y), (x, y + 20)], fill=(90, 100, 140), width=3)
        d.line([(lane_x(0) - 57, y0), (lane_x(5) + 57, y0)], fill=WHITE, width=6)
        for i in range(24):  # chequered finish line
            for k in range(2):
                c = WHITE if (i + k) % 2 else (20, 20, 20)
                xa = lane_x(0) - 57 + i * 28.5
                d.rectangle([xa, y1 - 16 + k * 14, xa + 28.5, y1 - 2 + k * 14], fill=c)
        return im

    # ---------------------------------------------------------------- common pieces
    def header(self, d: ImageDraw.ImageDraw, right: str = "") -> None:
        self.text(d, (X0, 252), "SIXEL SPEEDWAY", font("semi", 30), MUTED)
        if right:
            self.text(d, (X1, 252), right, self.fit(right, "semi", 30, 480), MUTED, anchor="ra")

    def pill(self, d, x1: int, y: int, label: str, fill, ink=NAVY) -> None:
        f = font("bold", 34)
        w = f.getlength(label)
        d.rounded_rectangle([x1 - w - 44, y, x1, y + 58], 14, fill=fill)
        self.text(d, (x1 - 22, y + 29), label, f, ink, anchor="rm")

    def car_name(self, no: int) -> str:
        return f"{no} {self.car(no)['name']}"

    def colour(self, no: int):
        return COLOURS[self.car(no)["colour"]]

    def ink_on(self, no: int):
        return NAVY if self.car(no)["colour"] in DARK_TEXT else WHITE

    def race_line(self, r: dict) -> str:
        fmt = r["format"]
        laps = f"{fmt['laps']} LAPS" if fmt["laps"] > 1 else "1/4 MILE"
        return f"{fmt['name'].upper()} · {laps}"

    def accent_line(self, d, y: int, line: str, size: int, x: int = X0, appear: float = 1.0) -> None:
        """A hook line where *starred* words are yellow; slides in as `appear` goes 0 → 1."""
        plain = line.replace("*", "")
        f = self.fit(plain, "black", size, X1 - X0)
        x = x - int(60 * (1 - ease(appear)))
        if appear <= 0:
            return
        for i, part in enumerate(line.split("*")):
            if part:
                self.text(d, (x, y), part, f, YELLOW if i % 2 else WHITE)
                x += int(f.getlength(part))

    # ---------------------------------------------------------------- scenes
    def draw(self, scene: str, t: float, dur: float) -> Image.Image:
        return getattr(self, f"_{scene}")(t, dur)

    def _boot(self, t: float, dur: float) -> Image.Image:
        im = self.bg.copy()
        if t > 0.12:  # the first frames are the bare screen the outro returns to
            d = ImageDraw.Draw(im)
            bars = int(min(4, (t - 0.12) / dur * 6)) + 1
            for i in range(4):
                h = 18 + i * 14
                d.rectangle([480 + i * 34, 960 - h, 504 + i * 34, 960], fill=WHITE if i < bars else DIM)
            self.text(d, (540, 1000), "CONNECTING", font("semi", 30), MUTED, anchor="ma")
        return im

    def _outro(self, t: float, dur: float) -> Image.Image:
        last = self._card(99, 99)
        return Image.blend(last, self.bg, ease(t / max(dur - 2 / FPS, 1e-3)))

    def _hook(self, t: float, dur: float) -> Image.Image:
        im = Image.blend(self.bg, self.map, 0.25) if self.race else self.bg.copy()
        d = ImageDraw.Draw(im)
        r = self.race
        self.header(d)
        if int(t * 2) % 2 == 0:
            d.ellipse([X1 - 150, 262, X1 - 134, 278], fill=RED)
        self.text(d, (X1, 252), "LIVE", font("bold", 30), WHITE, anchor="ra")
        y = 520
        for i, line in enumerate(self.spec["hook"]):
            self.accent_line(d, y, line, 112, appear=(t - 0.1 - i * 0.18) / 0.35)
            y += 140
        sub = (f"RACE {r['no']} · {self.race_line(r)}" if r else "A NEW RACE EVERY DAY")
        if t > 0.6:
            self.text(d, (X0, y + 30), sub, self.fit(sub, "semi", 36, X1 - X0), MUTED)
            if r:
                self.text(d, (X0, y + 80), r["track"]["name"].upper(), self.fit(r["track"]["name"].upper(), "semi", 36, X1 - X0), MUTED)
        return im

    def _rules(self, t: float, dur: float) -> Image.Image:
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        self.header(d, "HOW TO PLAY")
        self.text(d, (X0, 330), "BET ON THE RACE", font("black", 84), WHITE)
        steps = [("You start with §1,000", "Play money. The first time we see you, it's yours."),
                 ("Comment a car + stake", "4 250 = §250 on 4 BLUE STREAK. Each comment is a bet."),
                 ("A different race daily", "Ovals, rally, drag, endurance… cars suit some more than others."),
                 ("Winners get paid at the odds", "A 4/1 winner turns §250 into §1,250.")]
        for i, (head, sub) in enumerate(steps):
            a = ease((t - 0.3 - i * 0.5) / 0.4)
            if a <= 0:
                continue
            y = 500 + i * 200
            d.rounded_rectangle([X0, y, X1, y + 170], 22, fill=PANEL)
            d.ellipse([X0 + 26, y + 40, X0 + 116, y + 130], fill=YELLOW)
            self.text(d, (X0 + 71, y + 85), str(i + 1), font("black", 54), NAVY, anchor="mm")
            self.text(d, (X0 + 150, y + 34), head, self.fit(head, "bold", 46, X1 - X0 - 180), WHITE)
            self.text(d, (X0 + 150, y + 100), sub, self.fit(sub, "semi", 30, X1 - X0 - 180), MUTED)
        if t > 2.6:
            self.text(d, (X0, 1340), "Play money · no prizes · " + self.spec.get("domain", ""), font("semi", 32), MUTED)
        return im

    def _grid(self, t: float, dur: float) -> Image.Image:
        im = self.map.copy() if (t > 0.8 or self.drag) else self._draw_in(t / 0.8)
        d = ImageDraw.Draw(im)
        r = self.race
        self.header(d, f"RACE {r['no']}")
        self.text(d, (X0, 296), r["track"]["name"].upper(), self.fit(r["track"]["name"].upper(), "bold", 52, X1 - X0), WHITE)
        self.text(d, (X0, 362), self.race_line(r), font("semi", 30), MUTED)
        if self.drag:
            self._tree(d, t, dur)
        else:
            for i in range(5):  # start lights
                x = 300 + i * 100
                lit = t >= 0.6 + i * 0.32 and t < dur - 0.35
                d.ellipse([x, 420, x + 70, 490], fill=RED if lit else (40, 30, 50), outline=(70, 70, 90), width=3)
            if t >= dur - 0.35:
                self.text(d, (540, 455), "GO", font("black", 72), GREEN, anchor="mm")
        self._dots(d, 0.0, grid=True)
        self._tower(d, 0.0)
        return im

    def _tree(self, d, t: float, dur: float) -> None:
        """The drag start: three ambers together, then green."""
        x = 900
        for i in range(3):
            on = dur - 1.0 <= t < dur - 0.35
            d.ellipse([x, 520 + i * 90, x + 64, 584 + i * 90], fill=AMBER if on else (50, 40, 30))
        d.ellipse([x, 790, x + 64, 854], fill=GREEN if t >= dur - 0.35 else (25, 50, 35))

    def _draw_in(self, p: float) -> Image.Image:
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        n = max(2, int(len(self.track) * ease(p)))
        d.line([tuple(q) for q in self.track[:n]], fill=(150, 160, 200), width=6, joint="curve")
        return im

    def _race(self, t: float, dur: float) -> Image.Image:
        im = self.map.copy()
        d = ImageDraw.Draw(im)
        rows = self.standings(t)
        lead = rows[0]
        r = self.race
        laps = r["laps"]
        self.header(d, f"RACE {r['no']} · {r['format']['name'].upper()}")
        if self.drag:
            label = "FINISH" if lead["done"] else "1/4 MILE"
        else:
            label = f"LAP {min(laps, lead['lap'])}/{laps}" if not lead["done"] else "FINISH"
        self.text(d, (X0, 296), label, font("black", 64), WHITE)
        if r["scale"] > 2 and not lead["done"]:  # a long race shown sped up
            self.text(d, (X0 + 8, 372), f"×{r['scale']:.0f} SPEED", font("mono-bold", 26), DIM)
        ev = self.event_at(t)
        flag_ev = ev and ev["kind"] in YELLOW_FLAG
        if lead["done"]:
            self._flag(d, X1, 300)
        elif flag_ev:
            self.pill(d, X1, 300, "YELLOW", YELLOW)
        elif not self.drag:
            self.pill(d, X1, 300, "GREEN", GREEN)
        if ev and (ev["kind"] != "pit" or ev.get("dur", 0) > 27):
            no = ev["car"]
            label = EVENTS[ev["kind"]] if ev["kind"] != "pit" else f"SLOW STOP · {ev['dur']:.1f}s"
            fill = RED if ev["kind"] in ("blowup", "jumpstart") else self.colour(no)
            ink = WHITE if ev["kind"] in ("blowup", "jumpstart") else self.ink_on(no)
            d.rectangle([X0 - 12, 1092, X1 + 6, 1140], fill=fill)
            line = f"{self.car_name(no)} · {label}"
            self.text(d, (X0, 1116), line, self.fit(line, "bold", 34, X1 - X0), ink, anchor="lm")
        self._dots(d, t)
        self._tower(d, t)
        return im

    def _flag(self, d, x1: int, y: int) -> None:
        for i in range(6):
            for j in range(2):
                c = WHITE if (i + j) % 2 else (20, 20, 20)
                d.rectangle([x1 - 200 + i * 33, y + j * 29, x1 - 167 + i * 33, y + 29 + j * 29], fill=c)

    def _finish(self, t: float, dur: float) -> Image.Image:
        im = self._race(self.race["race_end"], dur)
        d = ImageDraw.Draw(im)
        win = self.race["order"][0]
        a = ease(t / 0.3)
        y = int(560 - 40 * (1 - a))
        d.rounded_rectangle([X0 - 12, y, X1 + 6, y + 250], 26, fill=PANEL)
        d.rectangle([X0 - 12, y, X0 + 8, y + 250], fill=self.colour(win))
        self.text(d, (X0 + 40, y + 34), "WINNER", font("semi", 32), MUTED)
        name = self.car_name(win)
        self.text(d, (X0 + 40, y + 80), name, self.fit(name, "black", 86, X1 - X0 - 80), WHITE)
        m = self.race.get("margin")
        if self.drag:
            rt = (self.race.get("reaction") or {}).get(str(win))
            et = self.times.get(win)
            line = f"ET {et:.3f}s · RT {rt:.3f}s" if et and rt else ""
            self.text(d, (X0 + 40, y + 186), line, font("mono", 34), YELLOW)
        elif m is not None and m < 0.15 and t > 0.4:
            self.pill(d, X1 - 20, y + 30, f"PHOTO FINISH +{m:.3f}s", YELLOW)
        elif m is not None:
            self.text(d, (X0 + 40, y + 186), f"by {m:.3f}s", font("mono", 36), YELLOW)
        return im

    def _pos(self, j: int, frac: float, grid: bool = False) -> tuple[float, float]:
        if self.drag:
            y0, y1 = LANES_Y
            return lane_x(j), y0 + (y1 - y0) * min(max(frac, 0.0), 1.0)
        x, y, a = point_at(self.track, frac)
        off = (j - 2.5) * 6
        return x - off * math.sin(a), y + off * math.cos(a)

    def _dots(self, d, t: float, grid: bool = False) -> None:
        k = self.frame_of(t)
        order = sorted(range(len(self.cars)), key=lambda j: self.dist[k, j])  # leaders drawn on top
        for j in order:
            no = self.cars[j]["no"]
            frac = (0.0 if self.drag else -0.012 * (j + 1)) if grid else self.dist[k, j]
            out = no in self.out_at and self.out_at[no] <= t
            col = (90, 90, 110) if out else self.colour(no)
            if not grid and not out:
                for back in (12, 8, 4):  # a short trail
                    xb, yb = self._pos(j, self.dist[max(0, k - back), j])
                    rr = 6 + (12 - back) // 2
                    d.ellipse([xb - rr, yb - rr, xb + rr, yb + rr], fill=tuple(c // 2 for c in col))
            x, y = self._pos(j, frac)
            if self.pit is not None and not grid and self.pit[k, j]:  # in the pit lane
                _, _, a = point_at(self.track, 0)
                x, y = x - 40 * math.sin(a), y + 40 * math.cos(a)
            d.ellipse([x - 30, y - 30, x + 30, y + 30], fill=col, outline=WHITE, width=4)
            self.text(d, (x, y + 1), str(no), font("black", 34), self.ink_on(no), anchor="mm", record=False)

    def _tower(self, d, t: float) -> None:
        now = self.standings(t)
        # a row's height is its average position over the last 0.3 s, so rows glide past each other
        samples = [{r["car"]: r["pos"] for r in self.standings(max(0.0, t - k * 0.04))} for k in range(8)]
        for r in now:
            p = sum(s[r["car"]] for s in samples) / len(samples)
            y = int(TOWER_Y + (p - 1) * ROW)
            d.rectangle([X0 - 12, y, X1 + 6, y + ROW - 4], fill=PANEL if r["pos"] % 2 else PANEL2)
            self.text(d, (X0 + 8, y + 22), str(r["pos"]), font("mono-bold", 32), WHITE, anchor="lm")
            d.rectangle([X0 + 52, y + 8, X0 + 62, y + ROW - 12], fill=self.colour(r["car"]))
            self.text(d, (X0 + 80, y + 22), self.car_name(r["car"]), font("bold", 32), WHITE, anchor="lm")
            if r["wear"] is not None and not r["out"]:  # tyre life: a bar that empties and goes red
                left = max(0.0, 1 - r["wear"])
                col = GREEN if left > 0.5 else YELLOW if left > 0.25 else RED
                d.rectangle([560, y + 16, 640, y + 28], fill=DIM)
                d.rectangle([560, y + 16, 560 + int(80 * left), y + 28], fill=col)
            gap, col = self._gap(r, t)
            self.text(d, (X1 - 8, y + 22), gap, font("mono", 32), col, anchor="rm")

    def _gap(self, r: dict, t: float) -> tuple[str, tuple]:
        if r["out"]:
            return "OUT", RED
        if r["pit"]:
            return "PIT", YELLOW
        if self.drag:
            rt = (self.race.get("reaction") or {}).get(str(r["car"]))
            if r["done"]:
                return f"{self.times[r['car']]:.3f}s", YELLOW if r["pos"] == 1 else (200, 205, 230)
            return (f"RT {rt:.3f}" if rt else ""), (200, 205, 230)
        if r["gap"] is None:
            return ("WINNER" if r["done"] else "LEADER"), YELLOW
        if r["gap"] > 90:
            return f"+{int(r['gap'] // 60)}:{r['gap'] % 60:04.1f}", (200, 205, 230)
        return (f"+{r['gap']:.3f}" if r["done"] else f"+{r['gap']:.2f}"), (200, 205, 230)

    def _result(self, t: float, dur: float) -> Image.Image:
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        res, race = self.spec["result"], self.race
        self.header(d, f"RACE {race['no']} · {race['format']['name'].upper()}")
        self.text(d, (X0, 300), "RESULT", font("black", 84), WHITE)
        win = race["order"][0]
        y = 430
        d.rounded_rectangle([X0 - 12, y, X1 + 6, y + 230], 26, fill=PANEL)
        d.rectangle([X0 - 12, y, X0 + 8, y + 230], fill=self.colour(win))
        self.text(d, (X0 + 40, y + 30), f"WINNER · AT {res['odds']}", font("semi", 32), MUTED)
        self.text(d, (X0 + 40, y + 78), self.car_name(win), self.fit(self.car_name(win), "black", 80, X1 - X0 - 80), WHITE)
        for i, no in enumerate(race["order"][1:3]):
            yy = y + 260 + i * 70
            d.rectangle([X0 + 52, yy + 10, X0 + 62, yy + 50], fill=self.colour(no))
            self.text(d, (X0, yy + 30), f"P{i + 2}", font("mono-bold", 34), MUTED, anchor="lm")
            self.text(d, (X0 + 80, yy + 30), self.car_name(no), font("bold", 38), WHITE, anchor="lm")
            gap = race["gaps"].get(str(no)) if race.get("gaps") else None
            if gap is not None:
                self.text(d, (X1 - 8, yy + 30), f"+{gap:.3f}", font("mono", 34), (200, 205, 230), anchor="rm")
        y = 860
        tiles = []
        if res["bettors"]:
            tiles.append((f"{res['backers']} of {res['bettors']} backed it", GREEN))
            if res.get("biggest"):
                b = res["biggest"]
                tiles.append((f"Biggest win @{b['name']}", WHITE))
                tiles.append((f"+§{b['won']:,} on §{b['stake']:,}", YELLOW))
            if res.get("bust"):
                tiles.append((f"Bust: {res['bust']} punters", RED))
        else:
            tiles += [("Nobody backed it.", WHITE), (f"Be the first: comment {win} 100", YELLOW)]
        for i, (line, col) in enumerate(tiles):
            if t < 0.6 + i * 0.35:
                break
            big = col == YELLOW
            self.text(d, (X0, y), line, self.fit(line, "black" if big else "bold", 64 if big else 44, X1 - X0), col)
            y += 92 if big else 72
        return im

    def _table(self, t: float, dur: float) -> Image.Image:
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        tb = self.spec["table"]
        self.header(d, tb.get("week", ""))
        self.text(d, (X0, 300), "LEAGUE TABLE", font("black", 84), WHITE)
        if tb["players"] < 5:
            self.text(d, (X0, 500), "The table opens", font("bold", 56), WHITE)
            self.text(d, (X0, 570), "at 5 punters.", font("bold", 56), WHITE)
            self.text(d, (X0, 680), f"{tb['players']} so far. Comment a bet to join.", font("semi", 36), MUTED)
            return im
        for i, row in enumerate(tb["rows"][:10]):
            if t < 0.2 + i * 0.08:
                break
            y = 420 + i * 70
            d.rectangle([X0 - 12, y, X1 + 6, y + 64], fill=PANEL if i % 2 else PANEL2)
            col = YELLOW if i < 3 else WHITE
            self.text(d, (X0 + 8, y + 32), f"{i + 1}", font("mono-bold", 34), col, anchor="lm")
            name = "@" + row["name"] if not row["name"].startswith("punter") else row["name"]
            self.text(d, (X0 + 80, y + 32), name, self.fit(name, "bold", 36, 540), col, anchor="lm")
            self.text(d, (X1 - 8, y + 32), f"§{row['balance']:,}", font("mono", 34), col, anchor="rm")
        y = 1140
        if tb.get("climber"):
            c = tb["climber"]
            line = f"Climber @{c['name']} +§{c['gain']:,}"
            self.text(d, (X0, y), line, self.fit(line, "bold", 40, X1 - X0), GREEN)
            y += 64
        self.text(d, (X0, y), f"{tb['players']:,} punters · {tb['bust']} bust", font("semi", 34), MUTED)
        return im

    def _card(self, t: float, dur: float) -> Image.Image:
        im = self.bg.copy()
        d = ImageDraw.Draw(im)
        c = self.spec["card"]
        fmt = c["format"]
        self.header(d, f"RACE {c['no']}")
        self.text(d, (X0, 296), "BETS OPEN", font("black", 84), WHITE)
        laps = f"{fmt['laps']} laps" if fmt["laps"] > 1 else "one run"
        self.text(d, (X0, 396), f"{fmt['name']} · {laps} · closes {c['closes'].title()}", font("semi", 32), YELLOW)
        name = c["track"]["name"]
        self.text(d, (X0, 440), name, self.fit(name, "semi", 30, 600), MUTED)
        mini = fit_track(c["track"]["pts"], (760, 268, 930, 438))  # the next race's track
        line = [tuple(p) for p in mini] + ([tuple(mini[0])] if c["track"].get("closed", True) else [])
        d.line(line, fill=(150, 160, 200), width=5, joint="curve")
        self.text(d, (640, 488), "ODDS", font("semi", 26), DIM)
        self.text(d, (X1 - 8, 488), "FORM", font("semi", 26), DIM, anchor="ra")
        for i, car in enumerate(self.cars):
            if t < 0.15 + i * 0.07:
                break
            no, y = car["no"], 524 + i * 100
            d.rounded_rectangle([X0 - 12, y, X1 + 6, y + 88], 16, fill=PANEL)
            d.rounded_rectangle([X0 - 12, y, X0 + 12, y + 88], 8, fill=self.colour(no))
            self.text(d, (X0 + 40, y + 44), self.car_name(no), font("bold", 40), WHITE, anchor="lm")
            self.text(d, (700, y + 44), c["odds"][i], font("mono-bold", 40), YELLOW, anchor="rm")
            form = c["form"].get(str(no)) or c["form"].get(no) or "-----"
            for k, ch in enumerate(form[-5:]):
                x = 728 + k * 40
                d.rounded_rectangle([x, y + 24, x + 34, y + 64], 6, fill=PURPLE if ch == "1" else DIM)
                self.text(d, (x + 17, y + 44), ch, font("bold", 26), WHITE, anchor="mm", record=False)
        y = 1140
        d.rounded_rectangle([X0 - 12, y, X1 + 6, y + 200], 24, fill=YELLOW)
        self.text(d, (X0 + 24, y + 22), "COMMENT CAR + STAKE", font("bold", 36), NAVY)
        self.text(d, (X0 + 24, y + 70), "4 250", font("black", 104), NAVY)
        self.text(d, (X0 + 380, y + 92), "= §250 on", font("bold", 36), NAVY)
        self.text(d, (X0 + 380, y + 136), "4 BLUE STREAK", font("bold", 36), NAVY)
        self.text(d, (X0, 1362), f"SEAL {c['seal'][:12]}…", font("mono", 28), DIM)
        self.text(d, (X1 - 8, 1362), self.spec.get("domain", ""), font("semi", 28), MUTED, anchor="ra")
        self.text(d, (X0, 1402), "Play money · no prizes · new players start with §1,000", font("semi", 28), MUTED)
        return im

    # ---------------------------------------------------------------- glitch
    def glitch(self, img: Image.Image, amount: float, seed: int) -> Image.Image:
        """A broadcast dropout: strips slide sideways and break into blocks, colour shifts in one."""
        if amount <= 0:
            return img
        a = np.asarray(img).copy()
        rng = np.random.default_rng(seed)
        for _ in range(int(2 + 4 * amount)):
            y, x = int(rng.integers(200, H - 300)), int(rng.integers(0, W - 400))
            h, w = int(rng.integers(14, 60)), int(rng.integers(200, 700))
            block = np.roll(a[y:y + h, x:x + w], int(rng.integers(-80, 80)), axis=1)
            a[y:y + h, x:x + w] = (block // 24 * 24 + 12).clip(0, 255)
        y = int(rng.integers(300, H - 400))
        a[y:y + 30, :, 0] = np.roll(a[y:y + 30, :, 0], 14, axis=1)
        a[y:y + 30, :, 2] = np.roll(a[y:y + 30, :, 2], -14, axis=1)
        return Image.fromarray(a)


def draw_track(d: ImageDraw.ImageDraw, track: np.ndarray, full: bool = True) -> None:
    pts = [tuple(p) for p in track] + [tuple(track[0])]
    d.line(pts, fill=(40, 48, 84), width=54, joint="curve")
    d.line(pts, fill=(150, 160, 200), width=6, joint="curve")
    third = len(track) // 3
    for s, col in enumerate((PURPLE, GREEN, YELLOW)):  # sectors
        d.line([tuple(p) for p in track[s * third:(s + 1) * third + 1]], fill=col, width=4)
