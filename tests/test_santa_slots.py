"""raosanta.uk's posting pattern and the shared busy list (app/slots.py, app/santa/schedule.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import channels, slots, store
from app.config import settings
from app.santa import schedule

TZ = settings.tz


def local(y, mo, d, h, mi=0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=TZ).astimezone(timezone.utc)


def hm(t: datetime | str) -> str:
    t = datetime.fromisoformat(t) if isinstance(t, str) else t
    return t.astimezone(TZ).strftime("%a %H:%M")


@pytest.fixture
def quiet(monkeypatch):
    """No other channel is busy, and 'now' is well before the pattern starts."""
    monkeypatch.setattr(slots, "busy", lambda *a, **k: [])
    monkeypatch.setattr(schedule, "now", lambda: local(2026, 11, 20, 12))


def test_the_pattern_walks_two_hours_earlier_then_wraps_to_the_anchor(quiet):
    times = schedule.nominal(local(2026, 11, 23, 0), 10, start=local(2026, 11, 23, 21, 30))
    assert [hm(t) for t in times] == [
        "Mon 21:30", "Tue 19:30", "Wed 17:30", "Thu 15:30", "Fri 13:30", "Sat 11:30", "Sun 09:30", "Mon 07:30",
        "Tue 21:30",  # 05:30 is before the window: that evening's anchor instead
        "Wed 19:30"]


def test_every_slot_is_inside_the_window_across_the_clock_change(quiet):
    times = schedule.nominal(local(2027, 3, 20, 0), 30, start=local(2027, 3, 20, 21, 30))
    for t in times:
        assert schedule.in_window(t), hm(t)
    gaps = {round((b - a).total_seconds() / 3600) for a, b in zip(times, times[1:])}
    assert gaps <= {21, 22, 23, 37, 38, 39}  # 22 h steps (an hour either way at the clock change) and the wrap


def test_too_late_goes_to_the_next_morning(monkeypatch, quiet):
    monkeypatch.setattr(settings, "santa_cadence_hours", 26.0)
    times = schedule.nominal(local(2026, 11, 23, 0), 3, start=local(2026, 11, 23, 21, 0))
    assert [hm(t) for t in times] == ["Mon 21:00", "Wed 07:00", "Thu 09:00"]


def busy_at(*items):
    return [slots.Busy(c, w, s, s + (timedelta(minutes=20) if w == "render" else timedelta()), f"{c} {w}")
            for c, w, s in items]


def test_a_clash_is_nudged_and_the_pattern_after_it_stays(monkeypatch):
    monkeypatch.setattr(schedule, "now", lambda: local(2026, 11, 20, 12))
    farside = local(2026, 11, 24, 19, 0)
    monkeypatch.setattr(slots, "busy", lambda *a, **k: busy_at(("colony", "post", farside)))
    rows = schedule.upcoming(3, after=local(2026, 11, 23, 0), start=local(2026, 11, 23, 21, 30))
    assert [r["planned_local"][-5:] for r in rows] == ["21:30", "19:30", "17:30"]
    assert rows[0].get("nudged") is None
    assert hm(rows[1]["at"]) == "Tue 20:00" and rows[1]["nudged"] == 30 and rows[1]["avoided"] == ["colony post"]
    assert hm(rows[2]["at"]) == "Wed 17:30"


def test_renders_must_not_overlap(monkeypatch):
    monkeypatch.setattr(schedule, "now", lambda: local(2026, 11, 20, 12))
    # another channel renders 16:40-17:00; our 17:30 post would render 16:45-17:05
    monkeypatch.setattr(slots, "busy", lambda *a, **k: busy_at(("main", "render", local(2026, 11, 25, 16, 40))))
    rows = schedule.upcoming(1, after=local(2026, 11, 25, 0), start=local(2026, 11, 25, 17, 30))
    assert rows[0]["at"] != rows[0]["planned"]
    at = datetime.fromisoformat(rows[0]["at"])
    assert not slots.clashes(at, channels.SANTA, 60, 45, busy_at(("main", "render", local(2026, 11, 25, 16, 40))))


def test_no_free_time_skips_the_slot(monkeypatch):
    monkeypatch.setattr(schedule, "now", lambda: local(2026, 11, 20, 12))
    monkeypatch.setattr(settings, "santa_nudge_max_minutes", 30)
    monkeypatch.setattr(slots, "busy", lambda *a, **k: busy_at(("main", "post", local(2026, 11, 26, 15, 30))))
    rows = schedule.upcoming(1, after=local(2026, 11, 26, 0), start=local(2026, 11, 26, 15, 30))
    assert rows[0]["skipped"] and "main post" in rows[0]["reason"] and "at" not in rows[0]


def test_busy_reads_the_other_channels(monkeypatch):
    monkeypatch.setattr(settings, "colony_enabled", True)
    monkeypatch.setattr(settings, "racing_enabled", False)
    start = local(2026, 11, 24, 0)
    got = slots.busy(start, start + timedelta(days=1))
    posts = {(b.channel, hm(b.start)) for b in got if b.what == "post"}
    assert ("main", "Tue 12:00") in posts and ("adventure", "Tue 09:00") in posts and ("colony", "Tue 19:00") in posts
    assert not any(b.channel == "racing" for b in got)  # switched off
    renders = {(b.channel, hm(b.start)) for b in got if b.what == "render"}
    assert ("main", "Tue 11:15") in renders and ("colony", "Tue 18:00") in renders


def test_busy_includes_extra_quiz_bookings(monkeypatch):
    from app import pipeline

    when = local(2026, 11, 24, 16, 15)
    monkeypatch.setattr(pipeline, "scheduled_jobs", lambda: [{"id": "q1", "publish_at": when.isoformat()}])
    got = slots.busy(local(2026, 11, 24, 0), local(2026, 11, 25, 0))
    assert any(b.channel == "main" and b.start == when and b.what == "post" for b in got)


def test_a_broken_source_doesnt_stop_the_others(monkeypatch):
    def boom(*a):
        raise RuntimeError("bad file")

    monkeypatch.setitem(slots.SOURCES, channels.ADVENTURE, boom)
    got = slots.busy(local(2026, 11, 24, 0), local(2026, 11, 25, 0))
    assert got and not any(b.channel == "adventure" for b in got)


def test_the_channel_is_registered_and_off_by_default():
    ch = channels.get(channels.SANTA)
    assert ch.kind == "promo" and ch.brand_handle == "raosanta.uk" and ch.platforms == ["instagram", "youtube"]
    assert channels.SANTA not in channels.active()


def test_endpoints(monkeypatch, quiet):
    from app.main import app

    c = TestClient(app)
    h = {"Authorization": "Bearer test-token"}
    assert c.get("/santa/slots").status_code == 401
    r = c.put("/santa/anchor", params={"at": "2026-11-23T05:00"}, headers=h)
    assert r.status_code == 422  # outside the window
    r = c.put("/santa/anchor", params={"at": "2026-11-23T21:30"}, headers=h)
    assert r.status_code == 200 and r.json()["anchor_saved"]
    assert store._read(schedule.STATE, {})["anchor"] == local(2026, 11, 23, 21, 30).isoformat()
    rows = c.get("/santa/slots", params={"count": 9}, headers=h).json()["slots"]
    assert [r["local"][-5:] for r in rows] == ["21:30", "19:30", "17:30", "15:30", "13:30", "11:30", "09:30", "07:30", "21:30"]
    assert c.get("/slots/busy", params={"channel": "nope"}, headers=h).status_code == 422
