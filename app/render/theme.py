"""Palettes, fonts and frame geometry.

Look: a Saturday-night TV quiz set. Flat stage colours with a turning sunburst, marquee bulbs,
sign-painted headings (Bungee) with hard ink drop shadows, clue text in condensed Bricolage
Grotesque, and paper cards with thick ink outlines. No glows or gradients.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

W, H = 1080, 1920
FPS = 30

# Areas covered by Instagram / YouTube UI (captions, buttons, tabs). Keep text inside SAFE.
SAFE_TOP = 270
SAFE_BOTTOM = 1450
SAFE_LEFT = 90
SAFE_RIGHT = W - 150
SAFE_W = SAFE_RIGHT - SAFE_LEFT
SAFE_CX = (SAFE_LEFT + SAFE_RIGHT) // 2

RGB = tuple[int, int, int]


def hex_rgb(h: str) -> RGB:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


@dataclass(frozen=True)
class Palette:
    stage: RGB  # the set's base colour
    ray: RGB  # alternate sunburst ray
    ink: RGB  # outlines, drop shadows, text on paper
    paper: RGB  # cards and clue text
    sign: RGB  # headings, highlights, the correct answer
    hot: RGB  # answer podium, ribbons
    cool: RGB  # third colour for confetti and small details
    bulb: RGB = (255, 226, 150)

    @property
    def muted(self) -> RGB:
        return tuple(int(p * 0.62 + s * 0.38) for p, s in zip(self.paper, self.stage))  # type: ignore[return-value]


def _p(stage, ray, ink, paper, sign, hot, cool) -> Palette:
    return Palette(*(hex_rgb(c) for c in (stage, ray, ink, paper, sign, hot, cool)))


PALETTES: dict[str, Palette] = {
    # teal studio with marigold signs and tomato podium
    "teatime": _p("#0D5C6B", "#12707F", "#06262C", "#FFF7E8", "#FFC22E", "#FF5A3C", "#8FE6D6"),
    # cobalt prime-time set, bubblegum podium
    "primetime": _p("#1C3DB8", "#2850D2", "#0A1546", "#FFF8EE", "#FFD43B", "#FF4F9A", "#7FE6FF"),
    # tomato-red jackpot set with a teal podium
    "jackpot": _p("#BF2F28", "#D2413A", "#370A08", "#FFF4E2", "#FFD23F", "#138F82", "#FFB4A3"),
    # plum late-night set
    "bingo": _p("#55287F", "#643294", "#1C0A2B", "#FFF5EA", "#FFC93C", "#FF6B4A", "#7CE6BC"),
    # bottle-green sports-quiz set
    "pitch": _p("#1B6638", "#227B45", "#082313", "#FFFBEA", "#FFE04A", "#FF7A3D", "#B9F0FF"),
}

_FONT_DIRS = [
    os.environ.get("FONT_DIR", ""),
    str(Path(__file__).resolve().parents[2] / "assets" / "fonts"),
]

# style -> (file, variable axes (wght, wdth) or None)
_STYLES = {
    "sign": ("Bungee-Regular", None),  # headings, labels, answers
    "shade": ("BungeeShade-Regular", None),  # inline-shaded sign face, big numbers
    "cond": ("BricolageGrotesque-VF", (800, 75)),  # clue text
    "bold": ("BricolageGrotesque-VF", (800, 100)),
    "semi": ("BricolageGrotesque-VF", (620, 100)),
    "medium": ("BricolageGrotesque-VF", (500, 100)),
}


@lru_cache(maxsize=None)
def _font_path(name: str) -> str:
    for d in _FONT_DIRS:
        if not d:
            continue
        for ext in (".ttf", ".otf"):
            p = Path(d) / f"{name}{ext}"
            if p.exists():
                return str(p)
    raise FileNotFoundError(f"font {name} not found in {_FONT_DIRS}")


@lru_cache(maxsize=256)
def font(style: str, size: int) -> ImageFont.FreeTypeFont:
    name, axes = _STYLES[style]
    f = ImageFont.truetype(_font_path(name), size)
    if axes:
        # axis order in the file: optical size, weight, width
        f.set_variation_by_axes([max(12, min(96, size)), *axes])
    return f
