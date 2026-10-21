"""Scene types. Each scene draws onto a transparent full-frame layer as a pure function of local time."""
from __future__ import annotations

import math
import re

from PIL import Image, ImageChops, ImageDraw

from .draw import (
    blit,
    clamp,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_expo,
    fit_size,
    glow,
    lerp,
    prog,
    rounded_rect,
    text_sprite,
    wrap_words,
)
from .theme import H, SAFE_BOTTOM, SAFE_CX, SAFE_LEFT, SAFE_RIGHT, SAFE_TOP, SAFE_W, W, Palette, font

CENTER_Y = (SAFE_TOP + SAFE_BOTTOM) // 2


class Scene:
    default_duration = 3.0

    def __init__(self, beat, pal: Palette, imgs: dict | None = None):
        self.beat = beat
        self.pal = pal
        self.imgs = imgs or {}  # image id -> (PIL image, credit)
        self.duration = beat.duration or self.default_duration

    def render(self, fg: Image.Image, t: float) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def backdrop(self, frame: Image.Image, t: float, alpha: float) -> None:
        """Optional layer drawn straight onto the frame, under the glowing foreground."""

    def sfx(self) -> list[tuple[float, str]]:
        return [(0.0, "whoosh")]


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


def cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale to fill w×h and centre-crop."""
    k = max(w / img.width, h / img.height)
    r = img.resize((max(w, round(img.width * k)), max(h, round(img.height * k))), Image.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


class KenBurns:
    """Slow zoom-and-pan over a photo, optionally as a rounded card."""

    def __init__(self, img: Image.Image, w: int, h: int, zoom=1.14, pan=(0.025, -0.02), radius=0, border=True):
        self.w, self.h, self.zoom, self.pan = w, h, zoom, pan
        self.big = cover(img, int(w * zoom), int(h * zoom))
        self.mask = None
        self.border = None
        if radius:
            self.mask = Image.new("L", (w, h), 0)
            ImageDraw.Draw(self.mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
            if border:
                self.border = rounded_rect(w, h, radius, (0, 0, 0, 0), (255, 255, 255, 70), 3)

    def frame(self, p: float) -> Image.Image:
        p = clamp(p)
        f = lerp(1.0, 1 / self.zoom, ease_in_out_cubic(p) * 0.6 + p * 0.4)
        ww, wh = self.big.width * f, self.big.height * f
        cx = self.big.width / 2 + self.pan[0] * self.big.width * (p - 0.5)
        cy = self.big.height / 2 + self.pan[1] * self.big.height * (p - 0.5)
        x0 = min(max(0.0, cx - ww / 2), self.big.width - ww)
        y0 = min(max(0.0, cy - wh / 2), self.big.height - wh)
        out = self.big.resize((self.w, self.h), Image.BILINEAR, box=(x0, y0, x0 + ww, y0 + wh)).convert("RGBA")
        if self.mask:
            out.putalpha(self.mask)
        if self.border:
            out.alpha_composite(self.border)
        return out


def _credit(text: str, pal: Palette):
    return text_sprite(text, "medium", 26, pal.muted) if text else None


def _parse_number(value: str):
    m = re.fullmatch(r"(\D*?)(\d[\d,]*(?:\.\d+)?)(.*)", value.strip())
    if not m:
        return None
    prefix, num, suffix = m.groups()
    decimals = len(num.split(".")[1]) if "." in num else 0
    return prefix, float(num.replace(",", "")), suffix, decimals, "," in num


def _fmt(n: float, decimals: int, commas: bool) -> str:
    return f"{n:,.{decimals}f}" if commas else f"{n:.{decimals}f}"


# --------------------------------------------------------------------------- scenes

def _shade(pal: Palette) -> Image.Image:
    """Darkening overlay so text stays readable over a photo."""
    import numpy as np

    y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    a = 168 + 60 * (np.abs(y - 0.45) * 2) ** 1.5
    a = np.broadcast_to(np.clip(a, 0, 235), (H, W)).astype(np.uint8)
    img = Image.new("RGBA", (W, H), pal.bg + (0,))
    img.putalpha(Image.fromarray(a, "L"))
    return img


class HookScene(Scene):
    default_duration = 2.8

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        clean = beat.text.replace("*", "")
        self.size = fit_size(clean, "black", 132, SAFE_W, 4, min_size=72)
        self.words = _word_layout(beat.text, "black", self.size, SAFE_W, pal, CENTER_Y - 40)
        self.kb = None
        if beat.image and beat.image in self.imgs:
            img, credit = self.imgs[beat.image]
            self.kb = KenBurns(img, W, H, zoom=1.18, pan=(0.04, 0.03))
            self.shade = _shade(pal)
            self.credit = _credit(credit, pal)

    def backdrop(self, frame, t, alpha):
        if not self.kb:
            return
        a = ease_out_cubic(prog(t, 0.0, 0.4)) * alpha
        blit(frame, self.kb.frame(t / self.duration), 0, 0, anchor="lt", alpha=a)
        blit(frame, self.shade, 0, 0, anchor="lt", alpha=a)
        if self.credit:
            blit(frame, self.credit, SAFE_RIGHT, SAFE_BOTTOM - 40, anchor="rt", alpha=a * 0.9)

    def render(self, fg, t):
        for i, (sprite, cx, cy, hl) in enumerate(self.words):
            p = prog(t, 0.12 + 0.085 * i, 0.38)
            if p <= 0:
                continue
            scale = lerp(0.35, 1.0, ease_out_back(p, 2.2))
            blit(fg, sprite, cx, cy + (1 - ease_out_cubic(p)) * 50, scale=scale, alpha=ease_out_cubic(p))
            if hl:
                up = ease_out_cubic(prog(t, 0.35 + 0.085 * i, 0.4))
                if up > 0:
                    bw = int(sprite.width * up)
                    bar = rounded_rect(max(bw, 8), 14, 7, self.pal.accent + (255,))
                    blit(fg, bar, cx - sprite.width / 2, cy + self.size * 0.62, anchor="lm")

    def sfx(self):
        return [(0.12 + 0.085 * i, "pop") for i in range(min(len(self.words), 10))]


class TitleScene(Scene):
    default_duration = 2.8

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        self.kicker = _pill(beat.kicker.upper(), pal)
        self.size = fit_size(beat.text, "black", 118, SAFE_W, 3, min_size=64)
        lines = wrap_words(beat.text, "black", self.size, SAFE_W)
        self.lines = [text_sprite(" ".join(w.replace("*", "") for w in ln), "black", self.size, pal.text) for ln in lines]
        self.line_h = int(self.size * 1.06)
        self.card = None
        self.card_h = 0
        if beat.image and beat.image in self.imgs:
            img, credit = self.imgs[beat.image]
            self.card_h = 500
            self.card = KenBurns(img, SAFE_W, self.card_h, zoom=1.1, radius=34)
            self.credit = _credit(credit, pal)
            self.default_duration = 3.4
            self.duration = beat.duration or self.default_duration
        img_block = self.card_h + 70 if self.card else 0
        block = img_block + self.kicker.height + 40 + self.line_h * len(self.lines)
        self.top = CENTER_Y - block // 2 - 30
        self.delay = 0.3 if self.card else 0.0

    def render(self, fg, t):
        top = self.top
        if self.card:
            pc = ease_out_cubic(prog(t, 0.0, 0.5))
            card = self.card.frame(t / self.duration)
            blit(fg, card, SAFE_CX, top + self.card_h / 2 + (1 - pc) * 60, scale=lerp(0.94, 1, pc), alpha=pc)
            if self.credit:
                blit(fg, self.credit, SAFE_RIGHT, top + self.card_h + 14, anchor="rt", alpha=pc * 0.9)
            top += self.card_h + 70
        t = t - self.delay
        p = ease_out_cubic(prog(t, 0.05, 0.45))
        blit(fg, self.kicker, lerp(-self.kicker.width, SAFE_LEFT, p), top, anchor="lt", alpha=p)
        y0 = top + self.kicker.height + 40
        for i, s in enumerate(self.lines):
            e = ease_out_expo(prog(t, 0.25 + 0.12 * i, 0.7))
            if e <= 0:
                continue
            off = int((1 - e) * s.height)
            if off < s.height:
                fg.alpha_composite(s.crop((0, 0, s.width, s.height - off)), (SAFE_LEFT, y0 + i * self.line_h + off))
        g = ease_in_out_cubic(prog(t, 0.6, 0.8))
        if g > 0:
            bar = rounded_rect(max(8, int(SAFE_W * 0.42 * g)), 10, 5, self.pal.accent2 + (255,))
            blit(fg, bar, SAFE_LEFT, y0 + len(self.lines) * self.line_h + 30, anchor="lt")

    def sfx(self):
        return [(0.05, "whoosh"), (0.3, "impact")]


class StatScene(Scene):
    default_duration = 3.0
    RING_R = 300

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        self.parsed = _parse_number(beat.value) if beat.count_up else None
        self.vsize = fit_size(beat.value, "black", 210, self.RING_R * 2 - 120, 1, min_size=90)
        self.label = text_sprite(beat.label.upper(), "bold", 44, pal.muted, 4)
        if self.label.width > SAFE_W:
            self.label = text_sprite(beat.label.upper(), "bold", int(44 * SAFE_W / self.label.width), pal.muted, 3)
        self.cy = CENTER_Y - 80

    def _value_text(self, x: float) -> str:
        if not self.parsed:
            return self.beat.value
        prefix, n, suffix, dec, commas = self.parsed
        return f"{prefix}{_fmt(n * x, dec, commas)}{suffix}"

    def render(self, fg, t):
        appear = ease_out_back(prog(t, 0.0, 0.5), 1.6)
        count = ease_out_expo(prog(t, 0.2, 1.4))
        r = self.RING_R
        size = r * 2 + 60
        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        box = (30, 30, size - 30, size - 30)
        d.ellipse(box, outline=self.pal.text + (34,), width=16)
        if count > 0:
            d.arc(box, -90, -90 + 360 * count, fill=self.pal.accent + (255,), width=16)
            a = math.radians(-90 + 360 * count)
            hx, hy = size / 2 + (r) * math.cos(a), size / 2 + (r) * math.sin(a)
            d.ellipse((hx - 16, hy - 16, hx + 16, hy + 16), fill=self.pal.accent2 + (255,))
        ring.alpha_composite(glow(ring, 24, 1.0, 2))
        blit(fg, ring, SAFE_CX, self.cy, scale=lerp(0.6, 1.0, appear), alpha=clamp(appear))

        val = text_sprite(self._value_text(count if self.parsed else 1), "black", self.vsize, self.pal.text)
        pv = ease_out_cubic(prog(t, 0.1, 0.4))
        blit(fg, val, SAFE_CX, self.cy - 6, scale=lerp(0.8, 1.0, pv), alpha=pv)

        pl = ease_out_cubic(prog(t, 0.5, 0.5))
        blit(fg, self.label, SAFE_CX, self.cy + r + 110 + (1 - pl) * 30, alpha=pl)

    def sfx(self):
        ticks = [(0.2 + 1.4 * (1 - (1 - k / 12) ** 0.3), "tick") for k in range(12)]
        return [(0.0, "whoosh")] + ticks + [(1.3, "ding")]


class SpecListScene(Scene):
    CARD_H = 128
    GAP = 26

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        n = len(beat.items)
        self.default_duration = 1.3 + 0.45 * n
        self.duration = beat.duration or self.default_duration
        self.title = text_sprite(beat.title, "black", 76, pal.text)
        tsize = min(fit_size(it, "semi", 54, SAFE_W - 170, 1, min_size=34) for it in beat.items)
        self.items = [text_sprite(it, "semi", tsize, pal.text) for it in beat.items]
        self.nums = [text_sprite(f"{i + 1:02d}", "black", 40, pal.accent) for i in range(n)]
        total = self.title.height + 60 + n * self.CARD_H + (n - 1) * self.GAP
        self.top = CENTER_Y - total // 2 - 20
        card = rounded_rect(SAFE_W, self.CARD_H, 26, (255, 255, 255, 20), (255, 255, 255, 46), 2).copy()
        ImageDraw.Draw(card).rounded_rectangle((0, 0, 9, self.CARD_H - 1), radius=4, fill=pal.accent + (255,))
        self.card = card

    def render(self, fg, t):
        p = ease_out_cubic(prog(t, 0.0, 0.45))
        blit(fg, self.title, SAFE_LEFT, self.top + (1 - p) * 40, anchor="lt", alpha=p)
        y = self.top + self.title.height + 60
        for i, (num, txt) in enumerate(zip(self.nums, self.items)):
            e = ease_out_expo(prog(t, 0.35 + 0.3 * i, 0.6))
            if e > 0:
                x = SAFE_LEFT + (1 - e) * 420
                blit(fg, self.card, x, y, anchor="lt", alpha=e)
                cy = y + self.CARD_H / 2
                blit(fg, num, x + 44, cy, anchor="lm", alpha=e)
                blit(fg, txt, x + 128, cy, anchor="lm", alpha=e)
            y += self.CARD_H + self.GAP

    def sfx(self):
        return [(0.0, "whoosh")] + [(0.35 + 0.3 * i, "swipe") for i in range(len(self.items))]


class PriceScene(Scene):
    default_duration = 2.8

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        self.kicker = text_sprite("PRICE", "bold", 40, pal.muted, 10)
        self.vsize = fit_size(beat.value, "black", 240, SAFE_W, 1, min_size=100)
        self.value = text_sprite(beat.value, "black", self.vsize, pal.text)
        self.sub = text_sprite(beat.subtext, "semi", 46, pal.accent2) if beat.subtext else None
        self.cy = CENTER_Y - 60

    def _shine(self, s: Image.Image, x: float) -> Image.Image:
        band = Image.new("L", s.size, 0)
        d = ImageDraw.Draw(band)
        h = s.height
        for k, a in ((70, 70), (40, 160), (18, 230)):
            d.polygon([(x - k, 0), (x + k, 0), (x + k - h * 0.4, h), (x - k - h * 0.4, h)], fill=a)
        mask = ImageChops.multiply(band, s.getchannel("A"))
        tint = Image.new("RGBA", s.size, self.pal.accent2 + (0,))
        tint.putalpha(mask)
        out = s.copy()
        out.alpha_composite(tint)
        return out

    def render(self, fg, t):
        pk = ease_out_cubic(prog(t, 0.0, 0.4))
        blit(fg, self.kicker, SAFE_CX, self.cy - self.vsize * 0.75, alpha=pk)
        p = prog(t, 0.15, 0.55)
        s = self.value
        sp = prog(t, 0.85, 0.7)
        if 0 < sp < 1:
            s = self._shine(s, lerp(-150, s.width + 250, ease_in_out_cubic(sp)))
        blit(fg, s, SAFE_CX, self.cy, scale=lerp(1.8, 1.0, ease_out_cubic(p)), alpha=clamp(p * 2.5))
        if self.sub:
            ps = ease_out_cubic(prog(t, 0.7, 0.5))
            blit(fg, self.sub, SAFE_CX, self.cy + self.vsize * 0.72 + (1 - ps) * 30, alpha=ps)

    def sfx(self):
        return [(0.15, "impact"), (0.85, "shimmer")]


class CompareScene(Scene):
    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        self.default_duration = 1.6 + 0.6 * len(beat.rows)
        self.duration = beat.duration or self.default_duration
        self.a = _pill(beat.a, pal, 40, tracking=1)
        self.b = _pill(beat.b, pal, 40, fill=pal.accent2, tracking=1)
        self.vs = text_sprite("VS", "black", 56, pal.text)
        col_w = SAFE_W // 2 - 40
        self.rows = []
        for label, av, bv in beat.rows:
            vs = min(fit_size(av, "black", 76, col_w, 1, 40), fit_size(bv, "black", 76, col_w, 1, 40))
            self.rows.append(
                (
                    text_sprite(label.upper(), "bold", 34, pal.muted, 4),
                    text_sprite(av, "black", vs, pal.text),
                    text_sprite(bv, "black", vs, pal.text),
                )
            )
        self.row_h = 210
        total = 140 + len(self.rows) * self.row_h
        self.top = CENTER_Y - total // 2

    def render(self, fg, t):
        lx, rx = SAFE_LEFT + SAFE_W * 0.25, SAFE_LEFT + SAFE_W * 0.75
        p = ease_out_back(prog(t, 0.0, 0.5))
        y = self.top + 50
        blit(fg, self.a, lerp(-300, lx, p), y, alpha=clamp(p))
        blit(fg, self.b, lerp(W + 300, rx, p), y, alpha=clamp(p))
        pv = ease_out_back(prog(t, 0.3, 0.4), 3)
        blit(fg, self.vs, SAFE_CX, y, scale=pv, alpha=clamp(pv))
        y += 150
        for i, (lab, av, bv) in enumerate(self.rows):
            e = ease_out_cubic(prog(t, 0.6 + 0.45 * i, 0.5))
            if e > 0:
                line = rounded_rect(SAFE_W, 3, 1, self.pal.text + (40,))
                blit(fg, line, SAFE_LEFT, y, anchor="lt", alpha=e)
                blit(fg, lab, SAFE_CX, y + 50, alpha=e)
                blit(fg, av, lx, y + 130 + (1 - e) * 30, alpha=e)
                blit(fg, bv, rx, y + 130 + (1 - e) * 30, alpha=e)
            y += self.row_h

    def sfx(self):
        return [(0.0, "whoosh"), (0.3, "impact")] + [(0.6 + 0.45 * i, "pop") for i in range(len(self.rows))]


class CtaScene(Scene):
    default_duration = 3.0

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        clean = beat.text.replace("*", "")
        self.size = fit_size(clean, "black", 110, SAFE_W, 3, min_size=64)
        self.words = _word_layout(beat.text, "black", self.size, SAFE_W, pal, CENTER_Y - 120)
        self.follow = _pill(beat.follow.upper(), pal, 38, fill=pal.accent2, tracking=2)
        self.n_lines = len({round(cy) for _, _, cy, _ in self.words})

    def render(self, fg, t):
        for i, (sprite, cx, cy, _) in enumerate(self.words):
            p = prog(t, 0.05 + 0.07 * i, 0.35)
            if p > 0:
                blit(fg, sprite, cx, cy, scale=lerp(0.5, 1, ease_out_back(p, 2)), alpha=ease_out_cubic(p))
        pf = prog(t, 0.6, 0.5)
        if pf > 0:
            pulse = 1 + 0.045 * math.sin((t - 1.1) * 6) * clamp((t - 1.1) * 2)
            y = CENTER_Y - 120 + self.size * 1.08 * self.n_lines / 2 + 140
            blit(fg, self.follow, SAFE_CX, y, scale=ease_out_back(pf) * pulse, alpha=clamp(pf * 2))

    def sfx(self):
        return [(0.0, "whoosh"), (0.6, "ding")]


class ImageScene(Scene):
    default_duration = 3.2

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        img, credit = self.imgs[beat.image]
        self.cap_lines = []
        cap_h = 0
        if beat.caption:
            size = fit_size(beat.caption, "bold", 64, SAFE_W, 2, min_size=40)
            self.cap_lines = [
                text_sprite(" ".join(w.replace("*", "") for w in ln), "bold", size, pal.text)
                for ln in wrap_words(beat.caption, "bold", size, SAFE_W)
            ]
            cap_h = 50 + len(self.cap_lines) * int(size * 1.15)
            self.cap_step = int(size * 1.15)
        self.card_h = 880 if not self.cap_lines else 760
        self.card = KenBurns(img, SAFE_W, self.card_h, zoom=1.16, pan=(0.03, -0.03), radius=40)
        self.credit = _credit(credit, pal)
        self.top = CENTER_Y - (self.card_h + cap_h) // 2 - 20

    def render(self, fg, t):
        pc = ease_out_cubic(prog(t, 0.0, 0.55))
        cy = self.top + self.card_h / 2 + (1 - pc) * 90
        blit(fg, self.card.frame(t / self.duration), SAFE_CX, cy, scale=lerp(0.9, 1, pc), alpha=pc)
        if self.credit:
            blit(fg, self.credit, SAFE_RIGHT - 20, self.top + self.card_h - 20, anchor="rb", alpha=pc * 0.9)
        y = self.top + self.card_h + 50
        for i, line in enumerate(self.cap_lines):
            e = ease_out_cubic(prog(t, 0.35 + 0.12 * i, 0.5))
            blit(fg, line, SAFE_CX, y + (1 - e) * 30, anchor="mt", alpha=e)
            y += self.cap_step

    def sfx(self):
        return [(0.0, "whoosh"), (0.1, "shimmer")]


class FactScene(Scene):
    default_duration = 3.6

    def __init__(self, beat, pal, imgs=None):
        super().__init__(beat, pal, imgs)
        clean = beat.text.replace("*", "")
        self.size = fit_size(clean, "black", 100, SAFE_W, 5, min_size=60)
        self.kicker = _pill(beat.kicker.upper(), pal, 32, fill=pal.accent2)
        n_lines = len(wrap_words(beat.text, "black", self.size, SAFE_W))
        block_h = self.kicker.height + 60 + n_lines * self.size * 1.08
        top = CENTER_Y - block_h / 2
        self.kicker_y = top
        self.words = _word_layout(beat.text, "black", self.size, SAFE_W, pal,
                                  top + self.kicker.height + 60 + n_lines * self.size * 1.08 / 2)

    def render(self, fg, t):
        pk = ease_out_back(prog(t, 0.0, 0.45))
        blit(fg, self.kicker, SAFE_CX, self.kicker_y, anchor="mt", scale=pk, alpha=clamp(pk))
        for i, (sprite, cx, cy, hl) in enumerate(self.words):
            p = prog(t, 0.25 + 0.06 * i, 0.35)
            if p <= 0:
                continue
            blit(fg, sprite, cx, cy + (1 - ease_out_cubic(p)) * 40, alpha=ease_out_cubic(p))
            if hl:
                up = ease_out_cubic(prog(t, 0.5 + 0.06 * i, 0.4))
                if up > 0:
                    bar = rounded_rect(max(int(sprite.width * up), 8), 12, 6, self.pal.accent + (255,))
                    blit(fg, bar, cx - sprite.width / 2, cy + self.size * 0.6, anchor="lm")

    def sfx(self):
        return [(0.0, "whoosh"), (0.05, "pop")]


SCENES = {
    "image": ImageScene,
    "fact": FactScene,
    "hook": HookScene,
    "title": TitleScene,
    "stat": StatScene,
    "spec_list": SpecListScene,
    "price": PriceScene,
    "compare": CompareScene,
    "cta": CtaScene,
}
