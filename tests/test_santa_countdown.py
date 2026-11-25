"""raosanta.uk's midnight countdown to Christmas: a different short video every night."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app import slots
from app.config import settings
from app.render.santa.video import Promo
from app.santa import countdown, jobs, schedule

DAYS = [date(2026, 11, 26) + timedelta(days=k) for k in range(30)]  # 26 Nov .. 25 Dec


def utc(y, mo, d, h=0, m=0):
    return datetime(y, mo, d, h, m, tzinfo=timezone.utc)


def test_every_night_is_different_and_short():
    specs = [countdown.spec_for(d) for d in DAYS]
    assert [s.segments[0].days for s in specs] == list(range(29, -1, -1))
    assert len({s.segments[0].line for s in specs}) == len(specs)  # a different line every night
    assert len({(s.music, s.segments[-1].line) for s in specs}) >= 5
    assert specs[-1].segments[0].days == 0 and specs[-1].caption.startswith("It's Christmas!")
    assert specs[-2].caption.startswith("1 sleep until Christmas.")
    assert specs[0].segments[0].date == "2026-11-26" and specs[-1].segments[0].date == "2026-12-25"
    assert specs[5].caption.startswith("24 sleeps until Christmas. Door 1:")
    for s in specs:
        assert not s.voiced and "#christmascountdown" in s.hashtags
        assert Promo(s).duration < 14


@pytest.fixture
def clock(monkeypatch):
    c = {"t": utc(2026, 11, 25, 1)}
    monkeypatch.setattr(jobs, "now", lambda: c["t"])
    monkeypatch.setattr(schedule, "now", lambda: c["t"])
    monkeypatch.setattr(slots, "busy", lambda *a, **k: [])
    return c


def test_books_the_next_midnights_once_and_stops_at_christmas(clock):
    got = countdown.sync()
    assert [j["publish_at"] for j in got] == [utc(2026, 11, d).isoformat() for d in (26, 27, 28)]
    assert countdown.sync() == []  # never twice
    clock["t"] = utc(2026, 12, 23, 23, 30)  # too close to midnight to make it: tomorrow's onwards
    assert [j["spec"]["id"] for j in countdown.sync()] == ["countdown-2026-12-25"]
    clock["t"] = utc(2026, 12, 26, 1)
    assert countdown.sync() == []


def test_it_stays_out_of_the_pattern_and_the_warning(clock, discord):
    countdown.sync()
    assert all(r["planned"] not in {j["planned"] for j in jobs.active()} for r in jobs.free_slots(3))
    jobs._warn_if_low(clock["t"])  # countdown bookings don't count as the pattern being booked
    assert any("nothing is booked for the next 48 hours" in m for m, _ in discord)


def test_switched_off(clock, monkeypatch):
    monkeypatch.setattr(settings, "santa_countdown", False)
    assert countdown.sync() == []


def test_the_calendar_fills_up_and_every_day_films_differently():
    from app.render.santa import advent, scenes

    assert sorted(advent.layout(2026)) == list(range(1, 26))
    assert set(advent.TREASURES) == set(range(26))
    paths = set()
    for d in DAYS:
        sc = scenes.AdventScene(countdown.spec_for(d).segments[0])
        assert sc.target == (d.day if d.month == 12 else 1)
        assert sc.target not in sc.visits
        if d.month == 12 and d.day > 2:
            assert all(v < d.day for v in sc.visits)  # the pan visits doors already open
        paths.add(tuple(sc.visits))
    assert len(paths) >= 25  # the camera takes a different route almost every day
