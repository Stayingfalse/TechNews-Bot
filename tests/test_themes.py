"""Viewer-picked themes: reading suggestions, ranking them and replying to the winner."""
from __future__ import annotations

import pytest

from app import themes
from app.spec import QuizSpec
from tests.helpers import comment, posted


@pytest.mark.parametrize("text,theme", [
    ("Disney villains please!", "Disney villains"),
    ("Theme: 80s music", "80s music"),
    ("@bob harry potter", "harry potter"),
    ("do marvel next week", "marvel"),
    ("5/5", None), ("4 out of 5", None), ("lol", None), ("too easy", None), ("🔥🔥", None),
    ("fuck off", None),
    ("Disney movies", "Disney movies"), ("can you do a Harry Potter one?", "Harry Potter"), ("what about 90s cartoons", "90s cartoons"),
    ("Star Wars quiz pls", "Star Wars"), ("Lord of the Rings", "Lord of the Rings"),
    ("I would never have guessed shining.", None), ("can't decide if I prefer the videos without a voice or not", None),
    ("Also had no clue for Round 4", None), ("this was so hard", None), ("you got me", None),
    ("my favourite was the last one honestly it was great", None),
])
def test_theme_text(text, theme):
    assert themes._theme_text(text) == theme


def test_suggestions_grouped_and_ranked(quiz, platforms):
    posted("ask-1", dict(quiz, id="ask", ask_theme=True), hours_ago=48)
    posted("plain-1", quiz, hours_ago=24)  # didn't ask: not read
    platforms["comments"]["instagram"] = [
        comment("c1", "early_bird", "Disney villains!", 1),
        comment("c2", "film_fan", "disney villains please", 5),
        comment("c3", "early_bird", "4/5", 6),
        comment("c4", "mediaquiz.daily", "Thanks!", 7),
    ]
    platforms["comments"]["youtube"] = [comment("y1", "TubeFan", "Harry Potter", 0, channel="UC1"),
                                        comment("y2", "Gamer", "Disney Villains", 59, channel="UC2")]
    out = themes.suggestions(8)
    assert [p["job_id"] for p in out["posts"]] == ["ask-1"]
    top = out["groups"][0]
    assert (top["theme"], top["count"], top["users"]) == ("Disney villains", 3, ["early_bird", "film_fan", "Gamer"])
    assert top["first"]["comment_id"] == "c1" and top["first"]["text"] == "Disney villains!"
    assert out["groups"][1]["theme"] == "Harry Potter"


def test_winner_gets_one_reply(quiz, platforms):
    spec = dict(quiz, picked_by={"user": "early_bird", "platform": "instagram", "comment_id": "c1", "text": "Disney villains!"})
    QuizSpec.model_validate(spec)
    job = {"id": "picked-1", "spec": spec, "dry_run": False, "results": {"instagram": {"ok": True, "url": "u"}}}
    themes.after_publish(job)
    themes.after_publish(job)
    assert [(p, k, c) for p, k, c, _ in platforms["calls"]] == [("instagram", "reply", "c1")]
    assert job["picked_reply"] == {"ok": True, "user": "early_bird"}


def test_late_credit_replies_and_records(quiz, platforms):
    from fastapi.testclient import TestClient

    from app import privacy, store
    from app.main import app

    posted("disney-1", quiz, hours_ago=20)
    c = TestClient(app)
    auth = {"Authorization": "Bearer test-token"}
    body = {"platform": "instagram", "comment_id": "c9", "user": "@fan_1", "text": "Disney movies", "message": "Thanks!"}
    r = c.post("/jobs/disney-1/credit", headers=auth, json=body)
    assert r.status_code == 200
    assert platforms["calls"][-1] == ("instagram", "reply", "c9", "Thanks!")
    job = store.get_job("disney-1")
    assert job["spec"]["picked_by"]["user"] == "fan_1" and job["picked_reply"]["ok"]
    privacy.opt_out("other")
    assert c.post("/jobs/disney-1/credit", headers=auth, json=dict(body, user="other")).status_code == 409
