"""Quiz spec: the contract between the daily writing routine and the renderer.

A video is an intro, 3-5 rounds and an outro. Each round shows a clue with a countdown for
`think` seconds, then reveals the answer for `reveal` seconds.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from .render.emoji import clusters, is_emoji_only

MEDIA = ("Movie", "TV show", "Song", "Book", "Video game", "Cartoon", "Band", "Celebrity", "Brand", "Place", "Food", "Animal")


class _Round(BaseModel):
    think: float = Field(default=5.0, ge=3.0, le=10.0, description="Seconds the clue is up with the countdown")
    reveal: float = Field(default=2.6, ge=1.8, le=6.0, description="Seconds the answer stays on screen")
    cliffhanger: bool = Field(default=False, description=(
        "Last round only: no reveal. Viewers comment their answer; the next quiz reveals it and gives the "
        "first correct commenters a shout-out"))
    accept: list[str] = Field(default_factory=list, max_length=6, description=(
        "Other spellings that count as correct when judging cliffhanger comments, e.g. ['Lion King']"))
    ask_comment: bool = Field(default=False, description="Show a 'Comment your guess!' sticker during this round's countdown")

    @field_validator("accept")
    @classmethod
    def _accept(cls, v: list[str]) -> list[str]:
        if any(not a.strip() or len(a) > 40 for a in v):
            raise ValueError("accept: each alternative 1-40 chars")
        return v

    def correct_texts(self) -> list[str]:
        """What a comment must say to be right (plus `accept`)."""
        return [self.answer_text(), *self.accept]

    def answer_text(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError


class EmojiRound(_Round):
    """Guess the thing from emojis. The emojis pop in one by one."""
    type: Literal["emoji"] = "emoji"
    category: str = Field(default="Movie", max_length=16, description="Shown as 'Guess the <category>'. " + ", ".join(MEDIA))
    emojis: str = Field(description="2-7 emojis, nothing else (no letters or spaces needed)")
    answer: str = Field(max_length=40)
    note: str = Field(default="", max_length=60, description="Optional line under the answer, e.g. the year")

    @field_validator("emojis")
    @classmethod
    def _emojis(cls, v: str) -> str:
        v = "".join(v.split())
        n = len(clusters(v))
        if not is_emoji_only(v):
            raise ValueError("emojis must contain only emoji characters")
        if not 2 <= n <= 7:
            raise ValueError(f"use 2-7 emojis (got {n})")
        return v

    def answer_text(self) -> str:
        return self.answer


class BadDescriptionRound(_Round):
    """A famous movie/show/book/song described badly, literally or unhelpfully."""
    type: Literal["bad_description"] = "bad_description"
    category: str = Field(default="Movie", max_length=16, description=", ".join(MEDIA))
    description: str = Field(max_length=120, description="The badly described plot. Wrap one word in *asterisks* to highlight it.")
    answer: str = Field(max_length=40)
    note: str = Field(default="", max_length=60)
    think: float = Field(default=6.0, ge=3.0, le=10.0)

    def answer_text(self) -> str:
        return self.answer


class TrueFalseRound(_Round):
    """Real or fake? A surprising statement; reveal says which and why."""
    type: Literal["true_false"] = "true_false"
    statement: str = Field(max_length=110, description="Wrap one word in *asterisks* to highlight it")
    answer: bool
    explanation: str = Field(max_length=70, description="One short line shown with the reveal")

    def answer_text(self) -> str:
        return f"{'TRUE' if self.answer else 'FALSE'}: {self.statement.replace('*', '')}"

    def correct_texts(self) -> list[str]:
        return ["real", "true"] if self.answer else ["fake", "false"]


class ChoiceRound(_Round):
    """Multiple choice (3-4 options). Also covers 'which came first', 'guess the year', etc."""
    type: Literal["choice"] = "choice"
    question: str = Field(max_length=80)
    options: list[str] = Field(min_length=3, max_length=4)
    correct: int = Field(ge=0, le=3, description="Index into options")
    note: str = Field(default="", max_length=60)

    @field_validator("options")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        for o in v:
            if not o.strip() or len(o) > 28:
                raise ValueError(f"options must be 1-28 chars: {o!r}")
        return v

    @model_validator(mode="after")
    def _correct(self) -> "ChoiceRound":
        if self.correct >= len(self.options):
            raise ValueError("correct is out of range")
        return self

    def answer_text(self) -> str:
        return f"{self.question} {self.options[self.correct]}"

    def correct_texts(self) -> list[str]:
        return [self.options[self.correct], *self.accept]


class OddOneOutRound(_Round):
    """Four items, one doesn't belong."""
    type: Literal["odd_one_out"] = "odd_one_out"
    items: list[str] = Field(min_length=4, max_length=4)
    odd: int = Field(ge=0, le=3, description="Index of the odd one out")
    reason: str = Field(max_length=70, description="Why it's the odd one out")

    @field_validator("items")
    @classmethod
    def _short(cls, v: list[str]) -> list[str]:
        for o in v:
            if not o.strip() or len(o) > 28:
                raise ValueError(f"items must be 1-28 chars: {o!r}")
        return v

    def answer_text(self) -> str:
        return f"odd one out {self.items[self.odd]} ({', '.join(self.items)})"

    def correct_texts(self) -> list[str]:
        return [self.items[self.odd], *self.accept]


class UnscrambleRound(_Round):
    """The answer's letters are shuffled by the renderer; viewers unscramble them."""
    type: Literal["unscramble"] = "unscramble"
    category: str = Field(default="Movie", max_length=16, description=", ".join(MEDIA))
    answer: str = Field(max_length=22, description="Letters and spaces only; the renderer scrambles it")
    note: str = Field(default="", max_length=60)

    @field_validator("answer")
    @classmethod
    def _letters(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z][A-Za-z ']*[A-Za-z]", v.strip()) or len(v.replace(" ", "")) < 4:
            raise ValueError("unscramble answer must be 4+ letters (letters, spaces, apostrophes)")
        return v.strip()

    def answer_text(self) -> str:
        return self.answer


Round = Annotated[
    Union[EmojiRound, BadDescriptionRound, TrueFalseRound, ChoiceRound, OddOneOutRound, UnscrambleRound],
    Field(discriminator="type"),
]

PALETTES = ("teatime", "primetime", "jackpot", "bingo", "pitch")


class PickedBy(BaseModel):
    """The viewer whose comment suggested this quiz's theme (from GET /themes/suggestions)."""
    user: str = Field(pattern=r"^[A-Za-z0-9._-]{2,28}$", description="Their username, exactly as the suggestions list gives it")
    platform: Literal["instagram", "youtube"]
    comment_id: str = Field(min_length=1, max_length=120, description="The suggestion's comment_id; they get a reply there once it posts")
    text: str = Field(default="", max_length=120, description="Their comment as the suggestions list gives it, shown on screen as a comment card")


class QuizSpec(BaseModel):
    """An intro, 3-5 rounds (any mix of: emoji, bad_description, true_false, choice, odd_one_out,
    unscramble) and an outro asking viewers to comment their score."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{2,80}$")
    theme: str = Field(default="", max_length=40, description="Optional theme, e.g. '90s movies', 'Disney'")
    title: str = Field(max_length=60, description="Intro hook, e.g. 'Only *real* film fans get 5/5'. One *highlighted* word.")
    subtitle: str = Field(default="", max_length=40, description="Small line under the title, e.g. 'Guess before the timer ends'")
    palette: Literal["teatime", "primetime", "jackpot", "bingo", "pitch"] = "teatime"
    rounds: list[Round] = Field(min_length=3, max_length=5)
    outro: str = Field(default="How many did you *get*?", max_length=50)
    follow: str = Field(default="Follow for a daily quiz", max_length=32)
    caption: str = Field(max_length=2000)
    hashtags: list[str] = Field(default_factory=list, max_length=8)
    intro: Literal["card", "quick", "banner"] = Field(default="card", description=(
        "card = 2.8 s title card; quick = 1.2 s title card; banner = no card, the title rides a banner over round 1"))
    pause_hint: bool = Field(default=False, description="Show a 'Pause to answer' sticker during countdowns")
    voice: bool = Field(default=False, description=(
        "Game-show host voice-over (ElevenLabs): reads the title, calls each round and announces the answers"))
    ask_theme: bool = Field(default=False, description="The outro asks viewers to comment a theme for next week")
    picked_by: PickedBy | None = Field(default=None, description=(
        "This quiz's theme came from a viewer's comment: credited on screen, and they get a reply once it posts"))
    music: str = Field(
        default="auto",
        description="'auto' (random track from the music library, else synth), 'synth', 'none', or a library file name",
    )
    sfx: bool = True
    tags: dict[str, str] = Field(
        default_factory=dict,
        description="Experiment labels for the dashboard, e.g. {'special': 'hard', 'cta': 'answer-before-reveal'}",
    )

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

    @model_validator(mode="after")
    def _cliffhanger_last(self) -> "QuizSpec":
        if any(r.cliffhanger for r in self.rounds[:-1]):
            raise ValueError("only the last round can be the cliffhanger")
        return self

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 8:
            raise ValueError("at most 8 tags")
        for k, val in v.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,23}", k) or not 0 < len(val) <= 40:
                raise ValueError(f"tag {k!r}: key = lowercase word (max 24), value = 1-40 chars")
        return v

    def answer_keys(self) -> list[str]:
        """Normalised answers, used to avoid repeating a puzzle."""
        return [normalise(r.answer_text()) for r in self.rounds]

    def full_caption(self) -> str:
        tags = " ".join(self.hashtags)
        return f"{self.caption}\n\n{tags}".strip()


def normalise(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", "", text.lower())
    text = re.sub(r"^(the|a|an) ", "", text)
    return " ".join(text.split())
