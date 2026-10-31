"""Numbers for every channel: each post fetched as its own channel, the channels' own counts (votes,
bets) alongside, the per-channel API and the summary."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import channels, metrics, store
from app.adventure import jobs as adv
from app.main import app
from app.racing import jobs as rjobs, races

from helpers import ago, posted

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def fetched(monkeypatch):
    """Instagram and YouTube metrics faked; records which channel's account each fetch ran as."""
    from app.publish import instagram, youtube

    calls = []
    for mod in (instagram, youtube):
        monkeypatch.setattr(mod, "configured", lambda: True)

    def ig(media_id):
        calls.append(("instagram", media_id, channels.current.get()))
        return {"views": 200, "likes": 4, "comments": 2, "shares": 1, "saves": 0, "avg_watch_s": 12.0}

    def yt(video_id, published):
        calls.append(("youtube", video_id, channels.current.get()))
        return {"views": 50, "likes": 1, "comments": 0}

    monkeypatch.setattr(instagram, "metrics", ig)
    monkeypatch.setattr(youtube, "metrics", yt)
    return calls


def ig_result(media):
    return {"instagram": {"ok": True, "media_id": media, "url": f"https://instagram.com/reel/{media}"}}


def adventure_posts():
    first = {"id": "adv-1", "kind": "episode0", "spec": {"kind": "episode0", "part": 1}, "channel": channels.ADVENTURE,
             "status": "done", "publish_at": ago(30), "published_at": ago(30), "results": ig_result("A1"),
             "render": {"duration": 40.0}, "voice_clip": {"chars": 90}, "script": {"options": ["a", "b", "c"], "default": 0}}
    second = {"id": "adv-2", "kind": "episode0", "spec": {"kind": "episode0", "part": 2}, "channel": channels.ADVENTURE,
              "status": "done", "publish_at": ago(6), "published_at": ago(6), "results": ig_result("A2"),
              "render": {"duration": 48.0}, "voice_clip": {"skipped": "budget"},
              "votes": {"from_job": "adv-1", "counts": [3, 1, 0], "voters": 4, "comments": 7, "how": "votes"}}
    booked = {"id": "adv-3", "spec": {"kind": "episode0", "part": 3}, "status": "booked", "publish_at": ago(-10), "results": {}}
    for j in (first, second, booked):
        adv.save(j)


def racing_posts():
    races.save({"no": 1, "status": "run", "format": "oval", "commenters": ["p1", "p2"], "new_players": 2, "comments_read": 5,
                "bets": [{"pid": "p1", "stake": 250}, {"pid": "p1", "stake": 100}, {"pid": "p2", "stake": 50},
                         {"pid": "p3", "stake": 0, "refused": "no balance"}]})
    races.save({"no": 2, "status": "open", "format": "rally"})
    launch = {"id": "race-launch", "kind": "launch", "card": 1, "run": None, "theme": "pitwall", "channel": channels.RACING,
              "status": "done", "publish_at": ago(50), "published_at": ago(50), "results": ig_result("R1"),
              "render": {"duration": 40.0}, "metrics": {"24h": {"views": 321, "likes": 9, "comments": 6}}}
    race = {"id": "race-1", "kind": "race", "card": 2, "run": 1, "theme": "pitwall", "channel": channels.RACING,
            "status": "done", "publish_at": ago(3), "published_at": ago(3), "results": ig_result("R2"), "render": {"duration": 42.0}}
    preview = {"id": "race-preview", "kind": "preview", "theme": "pitwall", "status": "done", "results": {}, "publish_at": ago(1)}
    for j in (launch, race, preview):
        rjobs.save(j)


def test_every_channel_is_collected_as_itself(fetched, quiz):
    posted("q-1", quiz, hours_ago=26)
    adventure_posts()
    racing_posts()
    assert metrics.collect() == 6  # quiz on two platforms, two adventure parts, two races
    as_channel = {media: ch for _, media, ch in fetched}
    assert as_channel == {"M-q-1": "main", "V-q-1": "main", "A1": "adventure", "A2": "adventure", "R1": "racing", "R2": "racing"}

    rows = {r["job_id"]: r for r in metrics.report(None)}
    assert set(rows) == {"q-1", "adv-1", "adv-2", "race-launch", "race-1"}  # nothing booked, no previews
    assert [r["job_id"] for r in metrics.report()] == ["q-1"]  # the default stays the quiz, for its review

    a1 = rows["adv-1"]
    assert a1["channel"] == "adventure" and a1["title"] == "Episode 0, part 1"
    assert a1["extra"] == {"votes": 4, "voters": 4, "comments_read": 7}  # counted on the part after it
    assert a1["tags"]["voice"] == "yes" and rows["adv-2"]["tags"]["voice"] == "no"
    assert a1["platforms"]["instagram"]["latest"]["watched_pct"] == 30.0  # 12 s of 40 s
    assert rows["adv-2"]["extra"] == {}  # still being voted on
    assert set(a1["platforms"]["instagram"]["snapshots"]) == {"1h", "24h"}

    launch, race = rows["race-launch"], rows["race-1"]
    assert launch["extra"] == {"bets": 3, "bettors": 2, "staked": 400, "new_players": 2, "comments_read": 5}
    assert race["extra"] == {}  # its card is still open
    assert race["tags"]["race_format"] == "oval" and race["tags"]["card_format"] == "rally"
    # the 24h numbers racing took itself are kept, not replaced by today's
    assert launch["platforms"]["instagram"]["snapshots"]["24h"]["views"] == 321
    assert launch["platforms"]["instagram"]["latest"]["views"] == 200

    assert rjobs.metrics_by_theme()["pitwall"] == {"posts": 1, "views": 321, "comments": 6, "likes": 9, "bets": 3,
                                                   "avg_views": 321.0, "avg_comments": 6.0, "avg_likes": 9.0, "avg_bets": 3.0}
    fetched.clear()
    assert metrics.collect() == 0 and not fetched  # nothing due again yet


def test_one_broken_channel_does_not_hide_the_rest(fetched, quiz, monkeypatch):
    posted("q-1", quiz, hours_ago=2)
    monkeypatch.setattr(metrics, "_racing_posts", lambda: 1 / 0)
    assert [p["id"] for p in metrics.posts()] == ["q-1"]


def test_api_by_channel_summary_and_reviews(fetched, quiz):
    posted("q-1", quiz, hours_ago=26)
    adventure_posts()
    racing_posts()
    metrics.collect()
    c = TestClient(app)
    assert [r["job_id"] for r in c.get("/metrics?channel=adventure", headers=AUTH).json()] == ["adv-2", "adv-1"]
    assert len(c.get("/metrics?channel=all", headers=AUTH).json()) == 5
    assert c.get("/metrics?channel=nope", headers=AUTH).status_code == 422

    s = c.get("/metrics/summary", headers=AUTH).json()
    assert s["main"]["posts"] == 1 and s["main"]["platforms"]["youtube"]["median_views_24h"] == 50
    assert s["adventure"]["posts"] == 2 and s["adventure"]["platforms"]["instagram"]["posts_with_24h"] == 1
    assert s["racing"]["platforms"]["instagram"]["median_views_24h"] == 321

    store._write("insights.json", [{"at": "2026-10-26T18:40:00Z", "week_of": "2026-10-19", "summary": "old quiz review"}])
    body = {"week_of": "2026-10-26", "summary": "racing review", "channel": "racing"}
    assert c.post("/insights", json=body, headers=AUTH).status_code == 201
    assert c.get("/insights/latest", headers=AUTH).json()["summary"] == "old quiz review"  # reviews from before channels count as the quiz's
    assert c.get("/insights/latest?channel=racing", headers=AUTH).json()["summary"] == "racing review"
    assert c.get("/insights/latest?channel=adventure", headers=AUTH).status_code == 404
    assert c.post("/insights", json={**body, "channel": "nope"}, headers=AUTH).status_code == 422
