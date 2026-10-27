"""GDPR: the public policy page, opt-outs, erasure and automatic anonymising."""
from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from app import cliffhanger as ch
from app import privacy, store
from app.config import settings
from app.main import app
from tests.helpers import comment, posted

AUTH = {"Authorization": "Bearer test-token"}


def test_policy_page_is_public_and_complete(monkeypatch):
    monkeypatch.setattr(settings, "privacy_contact_email", "privacy@example.com")
    r = TestClient(app).get("/privacy")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    page = r.text
    for must in ("privacy@example.com", "Legitimate interests", "Your rights", "ico.org.uk", "ElevenLabs",
                 "Anthropic", "90 days", 'id="deletion"', "Children"):
        assert must in page, must
    assert TestClient(app).get("/data-deletion", follow_redirects=False).headers["location"] == "/privacy#deletion"


def test_policy_without_contact_says_so(monkeypatch):
    monkeypatch.setattr(settings, "privacy_contact_email", "")
    assert "contact address not set" in privacy.policy_html()


def test_opted_out_viewers_are_never_read(quiz, platforms):
    job = posted("cliff-1", quiz, hours_ago=5)
    platforms["comments"]["instagram"] = [comment("c1", "Early_Bird", "toy story", 1), comment("c2", "fan", "toy story", 2)]
    assert TestClient(app).post("/privacy/optout", headers=AUTH, json={"user": "@early_bird"}).status_code == 200
    rows, _, _ = ch.read_comments(job)
    assert [c["user"] for c in rows] == ["fan"]  # case and @ don't matter


def test_erase_removes_a_viewer_everywhere(quiz):
    spec = copy.deepcopy(quiz)
    spec["picked_by"] = {"user": "early_bird", "platform": "instagram", "comment_id": "c9", "text": "Disney!"}
    posted("reveal-1", quiz, hours_ago=5, reveal={"winners": [{"user": "early_bird", "platform": "instagram", "comment_id": "c1"},
                                                                {"user": "TubeFan", "platform": "youtube", "comment_id": "y1"}],
                                                    "shoutouts": ["early_bird", "TubeFan"],
                                                    "replies": [{"user": "early_bird", "ok": True}]})
    posted("picked-1", spec, hours_ago=5, picked_reply={"ok": True, "user": "early_bird"})
    r = TestClient(app).post("/privacy/erase", headers=AUTH, json={"user": "Early_Bird"})
    assert r.json()["records_changed"] == 2
    rv = store.get_job("reveal-1")["reveal"]
    assert rv["shoutouts"] == ["TubeFan"] and [w["user"] for w in rv["winners"]] == ["TubeFan"] and rv["replies"] == []
    assert store.get_job("picked-1")["spec"]["picked_by"] is None
    assert privacy.is_opted_out("EARLY_BIRD")


def test_names_leave_old_records(quiz):
    posted("old", quiz, hours_ago=24 * 100, reveal={"shoutouts": ["a1"], "winners": [{"user": "a1"}]})
    posted("new", quiz, hours_ago=24 * 10, reveal={"shoutouts": ["b1"], "winners": [{"user": "b1"}]})
    assert privacy.anonymise_old() == 1
    assert store.get_job("old")["reveal"]["shoutouts"] == [] and store.get_job("new")["reveal"]["shoutouts"] == ["b1"]
    assert privacy.anonymise_old() == 0  # once
