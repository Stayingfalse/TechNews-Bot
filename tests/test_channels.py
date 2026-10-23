"""Channels: the main channel keeps its existing tokens; others get their own."""
from __future__ import annotations

from app import channels, store


def test_main_channel_keeps_plain_token_keys():
    store.set_tokens("instagram", {"access_token": "main"})
    assert list(store._read("tokens.json", {})) == ["instagram"]
    with channels.use("main"):
        assert store.get_tokens("instagram")["access_token"] == "main"


def test_other_channels_are_separate():
    store.set_tokens("instagram", {"access_token": "main"})
    token = channels.current.set("facts")
    try:
        store.set_tokens("instagram", {"access_token": "facts"})
        assert store.get_tokens("instagram")["access_token"] == "facts"
        assert store.get_tokens("instagram", "main")["access_token"] == "main"
    finally:
        channels.current.reset(token)
    assert sorted(store._read("tokens.json", {})) == ["facts:instagram", "instagram"]
