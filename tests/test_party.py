"""The story's party and the Voices: joining, places that follow turnout, leaving, credits, the way
and Rally reaching the roll, moderation (approve, or remove and make again) and privacy."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import privacy
from app.adventure import campaign, jobs, party, votes
from app.config import settings
from app.main import app
from app.publish import instagram

from test_adventure import ARC, _connect, _fake_cli, _posted_part4, _story_script  # noqa: F401  (fixtures below)
from test_adventure import client, ig, scheduled, story  # noqa: F401

AUTH = {"Authorization": "Bearer test-token"}


def t(*pairs, voters=None):
    """A tally from (user, text) pairs."""
    return votes.tally([{"user": u, "text": x} for u, x in pairs], ["Go left", "Go right"])


# ------------------------------------------------------------------ reading comments


def test_a_comment_can_vote_pick_a_way_and_join_at_once():
    r = t(("amy", "A sly join"), ("bob", "b boldly"), ("amy", "B wise"), ("cat", "leave"), ("dan", "a sly"), ("eve", "what a wise move"))
    assert r["counts"] == [2, 1] and r["ways"] == [1, 2, 1]  # amy's first way counts, not her second
    assert [j["key"] for j in r["joins"]] == ["amy"] and [j["key"] for j in r["leaves"]] == ["cat"]
    assert votes.top_way(r["ways"]) == 1 and votes.top_way([2, 2, 0]) is None and votes.top_way([0, 0, 0]) is None
    assert votes.party_word("I'd join you but the gate is scary and also I have a lot to say about it") is None


def test_rally_and_places_follow_turnout():
    assert [party.rally(n) for n in (0, 9, 10, 24, 25, 49, 50, 300)] == [0, 0, 1, 1, 2, 2, 3, 3]
    assert party.places_for([]) == 3 and party.places_for([1, 2]) == party.MIN_PLACES
    assert party.places_for([19, 19, 19]) == 5 and party.places_for([200]) == party.MAX_PLACES


# ------------------------------------------------------------------ the party


def joiners(n, prefix="p"):
    return t(*[(f"{prefix}{i}", "join") for i in range(n)])


def test_joiners_fill_places_in_order_with_one_weekly_draw_and_the_rest_wait():
    when = datetime(2030, 3, 6, 8, tzinfo=timezone.utc)
    out = party.update(2, joiners(6), when)  # 6 voters? no: joins aren't votes, so places stay at the minimum
    assert out["places"] == party.MIN_PLACES and out["members"] == 2 and out["waiting"] == 4
    hows = [j["how"] for j in out["joined"]]
    assert hows == ["weekly draw", "first in line"]
    assert party.update(2, joiners(6), when) == out  # the same episode again changes nothing
    s = party.load()
    names = [m["companion"]["name"] for m in s["members"]]
    assert len(set(names)) == 2 and all(m["companion"]["cls"] in party.CLASSES for m in s["members"])
    # a companion is the server's draw for that member, whatever they wrote
    assert party._draw("p1", set()) == party._draw("p1", set())


def test_members_who_stop_commenting_head_home_and_leave_frees_a_place():
    when = datetime(2030, 3, 6, 8, tzinfo=timezone.utc)
    party.update(2, t(("amy", "A join"), ("bob", "B join")), when)
    assert {m["key"] for m in party.load()["members"]} == {"amy", "bob"}
    party.update(3, t(("amy", "A")), when)                 # bob quiet once
    party.update(4, t(("amy", "B")), when)                 # twice
    out = party.update(5, t(("amy", "A"), ("cat", "join")), when)  # three times: home
    assert [l["reason"] for l in out["left"]] == ["inactive"] and out["left"][0]["handle"] == "bob"
    assert {m["key"] for m in party.load()["members"]} == {"amy", "cat"}
    out = party.update(6, t(("amy", "leave")), when)
    assert out["left"][0]["reason"] == "left" and [m["key"] for m in party.load()["members"]] == ["cat"]


def test_offensive_and_opted_out_names_never_join_and_opting_out_leaves():
    when = datetime(2030, 3, 6, 8, tzinfo=timezone.utc)
    privacy.opt_out("nope")
    party.update(2, t(("shitlord", "join"), ("nope", "join"), ("amy", "join")), when)
    assert [m["key"] for m in party.load()["members"]] == ["amy"] and not party.load()["queue"]
    privacy.opt_out("amy")
    out = party.update(3, t(("amy", "A")), when)
    assert out["left"][0] == {"name": out["left"][0]["name"], "handle": None, "reason": "opted out"}
    assert not party.load()["members"] and party.load()["past"][-1]["user"] is None


def test_erasure_and_retention_remove_usernames_but_keep_the_story():
    when = datetime(2030, 3, 6, 8, tzinfo=timezone.utc)
    party.update(2, t(("amy", "join"), ("bob", "join")), when)
    party.credit(2, "adv-x", "rolled_by", "amy")
    assert privacy.erase("@Amy") >= 2
    s = party.load()
    assert [m["key"] for m in s["members"]] == ["bob"] and not s["credits"]
    assert s["past"][-1]["companion"]["name"] and s["past"][-1]["user"] is None
    party.update(3, t(("bob", "leave")), when)
    party.credit(3, "adv-y", "rolled_by", "bob")
    s = party.load()
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    s["past"][-1]["left_at"] = old
    s["credits"][-1]["at"] = old
    party.save(s)
    assert privacy.anonymise_old() >= 2
    s = party.load()
    assert all(p["user"] is None for p in s["past"]) and not s["credits"]


def test_the_ai_writer_only_ever_gets_story_data():
    party.update(2, t(("amy_secret", "join")), datetime(2030, 3, 6, 8, tzinfo=timezone.utc))
    out = party.story_party(party.spec_party())
    assert out and "amy" not in json.dumps(out).lower() and set(out[0]) == {"slot", "name", "cls"}


# ------------------------------------------------------------------ the episode


@pytest.fixture
def episode(story, monkeypatch):
    """Episode 1 prepared from comments with votes, ways and joins."""
    (rendered, posted), seen = story
    monkeypatch.setattr(instagram, "comments", lambda media: [
        {"user": "ann", "text": "b sly join"}, {"user": "bob", "text": "B! sly"}, {"user": "cat", "text": "a bold"},
        {"user": "dan", "text": "join"}])
    campaign.accept(ARC)
    slot = datetime(2030, 3, 7, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    first = jobs._book_next(_posted_part4(slot))
    jobs.tick(datetime.fromisoformat(first["publish_at"]) - timedelta(minutes=60))
    return jobs.get(first["id"]), rendered, seen


def test_the_episode_gets_the_party_credits_and_the_way_and_names_need_a_look(episode, discord):
    job, rendered, seen = episode
    assert job["status"] == "scheduled", job.get("error")
    spec = job["spec"]
    assert {c["handle"] for c in spec["party"]} == {"ann", "dan"} and all(c["name"] and c["cls"] for c in spec["party"])
    assert spec["credits"]["rolledBy"] in ("ann", "bob", "cat")
    assert spec["voices"] == {"ways": [1, 2, 0], "way": "sly", "voters": 3}
    ctx = [p for cmd, p in seen if cmd == "resolve"][-1]["ctx"]
    assert ctx["way"] == "sly" and ctx["rally"] == 0  # 3 voters: no Rally yet
    assert job["votes"]["joins"] == 2 and "ann" not in json.dumps(job["votes"])  # the episode keeps totals only
    assert {i["status"] for i in job["moderation"]} == {"pending"} and len(job["moderation"]) == 3
    assert any("shown for the first time" in m for m, _ in discord)


def test_remove_makes_the_episode_again_without_that_name_and_approve_sticks(episode, client, discord):
    job, rendered, _ = episode
    n = len(rendered)
    r = client.post(f"/adventure/moderation/{job['id']}/remove?key=ann", headers=AUTH)
    assert r.status_code == 200
    job = jobs.get(job["id"])
    assert job["status"] == "scheduled" and len(rendered) == n + 1
    assert "ann" not in {c["handle"] for c in job["spec"]["party"]} and "ann" in party.load()["blocked"]
    assert any("made again without @ann" in m for m, _ in discord)
    assert client.post(f"/adventure/moderation/{job['id']}/approve?key=*", headers=AUTH).status_code == 200
    assert party.approved("dan") and all(i["status"] in ("approved", "removed") for i in jobs.get(job["id"])["moderation"])
    q = client.get("/adventure/moderation", headers=AUTH).json()
    assert q[0]["job"] == job["id"] and {i["status"] for i in q[0]["items"]} == {"approved", "removed"}
    assert client.post(f"/adventure/moderation/{job['id']}/remove?key=zed", headers=AUTH).status_code == 409
    assert client.post(f"/adventure/moderation/{job['id']}/remove?key=dan").status_code == 401


def test_posting_credits_the_roll_and_the_chronicle_shows_it(episode, client):
    job, _, _ = episode
    jobs.tick(datetime.fromisoformat(job["publish_at"]))
    assert jobs.get(job["id"])["status"] == "done"
    assert party.load()["credits"][-1]["user"] == job["credits"]["rolledBy"]
    page = TestClient(app).get("/chronicle")
    assert page.status_code == 200 and "@ann" in page.text and f"@{job['credits']['rolledBy']}" in page.text
    assert "join" in TestClient(app).get("/privacy").text
