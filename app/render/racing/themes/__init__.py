"""Racing themes: each is one look for the whole video, chosen per video so looks can be A/B tested
(RACING_THEMES in config). Add a theme by writing a Theme subclass and listing it here."""
from __future__ import annotations

from .base import Theme
from .pitwall import PitWall

THEMES: dict[str, type[Theme]] = {PitWall.name: PitWall}


def get(name: str) -> type[Theme]:
    if name not in THEMES:
        raise ValueError(f"unknown racing theme {name!r}; themes: {sorted(THEMES)}")
    return THEMES[name]
