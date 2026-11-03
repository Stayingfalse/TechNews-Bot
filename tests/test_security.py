"""The server's own defences: the API token, the sign-in cookie and what it may change, OAuth state,
the sign-in redirect, and music uploads."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app import main, store
from app.config import settings
from app.main import SESSION_COOKIE, app, make_session

AUTH = {"Authorization": "Bearer test-token"}
DASH = {"X-Quizbot": "1"}


@pytest.fixture
def client():
    return TestClient(app)


def signed_in(cookie: str | None = None) -> TestClient:
    c = TestClient(app)
    c.cookies.set(SESSION_COOKIE, cookie or make_session("instagram"))
    return c


# ------------------------------------------------------------------ the API token and the cookie


def test_server_refuses_to_start_without_a_token(monkeypatch):
    monkeypatch.setattr(settings, "api_token", "")
    with pytest.raises(RuntimeError, match="API_TOKEN"):
        with TestClient(app):
            pass


def test_token_works_as_header_or_query_and_nothing_else_does(client):
    assert client.get("/status?token=test-token").status_code == 200
    for bad in ({"Authorization": "test-token-and-more"}, {"Authorization": "Bearer "}, {"Authorization": "Basic test-token"}):
        assert client.get("/status", headers=bad).status_code == 401, bad
    assert client.get("/status?token=").status_code == 401


def test_a_forged_or_expired_cookie_is_refused():
    assert signed_in().get("/status").status_code == 200
    provider, expiry, sig = make_session("instagram").split("|")
    later = str(int(expiry) + 86400 * 365)
    assert signed_in(f"{provider}|{later}|{sig}").get("/status").status_code == 401  # extended expiry, old signature
    assert signed_in(f"{provider}|{expiry}|{'0' * len(sig)}").get("/status").status_code == 401
    past = f"instagram|{int(time.time()) - 1}"
    assert signed_in(f"{past}|{main._sign(past)}").get("/status").status_code == 401  # correctly signed, but expired
    assert signed_in("garbage").get("/status").status_code == 401
    assert signed_in("a|b|c|d").get("/status").status_code == 401


def test_the_cookie_can_only_make_dashboard_changes_and_only_with_the_header(quiz):
    c = signed_in()
    # changes the dashboard makes: refused without the header (a cross-site form can't add it)
    assert c.patch("/schedule/job/nope", json={}).status_code == 401
    assert c.patch("/schedule/job/nope", json={}, headers=DASH).status_code == 404  # past auth: no such booking
    assert c.delete("/schedule/2030-01-01", headers=DASH).status_code != 401
    # everything else needs the API token, header or not
    for method, path, body in (("post", "/schedule", {"items": [{"date": "2030-01-01", "spec": quiz}]}),
                               ("post", "/jobs", quiz), ("post", "/privacy/erase", {"user": "x"}),
                               ("post", "/privacy/optout", {"user": "x"}), ("post", "/racing/start", {}),
                               ("post", "/adventure/arc", {}), ("post", "/avatars/next", None)):
        r = getattr(c, method)(path, json=body, headers=DASH)
        assert r.status_code == 401, (path, r.status_code)
    assert c.put("/music/x.mp3", content=b"x", headers=DASH).status_code == 401
    assert c.delete("/music/x.mp3", headers=DASH).status_code == 401
    assert store.list_jobs() == []


def test_the_dashboard_page_needs_signing_in(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code in (303, 307) and r.headers["location"].startswith("/login")


# ------------------------------------------------------------------ OAuth state


@pytest.fixture
def ig_app(monkeypatch):
    monkeypatch.setattr(settings, "instagram_app_id", "app")
    monkeypatch.setattr(settings, "instagram_app_secret", "secret")
    monkeypatch.setattr(main, "_states", {})


def _state(client) -> str:
    r = client.get("/oauth/instagram/start", headers=AUTH, follow_redirects=False)
    assert r.status_code == 307
    return r.headers["location"].split("state=")[1].split("&")[0]


def test_oauth_callback_needs_a_live_state_for_that_provider_and_uses_it_once(client, ig_app, monkeypatch):
    from app.publish import instagram

    exchanged = []
    monkeypatch.setattr(instagram, "exchange_code", lambda code: exchanged.append(code))
    assert client.get("/oauth/instagram/callback?code=abc&state=made-up").status_code == 400
    assert client.get("/oauth/instagram/callback?code=abc").status_code == 400

    s = _state(client)
    assert client.get(f"/oauth/youtube/callback?code=abc&state={s}").status_code == 400  # another provider's callback
    assert client.get(f"/oauth/instagram/callback?code=abc&state={s}").status_code == 400  # and it's spent

    s = _state(client)
    assert client.get(f"/oauth/instagram/callback?error=access_denied&state={s}").status_code == 400
    assert client.get(f"/oauth/instagram/callback?code=abc&state={s}").status_code == 400  # no second go

    s = _state(client)
    main._states[s] = (main._states[s][0], time.time() - 1, *main._states[s][2:])  # ten minutes passed
    assert client.get(f"/oauth/instagram/callback?code=abc&state={s}").status_code == 400
    assert exchanged == []  # no code was ever exchanged


def test_unconnected_or_unknown_providers_have_no_sign_in(client, ig_app):
    assert client.get("/login/instagram", follow_redirects=False).status_code == 404  # nothing connected yet
    assert client.get("/login/tiktok", follow_redirects=False).status_code == 404
    assert client.get("/oauth/tiktok/start", headers=AUTH, follow_redirects=False).status_code == 404


@pytest.mark.parametrize("nxt", ["//evil.example", "https://evil.example", "/\\evil.example", "/\\/evil.example",
                                 "/%2F%2Fevil.example", "javascript:alert(1)", "/\t/evil.example"])
def test_sign_in_never_redirects_off_site(client, ig_app, monkeypatch, nxt):
    from app.publish import instagram

    store.set_tokens("instagram", {"access_token": "t", "user_id": "111", "expires_at": 9e9})
    monkeypatch.setattr(instagram, "connected_identity", lambda: "111")
    monkeypatch.setattr(instagram, "login_identity", lambda code: "111")
    r = client.get("/login/instagram", params={"next": nxt}, follow_redirects=False)
    state = r.headers["location"].split("state=")[1].split("&")[0]
    r = client.get(f"/oauth/instagram/callback?code=abc&state={state}", follow_redirects=False)
    assert SESSION_COOKIE in r.headers.get("set-cookie", "")
    where = r.headers["location"]
    # browsers read "//host", "/\host" and "\\host" as another site; whatever comes back must be a plain path here
    assert where.startswith("/") and where[1:2] not in ("/", "\\") and "\\" not in where and "\t" not in where, where
    page = signed_in().get("/login", params={"next": nxt}, follow_redirects=False).headers["location"]
    assert page.startswith("/") and page[1:2] not in ("/", "\\") and "\\" not in page and "\t" not in page, page


# ------------------------------------------------------------------ music uploads


@pytest.mark.parametrize("name", ["..%2Fescape.mp3", "%2E%2E%2Fescape.mp3", ".hidden.mp3", "track.exe", "track",
                                  "track.mp3.sh", "a" * 120 + ".mp3", "%00.mp3"])
def test_music_upload_rejects_unsafe_names(client, name):
    r = client.put(f"/music/{name}", content=b"ID3data", headers=AUTH)
    assert r.status_code in (400, 404, 405), (name, r.status_code)
    assert not (settings.data_dir / "escape.mp3").exists()
    assert not settings.music_dir.exists() or not any(settings.music_dir.iterdir())


def test_music_upload_size_limits_and_round_trip(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_TRACK", 10)
    assert client.put("/music/big.mp3", content=b"x" * 11, headers=AUTH).status_code == 413
    assert client.put("/music/empty.mp3", content=b"", headers=AUTH).status_code == 400
    assert not any(settings.music_dir.iterdir())  # no partial files left behind
    assert client.put("/music/My Theme (v2).mp3", content=b"ID3", headers=AUTH).status_code == 201
    rows = {r["name"]: r for r in client.get("/music", headers=AUTH).json()}
    assert rows["My Theme (v2).mp3"] == {"name": "My Theme (v2).mp3", "bytes": 3, "source": "uploaded"}
    assert client.delete("/music/My Theme (v2).mp3", headers=AUTH).status_code == 200
    assert client.delete("/music/My Theme (v2).mp3", headers=AUTH).status_code == 404
    assert client.delete("/music/..%2F..%2Fdata.json", headers=AUTH).status_code in (404, 405)
