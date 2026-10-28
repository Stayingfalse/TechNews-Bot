"""Sixel Speedway: the race, the odds, bets in comments, the ledger, replies, the daily cycle, the
renderer's safe zone and the bets domain. Platforms are faked; the video encode is replaced by a
stub in the cycle tests (one real frame-by-frame check covers the drawing)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient

from app import privacy
from app.config import settings
from app.main import app
from app.racing import bets, hooks, jobs, ledger, races, replies, sim, tracks, video
from app.render.racing.engine import Video, timeline
from app.render.racing.themes.base import SAFE

STATS = sim.initial_stats()


@pytest.fixture(autouse=True)
def quick_odds(monkeypatch):
    monkeypatch.setattr(sim, "MC_RUNS", 1500)  # pricing every race with 20,000 runs is slow in tests


def comment(cid, user, text, minute, hour=12, uid="", day="2026-10-28"):
    return {"id": cid, "user": user, "uid": uid or f"u-{user}", "text": text,
            "at": f"{day}T{hour:02d}:{minute:02d}:00+00:00", "platform": "instagram"}


# ------------------------------------------------------------------ the race


def test_a_seed_always_gives_the_same_race_and_seal():
    seed = "00ff" * 8
    a = sim.summary(sim.race(3, seed, STATS, "gp", 11), "gp")
    assert a == sim.summary(sim.race(3, seed, STATS, "gp", 11), "gp")
    assert sim.seal(3, seed, "gp", 11, STATS) == sim.seal(3, seed, "gp", 11, STATS)
    assert len({sim.seal(3, seed, "gp", 11, STATS), sim.seal(4, seed, "gp", 11, STATS),
                sim.seal(3, seed, "rally", 11, STATS), sim.seal(3, seed, "gp", 12, STATS)}) == 4
    assert sorted(a["order"]) == [1, 2, 3, 4, 5, 6]
    assert len(a["dist"]) == int(sim.FORMATS["gp"]["video"] * sim.FPS) + 1  # fitted to its time on screen


@pytest.mark.parametrize("kind", ["oval", "gp", "rally", "figure8", "endurance", "drag"])
def test_every_track_kind_is_generated_the_same_from_its_seed(kind):
    a, b = tracks.generate(kind, 5), tracks.generate(kind, 5)
    assert (a.pts == b.pts).all() and a.name == b.name
    assert (a.pts >= 0).all() and (a.pts <= 1).all()
    if kind in ("gp", "rally", "endurance", "oval"):
        assert not tracks._intersects(a.pts)
    if kind == "drag":
        assert round(a.length, 1) == 402.3 and not a.closed
    assert tracks.corners(tracks.generate("rally", 5)) > tracks.corners(tracks.generate("oval", 5))


def test_each_format_suits_different_cars():
    """Top speed wins ovals, acceleration wins drag races, grip wins rally stages."""
    fav = {fmt: max(range(6), key=lambda j: c[j]) + 1
           for fmt in ("oval", "drag", "rally") for c in [sim.win_chances(STATS, fmt, 3, runs=1500)]}
    assert fav["oval"] == 1 and fav["drag"] == 4 and fav["rally"] in (2, 6)


def test_endurance_races_have_pit_stops_and_tyre_wear():
    res = sim.summary(sim.race(1, "ab" * 16, STATS, "endurance", 4), "endurance")
    pits = [e for e in res["events"] if e["kind"] == "pit"]
    assert len(pits) >= 6 and all(20 < e["dur"] < 35 for e in pits)
    assert max(max(w) for w in res["wear"]) > 0.6 and any(any(p) for p in res["pit"])
    assert 20 < res["scale"] < 50  # half an hour of racing in 50 s: sped up, but you can follow it


def test_drag_races_have_reaction_times_and_no_laps():
    res = sim.summary(sim.race(1, "cd" * 16, STATS, "drag", 4), "drag")
    assert res["laps"] == 1 and set(res["reaction"]) == {"1", "2", "3", "4", "5", "6"}
    assert all(t is None or 8 < t < 14 for t in res["times"].values())


def test_endurance_comes_every_other_saturday():
    from datetime import date

    sats = [races.format_on(date(2026, 10, 31) + timedelta(weeks=k)) for k in range(4)]
    assert sats.count("endurance") == 2 and sats[0] != sats[1]
    assert races.format_on(date(2026, 11, 2)) == "oval" and races.format_on(date(2026, 11, 6)) == "drag"
    assert sim.FORMATS["endurance"]["laps"] == 18


def test_the_video_shows_the_week_ahead():
    race = _race(1)
    sched = video.schedule_part(race)
    assert len(sched) == 5 and sched[0]["day"] == "TOMORROW" and sched[0]["open"]
    assert sched[0]["format"]["key"] == race["format"] and [r["no"] for r in sched] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("fmt", ["gp", "endurance", "drag"])
def test_commentary_follows_the_race_and_never_overlaps(fmt):
    race = races.draft(1, STATS, "2026-10-27T18:00:00+00:00", "2026-10-28T17:00:00+00:00", fmt)
    race["result"] = races.run(race)
    part = json.loads(json.dumps(video.race_part(race)))
    lines = part["commentary"]
    assert len(lines) >= 2
    for a, b in zip(lines, lines[1:]):
        assert a["until"] <= b["t"]
    assert all(0 < c["t"] and c["until"] <= part["race_end"] for c in lines)
    names = {c["name"].title() for c in sim.CARS}
    assert all(any(n in c["text"] for n in names) or "mile" in c["text"].lower() for c in lines)
    spun = {e["car"] for e in part["events"] if e["kind"] == "spin"}
    for c in lines:  # a spin line names a car that really spun
        if "spin" in c["text"].lower() and c.get("car"):
            assert c["car"] in spun


def test_odds_carry_the_margin_and_cover_every_car():
    chances = sim.win_chances(STATS, "gp", 11, runs=3000)
    assert abs(sum(chances) - 1) < 1e-9
    prices = [sim.price(c) for c in chances]
    implied = sum(1 / (1 + Fraction(p)) for p in prices)
    assert implied >= 1.05  # rounded down the ladder: never better than the margin allows
    assert all(p in sim.LADDER for p in prices)
    assert sim.payout(250, "4/1") == 1250
    assert sim.payout(100, "4/6") == 166


def test_odds_match_how_often_cars_really_win():
    """The real races (one seed each) win about as often as the priced chances say."""
    chances = sim.win_chances(STATS, "rally", 9, runs=4000, seed=1)
    wins = [0] * 6
    for i in range(300):
        wins[sim.race(i, f"{i:032x}", STATS, "rally", 9).order(0)[0]] += 1
    for c, w in zip(chances, wins):
        assert abs(w / 300 - c) < 0.08


def test_stats_drift_a_little_and_stay_in_range():
    s = STATS
    for k in range(200):
        s = sim.drift(s, k)
    assert all(0.93 <= c["speed"] <= 1.08 and 0.15 <= c["consistency"] <= 0.97 for c in s)
    assert sim.drift(STATS, 5) == sim.drift(STATS, 5)


# ------------------------------------------------------------------ reading bets


@pytest.mark.parametrize("text, want", [
    ("4 250", (4, 250)), ("#4 £250", (4, 250)), ("250 on 4", (4, 250)), ("car 4 250", (4, 250)),
    ("blue streak 300", (4, 300)), ("blue 300", (4, 300)), ("all in on 3", (3, "all")), ("3 all", (3, "all")),
    ("1k on 2", (2, 1000)), ("£1,000 on red rocket", (1, 1000)), ("4", (4, None)), ("custard!", (3, None)),
    ("go hot pink", (5, None)), ("race 15: 4 250", (4, 250)), ("I bet 300 on cyanara", (6, 300)),
    ("hot pink was robbed lol omg", None), ("5 4", None), ("2 100 4 50", None), ("#4 5", None),
    ("7 100", None), ("great video", None), ("red and blue 100", None), ("100", None),
])
def test_bets_in_comments(text, want):
    got = bets.parse(text)
    assert (got and (got["car"], got["stake"])) == want if want else got is None


def test_a_number_without_a_car_gets_the_how_to_bet_reply():
    assert bets.looks_like_bet("7 100") and bets.looks_like_bet("100") and not bets.looks_like_bet("great video")


# ------------------------------------------------------------------ the ledger


def _race(no=1):
    return races.open_race(no, STATS, "2026-10-27T18:00:00+00:00", "2026-10-28T17:00:00+00:00")


def test_every_comment_is_a_bet_taken_in_posting_order_until_the_money_runs_out():
    race = _race()
    cs = [comment("c3", "tess", "6 900", 3), comment("c1", "tess", "4 250", 1), comment("c2", "tess", "2", 2),
          comment("c4", "tess", "1 50", 4), comment("c5", "bob", "hello", 5)]
    out = ledger.settle(race, cs, winner=4, odds=["2/1"] * 3 + ["4/1"] + ["2/1"] * 2)
    taken = [(b["comment_id"], b["stake"], b.get("refused")) for b in out["bets"]]
    assert taken == [("c1", 250, None), ("c2", 100, None), ("c3", 650, None), ("c4", 0, "no balance")]
    tess = ledger.player("instagram:u-tess")
    assert tess["balance"] == 0 + 250 * 5  # everything staked, then 4 won at 4/1
    assert ledger.player("instagram:u-bob")["balance"] == 1000  # commented, so he's a player
    assert out["new_players"] == 2 and len(out["commenters"]) == 2
    assert ledger.rebuild() == {p: v["balance"] for p, v in ledger.players().items()}


def test_provisional_balances_match_what_settlement_will_do():
    race = _race()
    cs = [comment("c1", "amy", "4 700", 1), comment("c2", "amy", "1 500", 2), comment("c3", "amy", "2 10", 3)]
    rows = ledger.provisional(cs)
    assert [(r["stake"], r["cut"], r["left"]) for r in rows] == [(700, False, 300), (300, True, 0), (0, False, 0)]
    assert ledger.players() == {}  # nothing written
    texts = [replies.for_bet(r, race) for r in rows]
    assert texts[0][0] == "taken" and texts[0][1].startswith("Welcome!") and "§300" in texts[0][1]
    assert texts[1][0] == "cut" and texts[2][0] == "broke"
    assert settings.racing_domain in texts[0][1]


def test_weekly_bonus_pays_every_known_player_once_a_week():
    race = _race()
    ledger.settle(race, [comment("c1", "amy", "hi", 1), comment("c2", "bob", "4 100", 2)], winner=1, odds=["2/1"] * 6)
    privacy.opt_out("carl")
    ledger.settle(race, [comment("c3", "carl", "4 100", 3)], winner=1, odds=["2/1"] * 6)
    got = ledger.weekly_bonus("2026-W44", {"instagram:u-amy": 3})
    assert got["players"] == 2 and got["paid"] == 250 + 100
    assert ledger.balance("instagram:u-amy") == 1250 and ledger.balance("instagram:u-bob") == 1000
    assert ledger.weekly_bonus("2026-W44", {})["already"]
    assert ledger.weekly_bonus("2026-W45", {}, doubled=True)["paid"] == 400


def test_league_table_climber_bust_and_anonymised_players():
    race = _race()
    ledger.settle(race, [comment("c1", "amy", "4 all", 1), comment("c2", "bob", "1 all", 2)], winner=1, odds=["3/1"] * 6)
    tb = ledger.table(since="2000-01-01")
    assert [r["name"] for r in tb["rows"]] == ["bob", "amy"] and tb["bust"] == 1
    assert tb["climber"] == {"name": "bob", "gain": 3000}
    ps = ledger.players()
    ps["instagram:u-bob"]["last_bet"] = "2000-01-01T00:00:00+00:00"
    ledger._write("players.json", ps)
    assert ledger.anonymise_idle() == 1
    assert ledger.table()["rows"][0]["name"].startswith("punter #")
    assert races.get(1) and all(b.get("name") != "bob" for b in races.get(1).get("bets", []))


def test_erasure_removes_the_player_and_their_ledger_lines():
    race = _race()
    out = ledger.settle(race, [comment("c1", "amy", "4 100", 1), comment("c2", "bob", "4 100", 2)], winner=4, odds=["2/1"] * 6)
    race["bets"] = out["bets"]
    races.save(race)
    privacy.erase("amy")
    assert ledger.find("amy") is None and all(e["pid"] != "instagram:u-amy" for e in ledger.entries())
    assert [b["name"] for b in races.get(1)["bets"]] == ["bob"]


# ------------------------------------------------------------------ hooks and the spec


def _ran(no=1, bets_=None):
    race = _race(no)
    race["result"] = races.run(race)
    race["status"] = "run"
    out = ledger.settle(race, bets_ or [], race["result"]["order"][0], race["odds"])
    race["bets"] = out["bets"]
    races.save(race)
    return race, out


def test_hooks_never_need_bets_and_use_them_when_there_are_some():
    race, out = _ran()
    assert hooks.choose(race, out)  # zero bets: still a hook
    race2, out2 = _ran(2, [comment(f"c{i}", f"p{i}", f"{1 + i % 6} 400", i) for i in range(6)])
    lines = hooks.choose(race2, out2)
    assert 2 <= len(lines) <= 3 and all(len(line.replace("*", "")) <= 20 for line in lines)


@pytest.mark.parametrize("fmt", ["gp", "endurance", "drag"])
def test_every_scene_keeps_its_text_inside_the_safe_area(fmt):
    race = races.draft(1, STATS, "2026-10-27T18:00:00+00:00", "2026-10-28T17:00:00+00:00", fmt)
    race["result"], race["status"] = races.run(race), "run"
    out = ledger.settle(race, [comment("c1", "averyveryverylonghandle_99", "4 all", 1), comment("c2", "bob", "2 300", 2)],
                        race["result"]["order"][0], race["odds"])
    nxt = races.draft(2, STATS, "2026-10-28T18:00:00+00:00", "2026-10-29T17:00:00+00:00", fmt)
    tb = ledger.table(since="2000-01-01")
    tb["week"] = "WEEK 44"
    spec = json.loads(json.dumps(video.spec("pitwall", nxt, race, out, tb, tb["bust"])))
    for sp in (spec, json.loads(json.dumps(video.spec("pitwall", nxt)))):
        v = Video(sp, record=True)
        for name, dur in timeline(sp):
            for t in (0.0, dur * 0.5, dur - 0.05):
                v.theme.frame(name, t, dur)
        assert v.theme.boxes, "nothing recorded"
        x0, y0, x1, y1 = SAFE
        bad = [(s, b) for s, b in v.theme.boxes if b[0] < x0 or b[1] < y0 or b[2] > x1 or b[3] > y1]
        assert not bad


def test_the_video_loops_back_to_its_first_frame():
    race, out = _ran()
    spec = json.loads(json.dumps(video.spec("pitwall", _race(2), race, out)))
    v = Video(spec)
    first, last = v.frame(0), v.frame(v.n_frames - 1)
    assert list(first.getdata()) == list(last.getdata())


# ------------------------------------------------------------------ the daily cycle


@pytest.fixture
def cycle(monkeypatch, platforms):
    """The racing channel connected, with the encode and the Reel upload faked."""
    from app.publish import instagram
    from app.render.racing import engine

    monkeypatch.setattr(jobs, "can_publish", lambda: None)
    renders = []

    def fake_render(spec, out, workers=None, cover_path=None):
        renders.append(spec)
        out.write_bytes(b"mp4")
        return {"duration": 40.0, "seconds": 1, "theme": spec["theme"]}

    monkeypatch.setattr(engine, "render", fake_render)
    n = iter(range(1, 100))
    monkeypatch.setattr(instagram, "publish_reel", lambda url, cap, cover=None: {"media_id": f"M{next(n)}", "url": "https://ig/x", "caption": cap})
    monkeypatch.setattr(instagram, "metrics", lambda media: {"views": 100, "comments": 5, "likes": 9})
    # run the worker threads inline
    monkeypatch.setattr(jobs.threading, "Thread", lambda target, args=(), **k: type("T", (), {"start": lambda self: target(*args)})())
    platforms["renders"] = renders
    return platforms


def test_launch_then_a_day_of_betting_then_the_race(cycle, discord):
    slot = datetime(2026, 11, 1, 19, 0, tzinfo=timezone.utc)  # a Sunday (UTC = London in November)
    job = jobs.start(slot - timedelta(days=1))
    assert job["kind"] == "launch" and races.get(1)["status"] == "open"
    jobs.tick(slot - timedelta(days=1, minutes=20))
    assert jobs.get(job["id"])["status"] == "scheduled" and cycle["renders"][0]["launch"]
    jobs.tick(slot - timedelta(days=1))
    launch = jobs.get(job["id"])
    assert launch["status"] == "done" and races.get(1)["post"]["media_id"] == "M1"
    assert ("instagram", "comment", "M1", jobs.FIRST_COMMENT) in cycle["calls"]
    assert "Race 1 seal: " + races.get(1)["seal"] in launch["results"]["instagram"]["caption"]

    # bets come in; replies are queued and paced
    cycle["comments"]["instagram"] = [comment("c1", "amy", "4 250", 1, hour=10), comment("c2", "bob", "lol", 2, hour=10),
                                      comment("c3", "bob", "7 100", 3, hour=10), comment("c4", "mediaquiz.daily", "4 1", 4, hour=10)]
    assert jobs.poll(slot - timedelta(hours=8)) == 2
    assert jobs.poll(slot - timedelta(hours=7)) == 0  # nothing twice
    t0 = datetime.now(timezone.utc)
    assert replies.send_due(t0) == 1 and replies.send_due(t0) == 0  # one at a time, RACING_REPLY_GAP apart
    assert replies.send_due(t0 + timedelta(seconds=settings.racing_reply_gap + 1)) == 1
    sent = [c for c in cycle["calls"] if c[1] == "reply"]
    assert sent[0][2] == "c1" and "§250 on 4 BLUE STREAK" in sent[0][3] and "§750" in sent[0][3]
    assert sent[1][2] == "c3" and "4 250" in sent[1][3]

    # 18:00: race 1 runs and settles, race 2 opens, Sunday adds the bonus and table
    nxt = [j for j in jobs.recent(10) if j["kind"] == "race"][0]
    assert nxt["run"] == 1 and nxt["publish_at"] == slot.isoformat()
    jobs.tick(slot - timedelta(minutes=60))
    r1, r2 = races.get(1), races.get(2)
    assert r1["status"] == "run" and r2["status"] == "open" and r2["stats"] != r1["stats"]
    assert [b["comment_id"] for b in r1["bets"]] == ["c1"]
    spec = cycle["renders"][-1]
    assert spec["race"]["no"] == 1 and spec["card"]["no"] == 2 and spec["table"]["week"] == "WEEK 44"
    assert jobs.get(nxt["id"])["bonus"]["doubled"]  # launch weeks
    won = r1["result"]["order"][0] == 4
    assert ledger.balance("instagram:u-amy") == 750 + (sim.payout(250, r1["odds"][3]) if won else 0) + 200 + 100
    jobs.tick(slot)
    done = jobs.get(nxt["id"])
    assert done["status"] == "done" and races.get(2)["post"]["media_id"] == "M2"
    assert f"Its seed: {r1['seed']}" in done["results"]["instagram"]["caption"]
    assert [j for j in jobs.recent(10) if j.get("run") == 2]  # tomorrow is booked

    # a bet left under the old post after it closed is told so, once
    cycle["comments"]["instagram"] = [comment("c9", "amy", "4 100", 30, hour=18, day="2026-11-01"),
                                      comment("c10", "amy", "2 100", 31, hour=18, day="2026-11-01")]
    late = jobs.poll(slot + timedelta(minutes=30))
    assert late >= 1
    closed = [i for i in replies.queue()["items"] if i["kind"] == "closed"]
    assert len(closed) == 1 and "race 2" in closed[0]["text"]


def test_a_race_is_never_run_twice(cycle):
    slot = datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc)
    jobs.start(slot - timedelta(days=1))
    jobs.tick(slot - timedelta(days=1, minutes=20))
    jobs.tick(slot - timedelta(days=1))
    job = [j for j in jobs.recent(10) if j["kind"] == "race"][0]
    jobs.tick(slot - timedelta(minutes=60))
    first = races.get(1)["result"]
    job = jobs.get(job["id"])
    job["status"] = "booked"
    jobs.save(job)
    jobs.tick(slot - timedelta(minutes=59))
    assert races.get(1)["result"] == first and races.get(3) is None


def test_replies_pause_for_an_hour_when_instagram_refuses(monkeypatch, discord):
    from app.publish import instagram

    replies.add([{"comment_id": "x1", "platform": "instagram", "kind": "taken", "text": "hi", "race": 1, "pid": "p"}])

    def refuse(cid, text):
        raise RuntimeError("Instagram reply failed: (#4) Application request limit reached, action is blocked")

    monkeypatch.setattr(instagram, "reply", refuse)
    t = datetime.now(timezone.utc)
    assert replies.send_due(t) == 0
    q = replies.queue()
    assert q["items"] and q["paused_until"] and "paused" in discord[-1][0]
    monkeypatch.setattr(instagram, "reply", lambda cid, text: "r")
    assert replies.send_due(t + timedelta(minutes=30)) == 0
    assert replies.send_due(t + timedelta(minutes=61)) == 1


def test_themes_take_turns_when_there_are_two(monkeypatch):
    monkeypatch.setattr(settings, "racing_themes", ["pitwall", "other"])
    assert [jobs.theme_for(n) for n in (1, 2, 3)] == ["other", "pitwall", "other"]


# ------------------------------------------------------------------ the bets domain

DOMAIN = {"host": "race.onlydan.uk"}


def test_the_bets_domain_serves_only_racing_and_legal_pages():
    c = TestClient(app)
    race, out = _ran(1, [comment("c1", "amy", "4 250", 1)])
    _race(2)
    home = c.get("/", headers=DOMAIN)
    assert home.status_code == 200 and "Sixel Speedway" in home.text and "Race 2" in home.text
    assert c.get("/status", headers=DOMAIN).status_code == 404
    assert c.get("/dashboard", headers=DOMAIN).status_code == 404
    assert c.get("/privacy", headers=DOMAIN).status_code == 200
    page = c.get("/race/1", headers=DOMAIN)
    assert "Matches the seal" in page.text and race["seed"] in page.text and "@amy" in page.text
    open_page = c.get("/race/2", headers=DOMAIN)
    assert races.get(2)["seed"] not in open_page.text and races.get(2)["seal"] in open_page.text
    assert "§" in c.get("/p/amy", headers=DOMAIN).text
    found = c.get("/find?name=@AMY", headers=DOMAIN, follow_redirects=False)
    assert found.status_code == 303 and found.headers["location"] == "/p/amy"
    assert c.get("/p/nobody", headers=DOMAIN).status_code == 404
    # and none of it exists on the main domain
    assert c.get("/_racing/").status_code == 404 and c.get("/race/1").status_code == 404
    assert "Sixel Speedway" not in c.get("/p/amy").text


def test_opted_out_players_vanish_from_the_bets_pages():
    c = TestClient(app)
    _ran(1, [comment("c1", "amy", "4 250", 1)])
    privacy.opt_out("amy")
    assert c.get("/p/amy", headers=DOMAIN).status_code == 404
    assert "@amy" not in c.get("/race/1", headers=DOMAIN).text and "@amy" not in c.get("/", headers=DOMAIN).text


def test_racing_endpoints_need_the_token():
    c = TestClient(app)
    assert c.get("/racing/state").status_code == 401
    r = c.get("/racing/state", headers={"Authorization": f"Bearer {settings.api_token}"})
    assert r.status_code == 200 and r.json()["domain"] == "race.onlydan.uk"
