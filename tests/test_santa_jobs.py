"""raosanta.uk bookings: the week's batch into the slots, made before the slot, posted at it,
retried, recovered, and counted in the metrics. Nothing talks to a real platform."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import channels, slots, store
from app.config import settings
from app.santa import jobs, schedule

TZ = settings.tz
H = {"Authorization": "Bearer test-token"}
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=TZ).astimezone(timezone.utc)


def local(d, h, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=TZ).astimezone(timezone.utc)


def promo(pid: str, fmt: str = "pitch") -> dict:
    return {"id": pid, "format": fmt, "caption": "Gift *anyone*",
            "segments": [{"type": "title", "text": "Remote *team*?"}, {"type": "end"}]}


@pytest.fixture
def world(monkeypatch):
    """A fixed clock, no other channel busy, the anchor on Mon 23 Nov 21:30, renders and threads
    replaced: `made` lists rendered specs."""
    clock = {"t": NOW}
    monkeypatch.setattr(jobs, "now", lambda: clock["t"])
    monkeypatch.setattr(schedule, "now", lambda: clock["t"])
    monkeypatch.setattr(slots, "busy", lambda *a, **k: [])
    schedule.set_anchor(local(23, 21, 30))
    made = []

    def render(spec, out, **kw):
        made.append(spec)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"video")
        out.with_suffix(".jpg").write_bytes(b"jpg")
        return {"duration": 14.0, "music": "jingle-bells", "voice_lines": 0}

    monkeypatch.setattr(jobs, "render_promo", render)
    monkeypatch.setattr(jobs, "_spawn", lambda target, job: target(job))
    monkeypatch.setattr(jobs.voice, "lines", lambda spec: ({}, "off"))
    return {"clock": clock, "made": made}


@pytest.fixture
def live(monkeypatch):
    """Publishing on, both accounts connected, platforms faked: `sent` lists (platform, title)."""
    sent, broken = [], set()

    class Fake:
        def __init__(self, name):
            self.name = name

        def publish(self, video, spec, job):
            if self.name in broken:
                raise RuntimeError(f"{self.name} said no")
            sent.append((self.name, spec.title, spec.full_caption()))
            return {"media_id": "M1"} if self.name == "instagram" else {"video_id": "V1", "url": "https://youtube.com/shorts/V1"}

    monkeypatch.setattr(jobs, "PUBLISHERS", {"instagram": Fake("instagram"), "youtube": Fake("youtube")})
    monkeypatch.setattr(settings, "publish_enabled", True)
    for p in ("instagram", "youtube"):
        store.set_tokens(p, {"access_token": "x"}, channel=channels.SANTA)
    return {"sent": sent, "broken": broken}


def test_a_batch_takes_the_next_free_slots_in_order(world, discord):
    booked = jobs.book([promo("one"), promo("two"), promo("three")])
    assert [jobs._local(j["publish_at"])[-5:] for j in booked] == ["21:30", "19:30", "17:30"]
    more = jobs.book([promo("four")])
    assert jobs._local(more[0]["publish_at"]) == "Thu 26 Nov 15:30"
    assert "3 promo(s) booked" in discord[0][0]


def test_bad_batches_book_nothing(world):
    jobs.book([promo("one")])
    with pytest.raises(ValueError) as e:
        jobs.book([promo("one"), promo("two"), promo("two"), {"id": "x", "format": "pitch", "segments": []}])
    probs = e.value.args[0]
    assert any("'one' was already booked" in p for p in probs)
    assert any("'two' is used twice" in p for p in probs)
    assert any(p.startswith("items[3].segments") for p in probs)
    assert len(jobs.active()) == 1


def test_replace_cancels_what_is_only_booked(world):
    jobs.book([promo("one"), promo("two")])
    new = jobs.book([promo("one"), promo("three")], replace=True)
    assert [j["spec"]["id"] for j in jobs.active()] == ["one", "three"]
    assert jobs._local(new[0]["publish_at"])[-5:] == "21:30"


def test_made_before_its_slot_then_posted_at_it(world, live, discord):
    job, = jobs.book([promo("one")])
    world["clock"]["t"] = local(23, 20, 40)  # 50 minutes before: not yet
    jobs.tick()
    assert jobs.get(job["id"])["status"] == "booked"
    world["clock"]["t"] = local(23, 20, 45)
    jobs.tick()
    j = jobs.get(job["id"])
    assert j["status"] == "scheduled" and world["made"][0].id == "one"
    assert "posts **Mon 23 Nov 21:30**" in discord[-1][0] and discord[-1][1].name == j["video"]
    world["clock"]["t"] = local(23, 21, 30)
    jobs.tick()
    j = jobs.get(job["id"])
    assert j["status"] == "done" and j["published_at"]
    assert {s[0] for s in live["sent"]} == {"instagram", "youtube"}
    title, caption = live["sent"][0][1], live["sent"][0][2]
    assert title == "Remote team? | raosanta.uk" and "#raosanta" in caption and "raosanta.uk" in caption
    assert not (settings.videos_dir / j["video"]).exists()  # every platform has it
    assert "posted" in discord[-1][0]


def test_nothing_goes_out_unless_publishing_is_on(world, discord, monkeypatch):
    monkeypatch.setattr(settings, "publish_enabled", False)
    job, = jobs.book([promo("one")])
    world["clock"]["t"] = local(23, 20, 45)
    jobs.tick()
    assert any("won't post as things stand: PUBLISH_ENABLED is off" in m for m, _ in discord)
    world["clock"]["t"] = local(23, 21, 30)
    jobs.tick()
    j = jobs.get(job["id"])
    assert j["status"] == "failed" and "PUBLISH_ENABLED" in j["error"]


def test_one_platform_failing_is_retried_alone(world, live, discord):
    live["broken"].add("youtube")
    job, = jobs.book([promo("one")])
    world["clock"]["t"] = local(23, 21, 30)
    jobs.tick()  # made and, being due, posted on the next tick
    jobs.tick()
    j = jobs.get(job["id"])
    assert j["status"] == "failed" and j["results"]["instagram"]["ok"] and not j["results"]["youtube"]["ok"]
    assert (settings.videos_dir / j["video"]).exists()  # kept for the retry
    live["broken"].clear()
    jobs.retry(j)
    j = jobs.get(job["id"])
    assert j["status"] == "done" and [s[0] for s in live["sent"]] == ["instagram", "youtube"]


def test_a_slot_missed_while_the_server_was_down(world, discord):
    job, = jobs.book([promo("one")])
    world["clock"]["t"] = local(24, 0, 0)
    jobs.tick()
    assert jobs.get(job["id"])["status"] == "missed" and any("missed its slot" in m for m, _ in discord)


def test_a_clash_that_appeared_after_booking_moves_the_post(world, monkeypatch, discord):
    job, = jobs.book([promo("one")])
    other = slots.Busy("colony", "post", local(23, 21, 0), local(23, 21, 0), "Farside extra")
    monkeypatch.setattr(slots, "busy", lambda *a, **k: [other])
    world["clock"]["t"] = local(23, 20, 45)
    jobs.tick()
    j = jobs.get(job["id"])
    assert jobs._local(j["publish_at"]) == "Mon 23 Nov 22:00" and j["moved_for"] == ["Farside extra"]


def test_cancel_and_recover(world, discord):
    a, b = jobs.book([promo("one"), promo("two")])
    assert jobs.cancel(jobs.get(a["id"]))["status"] == "cancelled"
    j = jobs.get(b["id"]) | {"status": "publishing", "updated_at": (NOW - timedelta(hours=1)).isoformat()}
    (jobs._dir() / f"{j['id']}.json").write_text(__import__("json").dumps(j))
    jobs.recover()
    assert jobs.get(b["id"])["status"] == "failed"  # never posted twice: check, then retry


def test_low_queue_warning_once_a_day(world, discord):
    jobs.tick()
    jobs.tick()
    assert sum("only 0 promo(s) booked ahead" in m for m, _ in discord) == 1


def test_posts_reach_the_metrics(world, live):
    from app import metrics

    jobs.book([promo("one", "pitch")])
    world["clock"]["t"] = local(23, 21, 30)
    jobs.tick()
    jobs.tick()
    p, = metrics.posts(channels.SANTA)
    assert p["tags"]["format"] == "pitch" and p["tags"]["hour"] == "21:00" and p["title"] == "Remote team?"
    assert set(p["results"]) == {"instagram", "youtube"}


def test_endpoints(world):
    from app.main import app

    c = TestClient(app)
    assert c.post("/santa/week", json={"items": [promo("one")]}).status_code == 401
    r = c.post("/santa/week", headers=H, json={"items": [promo("one"), promo("one")]})
    assert r.status_code == 409 and any("used twice" in p for p in r.json()["detail"])
    r = c.post("/santa/week", headers=H, json={"items": [promo("one")]})
    assert r.status_code == 200 and r.json()["booked"][0]["local"] == "Mon 23 Nov 21:30"
    jid = r.json()["booked"][0]["id"]
    slot = c.get("/santa/slots", headers=H, params={"count": 2}).json()["slots"][0]
    assert slot["booked"]["spec"] == "one"
    assert c.get("/santa/jobs", headers=H).json()["jobs"][0]["id"] == jid
    assert c.delete(f"/santa/jobs/{jid}", headers=H).json()["status"] == "cancelled"
    assert c.post(f"/santa/jobs/{jid}/retry", headers=H).status_code == 409
