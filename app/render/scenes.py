"""Scene types. Each scene draws onto a transparent full-frame layer as a pure function of local time.

Visual vocabulary (see theme.py): sign-painted headings, paper cue cards and slabs with ink
outlines and hard shadows, a split-flap countdown with a bulb strip, and a hot-coloured answer
podium.
"""
from __future__ import annotations

import math
import random
import re

from PIL import Image, ImageDraw

from .draw import (
    blit,
    clamp,
    disc,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_expo,
    fit_size,
    ink_text,
    lerp,
    place,
    prog,
    slab,
    text_sprite,
    wrap_words,
)
from .emoji import clusters, emoji_sprite
from .theme import SAFE_BOTTOM, SAFE_CX, SAFE_LEFT, SAFE_TOP, SAFE_W, Palette, font

CENTER_Y = (SAFE_TOP + SAFE_BOTTOM) // 2
CLUE_Y = 850  # centre of the clue area
TIMER_Y = 1300  # split-flap countdown; the answer podium replaces it on reveal


class Scene:
    default_duration = 3.0

    def __init__(self, item, pal: Palette, index: int = 0, total: int = 0, seed: int = 0):
        self.item = item
        self.pal = pal
        self.index, self.total, self.seed = index, total, seed
        self.duration = self.default_duration

    def render(self, fg: Image.Image, t: float) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def sfx(self) -> list[tuple[float, str]]:
        return [(0.0, "whoosh")]

    def pulses(self) -> list[float]:
        """Moments (local time) when the set lights up."""
        return [0.0]


# --------------------------------------------------------------------------- helpers

def _highlight(word: str) -> tuple[str, bool]:
    """'*word*' or '*word*?' -> ('word?', True); anything else loses stray asterisks."""
    m = re.fullmatch(r"([^\w*]*)\*(.+?)\*([^\w*]*)", word)
    if m:
        return "".join(m.groups()), True
    return word.replace("*", ""), False


def _sign(text: str, size: int, pal: Palette, color=None, style="sign", tracking=0, shadow=None):
    """Sign-painted text on the stage: fill + ink outline + hard ink shadow."""
    return ink_text(text, style, size, color or pal.sign, pal.ink, max(3, size // 16),
                    max(4, size // 11) if shadow is None else shadow, tracking)


def _word_layout(text: str, style: str, size: int, max_w: int, pal: Palette, center_y: float, line_gap=1.04):
    """Words centred on the stage; *word* is painted in the sign colour. Returns [(sprite, cx, cy, hl)]."""
    lines = wrap_words(text, style, size, max_w)
    f = font(style, size)
    space = f.getlength(" ")
    line_h = size * line_gap
    top = center_y - line_h * len(lines) / 2 + line_h / 2
    out = []
    for li, line in enumerate(lines):
        words = [_highlight(w) for w in line]
        widths = [f.getlength(w) for w, _ in words]
        total = sum(widths) + space * (len(words) - 1)
        x = SAFE_CX - total / 2
        cy = top + li * line_h
        for (word, hl), ww in zip(words, widths):
            sprite = _sign(word, size, pal, pal.sign if hl else pal.paper, style)
            out.append((sprite, x + ww / 2, cy, hl))
            x += ww + space
    return out


def _n_lines(words) -> int:
    return len({round(cy) for _, _, cy, _ in words})


def _ribbon(text: str, pal: Palette, size=30, fill=None, color=None, angle=-3.0) -> Image.Image:
    """A tilted ticket/ribbon label with notched ends."""
    label = ink_text(text, "sign", size, color or pal.paper, pal.ink, 0, 0, 2)
    w, h = label.width + 56, int(size * 1.9)
    r = slab(w, h, (fill or pal.hot) + (255,), pal.ink, radius=6, border=5, shadow=7).copy()
    d = ImageDraw.Draw(r)
    for nx in (7, 7 + w):  # notches
        d.ellipse((nx - 12, 7 + h / 2 - 12, nx + 12, 7 + h / 2 + 12), fill=(0, 0, 0, 0))
    place(r, label, r.width / 2 - 3, r.height / 2 - 2)
    return r.rotate(angle, resample=Image.BICUBIC, expand=True)


def _lines(text: str, style: str, size: int, max_w: int, color) -> list[Image.Image]:
    return [text_sprite(" ".join(w.replace("*", "") for w in ln), style, size, color)
            for ln in wrap_words(text, style, size, max_w)]


def _cue_card(text: str, pal: Palette, width: int, start: int, max_lines: int, angle: float) -> Image.Image:
    """Ink text on a paper card; *word* gets a highlighter stripe behind it."""
    clean = text.replace("*", "")
    inner = width - 110
    size = fit_size(clean, "cond", start, inner, max_lines, min_size=44)
    lines = wrap_words(text, "cond", size, inner)
    f = font("cond", size)
    space = f.getlength(" ")
    lh = int(size * 1.1)
    h = lh * len(lines) + 100
    card = slab(width, h, pal.paper + (255,), pal.ink, radius=18, border=6, shadow=12).copy()
    d = ImageDraw.Draw(card)
    y = 12 + 50
    for line in lines:
        words = [_highlight(w) for w in line]
        widths = [f.getlength(w) for w, _ in words]
        x = 12 + (width - sum(widths) - space * (len(words) - 1)) / 2
        for (word, hl), ww in zip(words, widths):
            if hl:
                d.polygon([(x - 8, y + size * 0.42), (x + ww + 10, y + size * 0.36),
                           (x + ww + 6, y + size * 1.02), (x - 12, y + size * 1.06)], fill=pal.sign + (255,))
            d.text((x, y), word, font=f, fill=pal.ink + (255,))
            x += ww + space
        y += lh
    return card.rotate(angle, resample=Image.BICUBIC, expand=True)


class Confetti:
    """A deterministic burst of flat paper bits from (x, y)."""

    def __init__(self, pal: Palette, seed: int, x: float, y: float, n: int = 50):
        rng = random.Random(seed)
        cols = [pal.sign, pal.hot, pal.cool, pal.paper]
        self.x, self.y = x, y
        self.bits = []
        for _ in range(n):
            a = rng.uniform(-math.pi * 0.95, -math.pi * 0.05)
            v = rng.uniform(700, 1500)
            self.bits.append((math.cos(a) * v, math.sin(a) * v, rng.uniform(0, 6.28), rng.uniform(-9, 9),
                              rng.uniform(11, 19), rng.choice(cols)))

    def draw(self, fg: Image.Image, t: float) -> None:
        if t <= 0 or t > 1.6:
            return
        d = ImageDraw.Draw(fg)
        fade = clamp((1.6 - t) / 0.5)
        drag = (1 - math.exp(-2.2 * t)) / 2.2
        for vx, vy, rot, spin, s, col in self.bits:
            x = self.x + vx * drag
            y = self.y + vy * drag + 900 * t * t
            r = rot + spin * t
            hw, hh = s, s * 0.45 * abs(math.cos(r * 1.7)) + 2
            c, sn = math.cos(r), math.sin(r)
            pts = [(x + px * c - py * sn, y + px * sn + py * c) for px, py in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
            d.polygon(pts, fill=col + (int(255 * fade),))


class FlapTimer:
    """Two split-flap digits that flip each second, over a strip of bulbs that go out one by one."""

    FW, FH = 118, 160
    FLIP = 0.2

    def __init__(self, pal: Palette, think: float):
        self.pal, self.think = pal, think
        self.cache: dict = {}
        self.n_bulbs = math.ceil(think)
        self.bulb_on = disc(13, pal.sign + (255,), pal.ink, 4, 4)
        self.bulb_off = disc(13, pal.ink + (255,), pal.ink, 4, 4)

    def flap(self, ch: str, urgent: bool) -> Image.Image:
        key = (ch, urgent)
        img = self.cache.get(key)
        if img is None:
            w, h = self.FW, self.FH
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=14, fill=self.pal.ink + (255,))
            s = text_sprite(ch, "sign", 112, self.pal.sign if urgent else self.pal.paper)
            img.alpha_composite(s, ((w - s.width) // 2, (h - s.height) // 2 + 6))
            d.rectangle((0, h // 2 - 2, w, h // 2 + 2), fill=self.pal.stage + (255,))
            for px in (2, w - 9):
                d.rounded_rectangle((px, h // 2 - 12, px + 7, h // 2 + 12), radius=3, fill=self.pal.muted + (255,))
            self.cache[key] = img
        return img

    def _digit(self, old: str, new: str, u: float, urgent: bool) -> Image.Image:
        """A flap mid-flip, u seconds after the change."""
        a, b = self.flap(old, urgent), self.flap(new, urgent)
        if old == new or u >= self.FLIP or u < 0:
            return b
        w, h = self.FW, self.FH
        half = h // 2
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.alpha_composite(b.crop((0, 0, w, half)), (0, 0))
        out.alpha_composite(a.crop((0, half, w, h)), (0, half))
        k = u / (self.FLIP / 2)
        if k < 1:  # old top half folds down onto the hinge
            fh = max(1, int(half * (1 - k)))
            out.alpha_composite(a.crop((0, 0, w, half)).resize((w, fh)), (0, half - fh))
        else:  # new bottom half unfolds from the hinge
            fh = max(1, int(half * (k - 1)))
            out.alpha_composite(b.crop((0, half, w, h)).resize((w, fh)), (0, half))
        return out

    def draw(self, fg: Image.Image, el: float, appear: float, gone: float) -> None:
        if appear <= 0 or gone >= 1:
            return
        think = self.think
        left = think - max(0.0, el)
        v = max(0, math.ceil(left - 1e-6))
        u = el - (think - v) if el > 0 and v < math.ceil(think) else 1.0  # seconds since v appeared
        urgent = el > 0 and left <= 3
        old, new = f"{min(99, v + 1):02d}", f"{v:02d}"
        a = clamp(appear) * (1 - gone)
        sc = lerp(0.6, 1, ease_out_back(clamp(appear))) * (1 - 0.3 * gone)
        gap = 14
        panel = Image.new("RGBA", (self.FW * 2 + gap + 10, self.FH + 10), (0, 0, 0, 0))
        for k in range(2):
            digit = self._digit(old[k], new[k], u, urgent)
            shadow = Image.new("RGBA", digit.size, self.pal.ink + (0,))
            shadow.putalpha(digit.getchannel("A"))
            x = k * (self.FW + gap)
            panel.alpha_composite(shadow, (x + 10, 10))
            panel.alpha_composite(digit, (x, 0))
        blit(fg, panel, SAFE_CX + 5, TIMER_Y - 30 + 5, scale=sc, alpha=a)
        # bulb strip: one bulb per second, going out as time runs down
        n = self.n_bulbs
        step = 46
        x0 = SAFE_CX - (n - 1) * step / 2
        for k in range(n):
            blit(fg, self.bulb_on if k < left else self.bulb_off, x0 + k * step, TIMER_Y + 92, alpha=a, scale=sc)


# --------------------------------------------------------------------------- intro / outro

class IntroScene(Scene):
    default_duration = 2.8

    def __init__(self, spec, pal, **kw):
        super().__init__(spec, pal, **kw)
        clean = spec.title.replace("*", "")
        self.size = fit_size(clean, "cond", 150, SAFE_W, 4, min_size=80)
        self.cy = CENTER_Y - 70
        self.words = _word_layout(spec.title, "cond", self.size, SAFE_W, pal, self.cy)
        half = _n_lines(self.words) * self.size * 1.04 / 2
        self.block_top, self.block_bottom = self.cy - half, self.cy + half
        self.theme = _ribbon(spec.theme.upper(), pal, 32, angle=-4) if spec.theme else None
        self.sub = _sign(spec.subtitle, 46, pal, pal.paper, "semi", shadow=4) if spec.subtitle else None
        n = len(spec.rounds)
        self.ticket = _ribbon(f"{n} ROUNDS", pal, 38, fill=pal.sign, color=pal.ink, angle=3)

    def render(self, fg, t):
        if self.theme:
            p = ease_out_back(prog(t, 0.0, 0.45))
            blit(fg, self.theme, SAFE_CX - 120, self.block_top - 80, scale=p, alpha=clamp(p))
        for i, (sprite, cx, cy, hl) in enumerate(self.words):
            p = prog(t, 0.12 + 0.085 * i, 0.38)
            if p <= 0:
                continue
            scale = lerp(0.35, 1.0, ease_out_back(p, 2.2))
            wob = 1 + 0.035 * math.sin(t * 5 + i) if hl else 1
            blit(fg, sprite, cx, cy + (1 - ease_out_cubic(p)) * 60, scale=scale * wob, alpha=ease_out_cubic(p))
        y = self.block_bottom + 60
        if self.sub:
            ps = ease_out_cubic(prog(t, 0.8, 0.4))
            blit(fg, self.sub, SAFE_CX, y + (1 - ps) * 20, anchor="mt", alpha=ps)
            y += 110
        pi = ease_out_back(prog(t, 1.0, 0.45), 2.4)
        blit(fg, self.ticket, SAFE_CX, y + 50, scale=pi, alpha=clamp(pi))

    def sfx(self):
        return [(0.12 + 0.085 * i, "pop") for i in range(min(len(self.words), 10))] + [(1.0, "swipe")]


class OutroScene(Scene):
    default_duration = 3.4

    def __init__(self, spec, pal, **kw):
        super().__init__(spec, pal, **kw)
        clean = spec.outro.replace("*", "")
        self.size = fit_size(clean, "cond", 130, SAFE_W, 3, min_size=72)
        self.cy = CENTER_Y - 230
        self.words = _word_layout(spec.outro, "cond", self.size, SAFE_W, pal, self.cy)
        self.chips_y = self.cy + self.size * 1.04 * _n_lines(self.words) / 2 + 120
        n = len(spec.rounds)
        r = min(62, int((SAFE_W - 22 * n) / (n + 1) / 2))
        self.r = r
        self.chips = []
        for k in range(n + 1):
            c = disc(r, (pal.sign if k == n else pal.paper) + (255,), pal.ink, 5, 8).copy()
            place(c, text_sprite(str(k), "sign", int(r * 1.05), pal.ink), c.width / 2 - 4, c.height / 2 - 1)
            self.chips.append(c)
        self.comment = _sign("COMMENT YOUR SCORE", 40, pal, pal.paper, tracking=2, shadow=4)
        self.follow = _ribbon(spec.follow.upper(), pal, 34, angle=-2)
        self.confetti = Confetti(pal, self.seed + 99, SAFE_CX, self.chips_y)

    def render(self, fg, t):
        for i, (sprite, cx, cy, _) in enumerate(self.words):
            p = prog(t, 0.05 + 0.07 * i, 0.35)
            if p > 0:
                blit(fg, sprite, cx, cy, scale=lerp(0.5, 1, ease_out_back(p, 2)), alpha=ease_out_cubic(p))
        n = len(self.chips)
        d = 2 * self.r
        gap = (SAFE_W - n * d) / max(1, n - 1)
        for k, chip in enumerate(self.chips):
            p = ease_out_back(prog(t, 0.5 + 0.08 * k, 0.4), 2.4)
            x = SAFE_LEFT + k * (d + gap) + self.r
            bob = 9 * math.sin(t * 4 + k * 0.9) * clamp(t - 1.2)
            blit(fg, chip, x, self.chips_y + bob, scale=p, alpha=clamp(p))
        pc = ease_out_cubic(prog(t, 0.9, 0.4))
        cy = self.chips_y + self.r + 50
        blit(fg, self.comment, SAFE_CX, cy + (1 - pc) * 20, anchor="mt", alpha=pc)
        pf = prog(t, 1.2, 0.5)
        if pf > 0:
            pulse = 1 + 0.04 * math.sin((t - 1.7) * 6) * clamp((t - 1.7) * 2)
            blit(fg, self.follow, SAFE_CX, cy + 200, scale=ease_out_back(pf) * pulse, alpha=clamp(pf * 2))
        self.confetti.draw(fg, t - 0.5)

    def sfx(self):
        return [(0.0, "whoosh"), (0.5, "chime")] + [(0.5 + 0.08 * k, "pop") for k in range(len(self.chips))] + [(1.2, "ding")]


# --------------------------------------------------------------------------- rounds

class RoundScene(Scene):
    """Ribbon + heading, the clue, a split-flap countdown for `think` seconds, then the reveal."""

    CLUE_IN = 0.8  # countdown starts once the clue is mostly on screen
    heading = "Guess it"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        self.reveal_at = self.CLUE_IN + rnd.think
        self.duration = self.reveal_at + rnd.reveal
        self.ribbon = _ribbon(f"ROUND {self.index} OF {self.total}", pal, 28, angle=-3 if self.index % 2 else 3)
        hsize = fit_size(self.heading.upper(), "sign", 74, SAFE_W, 1, min_size=40)
        self.head = _sign(self.heading.upper(), hsize, pal)
        self.timer = FlapTimer(pal, rnd.think)
        self.confetti = Confetti(pal, self.seed + 7 * self.index, SAFE_CX, TIMER_Y)

    # -- shared pieces
    def _header(self, fg, t):
        p = ease_out_back(prog(t, 0.0, 0.4), 2.2)
        blit(fg, self.ribbon, SAFE_CX, SAFE_TOP + 40, scale=p, alpha=clamp(p))
        ph = ease_out_back(prog(t, 0.1, 0.45), 1.8)
        blit(fg, self.head, SAFE_CX, SAFE_TOP + 140, scale=lerp(0.6, 1, ph), alpha=clamp(ph))

    def _timer(self, fg, t):
        appear = prog(t, self.CLUE_IN - 0.3, 0.35)
        gone = ease_out_cubic(prog(t, self.reveal_at, 0.25))
        self.timer.draw(fg, t - self.CLUE_IN, appear, gone)

    def _podium(self, answer: str, note: str = ""):
        """The answer on a hot-coloured podium card with an 'ANSWER' tab."""
        text = answer.upper()
        size = fit_size(text, "sign", 72, SAFE_W - 90, 2, min_size=38)
        lines = wrap_words(text, "sign", size, SAFE_W - 90)
        lh = int(size * 1.18)
        h = 80 + lh * len(lines)
        tab = _ribbon("ANSWER", self.pal, 24, fill=self.pal.sign, color=self.pal.ink, angle=-5)
        card = slab(SAFE_W, h, self.pal.hot + (255,), self.pal.ink, radius=24, border=6, shadow=12)
        out = Image.new("RGBA", (card.width, card.height + tab.height // 2), (0, 0, 0, 0))
        out.alpha_composite(card, (0, tab.height // 2))
        y = tab.height // 2 + 12 + 42
        for ln in lines:
            s = ink_text(" ".join(ln), "sign", size, self.pal.paper, self.pal.ink, max(2, size // 18), max(3, size // 14))
            out.alpha_composite(s, ((out.width - s.width) // 2, y - (s.height - lh) // 2 - 4))
            y += lh
        out.alpha_composite(tab, (34, 0))
        note_s = None
        if note:
            ns = fit_size(note, "semi", 46, SAFE_W, 1, min_size=30)
            note_s = _sign(note, ns, self.pal, self.pal.paper, "semi", shadow=3)
        return out, note_s

    def _draw_podium(self, fg, t, card, note_s, y=TIMER_Y):
        p = prog(t, self.reveal_at, 0.45)
        if p <= 0:
            return
        e = ease_out_back(p, 2.0)
        blit(fg, card, SAFE_CX, y + (1 - ease_out_cubic(p)) * 120, scale=lerp(0.7, 1, e), alpha=clamp(p * 3))
        if note_s:
            pn = ease_out_cubic(prog(t, self.reveal_at + 0.3, 0.4))
            blit(fg, note_s, SAFE_CX, y + card.height / 2 + 16 + (1 - pn) * 20, anchor="mt", alpha=pn)

    def _draw_lines_below(self, fg, t, lines, step, y=TIMER_Y):
        y0 = y - (len(lines) - 1) * step / 2
        for i, ln in enumerate(lines):
            p = ease_out_cubic(prog(t, self.reveal_at + 0.25 + 0.1 * i, 0.4))
            blit(fg, ln, SAFE_CX, y0 + i * step + (1 - p) * 24, alpha=p)

    def revealed(self, t) -> float:
        return ease_out_cubic(prog(t, self.reveal_at, 0.35))

    def render(self, fg, t):
        self._header(fg, t)
        self.clue(fg, t)
        self._timer(fg, t)
        self.answer(fg, t)
        self.confetti.draw(fg, t - self.reveal_at)

    def clue(self, fg, t):  # pragma: no cover - interface
        raise NotImplementedError

    def answer(self, fg, t):  # pragma: no cover - interface
        raise NotImplementedError

    def clue_sfx(self) -> list[tuple[float, str]]:
        return []

    def sfx(self):
        ev = [(0.0, "whoosh"), (0.1, "impact")] + self.clue_sfx()
        think = self.item.think
        for m in range(int(think), 0, -1):  # one tick each time the number changes
            ev.append((self.CLUE_IN + think - m, "tock" if m <= 3 else "clock"))
        ev += [(self.reveal_at, "reveal"), (self.reveal_at + 0.05, "chime")]
        return ev

    def pulses(self):
        return [0.0, self.reveal_at]


class EmojiScene(RoundScene):
    def __init__(self, rnd, pal, **kw):
        self.heading = f"Guess the {rnd.category}"
        super().__init__(rnd, pal, **kw)
        glyphs = clusters(rnd.emojis)
        n = len(glyphs)
        per_row = n if n <= 4 else math.ceil(n / 2)
        gap = 34
        dia = min(236, int((SAFE_W - gap * (per_row - 1)) / per_row))
        self.r = dia // 2
        esize = int(dia * 0.64)
        rows = [glyphs[:per_row], glyphs[per_row:]] if n > per_row else [glyphs]
        step = dia + gap
        self.pos = []
        for ri, row in enumerate(rows):
            cy = CLUE_Y - (len(rows) - 1) * step / 2 + ri * step - 40
            x0 = SAFE_CX - (len(row) - 1) * step / 2
            for k, g in enumerate(row):
                plate = disc(self.r, pal.paper + (255,), pal.ink, 6, 10).copy()
                place(plate, emoji_sprite(g, esize), plate.width / 2 - 5, plate.height / 2 - 5)
                self.pos.append((plate, x0 + k * step, cy))
        self.card, self.note = self._podium(rnd.answer, rnd.note)

    def clue(self, fg, t):
        rv = self.revealed(t)
        for i, (plate, x, y) in enumerate(self.pos):
            p = prog(t, 0.25 + 0.14 * i, 0.4)
            if p <= 0:
                continue
            bob = 10 * math.sin(t * 3.2 + i * 1.3) * clamp((t - 1.0) * 2)
            scale = ease_out_back(p, 2.6) * lerp(1, 0.84, rv)
            blit(fg, plate, x, y + bob - 70 * rv, scale=scale, alpha=clamp(p * 2))

    def answer(self, fg, t):
        self._draw_podium(fg, t, self.card, self.note)

    def clue_sfx(self):
        return [(0.25 + 0.14 * i, "pop") for i in range(len(self.pos))]


class BadDescriptionScene(RoundScene):
    def __init__(self, rnd, pal, **kw):
        self.heading = f"Badly described {rnd.category}"
        super().__init__(rnd, pal, **kw)
        self.card_img = _cue_card(rnd.description, pal, SAFE_W, 84, 5, angle=-2.0 if self.index % 2 else 2.0)
        self.card, self.note = self._podium(rnd.answer, rnd.note)

    def clue(self, fg, t):
        rv = self.revealed(t)
        p = prog(t, 0.2, 0.5)
        if p <= 0:
            return
        e = ease_out_back(p, 1.6)
        blit(fg, self.card_img, SAFE_CX, CLUE_Y - 40 - (1 - ease_out_cubic(p)) * 140 - 60 * rv,
             scale=lerp(0.85, 1, e) * lerp(1, 0.9, rv), alpha=clamp(p * 3))

    def answer(self, fg, t):
        self._draw_podium(fg, t, self.card, self.note)

    def clue_sfx(self):
        return [(0.2, "swipe")]


class TrueFalseScene(RoundScene):
    heading = "Real or fake?"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        self.card_img = _cue_card(rnd.statement, pal, SAFE_W, 80, 4, angle=1.5 if self.index % 2 else -1.5)
        self.card_y = CLUE_Y - 110
        self.btn_y = self.card_y + self.card_img.height / 2 + 120
        bw, bh = SAFE_W // 2 - 24, 140
        self.btns = []
        for k, label in enumerate(("REAL", "FAKE")):
            right = (k == 0) == rnd.answer
            plain = slab(bw, bh, pal.paper + (255,), pal.ink, radius=bh // 2, border=6, shadow=10).copy()
            place(plain, text_sprite(label, "sign", 60, pal.ink), plain.width / 2 - 5, plain.height / 2 - 2)
            lit = slab(bw, bh, pal.sign + (255,), pal.ink, radius=bh // 2, border=6, shadow=10).copy()
            place(lit, text_sprite(label, "sign", 60, pal.ink), lit.width / 2 - 5, lit.height / 2 - 2)
            struck = plain.copy()  # the wrong buzzer gets a hot strike-through
            ImageDraw.Draw(struck).line((40, struck.height - 40, struck.width - 50, 30), fill=pal.hot + (255,), width=14)
            x = SAFE_LEFT + bw / 2 + k * (bw + 48)
            self.btns.append((plain, lit if right else struck, x, right))
        size = fit_size(rnd.explanation, "semi", 48, SAFE_W, 2, min_size=32)
        self.expl = [_sign(" ".join(ln), size, pal, pal.paper, "semi", shadow=3)
                     for ln in wrap_words(rnd.explanation, "semi", size, SAFE_W)]
        self.expl_h = int(size * 1.2)

    def clue(self, fg, t):
        p = prog(t, 0.2, 0.5)
        if p > 0:
            blit(fg, self.card_img, SAFE_CX, self.card_y - (1 - ease_out_cubic(p)) * 140,
                 scale=lerp(0.85, 1, ease_out_back(p, 1.6)), alpha=clamp(p * 3))
        rv = self.revealed(t)
        for k, (plain, after, x, right) in enumerate(self.btns):
            p = ease_out_back(prog(t, 0.5 + 0.12 * k, 0.4))
            if p <= 0:
                continue
            if rv > 0:
                sc = p * (lerp(1, 1.1, rv) if right else lerp(1, 0.9, rv))
                blit(fg, after, x, self.btn_y, scale=sc, alpha=1 if right else lerp(1, 0.6, rv))
            else:
                blit(fg, plain, x, self.btn_y, scale=p, alpha=clamp(p))

    def answer(self, fg, t):
        self._draw_lines_below(fg, t, self.expl, self.expl_h)

    def clue_sfx(self):
        return [(0.2, "swipe"), (0.5, "pop"), (0.62, "pop")]


class _OptionsScene(RoundScene):
    """Shared by multiple choice and odd-one-out: paper slabs, one lights up on the reveal."""

    def _build(self, options: list[str], correct: int, grid: bool, top: float):
        cols = 2 if grid else 1
        gap = 30
        cw = (SAFE_W - gap * (cols - 1)) // cols
        ch = 180 if grid else 104
        text_w = cw - (50 if grid else 150)
        tsize = min(fit_size(o, "bold", 54 if grid else 50, text_w, 2 if grid else 1, min_size=30) for o in options)
        self.opts = []
        for k, o in enumerate(options):
            r, c = divmod(k, cols)
            x = SAFE_LEFT + c * (cw + gap) + cw / 2
            y = top + r * (ch + gap) + ch / 2
            lines = _lines(o, "bold", tsize, text_w, self.pal.ink)
            letter = "" if grid else "ABCD"[k]
            plain = self._opt(cw, ch, lines, letter, self.pal.paper)
            lit = self._opt(cw, ch, lines, letter, self.pal.sign)
            self.opts.append((plain, lit, x, y, k == correct))

    def _opt(self, w, h, lines, letter, fill):
        c = slab(w, h, fill + (255,), self.pal.ink, radius=20, border=6, shadow=9).copy()
        s = 9
        if letter:
            badge = disc(30, self.pal.hot + (255,), self.pal.ink, 4, 0).copy()
            place(badge, text_sprite(letter, "sign", 34, self.pal.paper), badge.width / 2, badge.height / 2 + 1)
            c.alpha_composite(badge, (s + 24, s + (h - badge.height) // 2))
        lh = lines[0].height * 0.9
        y = s + (h - lh * len(lines)) / 2
        for ln in lines:
            x = s + 100 if letter else s + (w - ln.width) // 2
            c.alpha_composite(ln, (int(x), int(y)))
            y += lh
        return c

    def clue_opts(self, fg, t, start):
        rv = self.revealed(t)
        for k, (plain, lit, x, y, right) in enumerate(self.opts):
            e = ease_out_expo(prog(t, start + 0.12 * k, 0.5))
            if e <= 0:
                continue
            if rv > 0:
                if right:
                    blit(fg, lit, x, y, scale=lerp(1, 1.06, ease_out_back(rv, 3)))
                else:
                    blit(fg, plain, x, y, scale=lerp(1, 0.94, rv), alpha=lerp(1, 0.4, rv))
            else:
                blit(fg, plain, x + (1 - e) * 420, y, alpha=e)

    def opts_sfx(self, start):
        return [(start + 0.12 * k, "swipe") for k in range(len(self.opts))]


class ChoiceScene(_OptionsScene):
    heading = "Quick quiz"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        clean = rnd.question.replace("*", "")
        self.size = fit_size(clean, "cond", 84, SAFE_W, 3, min_size=50)
        n_lines = len(wrap_words(rnd.question, "cond", self.size, SAFE_W))
        q_h = n_lines * self.size * 1.04
        opts_h = len(rnd.options) * 134 - 30
        top = max(SAFE_TOP + 220, CLUE_Y - 40 - (q_h + 50 + opts_h) / 2)
        self.words = _word_layout(rnd.question, "cond", self.size, SAFE_W, pal, top + q_h / 2)
        self._build(rnd.options, rnd.correct, False, top + q_h + 50)
        self.note = None
        if rnd.note:
            ns = fit_size(rnd.note, "semi", 48, SAFE_W, 1, min_size=30)
            self.note = _sign(rnd.note, ns, pal, pal.paper, "semi", shadow=3)

    def clue(self, fg, t):
        for i, (sprite, cx, cy, _) in enumerate(self.words):
            p = ease_out_cubic(prog(t, 0.2 + 0.04 * i, 0.3))
            blit(fg, sprite, cx, cy + (1 - p) * 30, alpha=p)
        self.clue_opts(fg, t, 0.45)

    def answer(self, fg, t):
        if self.note:
            self._draw_lines_below(fg, t, [self.note], 0)

    def clue_sfx(self):
        return self.opts_sfx(0.45)


class OddOneOutScene(_OptionsScene):
    heading = "Odd one out"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        self._build(rnd.items, rnd.odd, True, CLUE_Y - 60 - 195)
        size = fit_size(rnd.reason, "semi", 48, SAFE_W, 2, min_size=32)
        self.reason = [_sign(" ".join(ln), size, pal, pal.paper, "semi", shadow=3)
                       for ln in wrap_words(rnd.reason, "semi", size, SAFE_W)]
        self.reason_h = int(size * 1.2)

    def clue(self, fg, t):
        self.clue_opts(fg, t, 0.25)

    def answer(self, fg, t):
        self._draw_lines_below(fg, t, self.reason, self.reason_h)

    def clue_sfx(self):
        return self.opts_sfx(0.25)


def scramble(word: str, seed: int) -> list[int]:
    """A permutation of range(len(word)) that never leaves the word unchanged (when possible)."""
    rng = random.Random(seed)
    idx = list(range(len(word)))
    if len(set(word.lower())) < 2:
        return idx
    for _ in range(50):
        rng.shuffle(idx)
        if "".join(word[i] for i in idx).lower() != word.lower():
            break
    return idx


class UnscrambleScene(RoundScene):
    def __init__(self, rnd, pal, **kw):
        self.heading = f"Unscramble the {rnd.category}"
        super().__init__(rnd, pal, **kw)
        words = [w.replace("'", "") for w in rnd.answer.upper().split()]
        one_row = sum(len(w) for w in words) + len(words) - 1
        # one row if it fits at a decent size, else one word per row
        if one_row * 72 <= SAFE_W:
            rows = [" ".join(words)]
        else:
            rows = words
            if len(rows) > 3:
                rows = [" ".join(words[: len(words) // 2]), " ".join(words[len(words) // 2:])]
        cols = max(len(r) for r in rows)
        self.tile = min(140, int(SAFE_W / (cols * 1.14)))
        step = self.tile * 1.14
        lsize = int(self.tile * 0.56)
        rng = random.Random(self.seed + self.index)
        self.tiles = []  # (plain, lit, (sx, sy), (ex, ey))
        row_step = self.tile * 1.34
        top = CLUE_Y - 40 - (len(rows) - 1) * row_step / 2
        k = 0
        for ri, row in enumerate(rows):
            y = top + ri * row_step
            x0 = SAFE_CX - (len(row) - 1) * step / 2
            for wi, w in enumerate(row.split(" ")):
                offset = sum(len(p) + 1 for p in row.split(" ")[:wi])  # position of this word in the row
                perm = scramble(w, self.seed + k)
                for j, ch in enumerate(w):
                    end = (x0 + (offset + j) * step, y)
                    begin = (x0 + (offset + perm.index(j)) * step, y)
                    angle = rng.uniform(-6, 6)
                    pair = []
                    for fill in (pal.paper, pal.sign):
                        tl = slab(self.tile, self.tile, fill + (255,), pal.ink, radius=self.tile // 6,
                                  border=max(4, self.tile // 24), shadow=max(5, self.tile // 14)).copy()
                        place(tl, text_sprite(ch, "sign", lsize, pal.ink), tl.width / 2 - 3, tl.height / 2 - 1)
                        pair.append(tl.rotate(angle, resample=Image.BICUBIC, expand=True))
                    self.tiles.append((pair[0], pair[1], begin, end))
                    k += 1
        self.note = None
        if rnd.note:
            ns = fit_size(rnd.note, "semi", 46, SAFE_W, 1, min_size=30)
            self.note = _sign(rnd.note, ns, pal, pal.paper, "semi", shadow=3)

    def clue(self, fg, t):
        for i, (plain, lit, (sx, sy), (ex, ey)) in enumerate(self.tiles):
            p = ease_out_back(prog(t, 0.25 + 0.05 * i, 0.35), 2.2)
            if p <= 0:
                continue
            m = ease_in_out_cubic(prog(t, self.reveal_at + 0.03 * i, 0.5))
            hop = -math.sin(math.pi * m) * self.tile * 0.8
            x, y = lerp(sx, ex, m), lerp(sy, ey, m) + hop
            wig = 0 if m > 0 else 3 * math.sin(t * 9 + i)
            blit(fg, lit if m > 0.5 else plain, x + wig, y, scale=p, alpha=clamp(p * 2))

    def answer(self, fg, t):
        if self.note:
            pn = ease_out_cubic(prog(t, self.reveal_at + 0.6, 0.4))
            blit(fg, self.note, SAFE_CX, TIMER_Y + (1 - pn) * 20, alpha=pn)

    def clue_sfx(self):
        return [(0.25 + 0.05 * i, "tick") for i in range(len(self.tiles))]


ROUNDS = {
    "emoji": EmojiScene,
    "bad_description": BadDescriptionScene,
    "true_false": TrueFalseScene,
    "choice": ChoiceScene,
    "odd_one_out": OddOneOutScene,
    "unscramble": UnscrambleScene,
}


def build_scenes(spec, pal: Palette, seed: int) -> list[Scene]:
    n = len(spec.rounds)
    scenes: list[Scene] = [IntroScene(spec, pal, total=n, seed=seed)]
    for i, r in enumerate(spec.rounds, 1):
        scenes.append(ROUNDS[r.type](r, pal, index=i, total=n, seed=seed))
    scenes.append(OutroScene(spec, pal, total=n, seed=seed))
    return scenes
