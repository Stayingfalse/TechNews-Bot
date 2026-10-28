"""Reconnecting accounts from the dashboard: the Accounts card's data, and the reconnect guards."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import store
from app.config import settings
from app.main import SESSION_COOKIE, app, make_session
from app.publish import instagram, youtube

ACCOUNTS = {"111": "mediaquiz.daily", "222": "dungeoncrawlergram", "333": "sixelspeedway", "999": "someone.else"}


@pytest.fixture
def signed_in():
    c = TestClient(app)
    c.cookies.set(SESSION_COOKIE, make_session("instagram"))
    return c


@pytest.fixture
def ig(monkeypatch):
    """The three channels on Instagram (111, 222, 333); approving saves whichever account `who` names."""
    monkeypatch.setattr(settings, "instagram_app_id", "app")
    monkeypatch.setattr(settings, "instagram_app_secret", "secret")
    monkeypatch.setattr(settings, "youtube_client_id", "")  # YouTube not set up in these tests
    for ch, uid in (("main", "111"), ("adventure", "222"), ("racing", "333")):
        store.set_tokens("instagram", {"access_token": f"tok-{uid}", "user_id": uid, "expires_at": 9e9,
                                       "permissions": instagram.SCOPES.split(",")}, channel=ch)
    who = {"id": "111"}
    monkeypatch.setattr(instagram, "exchange_code", lambda code: store.set_tokens("instagram", {
        "access_token": f"new-{who['id']}", "user_id": who["id"], "expires_at": 9e9, "permissions": instagram.SCOPES.split(",")}))
    broken = set()

    def account():
        tok = store.get_tokens("instagram")
        if tok["access_token"] in broken:
            raise RuntimeError("Error validating access token: The session has been invalidated")
        return {"username": ACCOUNTS[tok["user_id"]]}

    monkeypatch.setattr(instagram, "account", account)
    return {"who": who, "broken": broken}


def _reconnect(client, channel="main", extra=""):
    q = "" if channel == "main" else f"?channel={channel}"
    q += ("&" if q else "?") + extra if extra else ""
    r = client.get(f"/oauth/instagram/start{q}", follow_redirects=False)
    assert r.status_code == 307, r.text
    assert "force_reauth=true" in r.headers["location"]  # Instagram asks which account
    state = r.headers["location"].split("state=")[1].split("&")[0]
    return client.get(f"/oauth/instagram/callback?code=abc&state={state}", follow_redirects=False)


def test_accounts_card_shows_each_channels_state(signed_in, ig):
    ig["broken"].add("tok-111")
    r = signed_in.get("/connections")
    assert r.status_code == 200  # the sign-in cookie is enough
    rows = {(a["channel"], a["platform"]): a for a in r.json()["accounts"]}
    assert rows[("main", "instagram")]["state"] == "broken" and "invalidated" in rows[("main", "instagram")]["detail"]
    assert rows[("main", "instagram")]["reconnect_url"] == "/oauth/instagram/start"
    assert rows[("racing", "instagram")]["state"] == "ok"
    assert rows[("racing", "instagram")]["account"] == "sixelspeedway"
    assert rows[("adventure", "instagram")]["reconnect_url"] == "/oauth/instagram/start?channel=adventure"
    assert rows[("main", "youtube")]["state"] == "not_configured"


def test_reconnecting_from_the_dashboard_needs_no_token_and_goes_back_there(signed_in, ig, discord):
    ig["broken"].add("tok-111")
    r = _reconnect(signed_in)
    assert r.status_code == 303 and r.headers["location"].startswith("/dashboard?connected=instagram&channel=main")
    assert store.get_tokens("instagram", channel="main")["access_token"] == "new-111"
    assert "connected as @mediaquiz.daily" in discord[-1][0]


def test_another_channels_account_is_refused(signed_in, ig):
    ig["who"]["id"] = "333"  # the browser was on the racing account
    r = _reconnect(signed_in)
    assert r.status_code == 409 and "Sixel Speedway" in r.text
    assert store.get_tokens("instagram", channel="main")["access_token"] == "tok-111"  # put back


def test_a_different_account_needs_switch(signed_in, ig):
    ig["who"]["id"] = "999"
    r = _reconnect(signed_in, "adventure")
    assert r.status_code == 409 and "switch=true" in r.text
    assert store.get_tokens("instagram", channel="adventure")["user_id"] == "222"
    r = _reconnect(signed_in, "adventure", "switch=true")
    assert r.status_code == 303 and store.get_tokens("instagram", channel="adventure")["user_id"] == "999"


def test_reconnect_without_sign_in_needs_the_token(ig):
    c = TestClient(app)
    assert c.get("/oauth/instagram/start", follow_redirects=False).status_code == 401
    assert c.get("/connections").status_code == 401


def test_youtube_account_is_checked_too(monkeypatch):
    monkeypatch.setattr(settings, "youtube_client_id", "id")
    monkeypatch.setattr(settings, "youtube_client_secret", "s")
    monkeypatch.setattr(settings, "instagram_app_id", "")
    store.set_tokens("youtube", {"access_token": "a", "refresh_token": "r", "expires_at": 9e9,
                                 "scope": youtube.SCOPES})

    def gone():
        raise RuntimeError("Google token error: invalid_grant")

    monkeypatch.setattr(youtube, "account", gone)
    from app import connections

    rows = {(a["channel"], a["platform"]): a for a in connections.report()}
    assert rows[("main", "youtube")]["state"] == "broken" and "invalid_grant" in rows[("main", "youtube")]["detail"]


def test_any_channels_account_can_sign_in(ig, monkeypatch):
    monkeypatch.setattr(instagram, "login_identity", lambda code: "333")  # the browser was on the racing account
    c = TestClient(app)
    r = c.get("/login/instagram", follow_redirects=False)
    state = r.headers["location"].split("state=")[1].split("&")[0]
    r = c.get(f"/oauth/instagram/callback?code=abc&state={state}", follow_redirects=False)
    assert r.status_code == 307 and SESSION_COOKIE in r.headers.get("set-cookie", "")
    monkeypatch.setattr(instagram, "login_identity", lambda code: "999")  # nobody's
    r = c.get("/login/instagram", follow_redirects=False)
    state = r.headers["location"].split("state=")[1].split("&")[0]
    assert TestClient(app).get(f"/oauth/instagram/callback?code=abc&state={state}").status_code == 403
