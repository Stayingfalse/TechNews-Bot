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
