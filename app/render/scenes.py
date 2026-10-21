"""Scene types. Each scene draws onto a transparent full-frame layer as a pure function of local time."""
from __future__ import annotations

import math
import random
import re

from PIL import Image, ImageDraw

from .draw import (
    blit,
    clamp,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_expo,
    fit_size,
    lerp,
    prog,
    rounded_rect,
    text_sprite,
    wrap_words,
)
from .emoji import clusters, emoji_sprite
from .theme import SAFE_BOTTOM, SAFE_CX, SAFE_LEFT, SAFE_TOP, SAFE_W, Palette, font

CENTER_Y = (SAFE_TOP + SAFE_BOTTOM) // 2
CLUE_Y = 840  # centre of the clue area
TIMER_Y = 1300  # countdown ring; the answer card replaces it on reveal
WRONG = (255, 77, 94)


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
        """Moments (local time) when the background flashes."""
        return [0.0]


# --------------------------------------------------------------------------- helpers

def _highlight(word: str) -> tuple[str, bool]:
    """'*word*' or '*word*?' -> ('word?', True); anything else loses stray asterisks."""
    m = re.fullmatch(r"([^\w*]*)\*(.+?)\*([^\w*]*)", word)
    if m:
        return "".join(m.groups()), True
    return word.replace("*", ""), False


def _word_layout(text: str, weight: str, size: int, max_w: int, pal: Palette, center_y: float, line_gap=1.08):
    """Lay out words centred; *word* is highlighted. Returns [(sprite, cx, cy, highlighted)]."""
    lines = wrap_words(text, weight, size, max_w)
    f = font(weight, size)
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
            sprite = text_sprite(word, weight, size, pal.accent if hl else pal.text)
            out.append((sprite, x + ww / 2, cy, hl))
            x += ww + space
    return out


def _pill(text: str, pal: Palette, size: int = 34, fill=None, color=None, pad_x=30, pad_y=16, tracking=3):
    s = text_sprite(text, "bold", size, color or pal.on_accent, tracking)
    w, h = s.width + pad_x * 2, int(size * 1.25) + pad_y * 2
    bg = rounded_rect(w, h, h // 2, (fill or pal.accent) + (255,)).copy()
    bg.alpha_composite(s, (pad_x, (h - s.height) // 2 + 2))
    return bg


def _lines(text: str, weight: str, size: int, max_w: int, color) -> list[Image.Image]:
    return [text_sprite(" ".join(w.replace("*", "") for w in ln), weight, size, color)
            for ln in wrap_words(text, weight, size, max_w)]


def _card(w: int, h: int, label: Image.Image | None, fill, outline=None, radius=30) -> Image.Image:
    c = rounded_rect(w, h, radius, fill, outline, 3 if outline else 0).copy()
    if label is not None:
        c.alpha_composite(label, ((w - label.width) // 2, (h - label.height) // 2 + 2))
    return c


def _words_in(fg, words, t, start, step=0.05, rise=36, size=0, pal=None):
    for i, (sprite, cx, cy, hl) in enumerate(words):
        p = prog(t, start + step * i, 0.32)
        if p <= 0:
            continue
        blit(fg, sprite, cx, cy + (1 - ease_out_cubic(p)) * rise, alpha=ease_out_cubic(p))
        if hl and pal:
            up = ease_out_cubic(prog(t, start + 0.25 + step * i, 0.4))
            if up > 0:
                bar = rounded_rect(max(int(sprite.width * up), 8), 12, 6, pal.accent + (255,))
                blit(fg, bar, cx - sprite.width / 2, cy + size * 0.6, anchor="lm")


class Confetti:
    """A deterministic burst of paper bits from (x, y)."""

    def __init__(self, pal: Palette, seed: int, x: float, y: float, n: int = 46):
        rng = random.Random(seed)
        cols = [pal.accent, pal.accent2, pal.text, (255, 214, 64)]
        self.x, self.y = x, y
        self.bits = []
        for _ in range(n):
            a = rng.uniform(-math.pi * 0.95, -math.pi * 0.05)
            v = rng.uniform(700, 1500)
            self.bits.append((math.cos(a) * v, math.sin(a) * v, rng.uniform(0, 6.28), rng.uniform(-9, 9),
                              rng.uniform(10, 18), rng.choice(cols)))

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


# --------------------------------------------------------------------------- intro / outro

class IntroScene(Scene):
    default_duration = 2.8

    def __init__(self, spec, pal, **kw):
        super().__init__(spec, pal, **kw)
        clean = spec.title.replace("*", "")
        self.size = fit_size(clean, "black", 128, SAFE_W, 4, min_size=72)
        self.words = _word_layout(spec.title, "black", self.size, SAFE_W, pal, CENTER_Y - 60)
        n_lines = len({round(cy) for _, _, cy, _ in self.words})
        self.block_top = CENTER_Y - 60 - n_lines * self.size * 1.08 / 2
        self.block_bottom = CENTER_Y - 60 + n_lines * self.size * 1.08 / 2
        self.theme = _pill(spec.theme.upper(), pal, 34, fill=pal.accent2) if spec.theme else None
        n = len(spec.rounds)
        label = text_sprite(f"{n} ROUNDS", "bold", 36, pal.text, 4)
        self.info = _card(label.width + 60, 77, label, (255, 255, 255, 26), (255, 255, 255, 80), 38)
        self.sub = text_sprite(spec.subtitle, "semi", 46, pal.muted) if spec.subtitle else None

    def render(self, fg, t):
        if self.theme:
            p = ease_out_back(prog(t, 0.0, 0.45))
            blit(fg, self.theme, SAFE_CX, self.block_top - 90, scale=p, alpha=clamp(p))
        for i, (sprite, cx, cy, hl) in enumerate(self.words):
            p = prog(t, 0.12 + 0.085 * i, 0.38)
            if p <= 0:
                continue
            scale = lerp(0.35, 1.0, ease_out_back(p, 2.2))
            wob = 1 + 0.03 * math.sin(t * 5 + i) if hl else 1
            blit(fg, sprite, cx, cy + (1 - ease_out_cubic(p)) * 50, scale=scale * wob, alpha=ease_out_cubic(p))
        y = self.block_bottom + 70
        if self.sub:
            ps = ease_out_cubic(prog(t, 0.8, 0.4))
            blit(fg, self.sub, SAFE_CX, y + (1 - ps) * 20, anchor="mt", alpha=ps)
            y += 100
        pi = ease_out_back(prog(t, 1.0, 0.45))
        blit(fg, self.info, SAFE_CX, y + 40, scale=pi, alpha=clamp(pi))

    def sfx(self):
        return [(0.12 + 0.085 * i, "pop") for i in range(min(len(self.words), 10))] + [(1.0, "swipe")]


class OutroScene(Scene):
    default_duration = 3.4

    def __init__(self, spec, pal, **kw):
        super().__init__(spec, pal, **kw)
        clean = spec.outro.replace("*", "")
        self.size = fit_size(clean, "black", 112, SAFE_W, 3, min_size=64)
        self.words = _word_layout(spec.outro, "black", self.size, SAFE_W, pal, CENTER_Y - 200)
        n_lines = len({round(cy) for _, _, cy, _ in self.words})
        self.chips_y = CENTER_Y - 200 + self.size * 1.08 * n_lines / 2 + 110
        n = len(spec.rounds)
        cw = min(140, (SAFE_W - 20 * n) // (n + 1))
        self.chips = [_card(cw, cw, text_sprite(str(k), "black", int(cw * 0.5), pal.text),
                            (255, 255, 255, 24), (255, 255, 255, 70), 24) for k in range(n + 1)]
        self.chip_w = cw
        self.comment = text_sprite("Comment your score", "semi", 50, pal.muted)
        self.follow = _pill(spec.follow.upper(), pal, 38, fill=pal.accent2, tracking=2)
        self.confetti = Confetti(pal, self.seed + 99, SAFE_CX, self.chips_y)

    def render(self, fg, t):
        for i, (sprite, cx, cy, _) in enumerate(self.words):
            p = prog(t, 0.05 + 0.07 * i, 0.35)
            if p > 0:
                blit(fg, sprite, cx, cy, scale=lerp(0.5, 1, ease_out_back(p, 2)), alpha=ease_out_cubic(p))
        n = len(self.chips)
        gap = (SAFE_W - n * self.chip_w) / max(1, n - 1)
        for k, chip in enumerate(self.chips):
            p = ease_out_back(prog(t, 0.5 + 0.08 * k, 0.4), 2.4)
            x = SAFE_LEFT + k * (self.chip_w + gap) + self.chip_w / 2
            bob = 8 * math.sin(t * 4 + k * 0.9) * clamp(t - 1.2)
            blit(fg, chip, x, self.chips_y + bob, scale=p, alpha=clamp(p))
        pc = ease_out_cubic(prog(t, 0.9, 0.4))
        blit(fg, self.comment, SAFE_CX, self.chips_y + self.chip_w / 2 + 40 + (1 - pc) * 20, anchor="mt", alpha=pc)
        pf = prog(t, 1.2, 0.5)
        if pf > 0:
            pulse = 1 + 0.045 * math.sin((t - 1.7) * 6) * clamp((t - 1.7) * 2)
            y = self.chips_y + self.chip_w / 2 + 230
            blit(fg, self.follow, SAFE_CX, y, scale=ease_out_back(pf) * pulse, alpha=clamp(pf * 2))
        self.confetti.draw(fg, t - 0.5)

    def sfx(self):
        return [(0.0, "whoosh"), (0.5, "chime")] + [(0.5 + 0.08 * k, "pop") for k in range(len(self.chips))] + [(1.2, "ding")]


# --------------------------------------------------------------------------- rounds

class RoundScene(Scene):
    """Header + clue, a countdown for `think` seconds, then the reveal."""

    CLUE_IN = 0.8  # countdown starts once the clue is mostly on screen
    heading = "Guess it"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        self.reveal_at = self.CLUE_IN + rnd.think
        self.duration = self.reveal_at + rnd.reveal
        self.round_label = text_sprite(f"ROUND {self.index} / {self.total}", "bold", 32, pal.muted, 5)
        hsize = fit_size(self.heading.upper(), "black", 78, SAFE_W, 1, min_size=48)
        self.head = text_sprite(self.heading.upper(), "black", hsize, pal.text, 2)
        self.ring = {}
        self.confetti = Confetti(pal, self.seed + 7 * self.index, SAFE_CX, TIMER_Y)

    # -- shared pieces
    def _header(self, fg, t):
        p = ease_out_cubic(prog(t, 0.0, 0.4))
        blit(fg, self.round_label, SAFE_CX, SAFE_TOP + 30 + (1 - p) * 20, anchor="mt", alpha=p)
        ph = ease_out_back(prog(t, 0.08, 0.45), 1.8)
        blit(fg, self.head, SAFE_CX, SAFE_TOP + 120, anchor="mm", scale=lerp(0.6, 1, ph), alpha=clamp(ph))

    def _timer(self, fg, t):
        think = self.item.think
        el = t - self.CLUE_IN
        appear = ease_out_back(prog(t, self.CLUE_IN - 0.3, 0.35))
        gone = ease_out_cubic(prog(t, self.reveal_at, 0.25))
        if appear <= 0 or gone >= 1:
            return
        left = clamp(1 - el / think)
        secs = max(0, math.ceil(think - el - 1e-6)) if el > 0 else math.ceil(think)
        urgent = el > think - 3
        r = 92
        size = r * 2 + 40
        key = (round(left * 240), urgent)
        ring = self.ring.get(key)
        if ring is None:
            ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            d = ImageDraw.Draw(ring)
            box = (20, 20, size - 20, size - 20)
            d.ellipse(box, fill=(0, 0, 0, 90), outline=self.pal.text + (40,), width=14)
            col = WRONG if urgent else self.pal.accent
            if left > 0:
                d.arc(box, -90, -90 + 360 * left, fill=col + (255,), width=14)
            self.ring[key] = ring
        num = text_sprite(str(secs), "black", 96, WRONG if urgent else self.pal.text)
        frac = (think - el) % 1 if el > 0 else 0
        beat = 1 + (0.12 if urgent else 0.06) * ease_out_cubic(clamp((frac - 0.75) / 0.25)) if el > 0 else 1
        sc = appear * (1 - gone) * beat
        blit(fg, ring, SAFE_CX, TIMER_Y, scale=sc, alpha=clamp(appear) * (1 - gone))
        blit(fg, num, SAFE_CX, TIMER_Y - 4, scale=sc, alpha=clamp(appear) * (1 - gone))

    def _answer_card(self, answer: str, note: str = ""):
        size = fit_size(answer, "black", 84, SAFE_W - 80, 2, min_size=48)
        lines = _lines(answer, "black", size, SAFE_W - 80, self.pal.on_accent)
        lh = int(size * 1.08)
        h = 70 + lh * len(lines)
        card = rounded_rect(SAFE_W, h, 36, self.pal.accent + (255,)).copy()
        y = 35
        for ln in lines:
            card.alpha_composite(ln, ((SAFE_W - ln.width) // 2, y))
            y += lh
        note_s = None
        if note:
            ns = fit_size(note, "semi", 44, SAFE_W, 1, min_size=30)
            note_s = text_sprite(note, "semi", ns, self.pal.text)
        return card, note_s

    def _draw_answer(self, fg, t, card, note_s, y=TIMER_Y):
        p = prog(t, self.reveal_at, 0.45)
        if p <= 0:
            return
        e = ease_out_back(p, 2.0)
        blit(fg, card, SAFE_CX, y, scale=lerp(0.4, 1, e), alpha=clamp(p * 3))
        if note_s:
            pn = ease_out_cubic(prog(t, self.reveal_at + 0.3, 0.4))
            blit(fg, note_s, SAFE_CX, y + card.height / 2 + 26 + (1 - pn) * 20, anchor="mt", alpha=pn)

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
        self.glyphs = clusters(rnd.emojis)
        n = len(self.glyphs)
        per_row = n if n <= 4 else math.ceil(n / 2)
        self.size = min(210, int((SAFE_W - 30 * (per_row - 1)) / per_row))
        rows = [self.glyphs[:per_row], self.glyphs[per_row:]] if n > per_row else [self.glyphs]
        step = self.size + 30
        self.pos = []
        for ri, row in enumerate(rows):
            cy = CLUE_Y - (len(rows) - 1) * step / 2 + ri * step - 40
            x0 = SAFE_CX - (len(row) - 1) * step / 2
            for k, g in enumerate(row):
                self.pos.append((g, x0 + k * step, cy))
        self.card, self.note = self._answer_card(rnd.answer, rnd.note)

    def clue(self, fg, t):
        rv = self.revealed(t)
        for i, (g, x, y) in enumerate(self.pos):
            p = prog(t, 0.25 + 0.14 * i, 0.4)
            if p <= 0:
                continue
            bob = 10 * math.sin(t * 3.2 + i * 1.3) * clamp((t - 1.0) * 2)
            sprite = emoji_sprite(g, self.size)
            scale = ease_out_back(p, 2.6) * lerp(1, 0.82, rv)
            blit(fg, sprite, x, y + bob - 60 * rv, scale=scale, alpha=clamp(p * 2))

    def answer(self, fg, t):
        self._draw_answer(fg, t, self.card, self.note)

    def clue_sfx(self):
        return [(0.25 + 0.14 * i, "pop") for i in range(len(self.pos))]


class BadDescriptionScene(RoundScene):
    def __init__(self, rnd, pal, **kw):
        self.heading = f"Badly described {rnd.category}"
        super().__init__(rnd, pal, **kw)
        clean = rnd.description.replace("*", "")
        self.size = fit_size(clean, "black", 84, SAFE_W - 40, 6, min_size=50)
        n_lines = len(wrap_words(rnd.description, "black", self.size, SAFE_W - 40))
        self.words = _word_layout(rnd.description, "black", self.size, SAFE_W - 40, pal, CLUE_Y - 30)
        self.quote_y = CLUE_Y - 30 - n_lines * self.size * 1.08 / 2 - 70
        self.quote = text_sprite("“", "black", 220, pal.accent)
        self.card, self.note = self._answer_card(rnd.answer, rnd.note)

    def clue(self, fg, t):
        rv = self.revealed(t)
        pq = ease_out_back(prog(t, 0.15, 0.4))
        blit(fg, self.quote, SAFE_LEFT + 40, self.quote_y, scale=pq, alpha=clamp(pq) * 0.9)
        layer = Image.new("RGBA", fg.size, (0, 0, 0, 0)) if rv > 0 else fg
        _words_in(layer, self.words, t, 0.3, step=0.035, size=self.size, pal=self.pal)
        if rv > 0:
            blit(fg, layer, 0, -50 * rv, anchor="lt", alpha=lerp(1, 0.55, rv))

    def answer(self, fg, t):
        self._draw_answer(fg, t, self.card, self.note)

    def clue_sfx(self):
        return [(0.15, "pop")]


class TrueFalseScene(RoundScene):
    heading = "Real or fake?"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        clean = rnd.statement.replace("*", "")
        self.size = fit_size(clean, "black", 88, SAFE_W, 5, min_size=52)
        self.words = _word_layout(rnd.statement, "black", self.size, SAFE_W, pal, CLUE_Y - 120)
        n_lines = len(wrap_words(rnd.statement, "black", self.size, SAFE_W))
        self.btn_y = CLUE_Y - 120 + n_lines * self.size * 1.08 / 2 + 130
        bw, bh = SAFE_W // 2 - 20, 130
        self.btns = []
        for k, label in enumerate(("REAL", "FAKE")):
            right = (k == 0) == rnd.answer
            plain = _card(bw, bh, text_sprite(label, "black", 64, pal.text, 3), (255, 255, 255, 24), (255, 255, 255, 80))
            col = (46, 204, 113) if right else WRONG
            lit = _card(bw, bh, text_sprite(label, "black", 64, (255, 255, 255), 3), col + (255,))
            x = SAFE_LEFT + bw / 2 + k * (bw + 40)
            self.btns.append((plain, lit, x, right))
        size = fit_size(rnd.explanation, "semi", 50, SAFE_W, 2, min_size=34)
        self.expl = _lines(rnd.explanation, "semi", size, SAFE_W, pal.text)
        self.expl_h = int(size * 1.15)

    def clue(self, fg, t):
        _words_in(fg, self.words, t, 0.25, size=self.size, pal=self.pal)
        rv = self.revealed(t)
        for k, (plain, lit, x, right) in enumerate(self.btns):
            p = ease_out_back(prog(t, 0.5 + 0.12 * k, 0.4))
            if p <= 0:
                continue
            if rv > 0:
                img = lit if right else plain
                sc = p * (lerp(1, 1.08, rv) if right else lerp(1, 0.9, rv))
                a = 1 if right else lerp(1, 0.35, rv)
                blit(fg, img, x, self.btn_y, scale=sc, alpha=a)
            else:
                blit(fg, plain, x, self.btn_y, scale=p, alpha=clamp(p))

    def answer(self, fg, t):
        y = TIMER_Y - (len(self.expl) - 1) * self.expl_h / 2
        for i, ln in enumerate(self.expl):
            p = ease_out_cubic(prog(t, self.reveal_at + 0.25 + 0.1 * i, 0.4))
            blit(fg, ln, SAFE_CX, y + i * self.expl_h + (1 - p) * 24, alpha=p)

    def clue_sfx(self):
        return [(0.5, "pop"), (0.62, "pop")]


class _OptionsScene(RoundScene):
    """Shared by multiple choice and odd-one-out: a list or grid of option cards, one gets lit."""

    def _build(self, options: list[str], correct: int, grid: bool, top: float):
        n = len(options)
        cols = 2 if grid else 1
        gap = 26
        cw = (SAFE_W - gap * (cols - 1)) // cols
        ch = 170 if grid else 104
        prefix = "" if grid else "ABCD"
        tsize = min(fit_size(o, "bold", 56 if grid else 52, cw - (60 if grid else 150), 2 if grid else 1, min_size=32)
                    for o in options)
        self.opts = []
        for k, o in enumerate(options):
            r, c = divmod(k, cols)
            x = SAFE_LEFT + c * (cw + gap) + cw / 2
            y = top + r * (ch + gap) + ch / 2
            lines = _lines(o, "bold", tsize, cw - (60 if grid else 150), self.pal.text)
            lit_lines = _lines(o, "bold", tsize, cw - (60 if grid else 150), self.pal.on_accent)
            plain = self._opt_card(cw, ch, lines, prefix[k] if prefix else "", (255, 255, 255, 22), (255, 255, 255, 70), self.pal.accent)
            lit = self._opt_card(cw, ch, lit_lines, prefix[k] if prefix else "", self.pal.accent + (255,), None, self.pal.on_accent)
            self.opts.append((plain, lit, x, y, k == correct))
        self.opts_bottom = top + math.ceil(n / cols) * (ch + gap) - gap

    def _opt_card(self, w, h, lines, letter, fill, outline, letter_col):
        c = rounded_rect(w, h, 28, fill, outline, 3 if outline else 0).copy()
        lh = lines[0].height * 0.92
        x0 = 120 if letter else None
        if letter:
            ls = text_sprite(letter, "black", 52, letter_col)
            c.alpha_composite(ls, (44, (h - ls.height) // 2 + 2))
        y = (h - lh * len(lines)) / 2
        for ln in lines:
            x = x0 if x0 is not None else (w - ln.width) // 2
            c.alpha_composite(ln, (int(x), int(y) + 2))
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
                    blit(fg, lit, x, y, scale=lerp(1, 1.05, rv))
                else:
                    blit(fg, plain, x, y, scale=lerp(1, 0.95, rv), alpha=lerp(1, 0.35, rv))
            else:
                blit(fg, plain, x + (1 - e) * 380, y, alpha=e)

    def opts_sfx(self, start):
        return [(start + 0.12 * k, "swipe") for k in range(len(self.opts))]


class ChoiceScene(_OptionsScene):
    heading = "Quick quiz"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        clean = rnd.question.replace("*", "")
        self.size = fit_size(clean, "black", 76, SAFE_W, 3, min_size=48)
        n_lines = len(wrap_words(rnd.question, "black", self.size, SAFE_W))
        q_h = n_lines * self.size * 1.08
        opts_h = len(rnd.options) * 130 - 26
        top = max(SAFE_TOP + 200, CLUE_Y - 30 - (q_h + 50 + opts_h) / 2)
        self.words = _word_layout(rnd.question, "black", self.size, SAFE_W, pal, top + q_h / 2)
        self._build(rnd.options, rnd.correct, False, top + q_h + 50)
        self.note = None
        if rnd.note:
            ns = fit_size(rnd.note, "semi", 48, SAFE_W, 1, min_size=30)
            self.note = text_sprite(rnd.note, "semi", ns, pal.text)

    def clue(self, fg, t):
        _words_in(fg, self.words, t, 0.2, size=self.size, pal=self.pal)
        self.clue_opts(fg, t, 0.45)

    def answer(self, fg, t):
        if self.note:
            p = ease_out_cubic(prog(t, self.reveal_at + 0.25, 0.4))
            blit(fg, self.note, SAFE_CX, TIMER_Y + (1 - p) * 24, alpha=p)

    def clue_sfx(self):
        return self.opts_sfx(0.45)


class OddOneOutScene(_OptionsScene):
    heading = "Odd one out"

    def __init__(self, rnd, pal, **kw):
        super().__init__(rnd, pal, **kw)
        self._build(rnd.items, rnd.odd, True, CLUE_Y - 40 - 183)
        size = fit_size(rnd.reason, "semi", 50, SAFE_W, 2, min_size=34)
        self.reason = _lines(rnd.reason, "semi", size, SAFE_W, pal.text)
        self.reason_h = int(size * 1.15)

    def clue(self, fg, t):
        self.clue_opts(fg, t, 0.25)

    def answer(self, fg, t):
        y = TIMER_Y - (len(self.reason) - 1) * self.reason_h / 2
        for i, ln in enumerate(self.reason):
            p = ease_out_cubic(prog(t, self.reveal_at + 0.25 + 0.1 * i, 0.4))
            blit(fg, ln, SAFE_CX, y + i * self.reason_h + (1 - p) * 24, alpha=p)

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
        n_letters = sum(len(w) for w in words)
        one_row = n_letters + len(words) - 1
        # one row if it fits at a decent size, else one word per row
        if one_row * 70 <= SAFE_W:
            rows = [" ".join(words)]
        else:
            rows = words
            if len(rows) > 3:
                rows = [" ".join(words[: len(words) // 2]), " ".join(words[len(words) // 2:])]
        cols = max(len(r) for r in rows)
        self.tile = min(150, int(SAFE_W / (cols * 1.12)))
        step = self.tile * 1.12
        lsize = int(self.tile * 0.62)
        plain_bg = rounded_rect(self.tile, self.tile, self.tile // 5, (255, 255, 255, 30), (255, 255, 255, 90), 3)
        lit_bg = rounded_rect(self.tile, self.tile, self.tile // 5, pal.accent + (255,))
        self.tiles = []  # (plain, lit, (sx, sy), (ex, ey))
        row_step = self.tile * 1.3
        top = CLUE_Y - 30 - (len(rows) - 1) * row_step / 2
        k = 0
        for ri, row in enumerate(rows):
            y = top + ri * row_step
            x0 = SAFE_CX - (len(row) - 1) * step / 2
            for wi, w in enumerate(row.split(" ")):
                # position of this word in the row
                offset = sum(len(p) + 1 for p in row.split(" ")[:wi])
                perm = scramble(w, self.seed + k)
                for j, ch in enumerate(w):
                    end = (x0 + (offset + j) * step, y)
                    src = perm.index(j)  # where letter j sits while scrambled
                    begin = (x0 + (offset + src) * step, y)
                    plain = plain_bg.copy()
                    lit = lit_bg.copy()
                    for bg, col in ((plain, pal.text), (lit, pal.on_accent)):
                        s = text_sprite(ch, "black", lsize, col)
                        bg.alpha_composite(s, ((self.tile - s.width) // 2, (self.tile - s.height) // 2 + 2))
                    self.tiles.append((plain, lit, begin, end))
                    k += 1
        self.card, self.note = self._answer_card(rnd.answer, rnd.note)
        self.card_y = TIMER_Y + 20

    def clue(self, fg, t):
        for i, (plain, lit, (sx, sy), (ex, ey)) in enumerate(self.tiles):
            p = ease_out_back(prog(t, 0.25 + 0.05 * i, 0.35), 2.2)
            if p <= 0:
                continue
            m = ease_in_out_cubic(prog(t, self.reveal_at + 0.02 * i, 0.5))
            hop = -math.sin(math.pi * m) * self.tile * 0.7
            x, y = lerp(sx, ex, m), lerp(sy, ey, m) + hop
            wig = 0 if m > 0 else 3 * math.sin(t * 9 + i)
            blit(fg, lit if m > 0.5 else plain, x + wig, y, scale=p, alpha=clamp(p * 2))

    def answer(self, fg, t):
        if self.note:
            pn = ease_out_cubic(prog(t, self.reveal_at + 0.6, 0.4))
            blit(fg, self.note, SAFE_CX, self.card_y + (1 - pn) * 20, alpha=pn)

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

