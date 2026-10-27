"""Adventure jobs: render (and post) a video now, or book it for a time.

A booked job is prepared RENDER_LEAD before its slot: for a part that follows an earlier post, the
votes on that post are counted first (votes close as preparation starts), then it is voiced and
rendered; it posts at the slot. Episode 0 runs as a series: each part, once posted, books the next
for the same time the next day; after part 4 the story episodes follow the same way, each day's node
picked by the votes from the weekly arcs (campaign.py) and rolled for when the votes close. Jobs are small JSON files in DATA_DIR/adventure/jobs; one adventure
render runs at a time, and only the server holding the deploy lease schedules."""
from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import channels, lease, notify, privacy, store
from ..config import settings
from ..publish import instagram
from . import campaign, votes, voice

log = logging.getLogger(__name__)
_render_lock = threading.Lock()

RENDER_LEAD = timedelta(minutes=60)  # 08:00 for a 09:00 post: votes close, then voice and render
MISSED_AFTER = timedelta(hours=6)
WORKING = ("preparing", "voicing", "rendering", "publishing")
FEAR_KEYS = ["skeleton", "goblin", "wraith"]
CLASS_KEYS = ["fighter", "rogue", "wizard"]


class NotConnected(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def _jobs_dir() -> Path:
    d = settings.data_dir / "adventure" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(job: dict) -> None:
    p = _jobs_dir() / f"{job['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1))
    tmp.replace(p)


def get(job_id: str) -> dict | None:
    p = _jobs_dir() / f"{job_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def recent(limit: int = 20) -> list[dict]:
    files = sorted(_jobs_dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    return [json.loads(f.read_text()) for f in files]


def _node(*args: str, timeout: int = 900) -> dict:
    """Run the renderer CLI; it prints a one-line JSON summary on stdout."""
    env = {**os.environ, "ADVENTURE_CACHE": str(settings.data_dir / "adventure" / "maps")}
    cmd = ["node", "--import", "tsx", "packages/renderer/src/cli.ts", *args]
    r = subprocess.run(cmd, cwd=settings.adventure_dir, env=env, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["renderer failed"])[-1][:500])
    return json.loads(r.stdout.strip().splitlines()[-1])


def script(spec: dict) -> dict:
    """The voice-over script, caption, options and default for a spec (also validates the spec)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        return _node("script", fh.name, timeout=60)
    finally:
        os.unlink(fh.name)


def can_publish() -> str | None:
    """Why the adventure channel can't post right now, or None."""
    if not settings.publish_enabled:
        return "PUBLISH_ENABLED is off"
    if not instagram.configured():
        return "the Instagram app isn't configured"
    with channels.use(channels.ADVENTURE):
        if not store.get_tokens("instagram"):
            return "Instagram isn't connected for the adventure channel: /oauth/instagram/start?channel=adventure"
    return None


def _new_id() -> str:
    return f"adv-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"


def submit(spec: dict, use_voice: bool = True, publish: bool = False, at: datetime | None = None,
           series: bool = False) -> dict:
    """Render now (and post if `publish`), or book it to post at `at` (UTC). `series` books each
    following Episode 0 part from this one's votes."""
    if publish and (why := can_publish()):
        raise NotConnected(why)
    if at is not None and at <= now() + timedelta(minutes=5):
        raise ValueError("pick a time at least 5 minutes ahead")
    job = {"id": _new_id(), "kind": spec.get("kind"), "spec": spec, "voice": use_voice, "publish": publish or at is not None,
           "series": series, "channel": channels.ADVENTURE, "created_at": store.now_iso(), "results": {}}
    job["script"] = script(spec)  # fails fast on a bad spec
    if at is not None:
        job.update(status="booked", publish_at=at.isoformat())
        save(job)
        return job
    job["status"] = "queued"
    save(job)
    threading.Thread(target=_run_now, args=(job,), daemon=True, name=f"adventure-{job['id']}").start()
    return job


def cancel(job: dict) -> None:
    job.update(status="cancelled")
    save(job)


# ------------------------------------------------------------------ the steps


def _resolve_votes(job: dict) -> None:
    """For a part that follows an earlier post: count that post's votes and build this part's spec."""
    prev = get(job["from_job"])
    if not prev:
        raise RuntimeError(f"previous post {job['from_job']} not found")
    opts, default = prev["script"]["options"], prev["script"]["default"]
    media = (prev.get("results", {}).get("instagram") or {}).get("media_id")
    comments, error = [], None
    if media:
        try:
            own, out = instagram.own_name().lower(), privacy.opted_out()  # one opt-out list for both channels
            comments = [c for c in instagram.comments(media) if c["user"].lower() != own and privacy._key(c["user"]) not in out]
        except Exception as e:
            error = str(e)[:300]
    else:
        error = "the previous part has no Instagram post"
    t = votes.tally(comments, opts)
    pick, how = votes.decide(t["counts"], default, prev["id"])
    if error:
        how = "default (comments unreadable)" if not any(t["counts"]) else how
        notify.send(f":warning: **Adventure**: couldn't read the votes on `{prev['id']}` ({error}); going with {'ABC'[pick]}")
    job["votes"] = {"from_job": prev["id"], "counts": t["counts"], "comments": t["comments"], "voters": len(t["voters"]),
                    "pick": pick, "how": how, "option": opts[pick], "counted_at": store.now_iso()}
    if job["kind"] == "story":
        job.update(campaign.build_story(prev, pick, t["counts"]))
    else:
        job["spec"] = next_spec(prev["spec"], pick, t["counts"])
        campaign.note_episode0(job["spec"])
    job["script"] = script(job["spec"])
    counts = " · ".join(f"{'ABC'[i]} {n}" for i, n in enumerate(t["counts"]))
    roll = (job["spec"].get("check") or {}).get("roll")
    rolled = f"\nRolled {roll['total']} vs DC {job['spec']['check']['dc']}: {'success' if roll['ok'] else 'failure'}" if roll else ""
    notify.send(f":ballot_box: **Adventure votes** on {_title(prev)}: {counts} "
                f"({t['comments']} comments) → **{'ABC'[pick]}: {opts[pick]}** ({how}){rolled}")


def next_spec(prev: dict, pick: int, counts: list[int]) -> dict:
    """The Episode 0 part after `prev`, given the winning option."""
    part = prev["part"] + 1
    recap = {"pick": pick, "votes": counts}
    spec = {"kind": "episode0", "part": part, "seed": prev.get("seed", 12), "recap": recap, "fear": prev.get("fear", "skeleton")}
    if part == 2:
        spec["fear"] = FEAR_KEYS[pick]
    elif part == 3:
        spec["hero"] = {"cls": CLASS_KEYS[pick], "look": 0}
    elif part == 4:
        spec["hero"] = {"cls": prev["hero"]["cls"], "look": pick}
    return spec


def _title(job: dict) -> str:
    spec = job["spec"]
    return f"Episode {spec['ep']}" if spec.get("kind") == "story" else f"Episode 0 part {spec.get('part')}"


def _voice(job: dict) -> list[str]:
    """The narration as renderer arguments: one clip for Episode 0; for a story episode the day's
    own clip plus the reusable check, roll and sign-off lines (cached by their words, so a line said
    before costs nothing). Nothing at all if this month's budget can't cover it."""
    s = job["script"]
    if job["spec"].get("kind") == "story":
        lines = {"daily": s["text"], "check": s.get("check"), "roll": s.get("roll"), "tail": s.get("tail")}
    else:
        lines = {"audio": s["text"]}
    args, chars, new = [], 0, 0
    for key, text in lines.items():
        if not text:
            continue
        mp3, align, made = voice.clip(text)
        chars, new = chars + len(text), new + (len(text) if made else 0)
        if key in ("audio", "daily"):
            try:
                mp3, align = voice.tighten(mp3, align, settings.adventure_max_pause)
            except Exception:  # long pauses are better than no video
                log.exception("adventure voice: could not shorten pauses")
            args += [f"--{key}", str(mp3), "--align", str(align)]
        else:
            args += [f"--{key}", str(mp3)]
    job["voice_clip"] = {"chars": chars, "new_chars": new, "new": new > 0, "month_spent": voice.spent()}
    return args


def _render(job: dict) -> None:
    """Voice (if wanted and affordable) and render the job's spec."""
    spec = job["spec"]
    audio: list[str] = []
    if job["voice"]:
        job["status"] = "voicing"
        save(job)
        try:
            audio = _voice(job)
        except voice.OutOfBudget as e:
            job["voice_clip"] = {"skipped": str(e)}  # goes out without narration
    job["status"] = "rendering"
    save(job)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    out = settings.videos_dir / f"{job['id']}-{secrets.token_urlsafe(8)}.mp4"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        workers = str(max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4")))))
        summary = _node(fh.name, "--out", str(out), "--workers", workers, *audio)
    finally:
        os.unlink(fh.name)
    job.update(video=out.name, video_url=f"{settings.public_base_url}/media/{out.name}", render=summary)
    save(job)


def _publish(job: dict) -> None:
    """Post the Reel to the adventure channel's Instagram, then comment the options under it."""
    s = job["script"]
    try:
        res = {"ok": True, **instagram.publish_reel(job["video_url"], s["caption"])}
    except Exception as e:
        log.exception("adventure post failed")
        job["results"]["instagram"] = {"ok": False, "error": str(e)[:500]}
        return
    try:
        res["comment_id"] = instagram.comment(res["media_id"], s["comment"])
    except Exception as e:  # the post is out; the options are in the caption too
        res["comment_error"] = str(e)[:300]
    job["results"]["instagram"] = res
    job["published_at"] = store.now_iso()


def _report(job: dict) -> None:
    spec, summary = job["spec"], job.get("render") or {}
    vc = job.get("voice_clip") or {}
    said = (f"voice {vc['chars']} chars ({vc.get('new_chars', 0)} new; {vc['month_spent']}/{settings.adventure_voice_budget} this month)"
            if "chars" in vc else f"no voice ({vc.get('skipped', 'off')})")
    ig = job["results"].get("instagram")
    if job.get("publish") and ig:
        title = "Adventure post" if ig.get("ok") else "Adventure post FAILED"
        posted = f"\nPosted to @{settings.adventure_handle}: {ig.get('url') or ig['media_id']}" if ig.get("ok") else f"\n{ig['error']}"
    elif job.get("status") == "scheduled":
        title, posted = "Adventure ready", f"\nPosts at {_local(job['publish_at'])}"
    else:
        title, posted = "Adventure preview", ""
    video = settings.videos_dir / job["video"] if job.get("video") else None
    what = f"{_title(job)} ({job['node']})" if job.get("node") else _title(job)
    dead = "\n:skull: The hero falls in this one." if spec.get("dead") else ""
    notify.send(f":crossed_swords: **{title}** `{job['id']}`: {what}{dead}, "
                f"{summary.get('duration', 0):.1f}s, rendered in {summary.get('seconds', 0):.0f}s, {said}{posted}\n{job.get('video_url', '')}",
                attach=video if title != "Adventure post" else None)


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(settings.tz).strftime("%a %d %b %H:%M")


def _fail(job: dict, e: Exception, step: str) -> None:
    log.exception("adventure job %s failed during %s", job["id"], step)
    job.update(status="failed", error=f"{step}: {e}"[:1000])
    save(job)
    notify.send(f":warning: **Adventure**: `{job['id']}` failed during {step}: {e}")


def _run_now(job: dict) -> None:
    try:
        with _render_lock, channels.use(channels.ADVENTURE):  # threads don't inherit the channel
            _render(job)
            if job.get("publish"):
                job["status"] = "publishing"
                save(job)
                _publish(job)
            job.update(status="done", finished_at=store.now_iso())
            save(job)
            _report(job)
    except Exception as e:
        _fail(job, e, job.get("status", "render"))


def _prepare(job: dict) -> None:
    """A booked job, an hour before its slot: count votes, voice, render; then wait for the slot."""
    try:
        with _render_lock, channels.use(channels.ADVENTURE):
            if job.get("from_job"):
                _resolve_votes(job)
            _render(job)
            job["status"] = "scheduled"
            save(job)
            _report(job)
    except campaign.NoArc as e:
        job.update(status="failed", error=f"no story to play: {e}", error_code="no_arc")
        save(job)
        notify.send(f":warning: **Adventure**: `{job['id']}` has no story to play ({e}). Submit the arc (the weekly "
                    f"routine, POST /adventure/arc) before {_local(job['publish_at'])} and it's prepared straight away.")
    except Exception as e:
        _fail(job, e, "preparing")


def _post(job: dict) -> None:
    try:
        with channels.use(channels.ADVENTURE):
            _publish(job)
            ok = (job["results"].get("instagram") or {}).get("ok")
            job.update(status="done" if ok else "failed", finished_at=store.now_iso())
            if not ok:
                job["error"] = job["results"]["instagram"]["error"]
            if ok and job["spec"].get("kind") == "story":
                campaign.commit(job)
            save(job)
            _report(job)
            if ok and job.get("series"):
                _book_next(job)
    except Exception as e:
        _fail(job, e, "publishing")


def _book_next(prev: dict) -> dict | None:
    """Tomorrow's episode, same local time: the next Episode 0 part, or the next story episode."""
    spec = prev["spec"]
    if spec.get("dead"):
        notify.send(":skull: **Adventure**: the hero has fallen. Nothing more is booked: a new hero's Episode 0 "
                    "(not built yet) has to come next.")
        return None
    if spec.get("kind") == "episode0" and spec["part"] < 4:
        kind, nxt, name = "episode0", {"kind": "episode0", "part": spec["part"] + 1}, f"Episode 0 part {spec['part'] + 1}"
    else:
        ep = campaign.state()["ep"] + 1
        kind, nxt, name = "story", {"kind": "story"}, f"Episode {ep}"
    when = datetime.fromisoformat(prev["publish_at"]) + timedelta(days=1)
    local = when.astimezone(settings.tz)  # same local time tomorrow, across clock changes
    prev_local = datetime.fromisoformat(prev["publish_at"]).astimezone(settings.tz)
    when = local.replace(hour=prev_local.hour, minute=prev_local.minute).astimezone(timezone.utc)
    job = {"id": _new_id(), "kind": kind, "spec": nxt, "from_job": prev["id"],
           "voice": prev.get("voice", True), "publish": True, "series": True, "channel": channels.ADVENTURE,
           "created_at": store.now_iso(), "results": {}, "script": None, "status": "booked", "publish_at": when.isoformat()}
    save(job)
    notify.send(f":calendar: **Adventure**: {name} booked for {_local(job['publish_at'])}; "
                f"votes on {_title(prev)} close at {_local((when - RENDER_LEAD).isoformat())}.")
    if kind == "story" and not campaign.covers_next(prev):
        notify.send(f":warning: **Adventure**: no arc says where {name} goes yet. The weekly routine has to submit "
                    f"one (POST /adventure/arc) before {_local((when - RENDER_LEAD).isoformat())}.")
    return job


def retry_waiting() -> list[str]:
    """Story jobs that failed for want of an arc go back on the schedule once one arrives."""
    again = []
    for job in recent(200):
        if job.get("error_code") == "no_arc" and job.get("status") == "failed" \
                and now() - datetime.fromisoformat(job["publish_at"]) < MISSED_AFTER:
            job.update(status="booked", error=None, error_code=None)
            save(job)
            again.append(job["id"])
    return again


# ------------------------------------------------------------------ schedule


def tick(t: datetime | None = None) -> None:
    """Start whatever is due: preparation an hour ahead, posting at the slot."""
    t = t or now()
    for job in recent(200):
        if job.get("status") not in ("booked", "scheduled") or not job.get("publish_at"):
            continue
        due = datetime.fromisoformat(job["publish_at"])
        if t - due > MISSED_AFTER:
            job.update(status="missed", error=f"the server was not running at {due.isoformat()}")
            save(job)
            notify.send(f":warning: **Adventure**: `{job['id']}` missed its slot ({_local(job['publish_at'])})")
        elif job["status"] == "booked" and t >= due - RENDER_LEAD:
            job["status"] = "preparing"  # claimed before the thread starts, so the next tick skips it
            save(job)
            threading.Thread(target=_prepare, args=(job,), daemon=True, name=f"adventure-{job['id']}").start()
        elif job["status"] == "scheduled" and t >= due:
            job["status"] = "publishing"
            save(job)
            threading.Thread(target=_post, args=(job,), daemon=True, name=f"adventure-post-{job['id']}").start()


def recover() -> None:
    """After a restart: unfinished preparation starts again; a post that was mid-flight is not
    retried blindly (it may have gone out), it's flagged."""
    for job in recent(200):
        st = job.get("status")
        if st in ("preparing", "voicing", "rendering") and job.get("publish_at"):
            job["status"] = "booked"
            save(job)
        elif st in WORKING + ("queued",):
            job.update(status="failed", error=f"the server restarted during {st}")
            save(job)
            if st == "publishing":
                notify.send(f":warning: **Adventure**: the server restarted while posting `{job['id']}`; check "
                            f"@{settings.adventure_handle} before retrying.")


def _loop() -> None:
    while True:
        try:
            if lease.held():
                tick()
        except Exception:
            log.exception("adventure tick failed")
        time.sleep(30)


def start() -> None:
    recover()
    threading.Thread(target=_loop, daemon=True, name="adventure-schedule").start()
