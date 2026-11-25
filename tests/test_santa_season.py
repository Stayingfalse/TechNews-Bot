"""raosanta.uk's season plan: the real 2026 file, and how the server books from a plan."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import slots
from app.config import settings
from app.render.santa.video import Promo
from app.santa import jobs, schedule, season, source
from app.santa.spec import MAX_SECONDS
from tests.test_santa_source import STATS

FULL = {**STATS, "season": {**STATS["season"], "lastOrderOn": "2026-12-19", "daysToLastOrder": 9},
        "thisSeason": {"membersTakingPart": "120+", "gifts": "300+", "giftsLast7Days": "80+", "thankYous": "40+"},
        "groups": {"workplaces": "20+", "communities": "10+", "friends": "30+"}}

TZ = settings.tz
REAL = season.ROOT / "2026.json"


def local(y, mo, d, h=12, m=0):
    return datetime(y, mo, d, h, m, tzinfo=TZ).astimezone(timezone.utc)


def test_the_2026_plan_is_valid_and_every_video_fits():
    items, probs = season.load(REAL)
    assert probs == [] and len(items) >= 43
    assert season.ends(REAL).isoformat() == "2027-01-07"
    for it in items:
        filled, _ = source.fill(it["spec"], FULL)
        lens = {i: len(s.say) / 13.0 for i, s in enumerate(filled.segments) if s.say} if filled.voiced else {}
        assert Promo(filled, lens).duration < MAX_SECONDS - 5, it["spec"].id
        if it["spec"].format in ("tutorial", "pitch"):  # the voiced half says something in every segment
            assert all(s.say for s in it["spec"].segments), it["spec"].id
        else:
            assert not any(s.say for s in it["spec"].segments), it["spec"].id


def test_the_2026_plan_never_says_draw_or_pairing_is_how_it_works():
    text = REAL.read_text().lower()
    for bad in ("matched with", "you'll be paired", "your match", "draw names"):
        assert bad not in text


def plan(tmp_path, items, ends=None):
    p = tmp_path / "plan.json"
    p.write_text(json.dumps({"year": 2026, **({"ends": ends} if ends else {}), "items": items}))
    return p


def promo(pid, fmt="pitch"):
    return {"id": pid, "format": fmt, "segments": [{"type": "title", "text": "Hi"}, {"type": "end"}]}


@pytest.fixture
def world(monkeypatch, tmp_path):
    clock = {"t": local(2026, 11, 26)}
    monkeypatch.setattr(jobs, "now", lambda: clock["t"])
    monkeypatch.setattr(schedule, "now", lambda: clock["t"])
    monkeypatch.setattr(slots, "busy", lambda *a, **k: [])
    schedule.set_anchor(local(2026, 11, 26, 21, 30))

    def use(items, ends=None):
        monkeypatch.setattr(settings, "santa_season_file", str(plan(tmp_path, items, ends)))

    def run_until(t):
        while clock["t"] < t:
            season.sync()
            for j in jobs.active():
                if datetime.fromisoformat(j["publish_at"]) <= clock["t"]:
                    j.update(status="done")
                    jobs.save(j)
            clock["t"] += timedelta(hours=6)
        return [(datetime.fromisoformat(j["publish_at"]).astimezone(TZ).date().isoformat(), j["spec"]["id"]) for j in jobs.all_jobs()]

    return {"clock": clock, "use": use, "run_until": run_until}


def test_promos_only_go_out_inside_their_window_and_fillers_fill_gaps(world):
    world["use"]([{"until": "2026-11-26", "spec": promo("before-opening")},
                  {"from": "2026-11-28", "until": "2026-11-28", "spec": promo("only-saturday")},
                  {"spec": promo("filler-a", "quiz") | {"segments": [{"type": "question", "question": "Q?", "options": ["a", "b"],
                                                                      "correct": 0}, {"type": "end"}]}},
                  {"from": "2026-11-27", "spec": promo("from-friday")}])
    got = world["run_until"](local(2026, 11, 30))
    assert got == [("2026-11-26", "before-opening"), ("2026-11-27", "from-friday"),
                   ("2026-11-28", "only-saturday"), ("2026-11-29", "filler-a")]


def test_a_missed_window_expires_and_nothing_books_after_the_end(world):
    world["use"]([{"until": "2026-11-25", "spec": promo("too-late")}, {"spec": promo("filler-1")}, {"spec": promo("filler-2")},
                  {"spec": promo("filler-3")}], ends="2026-11-27")
    got = world["run_until"](local(2026, 12, 3))
    assert [i for _, i in got] == ["filler-1", "filler-2"]
    rep = season.report()
    assert {r["id"]: r["status"] for r in rep["items"]} == {"too-late": "expired", "filler-1": "posted", "filler-2": "posted",
                                                            "filler-3": "expired"}
    assert season.finished()


def test_books_only_a_few_days_ahead_and_never_twice(world, monkeypatch):
    monkeypatch.setattr(settings, "santa_book_ahead_days", 2.0)
    world["use"]([{"spec": promo(f"promo-{k}")} for k in range(6)])
    first = season.sync()
    assert len(first) == 2 and season.sync() == []  # nothing new inside the horizon; ids not reused
    jobs.cancel(first[0])
    again = season.sync()
    assert [j["spec"]["id"] for j in again] == ["promo-0"]  # a cancelled booking frees its id


def test_a_broken_item_is_reported_and_the_rest_still_run(world):
    world["use"]([{"spec": promo("ok-one")}, {"spec": {"id": "bad", "format": "pitch", "segments": []}},
                  {"from": "2026-12-02", "until": "2026-12-01", "spec": promo("backwards")}, {"spec": promo("ok-one")}])
    items, probs = season.load()
    assert [i["spec"].id for i in items] == ["ok-one"]
    assert any(p.startswith("items[1]") for p in probs) and any("until is before from" in p for p in probs)
    assert any("used twice" in p for p in probs)


def test_endpoints(world, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    world["use"]([{"spec": promo("one")}])
    c = TestClient(app)
    h = {"Authorization": "Bearer test-token"}
    assert c.get("/santa/season", headers=h).json()["items"][0]["status"] == "waiting"
    assert c.post("/santa/season/sync", headers=h).status_code == 409  # SANTA_ENABLED off
    monkeypatch.setattr(settings, "santa_enabled", True)
    assert c.post("/santa/season/sync", headers=h).json()["booked"][0]["spec_id"] == "one"


def test_a_promo_with_no_figures_to_show_is_swapped_for_one_that_needs_none(world, monkeypatch, discord):
    figures = {"id": "figures-only", "format": "update", "segments": [
        {"type": "figures", "figures": [{"value": "{thisSeason.gifts}", "label": "gifts"}]}, {"type": "end"}]}
    world["use"]([{"spec": figures}, {"spec": promo("plain-one")}])
    monkeypatch.setattr(settings, "santa_book_ahead_days", 0.5)  # just tonight's slot
    job, = season.sync()
    assert job["spec"]["id"] == "figures-only"
    monkeypatch.setattr(source, "fetch", lambda: STATS)  # thisSeason.gifts is hidden (under 10)
    made = []
    def render(spec, out, **kw):
        made.append(spec.id)
        out.write_bytes(b"v")
        return {"duration": 9.0, "music": "none", "voice_lines": 0}

    monkeypatch.setattr(jobs, "render_promo", render)
    monkeypatch.setattr(jobs.voice, "lines", lambda spec: ({}, "off"))
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    jobs.prepare(jobs.get(job["id"]))
    j = jobs.get(job["id"])
    assert j["status"] == "scheduled" and made == ["plain-one"] and j["replaced"] == "figures-only"
    assert any("plays instead" in m for m, _ in discord)
    assert {r["id"]: r["status"] for r in season.report()["items"]}["figures-only"] == "waiting"  # free for a later day
