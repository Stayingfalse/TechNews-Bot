"""The HTTP API the routines and the dashboard use."""
from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def client():
    return TestClient(app)  # no "with": the background threads don't start


def future(days=3):
    return (date.today() + timedelta(days=days)).isoformat()


def item(quiz, day, quiz_id, **spec_changes):
    spec = copy.deepcopy(quiz)
    spec.update(id=quiz_id, **spec_changes)
    return {"date": day, "spec": spec}


def test_needs_the_token(client):
    assert client.get("/health").status_code == 200
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_status_and_schema(client):
    st = client.get("/status", headers=AUTH).json()
    assert {"voices", "voice_enabled", "instagram_carousels", "scheduled"} <= set(st)
    props = client.get("/schema", headers=AUTH).json()["properties"]
    assert {"intro", "voice", "voice_name", "ask_theme", "picked_by"} <= set(props)


def test_book_a_week(client, quiz):
    r = client.post("/schedule", headers=AUTH, json={"items": [item(quiz, future(3), "a-quiz")]})
    assert r.status_code == 202, r.text
    view = client.get("/schedule?days=7", headers=AUTH).json()
    assert future(3) not in view["free_dates"]
    day = next(s for s in view["slots"] if s["date"] == future(3))
    assert day["bookings"][0]["status"] == "booked"


def test_booking_rejects_problems_all_at_once(client, quiz):
    store.add_history({"date": "2026-10-01T11:00:00+00:00", "answers": ["lion king"], "job_id": "old"})
    batch = {"items": [item(quiz, future(4), "repeat-quiz"),  # the Lion King was used recently
                       item(quiz, future(5), "bad-voice", voice=True, voice_name="bob"),
                       item(quiz, future(5), "same-slot")]}  # two quizzes in one slot
    r = client.post("/schedule", headers=AUTH, json=batch)
    assert r.status_code == 409
    errors = " | ".join(r.json()["detail"]["errors"])
    assert "lion king" in errors and "voice_name 'bob'" in errors and "more than once" in errors
    assert store.list_jobs() == []  # all or nothing


def test_spec_rules(client, quiz):
    bad = copy.deepcopy(quiz)
    bad["rounds"][0]["cliffhanger"] = True  # only the last round may be the cliffhanger
    r = client.post("/schedule", headers=AUTH, json={"items": [{"date": future(), "spec": bad}]})
    assert r.status_code == 422


def test_move_and_cancel(client, quiz):
    client.post("/schedule", headers=AUTH, json={"items": [item(quiz, future(3), "movable")]})
    job_id = store.list_jobs()[0]["id"]
    r = client.patch(f"/schedule/job/{job_id}", headers=AUTH, json={"date": future(6)})
    assert r.status_code == 200 and r.json()["date"] == future(6)
    assert client.delete(f"/schedule/{future(6)}", headers=AUTH).status_code == 200
    assert store.get_job(job_id)["status"] == "cancelled"


def test_avatars(client):
    out = client.get("/avatars", headers=AUTH).json()
    assert "avatar-emoji.png" in out["pictures"] and out["every_weeks"] >= 0
