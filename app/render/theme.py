"""Palettes, fonts and frame geometry."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

W, H = 1080, 1920
FPS = 30

# Areas covered by TikTok / Instagram UI (captions, buttons, tabs). Keep text inside SAFE.
SAFE_TOP = 270
SAFE_BOTTOM = 1450
SAFE_LEFT = 90
SAFE_RIGHT = W - 150
SAFE_W = SAFE_RIGHT - SAFE_LEFT
SAFE_CX = (SAFE_LEFT + SAFE_RIGHT) // 2


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


@dataclass(frozen=True)
class Palette:
    bg: tuple[int, int, int]
    blob1: tuple[int, int, int]
    blob2: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent2: tuple[int, int, int]
    text: tuple[int, int, int]
    muted: tuple[int, int, int]
    on_accent: tuple[int, int, int]


def _p(bg, blob1, blob2, accent, accent2, text="#F5F7FF", muted="#9AA3B8", on_accent="#0A0A12") -> Palette:
    return Palette(*(hex_rgb(c) for c in (bg, blob1, blob2, accent, accent2, text, muted, on_accent)))


PALETTES: dict[str, Palette] = {
    "neon_dark": _p("#06060C", "#3B1D8F", "#00566B", "#8B6CFF", "#00E5FF"),
    "sunset": _p("#0C0608", "#7A1838", "#7A4A00", "#FF5C7A", "#FFB547"),
    "mint": _p("#04100C", "#0A5C43", "#0B3A6B", "#2EF2A6", "#3DA9FC"),
    "mono": _p("#080808", "#2A2A2A", "#3A1010", "#FFFFFF", "#FF3B30", muted="#8A8A8A"),
    "electric": _p("#05070F", "#0B2A8F", "#5A0B6B", "#3D7BFF", "#FF3DCB"),
    "candy": _p("#0E0614", "#7A1B6E", "#1B3F8F", "#FF5FD2", "#FFD23F"),
    "arcade": _p("#060B0A", "#0F5A2E", "#6B3A00", "#7CFF4F", "#FFB000"),
}

_FONT_DIRS = [
    os.environ.get("FONT_DIR", ""),
    str(Path(__file__).resolve().parents[2] / "assets" / "fonts"),
    "/usr/share/fonts/opentype/inter",
    "/usr/share/fonts/truetype/inter",
]

# Weight name -> (display file, text file)
_WEIGHTS = {
    "black": ("InterDisplay-Black", "Inter-Black"),
    "xbold": ("InterDisplay-ExtraBold", "Inter-ExtraBold"),
    "bold": ("InterDisplay-Bold", "Inter-Bold"),
    "semi": ("InterDisplay-SemiBold", "Inter-SemiBold"),
    "medium": ("InterDisplay-Medium", "Inter-Medium"),
    "regular": ("InterDisplay-Regular", "Inter-Regular"),
}


@lru_cache(maxsize=None)
def _font_path(name: str) -> str:
    for d in _FONT_DIRS:
        if not d:
            continue
        for ext in (".otf", ".ttf"):
            p = Path(d) / f"{name}{ext}"
            if p.exists():
                return str(p)
    raise FileNotFoundError(f"font {name} not found in {_FONT_DIRS}")


@lru_cache(maxsize=256)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    display, text = _WEIGHTS[weight]
    try:
        path = _font_path(display if size >= 48 else text)
    except FileNotFoundError:
        path = _font_path(text)
    return ImageFont.truetype(path, size)
