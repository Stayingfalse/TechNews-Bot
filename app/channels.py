"""Channels: one brand posting one kind of content to its own social accounts.

Three channels: "main" (the quiz account, built from the existing settings), "adventure" (the
dungeon crawl, docs/ADVENTURE_PLAN.md) and "racing" (Sixel Speedway, docs/RACING_PLAN.md). Every job records its channel, the worker runs each job
"as" its channel, OAuth tokens are stored per channel, and /oauth/{platform}/start?channel=…
connects a channel's own accounts. See docs/MULTI_ACCOUNT.md for what's still to come.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from .config import settings

MAIN = "main"
ADVENTURE = "adventure"
RACING = "racing"


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    kind: str  # the content it makes: "quiz", "adventure" or "racing"
    brand_handle: str
    post_time: str
    platforms: list[str] = field(default_factory=list)


def registry() -> dict[str, Channel]:
    return {
        MAIN: Channel(MAIN, "Daily quiz", "quiz", settings.brand_handle, settings.post_time, list(settings.platforms)),
        ADVENTURE: Channel(ADVENTURE, "Dungeon crawl", "adventure", settings.adventure_handle, settings.adventure_post_time,
                           list(settings.adventure_platforms)),
        RACING: Channel(RACING, "Sixel Speedway", "racing", settings.racing_handle, settings.racing_post_time,
                        list(settings.racing_platforms)),
    }


def get(channel_id: str | None) -> Channel:
    return registry()[channel_id or MAIN]


# The channel the code is working for right now: a job runs "as" its channel, so lower layers
# (token storage, publishers) pick that channel's accounts without passing it everywhere.
current: ContextVar[str] = ContextVar("channel", default=MAIN)


@contextmanager
def use(channel_id: str | None):
    token = current.set(channel_id or MAIN)
    try:
        yield get(channel_id)
    finally:
        current.reset(token)


def token_key(provider: str, channel_id: str | None = None) -> str:
    """Where a channel's tokens for a platform live in tokens.json. The main channel keeps the plain
    provider name, so the tokens connected before channels existed stay where they are."""
    ch = channel_id or current.get()
    return provider if ch == MAIN else f"{ch}:{provider}"
