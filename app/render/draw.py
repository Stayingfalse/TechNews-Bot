"""Easing curves and sprite helpers built on Pillow."""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from .theme import font

RGB = tuple[int, int, int]


# ---------------------------------------------------------------- easing

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def prog(t: float, start: float, dur: float) -> float:
    """Linear 0..1 progress of t through [start, start+dur]."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / dur)


def ease_out_cubic(x: float) -> float:
    return 1 - (1 - x) ** 3


def ease_in_cubic(x: float) -> float:
    return x**3


def ease_in_out_cubic(x: float) -> float:
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out_expo(x: float) -> float:
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


def ease_out_back(x: float, s: float = 1.70158) -> float:
    x -= 1
    return 1 + (s + 1) * x**3 + s * x**2


def ease_out_elastic(x: float) -> float:
    if x in (0, 1):
        return x
    return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi / 3)) + 1


def lerp(a: float, b: float, x: float) -> float:
    return a + (b - a) * x


def mix(c1: RGB, c2: RGB, x: float) -> RGB:
    return tuple(int(lerp(a, b, x)) for a, b in zip(c1, c2))  # type: ignore[return-value]


# ---------------------------------------------------------------- sprites

@lru_cache(maxsize=512)
def text_sprite(text: str, weight: str, size: int, color: RGB, tracking: int = 0) -> Image.Image:
    """Render text tightly into an RGBA image (cached). Height is the font line box."""
    f = font(weight, size)
    ascent, descent = f.getmetrics()
    if tracking:
        widths = [f.getlength(ch) + tracking for ch in text]
        w = int(math.ceil(sum(widths) - tracking)) + 4
    else:
        w = int(math.ceil(f.getlength(text))) + 4
    h = ascent + descent
    img = Image.new("RGBA", (max(w, 1), h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if tracking:
        x = 2.0
        for ch, cw in zip(text, widths):
            d.text((x, 0), ch, font=f, fill=color + (255,))
            x += cw
    else:
        d.text((2, 0), text, font=f, fill=color + (255,))
    return img


_ALPHA_LUTS: dict[int, list[int]] = {}


def with_alpha(img: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return img
    key = int(alpha * 255)
    lut = _ALPHA_LUTS.get(key)
    if lut is None:
        lut = [i * key // 255 for i in range(256)]
        _ALPHA_LUTS[key] = lut
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lut))
    return out


def blit(
    dst: Image.Image,
    sprite: Image.Image,
    x: float,
    y: float,
    *,
    anchor: str = "mm",
    scale: float = 1.0,
    alpha: float = 1.0,
) -> tuple[int, int, int, int]:
    """Paste sprite with scale/alpha. anchor: [l|m|r][t|m|b]. Returns the box drawn."""
    if alpha <= 0.003 or scale <= 0.01:
        return (0, 0, 0, 0)
    s = sprite
    if abs(scale - 1.0) > 0.002:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    s = with_alpha(s, alpha)
    ax, ay = anchor
    left = x - (0 if ax == "l" else s.width / 2 if ax == "m" else s.width)
    top = y - (0 if ay == "t" else s.height / 2 if ay == "m" else s.height)
    left, top = int(round(left)), int(round(top))
    if left >= 0 and top >= 0:
        dst.alpha_composite(s, (left, top))
    else:
        _paste_clipped(dst, s, left, top)
    return (left, top, left + s.width, top + s.height)


def _paste_clipped(dst: Image.Image, s: Image.Image, left: int, top: int) -> None:
    cl, ct = max(0, -left), max(0, -top)
    if cl >= s.width or ct >= s.height:
        return
    dst.alpha_composite(s.crop((cl, ct, s.width, s.height)), (left + cl, top + ct))


@lru_cache(maxsize=128)
def rounded_rect(w: int, h: int, r: int, fill: tuple, outline: tuple | None = None, width: int = 0) -> Image.Image:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=fill, outline=outline, width=width)
    return img


def wrap_words(text: str, weight: str, size: int, max_w: int) -> list[list[str]]:
    f = font(weight, size)
    space = f.getlength(" ")
    lines: list[list[str]] = [[]]
    cur = 0.0
    for word in text.split():
        ww = f.getlength(word.replace("*", ""))
        if lines[-1] and cur + space + ww > max_w:
            lines.append([word])
            cur = ww
        else:
            cur += (space if lines[-1] else 0) + ww
            lines[-1].append(word)
    return lines


def fit_size(text: str, weight: str, start: int, max_w: int, max_lines: int, min_size: int = 40) -> int:
    size = start
    while size > min_size:
        lines = wrap_words(text, weight, size, max_w)
        if len(lines) <= max_lines and all(
            font(weight, size).getlength(" ".join(w.replace("*", "") for w in ln)) <= max_w for ln in lines
        ):
            return size
        size -= 4
    return min_size


# ---------------------------------------------------------------- set pieces (ink outline + hard shadow)

@lru_cache(maxsize=512)
def ink_text(text: str, style: str, size: int, color: RGB, ink: RGB, stroke: int = 0, shadow: int = 0,
             tracking: int = 0) -> Image.Image:
    """Sign-painted text: fill, ink outline and a hard ink drop shadow (down-right).

    The sprite is padded by `shadow` on every side so its centre is the centre of the lettering."""
    f = font(style, size)
    ascent, descent = f.getmetrics()
    pad = stroke + shadow + 2
    if tracking:
        widths = [f.getlength(ch) + tracking for ch in text]
        w = int(math.ceil(sum(widths) - tracking))
    else:
        w = int(math.ceil(f.getlength(text)))
    img = Image.new("RGBA", (max(1, w) + pad * 2, ascent + descent + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def draw_at(x0, y0, fill, stroke_fill):
        kw = {"stroke_width": stroke, "stroke_fill": stroke_fill + (255,)} if stroke else {}
        if tracking:
            x = x0
            for ch, cw in zip(text, widths):
                d.text((x, y0), ch, font=f, fill=fill + (255,), **kw)
                x += cw
        else:
            d.text((x0, y0), text, font=f, fill=fill + (255,), **kw)

    if shadow:
        draw_at(pad + shadow, pad + shadow, ink, ink)
    draw_at(pad, pad, color, ink)
    return img


@lru_cache(maxsize=256)
def slab(w: int, h: int, fill: tuple, ink: RGB, radius: int = 22, border: int = 6, shadow: int = 10,
         shadow_col: tuple | None = None) -> Image.Image:
    """A card with an ink outline and a hard offset shadow. Padded by `shadow` on every side so the
    sprite's centre is the card face's centre."""
    s = shadow
    img = Image.new("RGBA", (w + 2 * s, h + 2 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if s:
        d.rounded_rectangle((2 * s, 2 * s, w + 2 * s - 1, h + 2 * s - 1), radius=radius, fill=shadow_col or ink + (255,))
    d.rounded_rectangle((s, s, s + w - 1, s + h - 1), radius=radius, fill=fill, outline=ink + (255,), width=border)
    return img


@lru_cache(maxsize=128)
def disc(r: int, fill: tuple, ink: RGB, border: int = 6, shadow: int = 9) -> Image.Image:
    s = shadow
    img = Image.new("RGBA", (2 * r + 2 * s, 2 * r + 2 * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((2 * s, 2 * s, 2 * s + 2 * r - 1, 2 * s + 2 * r - 1), fill=ink + (255,))
    d.ellipse((s, s, s + 2 * r - 1, s + 2 * r - 1), fill=fill, outline=ink + (255,), width=border)
    return img


def place(sprite: Image.Image, face: Image.Image, x: float, y: float) -> None:
    """Composite `face` onto `sprite` centred (helper for labels on slabs)."""
    sprite.alpha_composite(face, (int(x - face.width / 2), int(y - face.height / 2)))
