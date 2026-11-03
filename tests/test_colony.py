"""Farside's rules (app/colony/rules.py), the episode built from a day, and the fake week."""
from datetime import date, timedelta

from app.colony import dryrun, episode, rules
from app.render.colony import pixfont, scene
from app.render.colony.art import SAFE

D = date(2026, 11, 9)


def c(user, text, day=0, n=1):
    d = D + timedelta(days=day)
    return {"id": f"{user}{day}{n}", "user": user, "uid": f"u-{user}", "text": text,
            "at": f"{d}T09:{n:02d}:00+00:00", "platform": "instagram"}


def run(days):
    s = rules.new_state()
    out = []
    for i, (followers, comments, y) in enumerate(days):
        s, r = rules.apply_day(s, D + timedelta(days=i), comments, followers, y)
        out.append(r)
    return s, out


def test_first_comment_moves_you_in_and_a_day_applies_once():
    s, r = rules.apply_day(rules.new_state(), D, [c("nova.k", "hi")], 3)
    assert r["arrived"] == ["instagram:u-nova.k"] and s["settlers"]["instagram:u-nova.k"]["handle"] == "nova.k"
    s2, r2 = rules.apply_day(s, D, [c("other", "hi")], 50)
    assert s2 is s and r2 == r  # the same day again changes nothing


def test_streaks_raise_rank_and_a_missed_day_restarts_the_streak():
    days = [(5, [c("a", "x", i)], None) for i in range(3)] + [(5, [], None), (5, [c("a", "x", 4)], None)]
    s, reports = run(days)
    a = s["settlers"]["instagram:u-a"]
    assert reports[2]["ranked_up"] == [{"who": "instagram:u-a", "rank": "settler"}]
    assert a["rank"] == "settler" and a["streak"] == 1  # rank kept, streak restarted


def test_one_job_a_day_the_last_word_wins():
    s, r = rules.apply_day(rules.new_state(), D, [c("a", "I'll farm", n=1), c("a", "no, building", n=2)], 3)
    assert s["settlers"]["instagram:u-a"]["job"] == "build" and r["jobs"] == [{"who": "instagram:u-a", "job": "build"}]


def test_a_tagged_friend_who_turns_up_makes_a_recruit():
    s, reports = run([(3, [c("a", "come here @bee")], None), (4, [c("bee", "ok I'm here", 1)], None)])
    assert reports[1]["recruits"] == [{"by": "instagram:u-a", "friend": "instagram:u-bee"}]
    assert s["settlers"]["instagram:u-a"]["recruits"] == 1


def test_tagging_yourself_or_a_late_friend_doesnt_count():
    days = [(3, [c("a", "@a me")], None)] + [(3, [], None)] * 8 + [(3, [c("a2", "hi", 9)], None)]
    s, reports = run(days)
    assert not any(r["recruits"] for r in reports)


def test_milestones_unlock_and_the_busiest_job_goes_first():
    s = rules.new_state()
    s, r = rules.apply_day(s, D, [c("a", "tinker"), c("b", "tinker", n=2)], 30)
    # dome (build) is first in the tree, but two tinkerers put the condenser first
    assert r["unlocked"] == ["dome", "condenser", "greenhouse"] and s["building"]["id"] == "condenser"


def test_shares_saves_builders_and_slow_work_pay_for_the_build():
    s, r = rules.apply_day(rules.new_state(), D, [c("a", "build")], 5, {"shares": 6, "saves": 2})
    assert r["gained"] == {"shares": 6, "saves": 2, "builders": 1, "slow": rules.SLOW_WORK}
    assert s["building"]["paid"] == 6 + 2 + 1 + rules.SLOW_WORK


def test_stock_is_capped_while_nothing_is_unlocked():
    s, _ = run([(1, [], {"shares": 500, "saves": 0})])
    assert s["stock"] == rules.STOCK_CAP


def test_unreadable_followers_keep_the_last_count():
    s, reports = run([(12, [], None), (None, [], None)])
    assert s["followers"] == 12 and reports[1]["joined"] == reports[1]["left"] == 0


def test_blocked_people_never_move_in_and_erase_removes_everything():
    s, r = rules.apply_day(rules.new_state(), D, [c("troll", "hi"), c("a", "@troll hi", n=2)], 3, blocked={"troll"})
    assert [st["handle"] for st in s["settlers"].values()] == ["a"]
    assert rules.erase(s, "a") and not s["settlers"] and not s["pending_mentions"]
    assert s["days"][D.isoformat()]["arrived"] == []


def test_the_fake_week_builds_in_order_and_every_episode_fits():
    s, reports = dryrun.simulate()
    assert s["built"] == ["dome", "condenser"] and s["building"]["id"] == "greenhouse"
    from app.render.colony import video
    for r in reports:
        ep = episode.build(s, r)
        assert 8 <= ep["duration"] <= 30
        for cap in ep["shots"][0]["spec"]["captions"]:
            for line in cap["lines"]:
                assert pixfont.width(line.replace("*", ""), scene.fit_scale(line.replace("*", ""))) <= SAFE[2] - SAFE[0], line
        assert video.frame_at(ep, ep["duration"] / 2).shape == (1920, 1080, 3)


def test_episode_shows_people_first():
    s, reports = dryrun.simulate()
    ep = episode.build(s, reports[1])  # day 2: arrivals, then jobs, then the build
    texts = [" ".join(c["lines"]) for c in ep["shots"][0]["spec"]["captions"]]
    assert "SIGNALS" in texts[0] and any("IS NOW" in t for t in texts[1:4])
    assert texts[-1] == "COMMENT TO *MOVE IN*"
