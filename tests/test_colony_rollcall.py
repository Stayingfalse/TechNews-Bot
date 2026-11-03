"""Farside's roll call (app/colony/rollcall.py): everyone's settler, tagged where they stand."""
from datetime import date, datetime, timezone

from app import channels, store
from app.colony import dryrun, jobs, rollcall, state
from app.config import settings
from app.publish import instagram
from app.render.colony import rollcall as art


def colony(n=12):
    s, _ = dryrun.simulate()
    for i in range(n):
        s["settlers"][f"instagram:x{i}"] = {"handle": f"extra{i}", "joined": f"2026-11-{10 + i % 9:02d}", "rank": "newcomer",
                                             "look": {"hat": "crown"} if i % 2 else {}}
    state.save(s)
    return s


def test_every_settler_is_drawn_and_tagged_on_their_own_spot():
    s = colony()
    slides, tags, shown = rollcall.make(s, date(2026, 11, 20))
    assert shown == len(s["settlers"]) and len(slides) == 1 + -(-shown // art.PER_SLIDE)  # cover + grids
    assert slides[0].size == (1080, 1350) and tags[0] == []
    spots = [t for ts in tags for t in ts]
    assert sorted(t["username"] for t in spots) == sorted(st["handle"] for st in s["settlers"].values())
    for ts in tags:
        assert len(ts) <= 20 and len({(t["x"], t["y"]) for t in ts}) == len(ts)
        assert all(0 < t["x"] < 1 and 0 < t["y"] < 1 for t in ts)


def test_blocked_and_opted_out_people_are_left_out():
    from app import privacy

    s = colony(0)
    privacy.opt_out("nova.k")
    s["blocked"] = ["mossbyte"]
    handles = {p["handle"] for p in rollcall.who(s)}
    assert "nova.k" not in handles and "mossbyte" not in handles and "oldbarrel" in handles


def test_it_posts_with_tags_and_names_anyone_whose_tags_were_refused(monkeypatch, discord):
    colony()
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(instagram, "configured", lambda: True)
    store.set_tokens("instagram", {"access_token": "t", "user_id": "9", "expires_at": 9e12}, channel=channels.COLONY)
    sent, comments = {}, []

    def publish(slides, cap):
        sent["slides"], sent["caption"] = slides, cap
        return {"media_id": "m1", "url": "u", "untagged": [slides[1][0]]}

    monkeypatch.setattr(instagram, "publish_tagged", publish)
    monkeypatch.setattr(instagram, "comment", lambda mid, text: comments.append(text))
    res = rollcall.run()
    assert res["posted"] and len(sent["slides"]) == res["slides"] and "Roll call" in sent["caption"]
    assert comments and comments[0].startswith("Couldn't tag everyone") and len(res["untagged"]) == len(sent["slides"][1][1])
    assert jobs.channel_state()["last_rollcall"]


def test_it_comes_round_every_few_days_after_the_set_time():
    jobs._set_channel(started=True, start_date="2026-11-03")
    at = lambda d, h, m: datetime(2026, 11, d, h, m, tzinfo=settings.tz).astimezone(timezone.utc)  # noqa: E731
    assert not rollcall.due(at(5, 13, 0))  # two days in
    assert not rollcall.due(at(6, 12, 0))  # three days in, but before 12:40
    assert rollcall.due(at(6, 12, 41))
    jobs._set_channel(last_rollcall="2026-11-06")
    assert not rollcall.due(at(8, 13, 0)) and rollcall.due(at(9, 13, 0))


def test_tagged_publishing_falls_back_to_no_tags_for_a_refused_slide(monkeypatch):
    made = []

    def create(params, tries=3):
        if "user_tags" in params and "bad" in params["image_url"]:
            raise RuntimeError("Instagram container error: invalid user tag")
        made.append(params)
        return f"c{len(made)}"

    monkeypatch.setattr(instagram, "_create", create)
    monkeypatch.setattr(instagram, "_wait", lambda c, t: None)
    monkeypatch.setattr(instagram, "_publish_container", lambda c: {"media_id": "m"})
    monkeypatch.setattr(instagram.time, "sleep", lambda s: None)
    store.set_tokens("instagram", {"access_token": "t", "user_id": "9"})
    out = instagram.publish_tagged([("http://x/good.jpg", [{"username": "a", "x": .5, "y": .5}]),
                                    ("http://x/bad.jpg", [{"username": "b", "x": .5, "y": .5}])], "cap")
    assert out["untagged"] == ["http://x/bad.jpg"]
    assert "user_tags" in made[0] and "user_tags" not in made[1] and made[-1]["media_type"] == "CAROUSEL"
