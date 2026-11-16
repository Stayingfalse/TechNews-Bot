"""A raosanta.uk promo video: a list of segments played one after another (docs/SANTA_PLAN.md §1).

Every segment can carry `say`, a line the narrator reads when it starts. A segment lasts long
enough for its words to be read and for its line to be said (`seconds` sets a minimum). Only
tutorials and pitches have a voice-over unless `voice` says otherwise: half the posts, to save
credits. Text uses the site's face (Archivo), which has no emoji: they're refused. Wrap a word in
*asterisks* to show it in gold.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

FORMATS = ("tutorial", "pitch", "quiz", "update", "kudos")
VOICED = ("tutorial", "pitch")  # voiced by default; the rest are music and on-screen text
AUDIENCES = ("workplace", "community", "friends", "everyone")
MAX_SECONDS = 45.0  # longer is refused; aim for 20-35 (CHANNEL_REVIEW_AND_NEXT.md)
TARGET_SECONDS = 35.0

# Live figures from raosanta.uk (app/santa/source.py), filled in when the video is rendered. A
# segment whose placeholder has no value (hidden under 10, or the site unreachable) is left out.
PLACEHOLDERS = {
    "season.year": "the season's year, e.g. 2026",
    "season.opensOn": 'the day gifting opens, e.g. "27 November"',
    "season.closesOn": 'the season\'s last day, e.g. "6 January"',
    "season.lastOrderOn": "Amazon UK's last day to order for Christmas (unset until an admin sets it)",
    "season.daysToOpen": "days until gifting opens (none once open)",
    "season.daysToClose": "days until the season closes",
    "season.daysToLastOrder": "days until the last order day",
    "allTime.members": 'members since the site began, e.g. "450+"',
    "allTime.gifts": "gifts sent since the site began",
    "allTime.thankYous": "thank-you postcards since the site began",
    "thisSeason.membersTakingPart": "members checked in this season",
    "thisSeason.gifts": "gifts sent this season",
    "thisSeason.giftsLast7Days": "gifts sent in the last 7 days",
    "thisSeason.thankYous": "thank-yous posted this season",
    "groups.workplaces": "live workplaces",
    "groups.communities": "live communities (Discord servers and the like)",
    "groups.friends": "live friends and family groups",
}
PLACEHOLDER = re.compile(r"\{([A-Za-z]+\.[A-Za-z0-9]+)\}")

# Latin text and the punctuation people type; anything else (emoji, CJK) has no glyph in Archivo
_ALLOWED = re.compile(r"^[\x20-\x7E -ɏ‐-‧‰-⁞€™]*$")


def _plain(v: str | None) -> str | None:
    if v is None:
        return v
    v = " ".join(v.split())
    if not _ALLOWED.match(v):
        bad = "".join(sorted({c for c in v if not _ALLOWED.match(c)}))
        raise ValueError(f"characters the site's font can't draw (emoji?): {bad!r}")
    return v


class _Seg(BaseModel):
    say: str | None = Field(default=None, max_length=240, description="The narrator's line, read as the segment starts")
    seconds: float | None = Field(default=None, ge=1.0, le=12.0, description="At least this long")

    @model_validator(mode="before")
    @classmethod
    def _text(cls, data):
        """Every text field (and list of texts) tidied and checked for characters the font lacks."""
        if not isinstance(data, dict):
            return data
        out = {}
        for k, v in data.items():
            if k != "type" and isinstance(v, str):
                v = _plain(v)
            elif isinstance(v, list):
                v = [_plain(x) if isinstance(x, str) else x for x in v]
            out[k] = v
        return out


class Title(_Seg):
    """The hook, big, with the stamp: the first second has to stop the thumb."""
    type: Literal["title"] = "title"
    text: str = Field(max_length=70)
    sub: str | None = Field(default=None, max_length=90)


class Points(_Seg):
    """1-4 short selling points on postcards, one after another."""
    type: Literal["points"] = "points"
    heading: str | None = Field(default=None, max_length=50)
    items: list[str] = Field(min_length=1, max_length=4)

    @field_validator("items")
    @classmethod
    def _short(cls, v):
        if any(len(x) > 60 for x in v):
            raise ValueError("each item: at most 60 characters")
        return v


class Steps(_Seg):
    """2-5 numbered steps (a tutorial without a screen recording)."""
    type: Literal["steps"] = "steps"
    heading: str | None = Field(default=None, max_length=50)
    steps: list[str] = Field(min_length=2, max_length=5)

    @field_validator("steps")
    @classmethod
    def _short(cls, v):
        if any(len(x) > 60 for x in v):
            raise ValueError("each step: at most 60 characters")
        return v


class Figure(BaseModel):
    value: str = Field(max_length=40, description='e.g. "1,200+", "38", or a placeholder: "{allTime.gifts}"')
    label: str = Field(max_length=34)

    @field_validator("value", "label", mode="before")
    @classmethod
    def _text(cls, v):
        return _plain(v) if isinstance(v, str) else v

    @field_validator("value")
    @classmethod
    def _short(cls, v):
        if not PLACEHOLDER.search(v) and len(v) > 12:
            raise ValueError("at most 12 characters")
        return v


class Figures(_Seg):
    """1-3 big numbers that count up. Site figures come rounded (under 10 isn't shown)."""
    type: Literal["figures"] = "figures"
    heading: str | None = Field(default=None, max_length=50)
    figures: list[Figure] = Field(min_length=1, max_length=3)


class Question(_Seg):
    """A quiz question: options, a countdown, then the answer lights up."""
    type: Literal["question"] = "question"
    question: str = Field(max_length=110)
    options: list[str] = Field(min_length=2, max_length=4)
    correct: int = Field(ge=0, le=3)
    note: str | None = Field(default=None, max_length=90, description="Shown with the answer")
    think: float = Field(default=5.0, ge=3.0, le=8.0)

    @model_validator(mode="after")
    def _check(self):
        if self.correct >= len(self.options):
            raise ValueError("correct: the index of one of the options")
        if any(len(o) > 40 for o in self.options):
            raise ValueError("each option: at most 40 characters")
        return self


class Kudos(_Seg):
    """A thank-you postcard from the site: festive name, message and an optional photo
    (a file in DATA_DIR/santa/images; the live feed comes in a later step)."""
    type: Literal["kudos"] = "kudos"
    name: str = Field(max_length=40, description="The festive name it was posted under, never a real name")
    message: str = Field(max_length=220)
    image: str | None = Field(default=None, pattern=r"^[\w.-]+\.(jpg|jpeg|png|webp)$")


class End(_Seg):
    """The sign-off: the stamp, raosanta.uk and one line."""
    type: Literal["end"] = "end"
    line: str = Field(default="Random Acts, not Secret Santa", max_length=70)


Segment = Annotated[Union[Title, Points, Steps, Figures, Question, Kudos, End], Field(discriminator="type")]


class PromoSpec(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,60}$")
    format: Literal["tutorial", "pitch", "quiz", "update", "kudos"]
    audience: Literal["workplace", "community", "friends", "everyone"] = "everyone"
    segments: list[Segment] = Field(min_length=2, max_length=10)
    voice: bool | None = Field(default=None, description="Default: on for tutorials and pitches only")
    voice_name: str | None = Field(default=None, description="A name from SANTA_VOICES; default the first")
    music: str = Field(default="carol", pattern=r"^(carol|carol:(jingle-bells|deck-the-halls|we-wish-you)|none)$",
                       description='"carol" (a public-domain carol made in code, picked by the id), "carol:<name>", or "none"')
    caption: str = Field(default="", max_length=2000)

    @property
    def voiced(self) -> bool:
        return self.format in VOICED if self.voice is None else self.voice

    @model_validator(mode="after")
    def _check(self):
        unknown = sorted({name for text in texts(self.model_dump()["segments"]) for name in PLACEHOLDER.findall(text)}
                         - set(PLACEHOLDERS))
        if unknown:
            raise ValueError(f"unknown placeholders {unknown}: use any of {sorted(PLACEHOLDERS)}")
        if self.segments[-1].type != "end":
            raise ValueError("the last segment must be the `end` card")
        if self.format == "quiz" and not any(s.type == "question" for s in self.segments):
            raise ValueError("a quiz needs at least one `question` segment")
        if self.format == "kudos" and not any(s.type == "kudos" for s in self.segments):
            raise ValueError("a kudos spotlight needs a `kudos` segment")
        return self


def texts(value) -> list[str]:
    """Every string inside a dumped spec (or part of one)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in texts(v)]
    return []
