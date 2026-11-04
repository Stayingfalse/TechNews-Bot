"""POST /colony/today with malformed input: every case is a 422 naming the field, never a 500."""
import json

import pytest
from fastapi.testclient import TestClient

from app.colony import inbox, today
from app.config import settings
from app.main import app

AUTH = {"Authorization": f"Bearer {settings.api_token}"}
DAY = "2026-12-01"  # in the future, so it's before the cut-off whenever the tests run
GOOD_BEATS = [{"type": "slot", "slot": "arrivals"}, {"type": "say", "who": "MAREN", "text": "WELCOME.", "secs": 2.5}]


@pytest.fixture
def c():
    return TestClient(app, raise_server_exceptions=False)


def post(c, body, day=DAY):
    return c.post(f"/colony/today?date={day}", headers=AUTH, content=json.dumps(body),
                  )


def problems(r):
    assert r.status_code == 422, (r.status_code, r.text)
    return r.json()["detail"]["problems"]


@pytest.mark.parametrize("body, field", [
    ({"beats": ["x"]}, "beats[0]: must be an object"),
    ({"beats": [{"type": "slot", "slot": "people"}], "caption": "x", "replies": {"1": 2}}, "replies"),
    ({"beats": "arrivals", "caption": "x"}, "beats: a list"),
    ({"beats": None, "caption": "x"}, "beats"),
    ({"beats": [{"type": 3}], "caption": "x"}, "beats[0].type"),
    ({"beats": [{"type": "say", "who": "MAREN", "text": "HI", "secs": "two"}], "caption": "x"}, "beats[0].secs"),
    ({"beats": [{"type": "caption", "lines": "HELLO"}], "caption": "x"}, "beats[0].lines"),
    ({"beats": [{"type": "decision", "who": "MAREN", "lines": ["A?"], "choices": "A or B"}], "caption": "x"}, "beats[0].choices"),
    ({"beats": GOOD_BEATS, "caption": 5}, "caption: a string"),
    ({"beats": GOOD_BEATS, "caption": "x", "summary": ["a"]}, "summary: a string"),
    ({"beats": GOOD_BEATS, "caption": "x", "date": 20261201}, "date"),
    ({"beats": GOOD_BEATS, "caption": "x", "date": "tomorrow"}, "date"),
    ({"beats": GOOD_BEATS, "caption": "x", "settlers": "everyone"}, "settlers: an object"),
    ({"beats": GOOD_BEATS, "caption": "x", "settlers": {"@nova.k": "pirate"}}, "settlers.@nova.k"),
    ({"beats": GOOD_BEATS, "caption": "x", "settlers": {"@nova.k": {"look": "pirate"}}}, "settlers.@nova.k.look"),
    ({"beats": GOOD_BEATS, "caption": "x", "settlers": {"@nova.k": {"traits": "grumpy"}}}, "settlers.@nova.k.traits"),
    ({"beats": GOOD_BEATS, "caption": "x", "replies": "thanks all"}, "replies: a list"),
    ({"beats": GOOD_BEATS, "caption": "x", "replies": [None, "x", {"comment_id": "1"}]}, "replies[0]"),
    ({"beats": GOOD_BEATS, "caption": "x", "parts": {"slot": "pet"}}, "parts: a list"),
    ({"beats": GOOD_BEATS, "caption": "x", "parts": ["dragon"]}, "parts[0]: an object"),
    ({"beats": GOOD_BEATS, "caption": "x", "parts": [{"slot": "pet", "id": "dragon", "rows": "gg", "colors": []}]}, "parts[0].rows"),
    ({"beats": GOOD_BEATS, "caption": "x", "wanted": "a dragon"}, "wanted: a list"),
    ({"beats": GOOD_BEATS, "caption": "x", "wanted": [1, 2]}, "wanted"),
])
def test_wrong_types_are_a_422_naming_the_field(c, body, field):
    probs = problems(post(c, body))
    assert any(field in p for p in probs), probs


@pytest.mark.parametrize("body", [["beats"], "an episode", 42, None])
def test_a_body_that_isnt_an_object_is_a_422(c, body):
    probs = problems(post(c, body))
    assert any("JSON object" in p for p in probs)


def test_every_problem_comes_back_at_once(c):
    probs = problems(post(c, {"beats": ["x", {"type": "nope"}], "caption": 5, "replies": "hi", "wanted": "x"}))
    for field in ("beats[0]", "beats[1]", "caption", "replies", "wanted"):
        assert any(p.startswith(field) for p in probs), (field, probs)


def test_nothing_is_kept_when_there_are_problems(c):
    post(c, {"beats": ["x"]})
    assert today.adapted(__import__("datetime").date.fromisoformat(DAY)) is None


def test_an_unforeseen_error_while_checking_is_a_422_not_a_500(c, monkeypatch):
    def boom(*a, **k):
        raise KeyError("something")

    monkeypatch.setattr(today.plan, "check_episode", boom)
    probs = problems(post(c, {"beats": GOOD_BEATS, "caption": "x"}))
    assert "couldn't be checked" in probs[0]


def test_a_full_valid_episode_is_accepted_and_replies_in_object_form_are_converted(c):
    inbox.add([{"id": "18118414847047149", "user": "wolf.fan", "uid": "1", "text": "can I have a wolf",
                "at": "2026-11-30T19:30:00+00:00", "platform": "instagram"}])  # after the 30th's cut-off
    body = {"date": DAY, "summary": "A wolf joins the colony.", "caption": "A wolf moved in tonight.",
            "beats": GOOD_BEATS + [{"type": "feature", "who": "@wolf.fan", "lines": ["*@WOLF.FAN*", "GOT A *WOLF*"]}],
            "settlers": {"@wolf.fan": {"look": {"pet": "dog"}, "traits": ["wolf friend"], "sheet": "Asked for a wolf."}},
            "replies": {"18118414847047149": "Meet your wolf."}, "wanted": ["a real wolf"]}
    r = post(c, body)
    assert r.status_code == 200, r.text
    assert any("converted" in n for n in r.json()["notes"])
    kept = today.adapted(__import__("datetime").date.fromisoformat(DAY))
    assert kept["replies"] == [{"comment_id": "18118414847047149", "text": "Meet your wolf."}]


def test_the_week_endpoint_is_hardened_too(c):
    for body in (["x"], {"week_start": "2026-12-07", "episodes": "seven", "spares": ["a", "b"]},
                 {"week_start": "2026-12-07", "episodes": ["x"] * 7, "spares": [None, None]}):
        r = c.post("/colony/week", headers=AUTH, content=json.dumps(body))
        assert r.status_code == 422, (body, r.text)
        assert r.json()["detail"]["problems"]
