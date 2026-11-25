"""One scene per segment of a promo (app/santa/spec.py). Each knows how long it lasts, draws itself
at time t (seconds since it started) onto a transparent layer, and lists its sound effects.

A segment with a narrator line lasts at least until the line ends (SAY_AT + its length + a
breath), so the words and the picture stay together.
"""
from __future__ import annotations

import math
from pathlib import Path
import re

from PIL import Image, ImageDraw

from ..draw import blit, clamp, ease_in_out_cubic, ease_out_back, ease_out_cubic, prog
from ..theme import H, W, SAFE_BOTTOM, SAFE_CX, SAFE_LEFT, SAFE_RIGHT, SAFE_TOP, SAFE_W
from . import look
from .look import BODY, DISPLAY, SEMI, C

SAY_AT = 0.3  # the narrator starts this long into a segment
BREATH = 0.5  # after the line ends, before the next segment
READ_CPS = 17.0  # characters a second people read on screen
TOP = SAFE_TOP + 70  # below the brand line


def _enter(t: float, at: float, dur: float = 0.38) -> float:
    return ease_out_cubic(prog(t, at, dur))


def _read(*texts: str | None) -> float:
    return sum(len(x or "") for x in texts) / READ_CPS


class Scene:
    base = 2.5

    def __init__(self, seg, voice_len: float | None = None, **_):
        self.seg = seg
        own = max(self.base, seg.seconds or 0)
        self.duration = max(own, SAY_AT + voice_len + BREATH) if voice_len else own

    def sfx(self) -> list[tuple[float, str]]:
        return []

    def render(self, fg: Image.Image, t: float) -> None:
        raise NotImplementedError

    def heading(self, fg: Image.Image, t: float, text: str | None, y: float = TOP + 40) -> float:
        """Draw an optional gold heading; returns where the content below it may start."""
        if not text:
            return TOP
        size = look.fit(text, DISPLAY, 66, SAFE_W, 2, 44)
        spr = look.rich(text, DISPLAY, size, C.gold, C.label, SAFE_W)
        p = _enter(t, 0.0)
        blit(fg, spr, SAFE_CX, y + 30 * (1 - p), anchor="mt", alpha=p)
        return y + spr.height + 50


class TitleScene(Scene):
    """The stamp drops in, then the hook in big type."""

    def __init__(self, seg, voice_len=None, **kw):
        self.size = look.fit(seg.text, DISPLAY, 104, SAFE_W, 4, 60)
        self.base = 1.0 + _read(seg.text, seg.sub) * 0.55  # the hook: short, people decide in seconds
        super().__init__(seg, voice_len)
        self.head = look.rich(seg.text, DISPLAY, self.size, C.label, C.gold, SAFE_W)
        self.sub = look.rich(seg.sub, SEMI, 46, C.frost_soft, C.gold, SAFE_W - 40) if seg.sub else None
        self.stamp = look.stamp(330, -7)

    def sfx(self):
        return [(0.05, "whoosh"), (0.42, "pop"), (0.7, "shimmer")]

    def render(self, fg, t):
        block = self.head.height + (self.sub.height + 36 if self.sub else 0)
        top = max(SAFE_TOP + 420, (SAFE_TOP + 380 + SAFE_BOTTOM - block) / 2)
        p = ease_out_back(prog(t, 0.0, 0.5))
        blit(fg, self.stamp, SAFE_CX + 170, top - 230 - 260 * (1 - clamp(p)), scale=0.7 + 0.3 * p, alpha=clamp(p * 2))
        q = _enter(t, 0.12, 0.42)
        blit(fg, self.head, SAFE_CX, top + 40 * (1 - q), anchor="mt", alpha=q)
        if self.sub:
            r = _enter(t, 0.45)
            blit(fg, self.sub, SAFE_CX, top + self.head.height + 36 + 30 * (1 - r), anchor="mt", alpha=r)


class ListScene(Scene):
    """Points (ticks) or steps (numbers) on postcards that come in one after another."""

    def __init__(self, seg, voice_len=None, **kw):
        self.items = seg.items if seg.type == "points" else seg.steps
        self.numbered = seg.type == "steps"
        self.base = 1.0 + 0.6 * len(self.items) + _read(*self.items) * 0.7
        super().__init__(seg, voice_len)
        self.gap = min(1.4, max(0.35, (self.duration - 1.2) / len(self.items)))
        inner = SAFE_W - 170
        size = min(look.fit(x, SEMI, 50, inner, 2, 36) for x in self.items)
        self.cards = []
        for k, text in enumerate(self.items):
            txt = look.rich(text, SEMI, size, C.ink, C.post, inner, align="l")
            h = max(150, txt.height + 70)
            card = look.plain_card(SAFE_W, h).copy()
            b = look.badge(42, C.post, str(k + 1)) if self.numbered else look.badge(42, C.pine, tick=True)
            card.alpha_composite(b, (36, (card.height - b.height) // 2))
            card.alpha_composite(txt, (140, (card.height - txt.height) // 2))
            self.cards.append(look.rotated(card, (-1.2, 1.0, -0.6, 1.4)[k % 4]))

    def sfx(self):
        return [(0.35 + k * self.gap, "pop") for k in range(len(self.items))]

    def render(self, fg, t):
        y = self.heading(fg, t, self.seg.heading)
        total = sum(c.height for c in self.cards) + 26 * (len(self.cards) - 1)
        y = max(y, (y + SAFE_BOTTOM - total) / 2)
        for k, card in enumerate(self.cards):
            p = ease_out_back(prog(t, 0.35 + k * self.gap, 0.42))
            blit(fg, card, SAFE_CX + 260 * (1 - clamp(p)), y, anchor="mt", alpha=clamp(p * 1.6))
            y += card.height + 26


_NUM = re.compile(r"^(\D*?)(\d[\d,]*)(.*)$")


def counted(value: str, x: float) -> str:
    """`value` with its number counted up to fraction x ("1,200+" at 0.5 → "600+")."""
    m = _NUM.match(value)
    if not m or x >= 1:
        return value
    pre, num, post = m.groups()
    n = int(num.replace(",", ""))
    shown = int(round(n * x))
    return f"{pre}{shown:,}{post}" if "," in num or n >= 1000 else f"{pre}{shown}{post}"


class FiguresScene(Scene):
    """Big gold numbers counting up, each with its label."""
    COUNT = 1.1

    def __init__(self, seg, voice_len=None, **kw):
        self.base = 1.2 + 0.9 * len(seg.figures) + _read(*(f.label for f in seg.figures)) * 0.5
        super().__init__(seg, voice_len)
        self.gap = min(1.2, max(0.5, (self.duration - 2.0) / len(seg.figures)))
        widest = max(seg.figures, key=lambda f: len(f.value)).value
        self.size = look.fit(widest, DISPLAY, 170, SAFE_W, 1, 90)

    def sfx(self):
        out = []
        for k in range(len(self.seg.figures)):
            t0 = 0.4 + k * self.gap
            out += [(t0 + i * 0.1, "tick") for i in range(int(self.COUNT / 0.1))] + [(t0 + self.COUNT, "ding")]
        return out

    def render(self, fg, t):
        y = self.heading(fg, t, self.seg.heading)
        n = len(self.seg.figures)
        row = 330
        y = max(y, (y + SAFE_BOTTOM - row * n) / 2)
        for k, f in enumerate(self.seg.figures):
            t0 = 0.4 + k * self.gap
            p = _enter(t, t0)
            if p <= 0:
                continue
            val = counted(f.value, ease_out_cubic(prog(t, t0, self.COUNT)))
            num = look.rich(val, DISPLAY, self.size, C.gold, C.gold, SAFE_W)
            land = clamp((t - t0 - self.COUNT) / 0.25) if t > t0 + self.COUNT else 0
            pop = 1 + 0.08 * math.sin(math.pi * land) if 0 < land < 1 else 1
            blit(fg, num, SAFE_CX, y + 30 * (1 - p), anchor="mt", alpha=p, scale=pop)
            lab = look.rich(f.label, SEMI, 46, C.frost, C.gold, SAFE_W)
            blit(fg, lab, SAFE_CX, y + num.height + 4, anchor="mt", alpha=p)
            y += row


class QuestionScene(Scene):
    """The question on a card, the options, a countdown, then the right one lights up."""
    REVEAL = 2.8

    def __init__(self, seg, voice_len=None, **kw):
        n = len(seg.options)
        self.t_think = 0.8 + 0.18 * n + _read(seg.question) * 0.35
        if voice_len:  # the question is read out: the countdown starts once it's been asked
            self.t_think = max(self.t_think, SAY_AT + voice_len + 0.2)
        self.t_reveal = self.t_think + seg.think
        self.base = self.t_reveal + self.REVEAL + (0.8 if seg.note else 0)
        Scene.__init__(self, seg, None)
        qsize = look.fit(seg.question, SEMI, 58, SAFE_W - 90, 4, 40)
        q = look.rich(seg.question, SEMI, qsize, C.ink, C.post, SAFE_W - 90)
        self.qcard = look.postcard(SAFE_W, q.height + 110).copy()
        self.qcard.alpha_composite(q, ((self.qcard.width - q.width) // 2, (self.qcard.height - q.height) // 2))
        osize = min(look.fit(o, SEMI, 48, SAFE_W - 190, 1, 34) for o in seg.options)
        self.opts = []
        for k, o in enumerate(seg.options):
            rows = []
            for state in ("idle", "right", "wrong"):
                fill = {"idle": C.paper, "right": C.pine, "wrong": C.label_shade}[state]
                tc = C.label if state == "right" else (C.ink_soft if state == "wrong" else C.ink)
                card = look.plain_card(SAFE_W, 118, fill=fill, outline=C.pine if state == "right" else C.rule).copy()
                b = look.badge(36, C.gold if state == "right" else C.night, tick=state == "right",
                               text="ABCD"[k], text_col=C.label)
                card.alpha_composite(b, (30, (card.height - b.height) // 2))
                txt = look.rich(o, SEMI, osize, tc, tc, SAFE_W - 190, align="l")
                card.alpha_composite(txt, (128, (card.height - txt.height) // 2))
                rows.append(card)
            self.opts.append(rows)
        self.note = look.rich(seg.note, SEMI, 42, C.frost, C.gold, SAFE_W) if seg.note else None

    def sfx(self):
        n = len(self.seg.options)
        out = [(0.05, "whoosh")] + [(0.45 + 0.18 * k, "pop") for k in range(n)]
        secs = int(self.seg.think)
        out += [(self.t_think + i, "clock" if secs - i > 2 else "tock") for i in range(secs)]
        return out + [(self.t_reveal, "reveal"), (self.t_reveal + 0.05, "chime")]

    def render(self, fg, t):
        p = _enter(t, 0.0, 0.45)
        y = TOP + 20
        blit(fg, self.qcard, SAFE_CX, y + 50 * (1 - p), anchor="mt", alpha=p)
        y += self.qcard.height + 30
        revealed = t >= self.t_reveal
        for k, rows in enumerate(self.opts):
            q = _enter(t, 0.45 + 0.18 * k, 0.32)
            state = ("right" if k == self.seg.correct else "wrong") if revealed else "idle"
            bump = 1 + 0.06 * math.sin(math.pi * clamp((t - self.t_reveal) / 0.3)) if revealed and state == "right" else 1
            blit(fg, rows[("idle", "right", "wrong").index(state)], SAFE_CX - 200 * (1 - q), y, anchor="mt",
                 alpha=q * (0.75 if state == "wrong" else 1), scale=bump)
            y += 142
        # countdown: the seconds left, with a gold ring running down
        if self.t_think <= t < self.t_reveal:
            left = self.t_reveal - t
            ring = Image.new("RGBA", (190, 190), (0, 0, 0, 0))
            from PIL import ImageDraw

            d = ImageDraw.Draw(ring)
            d.ellipse((6, 6, 184, 184), fill=C.night_deep + (230,), outline=C.night_raised + (255,), width=10)
            frac = left / self.seg.think
            d.arc((6, 6, 184, 184), -90, -90 + 360 * frac, fill=(C.post if left < 2.5 else C.gold) + (255,), width=12)
            num = look.rich(str(math.ceil(left)), DISPLAY, 84, C.label, C.label, 200)
            ring.alpha_composite(num, ((190 - num.width) // 2, (190 - num.height) // 2 + 4))
            blit(fg, ring, SAFE_CX, y + 30, anchor="mt")
        elif revealed and self.note:
            r = _enter(t, self.t_reveal + 0.5)
            blit(fg, self.note, SAFE_CX, y + 30 + 20 * (1 - r), anchor="mt", alpha=r)


class KudosScene(Scene):
    """A thank-you postcard from the site, with its photo, stamp and postmark."""

    def __init__(self, seg, voice_len=None, images_dir=None, **kw):
        self.base = 2.0 + _read(seg.message) * 0.9
        super().__init__(seg, voice_len)
        w = SAFE_W + 20
        pic = look.photo(str(images_dir / seg.image), w - 120, 520) if (images_dir and seg.image) else None
        msize = look.fit(seg.message, BODY, 50 if not pic else 44, w - 130, 7 if not pic else 5, 32)
        msg = look.rich(f"“{seg.message}”", BODY, msize, C.ink, C.post, w - 130)
        sig = look.rich(f"— {seg.name}", SEMI, 42, C.post, C.post, w - 130, align="r")
        h = 90 + (pic.height + 40 if pic else 120) + msg.height + 30 + sig.height + 70
        card = look.postcard(w, h).copy()
        y = 50
        if pic:
            card.alpha_composite(pic, ((card.width - pic.width) // 2, y))
            y += pic.height + 40
        else:
            mark = look.postmark(60)
            card.alpha_composite(mark, (60, y + 10))
            y += 120 + 20
        card.alpha_composite(msg, ((card.width - msg.width) // 2, y))
        y += msg.height + 30
        card.alpha_composite(sig, (card.width - sig.width - 70, y))
        self.card = look.rotated(card, -1.6)
        self.stamp = look.stamp(190, 8)
        self.kicker = look.rich("A THANK-YOU POSTCARD", SEMI, 38, C.gold, C.gold, SAFE_W)

    def sfx(self):
        return [(0.05, "swipe"), (0.55, "impact"), (0.9, "shimmer")]

    def render(self, fg, t):
        k = _enter(t, 0.0)
        blit(fg, self.kicker, SAFE_CX, TOP + 20, anchor="mt", alpha=k)
        p = ease_out_back(prog(t, 0.1, 0.5))
        top = max(TOP + 90, (TOP + 90 + SAFE_BOTTOM - self.card.height) / 2)
        blit(fg, self.card, SAFE_CX, top + 380 * (1 - clamp(p)), anchor="mt", alpha=clamp(p * 1.5))
        s = ease_out_back(prog(t, 0.5, 0.35))
        blit(fg, self.stamp, SAFE_RIGHT - 20, top + 20, scale=1.6 - 0.6 * s, alpha=clamp(s * 2))


class EndScene(Scene):
    """The stamp, raosanta.uk, the line, and "link in bio"."""
    base = 3.0

    def __init__(self, seg, voice_len=None, **kw):
        super().__init__(seg, voice_len)
        self.stamp = look.stamp(400, 4)
        self.name = look.rich("raosanta*.uk*", DISPLAY, 112, C.label, C.gold, SAFE_W + 60)
        self.line = look.rich(seg.line, SEMI, 50, C.frost, C.gold, SAFE_W)
        pill = look.plain_card(420, 92, fill=C.post, outline=C.post_deep, radius=46, border=4, shadow=6).copy()
        txt = look.rich("Link in bio", SEMI, 42, C.label, C.label, 400)
        pill.alpha_composite(txt, ((pill.width - txt.width) // 2, (pill.height - txt.height) // 2))
        self.pill = pill

    def sfx(self):
        return [(0.05, "whoosh"), (0.4, "pop"), (0.75, "chime")]

    def render(self, fg, t):
        y = SAFE_TOP + 300
        p = ease_out_back(prog(t, 0.0, 0.55))
        blit(fg, self.stamp, SAFE_CX, y, anchor="mt", scale=0.6 + 0.4 * p, alpha=clamp(p * 2))
        y += self.stamp.height + 40
        q = _enter(t, 0.3)
        blit(fg, self.name, SAFE_CX, y + 30 * (1 - q), anchor="mt", alpha=q)
        y += self.name.height + 20
        r = _enter(t, 0.5)
        blit(fg, self.line, SAFE_CX, y + 30 * (1 - r), anchor="mt", alpha=r)
        y += self.line.height + 50
        s = _enter(t, 0.75)
        beat = 1 + 0.04 * math.sin(max(0.0, t - 1.1) * 5) if t > 1.1 else 1
        blit(fg, self.pill, SAFE_CX, y, anchor="mt", alpha=s, scale=beat)


class AdventScene(Scene):
    """The countdown, filmed on the advent calendar (advent.py): wide on the whole board, a pan past
    two doors, a zoom into the day's door, which opens, and its treasure flies out to the middle
    with the sleeps left and the day's line. The doors visited on the pan are picked by the date,
    so no two days move the same way. Before December, door 1 rattles but stays shut."""
    WIDE, PAN1, PAN2, ARRIVE = 0.9, 1.7, 2.5, 3.5
    OPEN, OPEN_FOR, FLY_FOR = 3.7, 0.7, 0.7

    def __init__(self, seg, voice_len=None, **kw):
        from datetime import date as _date

        from . import advent

        self.day = _date.fromisoformat(seg.date)
        self.n = seg.days
        self.december = self.day.month == 12
        self.target = (25 if self.day.day == 25 else self.day.day) if self.december else 1
        self.text_at = self.OPEN + self.OPEN_FOR + self.FLY_FOR
        self.base = self.text_at + 2.4 + _read(seg.line) * 0.5
        super().__init__(seg, voice_len)
        self.cal = advent.calendar(self.day)
        season = self.day.year if self.day.month >= 8 else self.day.year - 1
        self.doors = advent.layout(season)
        self.s0 = W / advent.CAL_W
        opened = list(range(1, self.day.day)) if self.december else []
        rng = __import__("random").Random(self.day.toordinal())
        pool = opened if len(opened) >= 2 else [n for n in range(1, 25) if n != self.target]
        self.visits = rng.sample(pool, 2)
        x, y, w, h = self.doors[self.target]
        self.keys = [(0.0, advent.CAL_W / 2, advent.CAL_H / 2, 1.0), (self.WIDE, advent.CAL_W / 2, advent.CAL_H / 2, 1.0)]
        for t, n in ((self.PAN1, self.visits[0]), (self.PAN2, self.visits[1])):
            vx, vy, vw, vh = self.doors[n]
            self.keys.append((t, vx + vw / 2, vy + vh / 2, 2.1))
        if self.target == 25:  # the wide door at the bottom: fill the width, board above it
            zoom = 0.96 * W / (w * self.s0)
            self.keys.append((self.ARRIVE, x + w / 2, y + h / 2 - 260 / (self.s0 * zoom), zoom))
        else:
            zoom = max(1.15, min(700 / (w * self.s0), 1100 / (h * self.s0)))
            self.keys.append((self.ARRIVE, x + w / 2, y + h / 2 + h * 0.35, zoom))
        self.face = advent.door_face(self.target, w, h)
        self.hole = advent.recess(self.target, w, h, with_treasure=False)
        # what comes out: the day's treasure, or in November a padlock (door 1 is locked: no peeking)
        self.prize = advent.treasure(self.target if self.december else 0, 560)
        if self.n == 0:
            self.big = look.rich("It's *Christmas!*", DISPLAY, look.fit("It's Christmas!", DISPLAY, 130, SAFE_W, 2, 60),
                                 C.label, C.gold, SAFE_W)
            self.sub = None
        else:
            self.big = look.rich(str(self.n), DISPLAY, 230, C.gold, C.gold, SAFE_W)
            self.sub = look.rich(f"{'sleep' if self.n == 1 else 'sleeps'} until *Christmas*", DISPLAY, 64, C.label, C.gold, SAFE_W)
        self.line = look.rich(seg.line, SEMI, look.fit(seg.line, SEMI, 46, SAFE_W, 3, 34), C.frost, C.gold, SAFE_W)
        when = f"{self.day.day} {self.day:%B}"
        self.kicker = look.rich(when.upper() if self.december else "DOORS OPEN 1 DECEMBER",
                                SEMI, 40, C.gold, C.gold, SAFE_W)

    # -------------------------------------------------------- camera
    def camera(self, t: float):
        keys = self.keys
        if t >= keys[-1][0]:
            return keys[-1][1:]
        for (t0, x0, y0, z0), (t1, x1, y1, z1) in zip(keys, keys[1:]):
            if t0 <= t < t1:
                e = ease_in_out_cubic((t - t0) / (t1 - t0))
                return (x0 + (x1 - x0) * e, y0 + (y1 - y0) * e, math.exp(math.log(z0) + (math.log(z1) - math.log(z0)) * e))
        return keys[0][1:]

    def _to_screen(self, cam, x, y):
        cx, cy, z = cam
        s = self.s0 * z
        return (x - cx) * s + W / 2, (y - cy) * s + H / 2, s

    def sfx(self):
        out = [(self.WIDE, "whoosh"), (self.PAN1, "swipe"), (self.PAN2 - 0.1, "whoosh"), (self.ARRIVE - 0.1, "swipe")]
        if self.december:
            out += [(self.OPEN - 0.25, "clock"), (self.OPEN, "swipe"), (self.OPEN + self.OPEN_FOR, "chime"),
                    (self.OPEN + self.OPEN_FOR + 0.1, "shimmer"), (self.text_at, "ding")]
        else:
            out += [(self.OPEN + k * 0.22, "clock") for k in range(3)] + [(self.text_at, "ding")]
        return out

    def render(self, fg, t):
        cam = self.camera(t)
        cx, cy, z = cam
        s = self.s0 * z
        left, top = cx - W / 2 / s, cy - H / 2 / s
        view = self.cal.transform((W, H), Image.AFFINE, (1 / s, 0, left, 0, 1 / s, top), resample=Image.BILINEAR)
        fg.alpha_composite(view)
        x, y, w, h = self.doors[self.target]
        sx, sy, _ = self._to_screen(cam, x, y)
        dw, dh = max(1, int(w * s)), max(1, int(h * s))
        if self.december and t >= self.OPEN:
            o = ease_out_cubic(prog(t, self.OPEN, self.OPEN_FOR))
            fg.alpha_composite(self.hole.resize((dw, dh), Image.BILINEAR), (int(sx), int(sy)))
            f = math.cos(o * math.pi / 2)
            if f > 0.03:
                flap = self.face.resize((max(1, int(dw * f)), dh), Image.BILINEAR)
                if o > 0:
                    shade = Image.new("RGBA", flap.size, (0, 0, 0, int(140 * o)))
                    flap = Image.composite(Image.alpha_composite(flap, shade), flap, flap.getchannel("A"))
                fg.alpha_composite(flap, (int(sx), int(sy)))
        elif not self.december and self.OPEN <= t < self.OPEN + 0.7:  # it rattles but won't open
            jig = int(10 * math.sin((t - self.OPEN) * 40) * (1 - (t - self.OPEN) / 0.7))
            fg.alpha_composite(self.face.resize((dw, dh), Image.BILINEAR), (int(sx) + jig, int(sy)))
        # dim the board, then the treasure flies out to the middle
        reveal = prog(t, self.OPEN + self.OPEN_FOR * 0.5, 0.6)
        if reveal > 0:
            fg.alpha_composite(Image.new("RGBA", (W, H), C.night_deep + (int(218 * reveal),)))
        if self.prize is not None and t >= self.OPEN + self.OPEN_FOR * 0.5:
            f = ease_out_back(prog(t, self.OPEN + self.OPEN_FOR * 0.5, self.FLY_FOR))
            fx = sx + dw / 2 + (SAFE_CX - sx - dw / 2) * clamp(f)
            fy = sy + dh / 2 + (680 - sy - dh / 2) * clamp(f)
            size = (min(dw, dh) * 0.78) / 560 + (1 - (min(dw, dh) * 0.78) / 560) * f
            glow = Image.new("RGBA", (760, 760), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            for k, r in enumerate((380, 300, 220)):  # soft rings of warm light
                gd.ellipse((380 - r, 380 - r, 380 + r, 380 + r), fill=C.gold + (int((14 + 10 * k) * clamp(f)),))
            blit(fg, glow, fx, fy, scale=0.4 + 0.6 * clamp(f))
            for k in range(8):  # sparkles turning round it
                a = t * 1.4 + k * math.pi / 4
                r = 330 * clamp(f)
                px, py = fx + r * math.cos(a), fy + r * math.sin(a)
                rr = 10 + 6 * math.sin(t * 6 + k)
                ImageDraw.Draw(fg).polygon([(px, py - rr * 2), (px + rr * 0.5, py), (px, py + rr * 2), (px - rr * 0.5, py)],
                                           fill=C.gold_soft + (int(230 * clamp(f)),))
            bob = 8 * math.sin(max(0.0, t - self.text_at) * 2.4)
            blit(fg, self.prize, fx, fy + bob, scale=max(0.05, size))
        if t >= self.text_at:
            k = _enter(t, self.text_at)
            blit(fg, self.kicker, SAFE_CX, TOP + 10, anchor="mt", alpha=k)
            ytxt = 1090
            blit(fg, self.big, SAFE_CX, ytxt + 40 * (1 - k), anchor="mt", alpha=k)
            ytxt += self.big.height - 10
            if self.sub:
                q = _enter(t, self.text_at + 0.15)
                blit(fg, self.sub, SAFE_CX, ytxt + 30 * (1 - q), anchor="mt", alpha=q)
                ytxt += self.sub.height + 26
            r = _enter(t, self.text_at + 0.45)
            blit(fg, self.line, SAFE_CX, ytxt + 20 * (1 - r), anchor="mt", alpha=r)


def clip_frames(name: str) -> tuple[Path, float]:
    """The clip's frames as JPEGs at 30 fps (made once, then shared by every render process), and
    its length in seconds."""
    import hashlib
    import subprocess
    import tempfile

    from ...santa.spec import CLIPS

    src = CLIPS / f"{name}.mp4"
    key = hashlib.sha1(f"{src.stat().st_mtime_ns}-{src.stat().st_size}".encode()).hexdigest()[:12]
    out = Path(tempfile.gettempdir()) / "santa-clips" / f"{name}-{key}"
    if not out.exists():
        part = out.with_name(out.name + f".part{__import__('os').getpid()}")
        part.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src), "-vf", f"fps=30,scale={ClipScene.SCREEN_W}:-2",
                        "-q:v", "3", str(part / "%05d.jpg")], check=True)
        try:
            part.rename(out)
        except OSError:  # another process made it first
            import shutil

            shutil.rmtree(part, ignore_errors=True)
    n = len(list(out.glob("*.jpg")))
    return out, n / 30.0


class ClipScene(Scene):
    """A screen recording of the site in a phone, under a caption. The phone rises in, the clip
    plays from `start` to `end`, and the last frame holds while the narrator finishes."""
    SCREEN_W = 560
    BEZEL, RADIUS = 20, 62
    PLAY_AT = 0.35

    def __init__(self, seg, voice_len=None, **kw):
        self.dir, length = clip_frames(seg.name)
        self.start = seg.start
        self.end = min(seg.end or length, length)
        self.base = self.PLAY_AT + (self.end - self.start) + 0.5
        super().__init__(seg, voice_len)
        first = Image.open(self.dir / "00001.jpg")
        self.sw, self.sh = first.size
        self.caption = (look.rich(seg.caption, DISPLAY, look.fit(seg.caption, DISPLAY, 60, SAFE_W, 2, 40), C.label, C.gold, SAFE_W)
                        if seg.caption else None)
        b, r = self.BEZEL, self.RADIUS
        phone = Image.new("RGBA", (self.sw + 2 * b, self.sh + 2 * b), (0, 0, 0, 0))
        d = ImageDraw.Draw(phone)
        d.rounded_rectangle((0, 0, phone.width - 1, phone.height - 1), radius=r + b, fill=C.ink + (255,),
                            outline=C.gold_ink + (255,), width=3)
        self.phone = phone
        self.mask = Image.new("L", (self.sw, self.sh), 0)
        ImageDraw.Draw(self.mask).rounded_rectangle((0, 0, self.sw - 1, self.sh - 1), radius=r, fill=255)
        self._frame = (None, None)

    def _screen(self, k: int) -> Image.Image:
        if self._frame[0] != k:
            path = self.dir / f"{k:05d}.jpg"
            self._frame = (k, Image.open(path).convert("RGB") if path.exists() else self._frame[1])
        return self._frame[1]

    def sfx(self):
        return [(0.02, "whoosh")]

    def render(self, fg, t):
        y = TOP + 10
        if self.caption:
            c = _enter(t, 0.0)
            blit(fg, self.caption, SAFE_CX, y + 24 * (1 - c), anchor="mt", alpha=c)
            y += self.caption.height + 30
        p = ease_out_cubic(prog(t, 0.0, 0.45))
        top = y + 260 * (1 - p)
        clip_t = min(self.end, self.start + max(0.0, t - self.PLAY_AT))
        k = min(int(clip_t * 30) + 1, int(self.end * 30))
        phone = self.phone.copy()
        phone.paste(self._screen(max(1, k)), (self.BEZEL, self.BEZEL), self.mask)
        ImageDraw.Draw(phone).rounded_rectangle((phone.width / 2 - 60, self.BEZEL + 14, phone.width / 2 + 60, self.BEZEL + 34),
                                                radius=10, fill=C.ink + (255,))
        blit(fg, phone, SAFE_CX, top, anchor="mt", alpha=clamp(p * 1.4))


SCENES = {"clip": ClipScene, "countdown": AdventScene, "title": TitleScene, "points": ListScene, "steps": ListScene, "figures": FiguresScene,
          "question": QuestionScene, "kudos": KudosScene, "end": EndScene}
