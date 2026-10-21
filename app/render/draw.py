"""Easing curves and sprite helpers built on Pillow."""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

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
        ww = f.getlength(word.strip("*"))
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
            font(weight, size).getlength(" ".join(w.strip("*") for w in ln)) <= max_w for ln in lines
        ):
            return size
        size -= 4
    return min_size


def glow(layer: Image.Image, radius: int = 18, strength: float = 1.0, factor: int = 4) -> Image.Image:
    """Cheap bloom: downscale, blur, upscale."""
    small = layer.resize((layer.width // factor, layer.height // factor), Image.BILINEAR)
    small = small.filter(ImageFilter.GaussianBlur(radius / factor))
    g = small.resize(layer.size, Image.BILINEAR)
    if strength != 1.0:
        g = with_alpha(g, min(1.0, strength))
    return g
