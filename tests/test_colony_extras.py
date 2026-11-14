"""Farside extras (app/colony/extras.py): a standalone video outside the daily cycle, rendered from
the colony as it stands, previewed, posted, and its comments read; the colony left untouched."""
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.colony import extras, inbox, jobs, state
from app.config import settings
from app.main import app
from app.publish import instagram
from tests.test_colony_launch import AUTH, DAY, at, comment, ig  # noqa: F401  (ig is a fixture)

EP = {"beats": [{"type": "caption", "lines": ["*CATCH UP*", "THE STORY SO FAR"]},
                {"type": "say", "who": "MAREN", "text": "STAY CLOSE.", "secs": 2.5},
                {"type": "caption", "lines": ["SOMETHING IS", "*COMING TONIGHT*"]}],
      "caption": "The story so far, before tonight's episode."}


@pytest.fixture
def x(ig, monkeypatch):  # noqa: F811
    monkeypatch.setattr(extras, "_spawn", lambda target, job: target(job))
    return ig


def send(c, body, at_=""):
    return c.post("/colony/extra" + (f"?at={at_}" if at_ else ""), headers=AUTH, content=json.dumps(body))


def test_an_extra_renders_previews_and_posts_without_touching_the_colony(x, monkeypatch):
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    before = json.dumps(state.load(), sort_keys=True)
    r = send(TestClient(app), EP)
    assert r.status_code == 202, r.text
    job = extras.get(r.json()["id"])
    assert job["status"] == "scheduled" and job["caption"] == EP["caption"]
    assert "Farside extra" in x["discord"][-1][0] and x["discord"][-1][1] is not None  # the video's attached
    extras.tick()  # no `at`: posts as soon as it's ready
    job = extras.get(job["id"])
    assert job["status"] == "done" and x["posts"][-1][1] == EP["caption"]
    assert json.dumps(state.load(), sort_keys=True) == before  # nobody arrived, nothing changed
    assert jobs.get(DAY.isoformat())["status"] == "booked"  # the day's own episode still posts at its slot
    # comments on the extra are read like any post's
    x["comments"] = [comment("e1", "newbie", "hello from the extra", datetime.now(timezone.utc))]
    jobs.poll()
    assert inbox.load()["comments"]["e1"]["post"] == job["id"]


def test_an_extra_waits_for_its_time_and_can_be_cancelled(x):
    c = TestClient(app)
    when = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
    r = send(c, EP, when.isoformat().replace("+", "%2B"))
    assert r.status_code == 202, r.text
    xid = r.json()["id"]
    extras.tick()
    assert extras.get(xid)["status"] == "scheduled" and not x["posts"]
    assert c.delete(f"/colony/extras/{xid}", headers=AUTH).json()["status"] == "cancelled"
    extras.tick(when + timedelta(minutes=1))
    assert not x["posts"]
    assert c.get("/colony/extras", headers=AUTH).json()["extras"][0]["status"] == "cancelled"


def test_a_failed_extra_can_be_retried(x, monkeypatch):
    monkeypatch.setattr(instagram, "publish_reel", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    xid = send(TestClient(app), EP).json()["id"]
    extras.tick()
    assert extras.get(xid)["status"] == "failed"
    monkeypatch.setattr(instagram, "publish_reel", lambda *a, **k: {"media_id": "m9", "url": "u"})
    r = TestClient(app).post(f"/colony/extras/{xid}/retry", headers=AUTH)
    assert r.status_code == 202 and extras.get(xid)["status"] == "done"


@pytest.mark.parametrize("extra, word", [({"settlers": {"@a": {"traits": ["x"]}}}, "settlers"),
                                         ({"replies": [{"comment_id": "1", "text": "hi"}]}, "replies"),
                                         ({"parts": [{"slot": "pet", "id": "x", "rows": ["g"], "colors": {"g": "ink"}}]}, "parts")])
def test_an_extra_cant_change_settlers_reply_or_add_parts(x, extra, word):
    r = send(TestClient(app), {**EP, **extra})
    assert r.status_code == 422 and any(p.startswith(word) for p in r.json()["detail"]["problems"])


def test_a_bad_episode_or_time_is_refused(x):
    c = TestClient(app)
    assert send(c, {"beats": "x"}).status_code == 422
    assert send(c, EP, "yesterday").status_code == 400
    assert send(c, EP, "2020-01-01T10:00:00").status_code == 400  # already passed


def test_parse_at_reads_a_plus_that_arrived_as_a_space():
    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    assert extras.parse_at("2026-11-14T15:00:00 00:00", now) == datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)
    assert extras.parse_at("2026-11-14T15:00 01:00", now) == datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc)
    local = extras.parse_at("2026-11-14 15:00", now)  # a space between date and time: local time
    assert local == datetime(2026, 11, 14, 15, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    assert extras.parse_at("", now) is None


def test_a_failed_post_still_books_the_next_day(ig, monkeypatch):  # noqa: F811
    monkeypatch.setattr(jobs, "now", lambda: at(DAY, 9, 0))
    jobs.start(DAY)
    jobs.tick(at(DAY, 18, 0))
    monkeypatch.setattr(instagram, "publish_reel", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    jobs.tick(at(DAY, 19, 0))
    assert jobs.get(DAY.isoformat())["status"] == "failed"
    assert jobs.get((DAY + timedelta(days=1)).isoformat())["status"] == "booked"
