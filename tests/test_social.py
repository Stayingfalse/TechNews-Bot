"""Instagram extras and the profile picture rotation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import social, store
from tests.helpers import posted


def test_carousel_pick_is_most_viewed_and_never_repeats(quiz):
    posted("q-small", quiz, hours_ago=30)
    posted("q-big", quiz, hours_ago=50)
    posted("test-x", quiz, hours_ago=5)
    store._write("metrics.json", {"q-small": {"instagram": {"latest": {"views": 120}}},
                                  "q-big": {"instagram": {"latest": {"views": 340}}, "youtube": {"latest": {"views": 10}}},
                                  "test-x": {"instagram": {"latest": {"views": 9999}}}})
    assert social.carousel_pick()["id"] == "q-big"
    big = store.get_job("q-big")
    big["carousel"] = {"ok": True}
    store.save_job(big)
    assert social.carousel_pick()["id"] == "q-small"


@pytest.fixture
def youtube_banner(monkeypatch):
    from app.publish import youtube

    set_ = []
    monkeypatch.setattr(youtube, "configured", lambda: True)
    monkeypatch.setattr(youtube, "set_banner", lambda p: set_.append(p.name) or "https://yt/banner")
    store.set_tokens("youtube", {"access_token": "x"})
    return set_


def test_avatar_rotation(discord, youtube_banner):
    monday = datetime(2026, 10, 26, 10, 5, tzinfo=ZoneInfo("Europe/London"))
    social.avatar_tick(monday.replace(hour=9))
    assert discord == []  # not before 10:00
    social.avatar_tick(monday)
    social.avatar_tick(monday)
    assert [a.name for _, a in discord] == ["avatar-emoji.png"] and youtube_banner == ["banner-emoji.jpg"]
    state = store._read("social.json", {})
    state["avatar_at"] = (datetime.now(timezone.utc) - timedelta(weeks=3)).isoformat()
    store._write("social.json", state)
    social.avatar_tick(monday)
    assert [a.name for _, a in discord][-1] == "avatar-question.png"
    for _ in range(3):
        social.send_next_avatar()
    assert [a.name for _, a in discord][-1] == "avatar-emoji.png"  # round again


def test_every_avatar_has_a_banner():
    pics = social.avatars()
    assert len(pics) >= 4 and all(social._banner_for(p) for p in pics)
