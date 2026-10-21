"""Colour emoji: grapheme splitting and sprites from Noto Color Emoji (a bitmap font, fixed at 109 px)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ZWJ = 0x200D
_EMOJI_FONT_PATHS = [
    os.environ.get("EMOJI_FONT", ""),
    str(Path(__file__).resolve().parents[2] / "assets" / "fonts" / "NotoColorEmoji.ttf"),
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/noto/NotoColorEmoji.ttf",
]
NATIVE = 109  # the only size the CBDT font renders at


def _is_modifier(cp: int) -> bool:
    return (
        cp in (0xFE0E, 0xFE0F, 0x20E3)  # variation selectors, keycap
        or 0x1F3FB <= cp <= 0x1F3FF  # skin tones
        or 0xE0020 <= cp <= 0xE007F  # tag sequences (subdivision flags)
    )


def _is_regional(cp: int) -> bool:
    return 0x1F1E6 <= cp <= 0x1F1FF


def _is_pictographic(cp: int) -> bool:
    return (
        0x1F000 <= cp <= 0x1FAFF
        or 0x2600 <= cp <= 0x27BF
        or 0x2300 <= cp <= 0x23FF
        or 0x2B00 <= cp <= 0x2BFF
        or 0x2190 <= cp <= 0x21FF
        or 0x2900 <= cp <= 0x297F
        or 0x3030 <= cp <= 0x303D
        or cp in (0x00A9, 0x00AE, 0x203C, 0x2049, 0x2122, 0x2139, 0x24C2, 0x3297, 0x3299)
    )


def clusters(text: str) -> list[str]:
    """Split into emoji grapheme clusters (ZWJ sequences, skin tones, flags and keycaps stay whole)."""
    out: list[str] = []
    join_next = False
    for ch in text:
        cp = ord(ch)
        if out and (join_next or _is_modifier(cp) or cp == ZWJ):
            out[-1] += ch
            join_next = cp == ZWJ
            continue
        if out and _is_regional(cp) and len(out[-1]) == 1 and _is_regional(ord(out[-1])):
            out[-1] += ch
            continue
        out.append(ch)
        join_next = False
    return [c for c in out if not c.isspace()]


def is_emoji_only(text: str) -> bool:
    for c in clusters(text):
        base = ord(c[0])
        if not (_is_pictographic(base) or _is_regional(base) or (c[0] in "#*0123456789" and "⃣" in c)):
            return False
    return True


@lru_cache(maxsize=1)
def _font() -> ImageFont.FreeTypeFont:
    for p in _EMOJI_FONT_PATHS:
        if p and Path(p).exists():
            return ImageFont.truetype(p, NATIVE)
    raise FileNotFoundError("Noto Color Emoji not found; install fonts-noto-color-emoji or set EMOJI_FONT")


@lru_cache(maxsize=64)
def emoji_sprite(cluster: str, size: int) -> Image.Image:
    """A square RGBA sprite of one emoji, scaled to `size` px."""
    f = _font()
    img = Image.new("RGBA", (NATIVE * 3, NATIVE * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((NATIVE // 2, NATIVE // 2), cluster, font=f, embedded_color=True)
    box = img.getbbox()
    if box:
        img = img.crop(box)
    k = size / max(img.width, img.height, 1)
    return img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS)
