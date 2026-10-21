"""Story spec: the contract between the daily research routine and the renderer."""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator


class HookBeat(BaseModel):
    type: Literal["hook"] = "hook"
    # Wrap a word in *asterisks* to highlight it in the accent colour.
    text: str = Field(max_length=90)
    duration: float | None = None


class TitleBeat(BaseModel):
    type: Literal["title"] = "title"
    kicker: str = Field(default="NEW", max_length=24)
    text: str = Field(max_length=70)
    duration: float | None = None


class StatBeat(BaseModel):
    type: Literal["stat"] = "stat"
    label: str = Field(max_length=40)
    value: str = Field(max_length=14)  # e.g. "10.2\"", "$2,499", "48MP", "5x"
    count_up: bool = True
    duration: float | None = None


class SpecListBeat(BaseModel):
    type: Literal["spec_list"] = "spec_list"
    title: str = Field(default="Key specs", max_length=32)
    items: list[str] = Field(min_length=1, max_length=5)
    duration: float | None = None

    @field_validator("items")
    @classmethod
    def _short_items(cls, v: list[str]) -> list[str]:
        for item in v:
            if len(item) > 34:
                raise ValueError(f"spec item too long (max 34 chars): {item!r}")
        return v


class PriceBeat(BaseModel):
    type: Literal["price"] = "price"
    value: str = Field(max_length=14)
    subtext: str = Field(default="", max_length=40)
    duration: float | None = None


class CompareBeat(BaseModel):
    type: Literal["compare"] = "compare"
    a: str = Field(max_length=16)
    b: str = Field(max_length=16)
    rows: list[tuple[str, str, str]] = Field(min_length=1, max_length=4)  # (label, a_value, b_value)
    duration: float | None = None

    @field_validator("rows")
    @classmethod
    def _filled(cls, v: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        for row in v:
            if any(not cell.strip() for cell in row):
                raise ValueError("compare rows need a label and a value for both sides; compare two products, not a timeline")
        return v


class CtaBeat(BaseModel):
    type: Literal["cta"] = "cta"
    text: str = Field(max_length=60)
    follow: str = Field(default="Follow for daily tech", max_length=32)
    duration: float | None = None


Beat = Annotated[
    Union[HookBeat, TitleBeat, StatBeat, SpecListBeat, PriceBeat, CompareBeat, CtaBeat],
    Field(discriminator="type"),
]

PALETTES = ("neon_dark", "sunset", "mint", "mono", "electric")


class StorySpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    topic_key: str = Field(
        default="",
        description="Short stable key for the story (e.g. 'samsung-trifold-launch') used to avoid repeats.",
    )
    template: str = "gadget_reveal"
    palette: Literal["neon_dark", "sunset", "mint", "mono", "electric"] = "neon_dark"
    beats: list[Beat] = Field(min_length=2, max_length=9)
    caption: str = Field(max_length=2000)
    hashtags: list[str] = Field(default_factory=list, max_length=8)
    sources: list[str] = Field(min_length=1)
    source_label: str = Field(default="", max_length=40, description="Shown on screen, e.g. 'via The Verge'")
    suggested_sound: str = ""
    sfx: bool = True

    @field_validator("hashtags")
    @classmethod
    def _hashtags(cls, v: list[str]) -> list[str]:
        out = []
        for tag in v:
            tag = tag.strip()
            if not tag.startswith("#"):
                tag = "#" + tag
            if not re.fullmatch(r"#\w{1,40}", tag):
                raise ValueError(f"invalid hashtag: {tag!r}")
            out.append(tag)
        return out

    def full_caption(self) -> str:
        tags = " ".join(self.hashtags)
        return f"{self.caption}\n\n{tags}".strip()
