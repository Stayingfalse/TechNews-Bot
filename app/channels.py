"""Channels: one brand posting one kind of content to its own social accounts.

Today there is one channel, "main" (the quiz account), built from the existing settings, so nothing
behaves differently. The seams for more are here: every job records its channel, the worker runs
each job "as" its channel, and OAuth tokens are stored per channel. See docs/MULTI_ACCOUNT.md for
the steps still to come (per-channel schedules, connections, routines and content kinds).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from .config import settings

MAIN = "main"


@dataclass(frozen=True)
class Channel:
    id: str
    name: str
    kind: str  # the content it makes; "quiz" is the only renderer so far
    brand_handle: str
    post_time: str
    platforms: list[str] = field(default_factory=list)


def registry() -> dict[str, Channel]:
    return {MAIN: Channel(MAIN, "Daily quiz", "quiz", settings.brand_handle, settings.post_time, list(settings.platforms))}


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
