"""GDPR: the public policy and terms pages, opt-outs, erasure, self-service requests and Meta callbacks."""
from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from app import cliffhanger as ch
from app import legal, privacy, store
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
                 "Anthropic", "90 days", 'id="deletion"', "Children", "YouTube API Services",
                 "policies.google.com/privacy", "how-we-use-comments.mp4", "/privacy/request", "/terms"):
        assert must in page, must
    assert TestClient(app).get("/data-deletion", follow_redirects=False).headers["location"] == "/privacy#deletion"


def test_policy_without_contact_says_so(monkeypatch):
    monkeypatch.setattr(settings, "privacy_contact_email", "")
    assert "contact address not set" in legal.privacy_page()
    assert "$" not in legal.privacy_page().split("<body", 1)[1]  # every placeholder filled


def test_terms_page_and_video_are_public():
    c = TestClient(app)
    r = c.get("/terms")
    assert r.status_code == 200 and "Terms of service" in r.text and "England and Wales" in r.text
    assert "$" not in r.text.split("<body", 1)[1]
    v = c.get("/privacy/how-we-use-comments.mp4")
    assert v.status_code == 200 and v.headers["content-type"] == "video/mp4"


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


def test_request_form_opts_out_and_gives_a_status_code(quiz):
    posted("reveal-1", quiz, hours_ago=5, reveal={"shoutouts": ["Quiz_Fan"], "winners": [{"user": "Quiz_Fan"}]})
    c = TestClient(app)
    assert "<form" in c.get("/privacy/request").text
    r = c.post("/privacy/request", data={"user": " @Quiz_Fan", "platform": "instagram", "kind": "delete"}, follow_redirects=False)
    assert r.status_code == 303
    code = r.headers["location"].rsplit("/", 1)[1]
    assert privacy.is_opted_out("quiz_fan") and store.get_job("reveal-1")["reveal"]["shoutouts"] == []
    page = c.get(f"/privacy/status/{code}").text
    assert "completed" in page and "@quiz_fan" in page and "removed from 1 stored record" in page
    assert "completed" in c.get(f"/privacy/status?code={code.lower()}").text
    assert "no request" in c.get("/privacy/status/NOPE").text


def test_request_form_rejects_junk_and_floods(monkeypatch):
    monkeypatch.setattr("app.main._request_times", {})
    c = TestClient(app)
    assert c.post("/privacy/request", data={"user": "<script>", "platform": "instagram", "kind": "delete"}).status_code == 400
    assert c.post("/privacy/request", data={"user": "a", "platform": "tiktok", "kind": "delete"}).status_code == 400
    assert privacy.opted_out() == set()
    codes = [c.post("/privacy/request", data={"user": f"u{i}", "platform": "youtube", "kind": "opt-out"},
                    follow_redirects=False).status_code for i in range(10)]
    assert codes == [303] * 8 + [429, 429]  # 10 an hour, the two junk ones included


def test_optout_comments_are_honoured_once(quiz, platforms):
    posted("cliff-1", quiz, hours_ago=5)
    platforms["comments"]["instagram"] = [comment("c1", "Shy_One", "#optout please", 1), comment("c2", "fan", "toy story", 2),
                                          comment("c3", "other", "Opt-out", 3)]
    assert legal.scan_comment_optouts() == 2
    assert privacy.opted_out() == {"shy_one", "other"}
    assert legal.scan_comment_optouts() == 0


def _signed(payload: dict, secret: str) -> str:
    enc = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")  # noqa: E731
    body = enc(json.dumps(payload).encode())
    return enc(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()) + "." + body


def test_meta_deletion_callback(monkeypatch):
    monkeypatch.setattr(settings, "instagram_app_secret", "s3cret")
    store._write("tokens.json", {"instagram": {"user_id": "1784"}, "youtube": {"refresh_token": "x"}})
    c = TestClient(app)
    good = _signed({"algorithm": "HMAC-SHA256", "user_id": "1784", "issued_at": 1}, "s3cret")
    r = c.post("/privacy/meta/deletion", data={"signed_request": good})
    assert r.status_code == 200
    body = r.json()
    assert body["url"].endswith(f"/privacy/status/{body['confirmation_code']}")
    assert set(store._read("tokens.json", {})) == {"youtube"}
    assert "completed" in c.get(f"/privacy/status/{body['confirmation_code']}").text

    forged = _signed({"algorithm": "HMAC-SHA256", "user_id": "1784"}, "wrong")
    assert c.post("/privacy/meta/deletion", data={"signed_request": forged}).status_code == 400
    assert c.post("/privacy/meta/deletion", data={"signed_request": "junk"}).status_code == 400
    assert c.post("/privacy/meta/deauthorize", data={"signed_request": good}).json() == {"ok": True}
