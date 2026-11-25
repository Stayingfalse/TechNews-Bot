"""One scene per segment of a promo (app/santa/spec.py). Each knows how long it lasts, draws itself
at time t (seconds since it started) onto a transparent layer, and lists its sound effects.

A segment with a narrator line lasts at least until the line ends (SAY_AT + its length + a
breath), so the words and the picture stay together.
"""
from __future__ import annotations

import math
import re

from PIL import Image

from ..draw import blit, clamp, ease_out_back, ease_out_cubic, prog
from ..theme import SAFE_BOTTOM, SAFE_CX, SAFE_LEFT, SAFE_RIGHT, SAFE_TOP, SAFE_W
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


SCENES = {"title": TitleScene, "points": ListScene, "steps": ListScene, "figures": FiguresScene,
          "question": QuestionScene, "kudos": KudosScene, "end": EndScene}
