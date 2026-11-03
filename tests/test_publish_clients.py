"""The platform clients' own logic, with HTTP faked at the httpx level: token exchange and refresh, and
errors that never carry a token or secret. Also Discord: never pings, never breaks the pipeline."""
from __future__ import annotations

import json
import logging
import time

import httpx
import pytest

from app import notify, store
from app.config import settings
from app.publish import instagram, youtube

REAL_SEND = notify.send  # taken at import, before conftest silences notify.send for each test
SECRET, TOKEN, REFRESH = "app-secret-xyz", "IGQ-live-token", "1//refresh-abc"


class Net:
    """Answers httpx.get/post from a list of (method, url-fragment) -> (status, json) rules; records calls."""

    def __init__(self, monkeypatch, *modules):
        self.rules, self.calls = [], []
        for mod in modules:
            monkeypatch.setattr(mod.httpx, "get", lambda url, **kw: self._answer("GET", url, kw))
            monkeypatch.setattr(mod.httpx, "post", lambda url, **kw: self._answer("POST", url, kw))

    def on(self, method, fragment, status=200, body=None):
        self.rules.append((method, fragment, status, body if body is not None else {}))
        return self

    def _answer(self, method, url, kw):
        self.calls.append((method, url, kw))
        for m, frag, status, body in self.rules:
            if m == method and frag in url:
                return httpx.Response(status, json=body, request=httpx.Request(method, url))
        raise AssertionError(f"unexpected {method} {url}")


@pytest.fixture
def ig_app(monkeypatch):
    monkeypatch.setattr(settings, "instagram_app_id", "app")
    monkeypatch.setattr(settings, "instagram_app_secret", SECRET)


@pytest.fixture
def yt_app(monkeypatch):
    monkeypatch.setattr(settings, "youtube_client_id", "cid")
    monkeypatch.setattr(settings, "youtube_client_secret", SECRET)


# ------------------------------------------------------------------ Instagram


def test_instagram_code_exchange_saves_a_long_lived_token(ig_app, monkeypatch):
    net = Net(monkeypatch, instagram)
    net.on("POST", "oauth/access_token", body={"access_token": "short", "user_id": 1784, "permissions": "a,b"})
    net.on("GET", "graph.instagram.com/access_token", body={"access_token": TOKEN, "expires_in": 5184000})
    instagram.exchange_code("the-code")
    tok = store.get_tokens("instagram")
    assert tok["access_token"] == TOKEN and tok["user_id"] == "1784" and tok["permissions"] == ["a", "b"]
    assert tok["expires_at"] > time.time() + 59 * 86400


def test_instagram_refreshes_only_when_under_20_days_remain(ig_app, monkeypatch):
    net = Net(monkeypatch, instagram).on("GET", "refresh_access_token", body={"access_token": "new", "expires_in": 5184000})
    store.set_tokens("instagram", {"access_token": TOKEN, "user_id": "1", "permissions": ["p"], "expires_at": time.time() + 40 * 86400})
    instagram.refresh_if_needed()
    assert net.calls == []
    store.set_tokens("instagram", {**store.get_tokens("instagram"), "expires_at": time.time() + 5 * 86400})
    instagram.refresh_if_needed()
    tok = store.get_tokens("instagram")
    assert tok["access_token"] == "new" and tok["user_id"] == "1" and tok["permissions"] == ["p"]  # the rest is kept


def test_instagram_errors_name_the_step_but_never_the_token_or_secret(ig_app, monkeypatch):
    Net(monkeypatch, instagram).on("GET", "refresh_access_token", 400, {"error": {"message": "Session has expired"}})
    store.set_tokens("instagram", {"access_token": TOKEN, "user_id": "1", "expires_at": 0})
    with pytest.raises(RuntimeError) as e:
        instagram.refresh_if_needed()
    assert "token refresh" in str(e.value) and "Session has expired" in str(e.value)
    assert TOKEN not in str(e.value) and SECRET not in str(e.value)
    assert store.get_tokens("instagram")["access_token"] == TOKEN  # nothing overwritten


# ------------------------------------------------------------------ YouTube


def test_youtube_refresh_keeps_the_refresh_token_google_doesnt_repeat(yt_app, monkeypatch):
    net = Net(monkeypatch, youtube).on("POST", "token", body={"access_token": "ya29.new", "expires_in": 3599})
    store.set_tokens("youtube", {"access_token": "old", "refresh_token": REFRESH, "expires_at": 0, "scope": youtube.SCOPES})
    assert youtube.access_token() == "ya29.new"  # expired: refreshed on use
    tok = store.get_tokens("youtube")
    assert tok["refresh_token"] == REFRESH and tok["scope"] == youtube.SCOPES and tok["expires_at"] > time.time() + 3000
    assert net.calls[0][2]["data"]["grant_type"] == "refresh_token"
    net.calls.clear()
    assert youtube.access_token() == "ya29.new" and net.calls == []  # still fresh: no request


def test_youtube_without_a_refresh_token_or_with_a_revoked_one_fails_clearly(yt_app, monkeypatch):
    Net(monkeypatch, youtube).on("POST", "token", body={"access_token": "ya29", "expires_in": 3599})
    with pytest.raises(RuntimeError, match="no refresh token"):
        youtube.exchange_code("c")
    assert store.get_tokens("youtube") is None

    Net(monkeypatch, youtube).on("POST", "token", 400, {"error": "invalid_grant"})
    store.set_tokens("youtube", {"access_token": "a", "refresh_token": REFRESH, "expires_at": 9e9})
    with pytest.raises(RuntimeError, match="invalid_grant") as e:
        youtube.refresh_if_needed()
    assert SECRET not in str(e.value) and REFRESH not in str(e.value)


# ------------------------------------------------------------------ Discord


@pytest.fixture
def real_notify(monkeypatch):
    """The real notify.send (conftest silences it for every test), with a webhook set."""
    monkeypatch.setattr(notify, "send", REAL_SEND)
    monkeypatch.setattr(settings, "discord_webhook_url", "https://discord.com/api/webhooks/1/WEBHOOK-SECRET")
    return notify


def test_discord_never_pings_and_trims_long_messages(real_notify, monkeypatch, tmp_path):
    sent = []
    monkeypatch.setattr(real_notify.httpx, "post", lambda url, **kw: sent.append(kw) or httpx.Response(204))
    real_notify.send("@everyone " + "x" * 3000)
    body = sent[0]["json"]
    assert body["allowed_mentions"] == {"parse": []} and len(body["content"]) == 2000
    small = tmp_path / "v.mp4"
    small.write_bytes(b"mp4")
    real_notify.send("with video", attach=small)
    assert json.loads(sent[1]["data"]["payload_json"])["allowed_mentions"] == {"parse": []} and "files" in sent[1]
    monkeypatch.setattr(real_notify, "MAX_ATTACH", 1)
    real_notify.send("too big to attach", attach=small)
    assert "files" not in sent[2]


def test_discord_failures_never_raise_or_log_the_webhook(real_notify, monkeypatch, caplog):
    def down(url, **kw):
        raise httpx.ConnectError(f"cannot reach {url}")

    monkeypatch.setattr(real_notify.httpx, "post", down)
    with caplog.at_level(logging.DEBUG):
        real_notify.send("hello")
    assert "WEBHOOK-SECRET" not in caplog.text and "ConnectError" in caplog.text

    monkeypatch.setattr(settings, "discord_webhook_url", "")
    monkeypatch.setattr(real_notify.httpx, "post", lambda *a, **k: pytest.fail("posted without a webhook"))
    real_notify.send("nowhere to send")
