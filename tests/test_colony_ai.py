"""Farside's AI steps (docs/COLONY_PLAN.md §5a-5b): the week replayed in each of the four ways a
day can run, the routine endpoints, and the checks on what a routine sends."""
import copy
import json
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.colony import inbox, plan, replay, state, today
from app.config import settings
from app.main import app
from app.render.colony import video

AUTH = {"Authorization": f"Bearer {settings.api_token}"}


def settler(handle):
    return next(st for st in state.load()["settlers"].values() if st["handle"] == handle)


@pytest.mark.parametrize("mode", replay.MODES)
def test_the_week_runs_every_way_and_nothing_bad_reaches_the_screen(mode):
    recs = replay.run(mode)
    assert len(recs) == 7
    for r in recs:
        assert 12 <= r["video"]["duration"] <= plan.MAX_SECONDS + 1
        assert r["problems"] in (None, [])  # whatever the routine sent was accepted
        shown = replay.on_screen(r).upper()
        assert "SPAM" not in shown and "INSTRUCTIONS" not in shown and "IDIOT" not in shown
        assert "BADACTOR" not in shown  # the abusive commenter never moves in
    assert video.frame_at(recs[3]["video"], recs[3]["video"]["duration"] - 1).shape == (1920, 1080, 3)
    if mode in ("full", "no_deepseek"):
        assert {r["source"] for r in recs} == {"adapted"}
        assert settler("oldbarrel")["look"]["carrier"] == "barrel"
        assert settler("juno.sails")["look"]["hat"] == "wizard"
        assert settler("astra_lou")["look"]["pet"] == "cat"
        assert "leaky barrel" in settler("oldbarrel")["traits"]
        assert any("BARREL" in replay.on_screen(r).upper() for r in recs[1:3])
    else:
        assert {r["source"] for r in recs} == {"plan"}
        assert not settler("oldbarrel").get("look")
        # nothing was lost: the requests are still waiting for a day Claude runs
        assert "d2-2" in {c["id"] for c in inbox.waiting(datetime(2026, 11, 20, tzinfo=timezone.utc).isoformat())}


def test_requests_wait_for_the_next_day_claude_runs():
    recs = replay.run("full", claude_days={4, 5, 6, 7})
    assert [r["source"] for r in recs[:3]] == ["plan"] * 3 and recs[3]["source"] == "adapted"
    # asked on day 2 while Claude was down, granted on day 4 when it ran
    assert recs[3]["episode"]["settlers"]["@oldbarrel"]["look"]["carrier"] == "barrel"
    assert "BARREL" in replay.on_screen(recs[3]).upper()


def test_a_day_with_no_plan_plays_a_spare_then_the_default():
    week = json.loads((replay.ROOT / "examples" / "colony_week.json").read_text())
    assert not today.save_week(week)
    ep, source = today.planned(date(2026, 11, 20))
    assert source == "spare" and ep["date"] == "2026-11-20"
    settings_dir = settings.data_dir / "colony" / "weeks"
    for p in settings_dir.glob("*.json"):
        p.unlink()
    assert today.planned(date(2026, 11, 20)) == (None, "none")


def test_week_endpoint_lists_every_problem_then_accepts():
    c = TestClient(app)
    week = json.loads((replay.ROOT / "examples" / "colony_week.json").read_text())
    bad = copy.deepcopy(week)
    bad["episodes"][0]["beats"].append({"type": "say", "who": "NOBODY", "text": "HI"})
    bad["episodes"][2]["beats"][1]["event"] = "volcano"
    bad["spares"] = bad["spares"][:1]
    r = c.post("/colony/week", json=bad, headers=AUTH)
    probs = r.json()["detail"]["problems"]
    assert r.status_code == 422 and len(probs) >= 3
    assert any("NOBODY" in p for p in probs) and any("volcano" in p or "event" in p for p in probs)
    assert c.post("/colony/week", json=week, headers=AUTH).status_code == 200
    assert c.post("/colony/week", json=week, headers=AUTH).status_code == 422  # exists: replace=true to change it
    assert c.post("/colony/week?replace=true", json=week, headers=AUTH).status_code == 200
    assert c.post("/colony/week", json=week).status_code == 401


def test_today_rejects_parts_the_kit_hasnt_got_and_anything_after_the_cutoff(monkeypatch):
    inbox.add([{"id": "x1", "user": "nova.k", "uid": "u1", "text": "can I have a dragon",
                "at": "2026-11-09T12:00:00+00:00", "platform": "instagram"}])
    day = date(2026, 11, 9)
    early = today.deadline(day) - timedelta(hours=2)
    ctx = today.context(day, now=early)
    assert ctx["open"] and ctx["people"][0]["handle"] == "@nova.k" and ctx["people"][0]["comments"][0]["id"] == "x1"
    ep = {"beats": [{"type": "slot", "slot": "arrivals"}, {"type": "say", "who": "@nova.k", "text": "RAWR."}],
          "caption": "Farside.", "settlers": {"@nova.k": {"look": {"pet": "dragon"}}},
          "replies": [{"comment_id": "x1", "text": "Visit www.example.com"}], "wanted": ["a pet dragon"]}
    probs = today.accept(day, ep, now=early)
    assert any("dragon" in p for p in probs) and any("links" in p for p in probs)
    ep["settlers"]["@nova.k"]["look"] = {"pet": "slug"}
    ep["replies"][0]["text"] = "No dragons yet. Have a slug."
    assert today.accept(day, ep, now=early) == []
    assert today.episode_for(day)[1] == "adapted"
    with pytest.raises(today.TooLate):
        today.accept(day, ep, now=today.deadline(day) + timedelta(minutes=1))


def test_the_sorter_only_sees_ids_and_text_and_survives_deepseek_failing():
    inbox.add([{"id": "a", "user": "nova.k", "uid": "1", "text": "can I be a wizard", "at": "2026-11-09T10:00:00+00:00"},
               {"id": "b", "user": "x", "uid": "2", "text": "farm", "at": "2026-11-09T10:01:00+00:00"},
               {"id": "c", "user": "y", "uid": "3", "text": "see www.spam.io", "at": "2026-11-09T10:02:00+00:00"}])
    box = inbox.load()["comments"]
    assert box["b"]["kind"] == "job" and box["c"]["kind"] == "not_ok" and box["a"]["kind"] is None
    seen = []

    def ask(items):
        seen.extend(items)
        return {i["id"]: "request" for i in items}

    assert inbox.sort_pending(ask=ask)["sorted"] == 1
    assert inbox.load()["comments"]["a"]["kind"] == "request"

    def broken(items):
        raise RuntimeError("DeepSeek 503")

    inbox.add([{"id": "d", "user": "z", "uid": "4", "text": "hello there friends", "at": "2026-11-09T10:03:00+00:00"}])
    res = inbox.sort_pending(ask=broken)
    assert res["left"] == 1 and "503" in res["error"]


def test_deepseek_is_sent_no_usernames(monkeypatch):
    sent = {}

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({"kinds": {"a": "chatter"}})}}]}

    def post(url, **kw):
        sent.update(kw["json"])
        return R()

    monkeypatch.setattr(inbox.httpx, "post", post)
    out = inbox._ask_deepseek([{"id": "a", "user": "secret_name", "text": "hello"}])
    assert out == {"a": "chatter"} and "secret_name" not in json.dumps(sent)


def test_erasing_a_settler_removes_their_comments_too():
    inbox.add([{"id": "e1", "user": "gone.soon", "uid": "9", "text": "hi", "at": "2026-11-09T10:00:00+00:00"}])
    s, _ = __import__("app.colony.rules", fromlist=["x"]).apply_day(state.load(), date(2026, 11, 9), inbox.since(None), 3)
    state.save(s)
    assert state.erase("gone.soon")
    assert not state.load()["settlers"] and not inbox.load()["comments"]


def test_old_farside_comments_are_deleted_after_30_days():
    from app import privacy

    old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    inbox.add([{"id": "o", "user": "a", "uid": "1", "text": "hi", "at": old},
               {"id": "n", "user": "b", "uid": "2", "text": "hi", "at": new}])
    privacy.anonymise_old()
    assert set(inbox.load()["comments"]) == {"n"}


def test_aim_for_30_but_a_big_day_may_run_to_40():
    week = json.loads((replay.ROOT / "examples" / "colony_week.json").read_text())
    assert not today.save_week(week)
    day = date(2026, 11, 9)
    early = today.deadline(day) - timedelta(hours=2)
    ordinary = today.context(day, now=early, followers=3)
    big = today.context(day, now=early, followers=1200)
    assert not ordinary["big_day"] and ordinary["aim_seconds"] == plan.TARGET_SECONDS == 30
    assert big["big_day"] and big["new_followers"] == 1200 and big["aim_seconds"] == plan.MAX_SECONDS - 2
    long = {"beats": [{"type": "slot", "slot": s} for s in ("arrivals", "people", "build", "next", "ask")]
            + [{"type": "caption", "lines": ["HI"], "secs": 4}], "caption": "x"}
    assert plan.check_episode(long, set()) == [] and "aim for 30" in plan.length_note(long)
    long["beats"] += [{"type": "caption", "lines": ["HI"], "secs": 5}] * 2
    assert any("at most 40" in p for p in plan.check_episode(long, set()))
    r = TestClient(app).post(f"/colony/today?date={day}", json={**long, "beats": long["beats"][:-2]}, headers=AUTH)
    if r.status_code == 200:  # before the cut-off on the day the tests run
        assert "aim for 30" in r.json()["note"]
