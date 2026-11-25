"""raosanta.uk's look, from the site's DESIGN.md: the Christmas post. A night-blue sky with falling
snow and a few gold stars, cream postcards with an airmail edge, the season's stamp, Archivo
(expanded and extra bold for headlines), postbox red and gold.

Everything is a pure function of time, so frames render in parallel.
"""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from ..draw import wrap_words
from ..theme import H, W, font, hex_rgb

ASSETS = Path(__file__).resolve().parents[3] / "assets" / "santa"


class C:
    night = hex_rgb("#13264d")
    night_deep = hex_rgb("#0c1a37")
    night_raised = hex_rgb("#1b3363")
    frost = hex_rgb("#e6ecf7")
    frost_soft = hex_rgb("#aebbd4")
    label = hex_rgb("#f6f0e2")
    label_shade = hex_rgb("#ebe2cd")
    rule = hex_rgb("#cdbf9f")
    ink = hex_rgb("#18223a")
    ink_soft = hex_rgb("#4b5670")
    post = hex_rgb("#b8262c")
    post_deep = hex_rgb("#941c21")
    paper = hex_rgb("#fffdf8")
    gold = hex_rgb("#caa24c")
    gold_soft = hex_rgb("#e5cf98")
    pine = hex_rgb("#1f5c47")
    pine_tint = hex_rgb("#d9e9df")


DISPLAY, SEMI, BODY = "santa-display", "santa-semi", "santa-body"


# ---------------------------------------------------------------- the sky

class Sky:
    """Night gradient, gold stars that twinkle, snow drifting down, and a snowbank at the bottom."""

    def __init__(self, seed: int):
        rng = random.Random(seed)
        base = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(base)
        for y in range(0, H, 4):
            x = y / H
            c = tuple(int(a + (b - a) * x) for a, b in zip(C.night_deep, C.night))
            d.rectangle((0, y, W, y + 4), fill=c + (255,))
        # two soft snowbanks under the platforms' captions
        for top, col in ((1700, C.night_raised), (1780, C.frost_soft)):
            pts = [(0, H)]
            ph = rng.random() * 6
            for x in range(0, W + 40, 40):
                pts.append((x, top + 34 * math.sin(x / 210 + ph) + 18 * math.sin(x / 77 + ph * 2)))
            pts.append((W, H))
            d.polygon(pts, fill=col + (255,))
        self.base = base
        self.stars = [(rng.uniform(40, W - 40), rng.uniform(60, 760), rng.uniform(5, 11), rng.uniform(0, 6.3),
                       rng.uniform(0.6, 1.4)) for _ in range(16)]
        self.flakes = [(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(2.0, 6.5), rng.uniform(0, 6.3),
                        rng.uniform(0.3, 0.9)) for _ in range(120)]

    def render(self, T: float) -> Image.Image:
        img = self.base.copy()
        d = ImageDraw.Draw(img, "RGBA")
        for x, y, r, ph, sp in self.stars:
            a = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(T * sp * 2.2 + ph))
            c = C.gold_soft + (int(255 * a),)
            rr = r * (0.8 + 0.25 * a)
            d.polygon([(x, y - rr * 1.8), (x + rr * 0.35, y), (x, y + rr * 1.8), (x - rr * 0.35, y)], fill=c)
            d.polygon([(x - rr * 1.8, y), (x, y + rr * 0.35), (x + rr * 1.8, y), (x, y - rr * 0.35)], fill=c)
        for x0, y0, r, ph, drift in self.flakes:
            speed = 26 + r * 16  # big flakes are nearer and fall faster
            y = (y0 + T * speed) % (H + 20) - 10
            x = x0 + 22 * drift * math.sin(T * 0.8 * drift + ph)
            alpha = int(90 + 22 * r)
            d.ellipse((x - r, y - r, x + r, y + r), fill=C.frost + (alpha,))
        return img


# ---------------------------------------------------------------- text

def _words(text: str):
    """(word, gold?) pairs: *asterisks* mark the gold words (they may span several)."""
    hi, out = False, []
    for w in text.split():
        starts, ends = w.startswith("*"), w.endswith("*") and len(w.strip("*")) > 0
        if starts:
            hi = True
        out.append((w.replace("*", ""), hi))
        if ends:
            hi = False
    return out


@lru_cache(maxsize=256)
def rich(text: str, style: str, size: int, color: tuple, hi: tuple, max_w: int, align: str = "c",
         gap: float = 1.1) -> Image.Image:
    """Wrapped text with *gold* words, as a tight RGBA sprite. `align`: l, c or r."""
    f = font(style, size)
    asc, desc = f.getmetrics()
    space = f.getlength(" ")
    words = _words(text)
    lines, k = [], 0
    for ln in wrap_words(text, style, size, max_w):
        lines.append(words[k:k + len(ln)])
        k += len(ln)
    widths = [sum(f.getlength(w) for w, _ in ln) + space * (len(ln) - 1) for ln in lines]
    lh = int(size * gap)
    w = int(max(widths, default=1)) + 8
    h = lh * (len(lines) - 1) + asc + desc + 4
    img = Image.new("RGBA", (max(w, 1), max(h, 1)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, (ln, lw) in enumerate(zip(lines, widths)):
        x = 4 + {"l": 0, "c": (w - 8 - lw) / 2, "r": w - 8 - lw}[align]
        for word, gold in ln:
            d.text((x, i * lh), word, font=f, fill=(hi if gold else color) + (255,))
            x += f.getlength(word) + space
    return img


def fit(text: str, style: str, start: int, max_w: int, max_lines: int, min_size: int = 34) -> int:
    size = start
    while size > min_size:
        if len(wrap_words(text, style, size, max_w)) <= max_lines:
            return size
        size -= 2
    return min_size


# ---------------------------------------------------------------- set pieces

@lru_cache(maxsize=64)
def postcard(w: int, h: int, edge: int = 16, fill: tuple = C.label, shadow: int = 12) -> Image.Image:
    """A cream card with an airmail edge (red and blue diagonal stripes) and a soft drop shadow.
    Padded by `shadow` on every side, so its centre is the card's centre."""
    s = shadow
    img = Image.new("RGBA", (w + 2 * s, h + 2 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((s + 6, s + 10, s + w + 4, s + h + 8), radius=20, fill=C.night_deep + (150,))
    stripes = Image.new("RGBA", (w, h), C.paper + (255,))
    sd = ImageDraw.Draw(stripes)
    step = 44
    for k, x in enumerate(range(-h, w + h, step)):
        col = (C.post if k % 2 == 0 else C.night) + (255,)
        sd.polygon([(x, 0), (x + step * 0.5, 0), (x + step * 0.5 - h, h), (x - h, h)], fill=col)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=20, fill=255)
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    card.paste(stripes, (0, 0), mask)
    ImageDraw.Draw(card).rounded_rectangle((edge, edge, w - 1 - edge, h - 1 - edge), radius=10, fill=fill + (255,))
    img.alpha_composite(card, (s, s))
    return img


@lru_cache(maxsize=64)
def plain_card(w: int, h: int, fill: tuple = C.label, outline: tuple = C.rule, radius: int = 18, border: int = 4,
               shadow: int = 8) -> Image.Image:
    s = shadow
    img = Image.new("RGBA", (w + 2 * s, h + 2 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((s + 4, s + 7, s + w + 3, s + h + 6), radius=radius, fill=C.night_deep + (140,))
    d.rounded_rectangle((s, s, s + w - 1, s + h - 1), radius=radius, fill=fill + (255,), outline=outline + (255,), width=border)
    return img


@lru_cache(maxsize=32)
def badge(r: int, fill: tuple, text: str = "", text_col: tuple = C.label, tick: bool = False) -> Image.Image:
    """A round badge: a number or letter, or a tick."""
    img = Image.new("RGBA", (2 * r + 6, 2 * r + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((3, 3, 3 + 2 * r, 3 + 2 * r), fill=fill + (255,))
    if tick:
        cx, cy = r + 3, r + 3
        d.line([(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.1, cy + r * 0.34), (cx + r * 0.46, cy - r * 0.32)],
               fill=text_col + (255,), width=max(4, r // 4), joint="curve")
    elif text:
        f = font(DISPLAY, int(r * 1.05))
        d.text((r + 3, r + 3), text, font=f, fill=text_col + (255,), anchor="mm")
    return img


@lru_cache(maxsize=16)
def stamp(height: int, angle: float = 0.0) -> Image.Image:
    img = Image.open(ASSETS / "stamp-2026.png").convert("RGBA")
    img = img.resize((int(img.width * height / img.height), height), Image.LANCZOS)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else img


@lru_cache(maxsize=8)
def postmark(r: int, text: str = "RAOSANTA 2026") -> Image.Image:
    """A franking mark: a ring with the words, and wavy cancellation lines to its right."""
    w = int(r * 4.6)
    img = Image.new("RGBA", (w, 2 * r + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = C.ink_soft + (150,)
    d.ellipse((4, 4, 4 + 2 * r, 4 + 2 * r), outline=col, width=5)
    d.ellipse((22, 22, 2 * r - 14, 2 * r - 14), outline=col, width=2)
    f = font(SEMI, max(14, r // 4))
    d.text((r + 4, r + 4), text.split()[0], font=f, fill=col, anchor="md")
    d.text((r + 4, r + 10), text.split()[-1], font=f, fill=col, anchor="ma")
    for k in range(4):
        y0 = 14 + k * (2 * r - 20) / 3
        pts = [(2 * r + 20 + x, y0 + 7 * math.sin(x / 16)) for x in range(0, w - 2 * r - 28, 4)]
        d.line(pts, fill=col, width=4)
    return img


def rotated(img: Image.Image, angle: float) -> Image.Image:
    return img.rotate(angle, resample=Image.BICUBIC, expand=True) if angle else img


@lru_cache(maxsize=32)
def photo(path: str, w: int, h: int) -> Image.Image | None:
    """A kudos photo cropped to fill w×h, with rounded corners and a white border."""
    try:
        src = Image.open(path).convert("RGB")
    except Exception:
        return None
    scale = max(w / src.width, h / src.height)
    src = src.resize((max(w, int(src.width * scale)), max(h, int(src.height * scale))), Image.LANCZOS)
    left, top = (src.width - w) // 2, (src.height - h) // 2
    src = src.crop((left, top, left + w, top + h))
    b = 14
    img = Image.new("RGBA", (w + 2 * b, h + 2 * b), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w + 2 * b - 1, h + 2 * b - 1), radius=16, fill=C.paper + (255,))
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=10, fill=255)
    img.paste(src, (b, b), mask)
    return img
