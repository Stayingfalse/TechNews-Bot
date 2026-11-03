"""Whose request gets done (app/colony/picks.py)."""
from datetime import date

from app.colony import picks

DAY = date(2026, 11, 16)


def colony(n, over=None):
    s = {"settlers": {}}
    for i in range(n):
        s["settlers"][f"k{i}"] = {"handle": f"p{i}", "streak": 1, "rank": "newcomer", **(over or {}).get(i, {})}
    return s


def req(i, likes=0, day="2026-11-15", cid=None):
    return {"id": cid or f"c{i}", "settler": f"k{i}", "at": f"{day}T20:00:00+00:00", "likes": likes, "text": "can I"}


def test_most_liked_gets_the_first_spotlight():
    s = colony(5)
    out = picks.choose(s, [req(0, 2), req(1, 40), req(2, 5), req(3), req(4)], set(), DAY)
    assert out["spotlights"][0]["handle"] == "@p1"


def test_a_newcomer_with_no_likes_can_still_win_a_spotlight_and_the_draw_is_repeatable():
    s = colony(6)
    reqs = [req(i, likes=50 - i) for i in range(4)] + [req(4), req(5)]
    a = picks.choose(s, reqs, {"k4", "k5"}, DAY)
    b = picks.choose(s, reqs, {"k4", "k5"}, DAY)
    drawn = [r for r in a["spotlights"] if r["why"] == "newcomer draw"]
    assert len(drawn) == 1 and drawn[0]["key"] in {"k4", "k5"} and a["spotlights"] == b["spotlights"]


def test_whoever_waited_longest_gets_a_spotlight():
    s = colony(4)
    reqs = [req(0, 30), req(1, 20), req(2, 10), req(3, 0, day="2026-11-05")]
    spots = picks.choose(s, reqs, set(), DAY)["spotlights"]
    assert any(r["handle"] == "@p3" and r["why"] == "waited longest" for r in spots)


def test_waiting_and_loyalty_add_up_and_last_weeks_star_steps_back():
    s = colony(3, {1: {"streak": 9, "rank": "veteran"}, 2: {"featured_on": ["2026-11-14"]}})
    ranked = picks.choose(s, [req(0), req(1), req(2, likes=2)], set(), DAY)["ranked"]
    assert [r["handle"] for r in ranked][:2] == ["@p1", "@p0"] and ranked[-1]["handle"] == "@p2"


def test_grants_are_capped_and_everyone_else_gets_a_place_in_the_queue():
    s = colony(40)
    out = picks.choose(s, [req(i, likes=i) for i in range(40)], set(), DAY)
    assert len(out["grant"]) == picks.GRANT_MAX and len(out["queue"]) == 40 - picks.GRANT_MAX
    assert [q["position"] for q in out["queue"]] == list(range(1, 16))
    assert not {q["handle"] for q in out["queue"]} & {g["handle"] for g in out["grant"]}


def test_one_row_per_person_carrying_all_their_requests():
    s = colony(1)
    out = picks.choose(s, [req(0, cid="a"), req(0, likes=3, cid="b")], set(), DAY)
    assert len(out["ranked"]) == 1 and set(out["ranked"][0]["comment_ids"]) == {"a", "b"}
