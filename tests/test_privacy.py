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
                 "policies.google.com/privacy", "how-we-use-comments.mp4", "how-we-use-votes.mp4", "/privacy/request", "/terms",
                 "@dungeoncrawlergram", "Story videos: votes", "One opt-out covers every account we run", "any account we add later"):
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
    assert "Story votes" in r.text and "@dungeoncrawlergram" in r.text
    for name in ("how-we-use-comments", "how-we-use-votes"):
        v = c.get(f"/privacy/{name}.mp4")
        assert v.status_code == 200 and v.headers["content-type"] == "video/mp4"
    assert c.get("/privacy/secrets.mp4").status_code == 404


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


def test_request_form_gives_a_code_and_deletes_once_confirmed(quiz, platforms):
    posted("reveal-1", quiz, hours_ago=5, reveal={"shoutouts": ["Quiz_Fan"], "winners": [{"user": "Quiz_Fan"}]})
    c = TestClient(app)
    assert "<form" in c.get("/privacy/request").text
    r = c.post("/privacy/request", data={"user": " @Quiz_Fan", "platform": "instagram", "kind": "delete"}, follow_redirects=False)
    assert r.status_code == 303
    code = r.headers["location"].rsplit("/", 1)[1]
    assert not privacy.is_opted_out("quiz_fan")  # not until they confirm
    platforms["comments"]["instagram"] = [_later("c9", "quiz_fan", code)]
    assert legal.scan_confirmations() == 1
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


def test_one_optout_covers_the_dungeon_crawl_too(monkeypatch):
    """An opt-out made on either channel drops that viewer's votes on the adventure, and "#optout" under an
    adventure episode opts them out of the quiz too."""
    from app.adventure import jobs as adv
    from app.publish import instagram

    monkeypatch.setattr(instagram, "own_name", lambda: "dungeoncrawlergram")
    rows = [{"id": "a1", "user": "Quiz_Fan", "text": "B", "at": "1"}, {"id": "a2", "user": "goblin", "text": "C", "at": "2"},
            {"id": "a3", "user": "Shy_Bard", "text": "#optout", "at": "3"}]
    monkeypatch.setattr(instagram, "comments", lambda media, limit=200: rows)
    adv.save({"id": "ep1", "channel": "adventure", "status": "done", "published_at": store.now_iso(),
              "results": {"instagram": {"ok": True, "media_id": "m1"}}})
    assert legal.scan_comment_optouts() == 1 and privacy.is_opted_out("shy_bard")

    privacy.opt_out("@quiz_fan")  # e.g. via the form, naming the quiz
    t = adv.votes.tally([c for c in rows if privacy._key(c["user"]) not in privacy.opted_out()], ["x", "y", "z"])
    assert t["counts"] == [0, 0, 1]


def test_home_page_lists_every_accounts_public_videos(quiz):
    from app.adventure import jobs as adv

    posted("q1", quiz, hours_ago=30)
    posted("q2", dict(quiz, title="Only *real* fans"), hours_ago=5,
           results={"instagram": {"ok": True, "url": "https://instagram.com/reel/q2"},
                    "youtube": {"ok": True, "url": "https://youtube.com/shorts/hidden", "privacy": "unlisted"}})
    posted("q3", quiz, hours_ago=2, dry_run=True)
    adv.save({"id": "ep1", "channel": "adventure", "status": "done", "published_at": store.now_iso(), "spec": {"kind": "episode0", "part": 2},
              "results": {"instagram": {"ok": True, "media_id": "m1", "url": "https://instagram.com/reel/ep1"}}})
    page = TestClient(app).get("/").text
    for must in ("Daily quiz", "Dungeon crawl", "instagram.com/reel/q1", "youtube.com/shorts/q1", "Only real fans",
                 "instagram.com/reel/ep1", "Episode 0, part 2", "instagram.com/dungeoncrawlergram/", "/privacy\"", "/terms\""):
        assert must in page, must
    assert "hidden" not in page and "reel/q3" not in page  # unlisted and test posts stay off
    assert page.index("reel/q2") < page.index("reel/q1")  # newest first


def test_comments_check_compares_readable_with_reported(quiz, monkeypatch):
    from app.publish import instagram

    posted("q1", quiz, hours_ago=5)
    monkeypatch.setattr(instagram, "_get", lambda path, fields: {"comments_count": 3})
    monkeypatch.setattr(instagram, "comments", lambda media, limit=200: [{"id": "1", "user": "fan", "text": "hi", "at": "1"}])
    monkeypatch.setattr(instagram, "own_name", lambda: "mediaquiz.daily")
    r = TestClient(app).get("/comments/check", headers=AUTH).json()
    assert r["main"] == [{"job_id": "q1", "title": quiz["title"], "reported": 3, "readable": 1, "from_viewers": 1}]
    assert TestClient(app).get("/comments/check").status_code == 401


def test_instagram_commenters_named_from_the_from_field(monkeypatch):
    """Instagram can leave `username` empty on viewers' comments; the name and id come from `from`."""
    from app.adventure import votes
    from app.publish import instagram

    store.set_tokens("instagram", {"access_token": "t", "user_id": "1"})
    data = {"data": [{"id": "c1", "text": "B", "timestamp": "1", "from": {"id": "111", "username": "goblin_fan"}},
                     {"id": "c2", "text": "b!", "timestamp": "2", "from": {"id": "111"}},
                     {"id": "c3", "text": "C", "timestamp": "3", "from": {"id": "222"}},
                     {"id": "c4", "text": "A", "timestamp": "4", "username": "named"}]}
    monkeypatch.setattr(instagram.httpx, "get", lambda *a, **k: type("R", (), {"status_code": 200, "json": lambda self: data})())
    rows = instagram.comments("m1")
    assert [(c["user"], c["uid"]) for c in rows] == [("goblin_fan", "111"), ("", "111"), ("", "222"), ("named", "")]
    t = votes.tally([dict(r, user="") if r["id"] == "c1" else r for r in rows], ["a", "b", "c"])
    assert t["counts"] == [1, 1, 1]  # c1/c2 are one person (by id): their first vote counts


# ------------------------------------------------------------------ form requests need the account to confirm


def _later(cid: str, user: str, text: str) -> dict:
    """A comment posted just now (after the request)."""
    from datetime import datetime, timedelta, timezone

    at = (datetime.now(timezone.utc) + timedelta(seconds=5)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    return {"id": cid, "user": user, "text": text, "at": at}


def _form(client, user="@Racer_One", kind="delete", platform="instagram"):
    r = client.post("/privacy/request", data={"user": user, "platform": platform, "kind": kind}, follow_redirects=False)
    assert r.status_code == 303, r.text
    return r.headers["location"].rsplit("/", 1)[1]


def test_the_form_changes_nothing_until_that_account_comments_the_code(quiz, platforms, discord):
    from app.racing import ledger

    ledger._write("players.json", {"instagram:racer_one": {"pid": "instagram:racer_one", "name": "racer_one", "balance": 5000}})
    posted("q1", quiz, hours_ago=30)
    c = TestClient(app)
    code = _form(c)  # a rival types the leader's name
    assert len(code) == 6 and ledger.player("instagram:racer_one")["balance"] == 5000
    assert not privacy.is_opted_out("racer_one")
    page = c.get(f"/privacy/status/{code}").text
    assert "One more step" in page and code in page and "@racer_one" in page and "$" not in page.split("<body", 1)[1]
    assert "instagram.com/mediaquiz.daily/" in page or "instagram.com/" in page

    # the code from someone else's account, or on the wrong platform, doesn't count
    platforms["comments"]["instagram"] = [_later("c1", "rival", f"{code}")]
    platforms["comments"]["youtube"] = [_later("c2", "racer_one", f"{code}")]
    assert legal.scan_confirmations() == 0 and ledger.player("instagram:racer_one")
    # from the named account it does (case and @ don't matter)
    platforms["comments"]["instagram"].append(_later("c3", "Racer_One", f"confirm {code.lower()} thanks"))
    assert legal.scan_confirmations() == 1
    assert ledger.player("instagram:racer_one") is None and privacy.is_opted_out("racer_one")
    assert "completed" in c.get(f"/privacy/status/{code}").text and "confirmed" in discord[-1][0]
    assert legal.scan_confirmations() == 0  # done once


def test_an_opted_out_viewer_can_still_confirm_a_deletion(quiz, platforms):
    posted("q1", quiz, hours_ago=3)
    privacy.opt_out("shy_one")
    code = _form(TestClient(app), user="shy_one")
    platforms["comments"]["instagram"] = [_later("c1", "shy_one", code)]
    assert legal.scan_confirmations() == 1 and legal.lookup(code)["status"] == "completed"


def test_unconfirmed_requests_lapse(quiz, platforms):
    code = _form(TestClient(app), kind="opt-out")
    log = store._read("privacy_requests.json", {})
    log[code]["expires"] = "2000-01-01T00:00:00+00:00"
    store._write("privacy_requests.json", log)
    legal.scan_confirmations()
    assert legal.lookup(code)["status"] == "expired" and not privacy.is_opted_out("racer_one")
    assert "lapsed" not in TestClient(app).get(f"/privacy/status/{code}").text  # says expired, nothing changed
    assert "Nothing was changed" in TestClient(app).get(f"/privacy/status/{code}").text


def test_the_owner_can_approve_or_reject_from_the_dashboard():
    from app.main import SESSION_COOKIE, make_session

    c = TestClient(app)
    yes, no = _form(c, user="emailed_us"), _form(c, user="someone_else")
    assert {r["code"] for r in c.get("/privacy/requests", headers=AUTH).json()} == {yes, no}
    assert c.get("/privacy/requests").status_code == 401  # not public
    owner = TestClient(app)
    owner.cookies.set(SESSION_COOKIE, make_session("instagram"))
    assert owner.post(f"/privacy/requests/{yes}/approve").status_code == 401  # needs the dashboard's header too
    assert owner.post(f"/privacy/requests/{yes}/approve", headers={"X-Quizbot": "1"}).json()["status"] == "completed"
    assert owner.post(f"/privacy/requests/{no}/reject", headers={"X-Quizbot": "1"}).json()["status"] == "rejected"
    assert privacy.opted_out() == {"emailed_us"}
    assert owner.post(f"/privacy/requests/{no}/approve", headers={"X-Quizbot": "1"}).status_code == 404  # not waiting
