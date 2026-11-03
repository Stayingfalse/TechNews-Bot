"""Farside's daily cycle (app/colony/jobs.py) with Instagram faked: start, read comments, render
after the cut-off, preview, post, keep what changed, and reply."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import channels, store
from app.colony import inbox, jobs, replies, state, today
from app.config import settings
from app.main import app
from app.publish import instagram

AUTH = {"Authorization": f"Bearer {settings.api_token}"}
DAY = date(2026, 11, 9)


@pytest.fixture
def ig(monkeypatch, discord):
    """Instagram faked for the colony's account; rendering stubbed (a real one takes a minute)."""
    from app.render.colony import video

    calls = {"posts": [], "replies": [], "comments": [], "followers": 12, "metrics": {"shares": 5, "saves": 2}}
    monkeypatch.setattr(settings, "colony_enabled", True)
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(instagram, "configured", lambda: True)
    monkeypatch.setattr(instagram, "followers", lambda: calls["followers"])
    monkeypatch.setattr(instagram, "own_name", lambda: "farside.colony")
    monkeypatch.setattr(instagram, "comments", lambda media, limit=200: list(calls["comments"]))
    monkeypatch.setattr(instagram, "metrics", lambda media: dict(calls["metrics"]))
    monkeypatch.setattr(instagram, "publish_reel", lambda url, cap, cover=None: calls["posts"].append((url, cap))
                        or {"media_id": f"m{len(calls['posts'])}", "url": "https://instagram.com/p/x"})
    monkeypatch.setattr(instagram, "reply", lambda cid, text: calls["replies"].append((cid, text)) or "r")
    monkeypatch.setattr(video, "render", lambda spec, path, audio=None: path.write_bytes(b"mp4"))
    monkeypatch.setattr(jobs, "_spawn", lambda target, job: target(job))  # run steps in this thread
    store.set_tokens("instagram", {"access_token": "t", "user_id": "9", "expires_at": 9e12}, channel=channels.COLONY)
    calls["discord"] = discord
    return calls


def at(day, hh, mm):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=settings.tz).astimezone(timezone.utc)


def comment(cid, user, text, when):
    return {"id": cid, "user": user, "uid": f"u-{user}", "text": text, "at": when.isoformat(), "likes": 0}


def test_start_needs_the_channel_switched_on_and_connected(monkeypatch):
    c = TestClient(app)
    assert c.post("/colony/start", headers=AUTH).status_code == 409  # COLONY_ENABLED is off
    monkeypatch.setattr(settings, "colony_enabled", True)
    r = c.post("/colony/start", headers=AUTH)
    assert r.status_code == 409 and ("PUBLISH_ENABLED" in r.text or "connected" in r.text)
    assert c.get("/colony/state", headers=AUTH).status_code == 200
    assert c.get("/colony/state").status_code == 401


def test_a_day_from_start_to_replies(ig, monkeypatch):
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    assert jobs.get(DAY.isoformat())["status"] == "booked" and state.load()["followers"] == 12
    # comments arrive before the cut-off (17:30); day 1's post doesn't exist yet, so they're on no post:
    inbox.add([comment("a", "nova.k", "hi! can I live here", at(DAY, 12, 0)), comment("b", "mossbyte", "farm", at(DAY, 13, 0))])
    jobs.tick(at(DAY, 17, 59))
    assert jobs.get(DAY.isoformat())["status"] == "booked"  # not yet: it renders an hour before
    jobs.tick(at(DAY, 18, 0))  # an hour before 19:00 → prepare
    job = jobs.get(DAY.isoformat())
    assert job["status"] == "scheduled" and job["summary"]["arrived_count"] == 2 and job["summary"]["source"] == "none"
    assert "posts" in ig["discord"][-1][0] or "Farside" in ig["discord"][-1][0]
    jobs.tick(at(DAY, 19, 0))  # the slot → post
    job = jobs.get(DAY.isoformat())
    assert job["status"] == "done" and len(ig["posts"]) == 1 and job["replies_queued"] == 2
    assert jobs.get((DAY + timedelta(days=1)).isoformat())["status"] == "booked"  # tomorrow is booked
    with channels.use(channels.COLONY):
        assert replies.send_due(at(DAY, 19, 1)) == 1  # one now, the next after the gap
        assert replies.send_due(at(DAY, 19, 1) + timedelta(seconds=25)) == 1
    assert {cid for cid, _ in ig["replies"]} == {"a", "b"} and "Welcome to Farside" in ig["replies"][0][1]


def test_an_adapted_day_posts_its_changes_and_replies(ig, monkeypatch):
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    inbox.add([comment("a", "oldbarrel", "can I be an old man in a barrel", at(DAY, 12, 0))])
    ep = {"beats": [{"type": "slot", "slot": "arrivals"},
                    {"type": "feature", "who": "@oldbarrel", "lines": ["*@OLDBARREL*", "GOT HIS *BARREL*"]}],
          "caption": "An old man moved into a barrel.", "summary": "Day 1.",
          "settlers": {"@oldbarrel": {"look": {"carrier": "barrel", "body": "old"}, "traits": ["grumpy"], "sheet": "Barrel."}},
          "replies": [{"comment_id": "a", "text": "Pull up a barrel."}]}
    assert today.accept(DAY, ep, now=at(DAY, 16, 0)) == []
    jobs.tick(at(DAY, 18, 0))
    jobs.tick(at(DAY, 19, 0))
    job = jobs.get(DAY.isoformat())
    assert job["status"] == "done" and ig["posts"][0][1] == "An old man moved into a barrel."
    st = next(x for x in state.load()["settlers"].values() if x["handle"] == "oldbarrel")
    assert st["look"]["carrier"] == "barrel" and st["featured_on"] == [DAY.isoformat()]
    with channels.use(channels.COLONY):
        replies.send_due(at(DAY, 19, 2))
    assert ig["replies"] == [("a", "Pull up a barrel.")]


def test_followers_and_yesterdays_shares_drive_the_next_day(ig, monkeypatch):
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    jobs.tick(at(DAY, 18, 0)); jobs.tick(at(DAY, 19, 0))
    ig["followers"], ig["metrics"] = 30, {"shares": 9, "saves": 3}
    d2 = DAY + timedelta(days=1)
    jobs.tick(at(d2, 18, 0))
    rep = state.load()["days"][d2.isoformat()]
    assert rep["joined"] == 18 and rep["gained"]["shares"] == 9 and rep["gained"]["saves"] == 3
    assert "greenhouse" in rep["unlocked"]


def test_blocking_someone_takes_them_out_and_renders_again(ig, monkeypatch):
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    inbox.add([comment("t", "troll", "hello", at(DAY, 12, 0))])
    jobs.tick(at(DAY, 18, 0))
    assert any(x["handle"] == "troll" for x in state.load()["settlers"].values())
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 18, 10))
    r = TestClient(app).post(f"/colony/block?user=@troll&date={DAY}", headers=AUTH)
    assert r.status_code == 200
    assert not any(x["handle"] == "troll" for x in state.load()["settlers"].values())
    assert jobs.get(DAY.isoformat())["status"] == "scheduled"  # rendered again


def test_a_failed_post_can_be_retried_and_a_missed_slot_is_reported(ig, monkeypatch):
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    jobs.tick(at(DAY, 18, 0))
    monkeypatch.setattr(instagram, "publish_reel", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    jobs.tick(at(DAY, 19, 0))
    assert jobs.get(DAY.isoformat())["status"] == "failed"
    monkeypatch.setattr(instagram, "publish_reel", lambda *a, **k: {"media_id": "m9", "url": "u"})
    jobs.retry(DAY.isoformat())
    assert jobs.get(DAY.isoformat())["status"] == "done"
    d2 = DAY + timedelta(days=1)
    jobs.tick(at(d2, 19, 0) + timedelta(hours=7))  # the server was down all evening
    assert jobs.get(d2.isoformat())["status"] == "missed"
