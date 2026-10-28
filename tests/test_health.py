"""Monitoring: healthchecks.io setup and pings, and the Discord warnings."""
from __future__ import annotations

import time

import httpx
import pytest

from app import health, pipeline, store
from app.config import settings


class Fake:
    """Records requests to healthchecks.io / ElevenLabs instead of sending them."""

    def __init__(self):
        self.calls = []
        self.subscription = {"character_count": 9000, "character_limit": 10000, "next_character_count_reset_unix": 1793000000}

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        return httpx.Response(201, json={"ping_url": f"https://hc-ping.com/{json['name'].split()[-1]}"},
                              request=httpx.Request("POST", url))

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        if "elevenlabs" in url:
            return httpx.Response(200, json=self.subscription, request=httpx.Request("GET", url))
        return httpx.Response(200, text="OK", request=httpx.Request("GET", url))


@pytest.fixture
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setattr(health.httpx, "post", f.post)
    monkeypatch.setattr(health.httpx, "get", f.get)
    return f


def test_no_key_no_checks(fake):
    assert health.setup() == {}
    health.ping("heartbeat")
    assert fake.calls == []


def test_setup_creates_the_three_checks(fake, monkeypatch):
    monkeypatch.setattr(settings, "healthchecks_api_key", "k")
    urls = health.setup()
    assert sorted(urls) == ["daily-post", "heartbeat", "weekly-batch"]
    bodies = {b["name"]: b for _, _, b in fake.calls}
    assert all(b["unique"] == ["name"] for b in bodies.values())  # re-running finds them, doesn't duplicate
    assert bodies["quizbot daily-post"]["schedule"] == "0 12 * * *" and bodies["quizbot daily-post"]["tz"] == "Europe/London"
    assert bodies["quizbot heartbeat"]["timeout"] == 600


def test_pings(fake, monkeypatch):
    store._write("health.json", {"heartbeat": "https://hc-ping.com/h", "daily-post": "https://hc-ping.com/d"})
    monkeypatch.setattr(health, "_last_beat", 0.0)
    health.heartbeat()
    health.heartbeat()  # at most every 5 minutes
    health.ping("daily-post", fail=True)
    assert [u for _, u, _ in fake.calls] == ["https://hc-ping.com/h", "https://hc-ping.com/d/fail"]


def test_ping_failure_never_raises(monkeypatch):
    store._write("health.json", {"heartbeat": "https://hc-ping.com/h"})

    def down(*a, **k):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(health.httpx, "get", down)
    health.ping("heartbeat")


def test_low_credits_warn_once_a_day(fake, discord, monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    assert health.check_elevenlabs()["left"] == 1000
    health.check_elevenlabs()
    assert len(discord) == 1 and "1,000 characters left" in discord[0][0]
    fake.subscription["character_count"] = 1000
    store._write("health.json", {})
    health.check_elevenlabs()
    assert len(discord) == 1  # plenty left: quiet


def test_instagram_login_about_to_expire(discord):
    store.set_tokens("instagram", {"access_token": "x", "expires_at": time.time() + 3 * 86400})
    health.check_logins()
    assert "expires in 3 days" in discord[0][0]
    store.set_tokens("instagram", {"access_token": "x", "expires_at": time.time() + 40 * 86400})
    store._write("health.json", {})
    health.check_logins()
    assert len(discord) == 1


def test_broken_connection_warns_once_a_day_per_channel(discord, monkeypatch):
    from app import channels
    from app.publish import instagram

    monkeypatch.setattr(instagram, "configured", lambda: True)
    store.set_tokens("instagram", {"access_token": "bad", "user_id": "1", "expires_at": time.time() + 50 * 86400})
    store.set_tokens("instagram", {"access_token": "good", "user_id": "2", "expires_at": time.time() + 50 * 86400},
                     channel=channels.RACING)

    def account():
        if store.get_tokens("instagram")["access_token"] == "bad":
            raise RuntimeError("Error validating access token: The session has been invalidated")
        return {"username": "sixelspeedway"}

    monkeypatch.setattr(instagram, "account", account)
    assert health.check_connections() == ["main:instagram"]  # the adventure channel has no login: skipped
    health.check_connections()
    assert len(discord) == 1 and "/oauth/instagram/start" in discord[0][0] and "invalidated" in discord[0][0]


def test_weekly_batch_pings_only_for_a_batch(quiz, monkeypatch):
    from datetime import date, timedelta

    from fastapi.testclient import TestClient

    from app.main import app

    from app import main

    pinged = []
    monkeypatch.setattr(main.monitoring, "ping", lambda name, fail=False: pinged.append(name))
    monkeypatch.setattr(main, "_repeats", lambda spec, used: [])  # same sample quiz each day is fine here
    client, auth = TestClient(app), {"Authorization": "Bearer test-token"}

    def items(ids, start):
        return [{"date": (date.today() + timedelta(days=start + k)).isoformat(), "spec": dict(quiz, id=i)}
                for k, i in enumerate(ids)]

    assert client.post("/schedule", headers=auth, json={"items": items(["one-off"], 2)}).status_code == 202
    assert pinged == []  # a one-off booking isn't the weekly batch
    r = client.post("/schedule", headers=auth, json={"items": items(["wk-a", "wk-b", "wk-c"], 4)})
    assert r.status_code == 202, r.text
    assert pinged == ["weekly-batch"]


def test_daily_post_pinged_after_a_slot_posts(quiz, monkeypatch, tmp_path):
    pinged = []
    monkeypatch.setattr(health, "ping", lambda name, fail=False: pinged.append((name, fail)))
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(settings, "platforms", ["instagram"])
    from app.publish import instagram

    monkeypatch.setattr(instagram, "configured", lambda: True)
    monkeypatch.setattr(instagram, "publish", lambda video, spec, job: {"media_id": "M", "url": "u"})
    for name in ("after_publish", "link_previous"):
        monkeypatch.setattr(pipeline.cliffhanger, name, lambda job: None)
    monkeypatch.setattr(pipeline.themes, "after_publish", lambda job: None)
    monkeypatch.setattr(pipeline.social, "after_publish", lambda job: None)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    (settings.videos_dir / "v.mp4").write_bytes(b"x")
    job = {"id": "slot-1", "spec": quiz, "status": "publishing", "dry_run": False, "slot": "2026-10-24",
           "publish_at": "2026-10-24T11:00:00+00:00", "video": "v.mp4", "video_url": "u", "results": {},
           "created_at": "2026-10-23T00:00:00+00:00", "render": {"duration": 50}}
    store.save_job(job)
    pipeline._publish(job)
    assert pinged == [("daily-post", False)]
