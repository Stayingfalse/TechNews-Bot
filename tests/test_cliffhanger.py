"""The cliffhanger loop: judging comments, shout-outs, replies and the next-quiz links."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import cliffhanger as ch
from app import store
from app.spec import ChoiceRound, EmojiRound, TrueFalseRound, UnscrambleRound
from tests.helpers import comment, posted

EMOJI = EmojiRound(emojis="🦁👑", answer="The Lion King", accept=["Lion King"])
CHOICE = ChoiceRound(question="Which came first?", options=["Toy Story", "Shrek", "Up"], correct=0)
REAL = TrueFalseRound(statement="x", answer=True, explanation="y")
WORD = UnscrambleRound(answer="Frozen")


@pytest.mark.parametrize("rnd,text,right", [
    (EMOJI, "lion king!!", True),
    (EMOJI, "Its the lion kingg 😍", True),  # typo forgiven
    (EMOJI, "frozen", False),
    (CHOICE, "A", True),  # option letter
    (CHOICE, "a) toy story", True),
    (CHOICE, "toy story obviously", True),
    (CHOICE, "toy story or shrek?", False),  # hedging between options doesn't count
    (CHOICE, "B", False),
    (REAL, "REAL 100%", True),
    (REAL, "fake", False),
    (REAL, "real or fake?", False),
    (WORD, "FROZEN", True),
    (WORD, "frozne", True),
    (WORD, "frozen 2", True),
])
def test_judging(rnd, text, right):
    assert ch.is_correct(rnd, text) is right


@pytest.mark.parametrize("name,shown", [
    ("film_fan_99", "film_fan_99"), ("@jo.may", "jo.may"), ("Émilie R", "EmilieR"),
    ("x", None),  # too short to be a name
    ("bigdickenergy", None),  # never shown on screen
])
def test_safe_names(name, shown):
    assert ch.safe_name(name) == shown


@pytest.fixture
def cliff_spec(quiz):
    quiz["rounds"][-1]["cliffhanger"] = True
    return quiz


def booked_next(quiz, hours_ahead=1):
    job = {"id": "next-1", "spec": quiz, "status": "booked", "dry_run": False, "slot": "2026-10-24",
           "publish_at": (datetime.now(timezone.utc) + timedelta(hours=hours_ahead)).isoformat(),
           "created_at": "2026-10-23T00:00:00+00:00", "results": {}}
    store.save_job(job)
    return job


def test_reveal_shoutouts_and_replies(quiz, cliff_spec, platforms):
    posted("cliff-1", cliff_spec, hours_ago=20)
    platforms["comments"]["instagram"] = [
        comment("c1", "mediaquiz.daily", "Toy Story", 1),  # our own comment: never a winner
        comment("c2", "early_bird", "toy story!", 2),
        comment("c3", "wrong_one", "Shrek", 3),
        comment("c4", "bigdick99", "toy story", 4),  # unsafe name: skipped
        comment("c5", "early_bird", "A", 5),  # same person again: counted once
    ]
    platforms["comments"]["youtube"] = [comment("y1", "TubeFan", "A) toy story", 1, channel="UC1"),
                                        comment("y2", "me", "Toy Story", 0, channel="UC_OWN")]
    nxt = booked_next(quiz)

    reveal = ch.prepare(nxt)
    assert reveal["answer"] == "Toy Story"
    assert reveal["shoutouts"] == ["TubeFan", "early_bird"]  # earliest first
    assert reveal["comments_read"] == 5  # our own comments are left out

    nxt.update(reveal=reveal, status="done", results={
        "instagram": {"ok": True, "url": "https://instagram.com/reel/NEW"},
        "youtube": {"ok": True, "url": "https://youtube.com/shorts/NEW"}})
    ch.after_publish(nxt)
    replies = [(p, cid) for p, kind, cid, _ in platforms["calls"] if kind == "reply"]
    assert replies == [("youtube", "y1"), ("instagram", "c2")]
    yt_text = next(t for p, k, c, t in platforms["calls"] if p == "youtube")
    assert "https://youtube.com/shorts/NEW" in yt_text  # YouTube replies carry the link
    assert store.get_job("cliff-1")["cliff_revealed_by"] == "next-1"
    assert ch.pending_for({"id": "later", "publish_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}) is None


def test_reveal_without_comment_access(quiz, cliff_spec, platforms, monkeypatch):
    from app.publish import instagram, youtube

    posted("cliff-1", cliff_spec, hours_ago=20)

    def refuse(_):
        raise RuntimeError("missing permission")

    monkeypatch.setattr(instagram, "comments", refuse)
    monkeypatch.setattr(youtube, "comments", refuse)
    reveal = ch.prepare(booked_next(quiz))
    assert reveal["answer"] == "Toy Story" and reveal["shoutouts"] is None  # the video says "did you get it?"
    assert len(reveal["errors"]) == 2


def test_old_or_test_cliffhangers_are_not_revealed(quiz, cliff_spec, platforms):
    posted("cliff-old", cliff_spec, hours_ago=24 * 5)  # past the lookback
    posted("test-cliff", cliff_spec, hours_ago=2)
    assert ch.prepare(booked_next(quiz)) is None


def test_next_quiz_link_comments(quiz, cliff_spec, platforms):
    posted("older", quiz, hours_ago=44)
    posted("cliff-1", cliff_spec, hours_ago=20, results={
        "instagram": {"ok": True, "media_id": "M1"}, "youtube": {"ok": False, "error": "x"},
        "tiktok": {"ok": False, "error": "retired"}})
    posted("test-thing", quiz, hours_ago=2)  # test posts are never "the previous post"
    nxt = {"id": "next-1", "spec": quiz, "dry_run": False, "published_at": datetime.now(timezone.utc).isoformat(),
           "reveal": {"from_job": "cliff-1"},
           "results": {"instagram": {"ok": True, "url": "u1"}, "youtube": {"ok": True, "url": "u2"}}}
    ch.link_previous(nxt)
    comments = [(p, mid) for p, kind, mid, _ in platforms["calls"] if kind == "comment"]
    assert comments == [("instagram", "M1")]  # YouTube skipped: the cliffhanger never made it there
    assert "Answer revealed" in platforms["calls"][0][3]
    assert nxt["linked_from"] == {"job": "cliff-1", "instagram": True}
    platforms["calls"].clear()
    ch.link_previous(nxt)
    assert platforms["calls"] == []  # once only
