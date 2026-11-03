"""The scheduler: slots are claimed once, deploys never double-post, stuck work is picked up."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import lease, pipeline, store
from tests.helpers import ago


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(pipeline.social, "weekly_tick", lambda now: None)
    monkeypatch.setattr(pipeline.social, "avatar_tick", lambda now: None)


def job(job_id, quiz, status, publish_in_min=None, updated=None, **extra):
    now = datetime.now(timezone.utc)
    j = {"id": job_id, "spec": quiz, "status": status, "dry_run": False, "results": {}, "created_at": ago(1),
         "slot": "2026-10-24" if publish_in_min is not None else None,
         "publish_at": (now + timedelta(minutes=publish_in_min)).isoformat() if publish_in_min is not None else None,
         **extra}
    store.save_job(j)
    if updated:  # save_job stamps updated_at; backdate it
        jobs = store._read("jobs.json", {})
        jobs[job_id]["updated_at"] = updated
        store._write("jobs.json", jobs)
    return j


def queued():
    return sorted(pipeline._queue.queue)  # order between different jobs doesn't matter


def test_due_slots_claimed_once(quiz):
    job("render-me", quiz, "booked", publish_in_min=30)  # inside the 45-minute render lead
    job("too-early", quiz, "booked", publish_in_min=120)
    job("post-me", quiz, "scheduled", publish_in_min=-1)
    pipeline.tick()
    pipeline.tick()
    assert queued() == [("publish", "post-me"), ("render", "render-me")]  # once each, despite two ticks
    assert store.get_job("post-me")["status"] == "publishing"
    assert store.get_job("too-early")["status"] == "booked"


def test_slot_missed_while_down(quiz, discord):
    job("late", quiz, "scheduled", publish_in_min=-7 * 60)
    pipeline.tick()
    assert store.get_job("late")["status"] == "missed" and queued() == []
    assert any("skipped" in m for m, _ in discord)


def test_lease_newest_server_wins(monkeypatch):
    monkeypatch.setattr(lease, "ME", "old-server")
    lease.claim()
    assert lease.held()
    monkeypatch.setattr(lease, "ME", "new-server")
    lease.claim()  # a deploy starts the new server
    monkeypatch.setattr(lease, "ME", "old-server")
    assert not lease.held()  # the old one stands down...
    assert store._read("lease.json", {})["holder"] == "new-server"  # ...without taking it back


def test_restart_leaves_in_flight_work_alone(quiz):
    job("not-due", quiz, "rendering", publish_in_min=180)
    job("posting", quiz, "publishing")
    job("rendering-now", quiz, "rendering", publish_in_min=20)
    pipeline._recover()
    assert store.get_job("not-due")["status"] == "booked"  # waits for its slot again
    assert queued() == []  # the old server may still be on the others


def test_watchdog_picks_up_orphans(quiz, discord):
    job("orphan-render", quiz, "rendering", updated=ago(0.5))
    job("orphan-post", quiz, "publishing", updated=ago(0.5))
    job("fresh", quiz, "publishing", updated=ago(0.05))
    pipeline._rescue_orphans()
    pipeline._rescue_orphans()
    assert queued() == [("publish", "orphan-post"), ("render", "orphan-render")]
    assert store.get_job("orphan-render")["status"] == "queued"
    assert sum("picking it up again" in m for m, _ in discord) == 2


def test_submit_records_channel(quiz, monkeypatch):
    from app.spec import QuizSpec

    j = pipeline.submit(QuizSpec.model_validate(quiz), dry_run=True)
    assert j["channel"] == "main" and queued() == [("render", j["id"])]


@pytest.fixture
def publishing(quiz, monkeypatch):
    """A slot's video ready to post to both platforms; `outcome[platform]` is a result or an exception."""
    from app import health
    from app.config import settings
    from app.publish import instagram, youtube

    outcome, pinged = {}, []
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(settings, "platforms", ["instagram", "youtube"])
    monkeypatch.setattr(health, "ping", lambda name, fail=False: pinged.append((name, fail)))
    for name, mod in (("instagram", instagram), ("youtube", youtube)):
        monkeypatch.setattr(mod, "configured", lambda: True)

        def publish(video, spec, job, _n=name):
            o = outcome[_n]
            if isinstance(o, Exception):
                raise o
            return o
        monkeypatch.setattr(mod, "publish", publish)
    for name in ("after_publish", "link_previous"):
        monkeypatch.setattr(pipeline.cliffhanger, name, lambda job: None)
    monkeypatch.setattr(pipeline.themes, "after_publish", lambda job: None)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    (settings.videos_dir / "v.mp4").write_bytes(b"x")
    j = job("slot-1", quiz, "publishing", publish_in_min=-1, video="v.mp4", video_url="u", render={"duration": 50})
    return j, outcome, pinged, settings.videos_dir / "v.mp4"


def test_one_platform_failing_keeps_the_other_post_and_the_video_for_a_retry(publishing, monkeypatch):
    j, outcome, pinged, video = publishing
    outcome.update(instagram={"media_id": "M", "url": "u"}, youtube=RuntimeError("quota exceeded"))
    pipeline._publish(j)
    done = store.get_job("slot-1")
    assert done["status"] == "done" and done["results"]["instagram"]["ok"]
    assert done["results"]["youtube"] == {"ok": False, "error": "quota exceeded"}
    assert pinged == [("daily-post", False)] and video.exists()  # kept: the retry needs it
    assert pipeline.failures(done) == {"youtube": "quota exceeded"}

    outcome["instagram"] = AssertionError("must not post twice")
    outcome["youtube"] = {"video_id": "V", "url": "y"}
    assert pipeline.retry(done) == ["youtube"] and queued() == [("publish", "slot-1")]
    pipeline._publish(store.get_job("slot-1"))
    done = store.get_job("slot-1")
    assert all(r["ok"] for r in done["results"].values()) and not video.exists() and done["video_deleted"]
    assert pinged == [("daily-post", False)]  # a retry doesn't ping again


def test_every_platform_failing_pings_failure(publishing):
    j, outcome, pinged, video = publishing
    outcome.update(instagram=RuntimeError("down"), youtube=RuntimeError("down"))
    pipeline._publish(j)
    assert pinged == [("daily-post", True)] and video.exists()
