"""Book → render shortly before the slot → publish → delete the video.

Booked quizzes are stored as specs only. A scheduler thread queues each one's render
RENDER_LEAD_MINUTES before its slot and its publish when the slot arrives; one worker thread runs
renders and publishes in order. Once every platform has the post, the video file is deleted, so
the disk only ever holds the next video or two. Job state lives in jobs.json, so a restart picks
up where it left off.
"""
from __future__ import annotations

import logging
import queue
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import channels, cliffhanger, health, lease, legal, metrics, notify, privacy, social, store, themes
from .config import settings
from .publish import LABELS, PUBLISHERS, refreshers
from .render.engine import render_video
from .render.voice import VoiceConfig
from .spec import QuizSpec

log = logging.getLogger(__name__)
_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()  # (action, job_id); action: render | publish

# booked: spec stored, not rendered yet; queued/rendering: render in progress;
# scheduled: rendered, waiting for its slot; publishing: going out now
ACTIVE = ("booked", "queued", "rendering", "scheduled", "publishing")  # still going to post
MISSED_AFTER = timedelta(hours=6)  # a slot more than this late (e.g. server was down) is skipped


def now() -> datetime:
    return datetime.now(timezone.utc)


def slot_time(day: date, at: str | None = None) -> datetime:
    """The UTC publish time for a local calendar day, at `at` (HH:MM, local) or POST_TIME."""
    h, m = (int(x) for x in (at or settings.post_time).split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=settings.tz).astimezone(timezone.utc)


def today_local() -> date:
    return now().astimezone(settings.tz).date()


def media_url(name: str) -> str:
    return f"{settings.public_base_url}/media/{name}"


def slot_key(job: dict) -> tuple[str, str]:
    """(local date, local HH:MM) of a booked job."""
    return job["slot"], job.get("slot_time") or settings.post_time


def submit(spec: QuizSpec, dry_run: bool = False, slot: date | None = None, at: str | None = None,
           platforms: list[str] | None = None) -> dict:
    job = {
        "id": f"{spec.id}-{secrets.token_hex(3)}",
        "spec": spec.model_dump(),
        "dry_run": dry_run,
        "status": "booked" if slot else "queued",
        "created_at": store.now_iso(),
        "slot": slot.isoformat() if slot else None,
        "slot_time": (at or settings.post_time) if slot else None,
        "publish_at": slot_time(slot, at).isoformat() if slot else None,
        "results": {},
        "channel": channels.current.get(),
        **({"platforms": platforms} if platforms else {}),
    }
    store.save_job(job)
    if not slot:  # booked jobs are rendered by the scheduler shortly before their slot
        _enqueue("render", job["id"])
    return job


def scheduled_jobs() -> list[dict]:
    """Jobs holding a slot that hasn't been posted yet, earliest slot first."""
    jobs = [j for j in store.list_jobs(200) if j.get("slot") and j["status"] in ACTIVE]
    return sorted(jobs, key=lambda j: j["publish_at"])


def booked_jobs() -> list[dict]:
    """Jobs that hold their slot: still to be posted, or already posted."""
    return [j for j in store.list_jobs(200) if j.get("slot") and j["status"] in ACTIVE + ("done",)]


def update_booking(job: dict, slot: date, at: str, spec: QuizSpec | None) -> dict:
    """Move a booked quiz and/or replace its content. A content change drops any video already made,
    so it is rendered again from the new spec before its slot."""
    job.update(slot=slot.isoformat(), slot_time=at, publish_at=slot_time(slot, at).isoformat())
    if spec is not None:
        job["spec"] = spec.model_dump()
        if job.get("video"):
            (settings.videos_dir / job["video"]).unlink(missing_ok=True)
            (settings.videos_dir / f"{Path(job['video']).stem}.jpg").unlink(missing_ok=True)
        for k in ("video", "video_url", "cover_url", "render"):
            job.pop(k, None)
        job["status"] = "booked"
    store.save_job(job)
    return job


def cancel(job: dict, reason: str = "cancelled") -> None:
    job.update(status="cancelled", error=reason)
    store.save_job(job)


# ------------------------------------------------------------------ render

def _render(job: dict) -> None:
    spec = QuizSpec.model_validate(job["spec"])
    stem = f"{spec.id}-{secrets.token_urlsafe(8)}"  # unguessable public URL
    video = settings.videos_dir / f"{stem}.mp4"
    cover = settings.videos_dir / f"{stem}.jpg"
    job["status"] = "rendering"
    store.save_job(job)
    if job.get("retry"):  # remaking a posted video: show the same reveal it went out with (or none)
        reveal = job.get("reveal")
    else:
        try:  # yesterday's cliffhanger: read and judge its comments now, so the shout-outs are as fresh as possible
            reveal = cliffhanger.prepare(job)
        except Exception as e:  # never let comment reading stop a post
            log.exception("cliffhanger prepare failed")
            reveal = None
            notify.error(f"couldn't prepare yesterday's cliffhanger reveal for `{job['id']}`: {e}")
    job["reveal"] = reveal
    screen = {k: reveal[k] for k in ("answer", "note", "shoutouts")} if reveal else None
    voice_id = settings.voices.get(spec.voice_name.lower(), settings.elevenlabs_voice_id)
    vcfg = VoiceConfig(settings.elevenlabs_api_key, voice_id, settings.elevenlabs_model,
                       settings.data_dir / "voice") if settings.elevenlabs_api_key else None
    info = render_video(spec, video, brand=settings.brand_handle, cover_path=cover, music_dir=settings.music_dir,
                        bundled_music=settings.music_bundled,
                        reveal=screen, voice=vcfg)
    if (store.get_job(job["id"]) or {}).get("status") == "cancelled":  # cancelled while rendering
        video.unlink(missing_ok=True)
        cover.unlink(missing_ok=True)
        return
    if info.get("voice_id"):  # label by name, as the routine and the review talk about voices
        names = {v: k for k, v in settings.voices.items()}
        info["voice_name"] = ",".join(names.get(v, v) for v in info["voice_id"].split(","))
    job.update(render=info, video=video.name, video_url=media_url(video.name), cover_url=media_url(cover.name))

    publish_at = datetime.fromisoformat(job["publish_at"]) if job.get("publish_at") else None
    if publish_at and publish_at > now():
        job["status"] = "scheduled"
        store.save_job(job)
        _notify_scheduled(job, spec, video)
    else:
        store.save_job(job)
        _publish(job)


# ------------------------------------------------------------------ publish

def _publish(job: dict) -> None:
    spec = QuizSpec.model_validate(job["spec"])
    video = settings.videos_dir / job.get("video", "")
    if not job.get("video") or not video.exists():  # never rendered, or the file was cleaned up
        if not job.get("retry"):  # a retry's slot is already past, and the schedule still shows it
            job["publish_at"] = None  # publish straight after this render
        _render(job)
        return
    job["status"] = "publishing"
    store.save_job(job)

    results = job["results"]
    if settings.publish_enabled and not job["dry_run"]:
        for name in job.get("platforms") or settings.platforms:
            if name not in PUBLISHERS or results.get(name, {}).get("ok"):
                continue  # retired platform, or already posted there (resuming after a restart)
            mod = PUBLISHERS[name]
            if not mod.configured():
                results[name] = {"ok": False, "error": "not configured (missing app credentials)"}
                continue
            try:
                results[name] = {"ok": True, **mod.publish(video, spec, job)}
            except Exception as e:
                log.exception("%s publish failed", name)
                results[name] = {"ok": False, "error": str(e)[:500]}
            store.save_job(job)  # record each platform as it completes

    retrying = job.pop("retry", False)
    if retrying:
        store.update_history(job["id"], {k: v.get("ok") for k, v in results.items()})
    elif not job["dry_run"]:
        store.add_history({
            "date": store.now_iso(),
            "slot": job.get("slot"),
            "id": spec.id,
            "theme": spec.theme,
            "palette": spec.palette,
            "title": spec.title.replace("*", ""),
            "round_types": [r.type for r in spec.rounds],
            "answers": spec.answer_keys(),
            "music": job.get("render", {}).get("music"),
            "platforms": {k: v.get("ok") for k, v in results.items()},
            "job_id": job["id"],
        })
    # a retry keeps the first posting time, which the metrics' age and the dashboard go by
    job.update(status="done", published_at=job.get("published_at") if retrying else store.now_iso())
    try:
        cliffhanger.after_publish(job)  # mark yesterday's cliffhanger revealed; reply under the winners' comments
    except Exception:
        log.exception("cliffhanger replies failed")
    try:
        cliffhanger.link_previous(job)  # yesterday's comment section points at today's quiz
    except Exception:
        log.exception("next-video comment failed")
    try:
        themes.after_publish(job)  # tell the viewer who picked this quiz's theme
    except Exception:
        log.exception("theme reply failed")
    try:
        social.after_publish(job)  # the "new quiz out now" story
    except Exception:
        log.exception("story failed")
    if job.get("slot") and not job["dry_run"] and settings.publish_enabled and not retrying:
        if any(r.get("ok") for r in results.values()):
            health.ping("daily-post")
        elif results:
            health.ping("daily-post", fail=True)
    if results and all(r.get("ok") for r in results.values()):
        # every platform has its copy; keep the file only when something needs a retry
        video.unlink(missing_ok=True)
        (settings.videos_dir / f"{video.stem}.jpg").unlink(missing_ok=True)
        job["video_deleted"] = True
    store.save_job(job)
    _notify_published(job, spec, video)


def failures(job: dict) -> dict[str, str]:
    """Platforms this job failed on that could be tried again: platform -> error."""
    return {name: res.get("error", "") for name, res in job.get("results", {}).items()
            if not res.get("ok") and name in PUBLISHERS and PUBLISHERS[name].configured()}


def failed_jobs(days: int = 14) -> list[dict]:
    """Recent posts that missed a platform, plus any retry still running, newest first."""
    since = (now() - timedelta(days=days)).isoformat()
    jobs = [j for j in store.list_jobs(200) if not j.get("dry_run") and (j.get("published_at") or "") >= since
            and ((j["status"] == "done" and failures(j)) or j.get("retry"))]
    return sorted(jobs, key=lambda j: j["published_at"], reverse=True)


def retry(job: dict) -> list[str]:
    """Post a finished job again to the platforms it failed on; the others are skipped. Returns those platforms."""
    failed = list(failures(job))
    if not settings.publish_enabled:
        raise ValueError("publishing is off (PUBLISH_ENABLED)")
    if job["status"] != "done" or job.get("dry_run") or not failed:
        raise ValueError("nothing to retry: this post has no failed platforms" if job["status"] == "done"
                         else f"can't retry while the post is {job['status']}")
    job.update(status="publishing", retry=True)  # publishing skips the platforms that already have it
    store.save_job(job)
    _enqueue("publish", job["id"])
    return failed


# ------------------------------------------------------------------ Discord

def _answers_field(spec: QuizSpec) -> dict:
    return {"name": "Answers", "inline": False, "value": "\n".join(
        f"{i}. {r.type}: {r.answer_text()}" for i, r in enumerate(spec.rounds, 1))[:1000]}


def _when(job: dict) -> str:
    return datetime.fromisoformat(job["publish_at"]).astimezone(settings.tz).strftime("%a %d %b, %H:%M")


def _notify_scheduled(job: dict, spec: QuizSpec, video: Path) -> None:
    embed = {
        "title": f"Scheduled for {_when(job)}: {spec.title.replace('*', '')}",
        "url": job["video_url"],
        "color": 0xFFC22E,
        "fields": [_answers_field(spec),
                   {"name": "Length", "value": f"{job['render']['duration']} s", "inline": True},
                   {"name": "Music", "value": job["render"].get("music", "?"), "inline": True},
                   {"name": "Voice", "value": f'{job["render"].get("voice", "off")} {job["render"].get("voice_name", "")}'.strip(), "inline": True},
                   {"name": "Platforms", "value": ", ".join(settings.platforms) or "(none)", "inline": True}],
    }
    slot, at = slot_key(job)
    notify.send(f"Preview of the {_when(job)} quiz. To pull it: `DELETE /schedule/{slot}?time={at}`", embed, attach=video)


def _notify_published(job: dict, spec: QuizSpec, video: Path) -> None:
    lines = []
    if not settings.publish_enabled or job["dry_run"]:
        lines.append("_Publishing is off; nothing was uploaded._")
    for name, res in job["results"].items():
        if not res["ok"]:
            lines.append(f"**{LABELS.get(name, name)}:** failed: {res['error']}")
        else:
            lines.append(f"**{LABELS.get(name, name)}:** posted {res.get('url') or res.get('privacy') or ''}".rstrip())
    embed = {
        "title": f"Posted: {spec.title.replace('*', '')}",
        "url": job["video_url"],
        "color": 0xFF5A3C,
        "fields": [_answers_field(spec)],
    }
    rv = job.get("reveal")
    if rv:
        names = rv.get("shoutouts")
        who = ", ".join("@" + n for n in names) if names else ("nobody got it" if names == [] else "comments not readable")
        ok = sum(1 for r in rv.get("replies", []) if r["ok"])
        lines.append(f"**Cliffhanger revealed:** {rv['answer']} · shout-outs: {who} · replies sent: {ok}")
    if spec.picked_by:
        pr = job.get("picked_reply") or {}
        lines.append(f"**Theme picked by:** @{spec.picked_by.user} ({LABELS[spec.picked_by.platform]}) · "
                     + ("replied under their comment" if pr.get("ok") else f"reply failed: {pr.get('error', 'not sent')}"))
    if spec.ask_theme:
        lines.append("**Theme ask:** this one asks viewers to comment a theme; Monday's batch reads them.")
    st = job.get("story")
    if st:
        lines.append("**Instagram story:** " + ("posted" if st["ok"] else f"failed: {st['error']}"))
    lf = job.get("linked_from")
    if lf:
        done = [LABELS.get(p, p) for p, ok in lf.items() if p != "job" and ok]
        lines.append(f"**Linked from {lf['job']}:** " + (", ".join(done) if done else "comment failed (check the comments permission)"))
    if spec.rounds[-1].cliffhanger:
        lines.append("**Cliffhanger:** the last round's answer is held back for the next quiz.")
    content = "\n".join(lines) + f"\n\n**Caption:**\n```\n{spec.full_caption()[:1500]}\n```"
    # scheduled posts already had the video attached to their preview
    notify.send(content, embed, attach=None if job.get("slot") else video)


# ------------------------------------------------------------------ threads

_mine: set[str] = set()  # jobs this process has queued or is working on
STALE = timedelta(minutes=20)  # in progress this long with no update and not ours: its process died


def _enqueue(action: str, job_id: str) -> None:
    _mine.add(job_id)
    _queue.put((action, job_id))


def _rescue_orphans() -> None:
    """A deploy starts the new server before stopping the old one, so a job the old one was working on
    can be left 'rendering' or 'publishing' with nobody on it. Pick those up again."""
    cutoff = (now() - STALE).isoformat()
    for job in store.list_jobs(200):
        if job["status"] not in ("queued", "rendering", "publishing") or job["id"] in _mine:
            continue
        if (job.get("updated_at") or "") > cutoff:
            continue
        log.warning("job %s was left %s; picking it up again", job["id"], job["status"])
        notify.error(f"job `{job['id']}` was left {job['status']} (the server restarted mid-way); picking it up again")
        if job["status"] == "publishing":
            _enqueue("publish", job["id"])
        else:
            job["status"] = "queued"
            store.save_job(job)
            _enqueue("render", job["id"])


def _worker() -> None:
    while True:
        action, job_id = _queue.get()
        try:
            _work(action, job_id)
        finally:
            if job_id not in [j for _, j in list(_queue.queue)]:
                _mine.discard(job_id)


def _work(action: str, job_id: str) -> None:
    job = store.get_job(job_id)
    if not job or job["status"] in ("cancelled", "done"):
        return
    try:
        with channels.use(job.get("channel")):  # its own accounts' tokens (jobs from before channels: main)
            if action == "render":
                _render(job)
            else:
                _publish(job)
    except Exception as e:
        log.exception("job %s failed", job_id)
        job = store.get_job(job_id) or {"id": job_id}
        if job.pop("retry", False):  # the first attempt's posts stand; the failed platforms can be tried again
            job["status"] = "done"
        else:
            job.update(status="failed", error=str(e)[:1000])
        store.save_job(job)
        when = f" (slot {job['slot']})" if job.get("slot") else ""
        notify.error(f"job `{job_id}`{when} failed during {action}: {e}")


_warned: set[str] = set()


def tick() -> None:
    """Hand due jobs to the worker; warn about an empty day and a short runway."""
    t = now()
    lead = timedelta(minutes=settings.render_lead_minutes)
    _rescue_orphans()
    try:
        social.weekly_tick(t.astimezone(settings.tz))
        social.avatar_tick(t.astimezone(settings.tz))
    except Exception:
        log.exception("weekly carousel / profile picture failed")
    for job in scheduled_jobs():
        due = datetime.fromisoformat(job["publish_at"])
        if job["status"] == "booked" and t >= due - lead:
            if t - due > MISSED_AFTER:
                job.update(status="missed", error=f"server was not running at {due.isoformat()}")
                store.save_job(job)
                notify.error(f"skipped the {job['slot']} quiz `{job['id']}`: its slot passed while the server was down")
            else:
                job["status"] = "queued"
                store.save_job(job)
                _enqueue("render", job["id"])
            continue
        if job["status"] != "scheduled":
            continue
        if due > t:
            continue
        if t - due > MISSED_AFTER:
            job.update(status="missed", error=f"server was not running at {due.isoformat()}")
            store.save_job(job)
            notify.error(f"skipped the {job['slot']} quiz `{job['id']}`: its slot passed while the server was down")
            continue
        job["status"] = "publishing"  # claim it so the next tick doesn't queue it twice
        store.save_job(job)
        _enqueue("publish", job["id"])

    today = today_local()
    if t >= slot_time(today) and today.isoformat() not in _warned:
        _warned.add(today.isoformat())
        held = [j for j in store.list_jobs(200) if j.get("slot") == today.isoformat() and j["status"] != "cancelled"]
        if not held:
            notify.error(f"nothing was scheduled for today ({today}); no quiz posted")
        ahead = [j for j in scheduled_jobs() if j["slot"] > today.isoformat()]
        if len(ahead) < 2:
            notify.error(f"only {len(ahead)} quiz(zes) scheduled after today; is the weekly routine running?")


def _scheduler() -> None:
    while True:
        try:
            if lease.held():  # an older server still running mid-deploy leaves the scheduling to the new one
                tick()
                health.heartbeat()
                health.connections_tick()
        except Exception:
            log.exception("scheduler tick failed")
        time.sleep(30)


def refresh_tokens() -> None:
    """Keep every channel's connections fresh (the quiz's platforms, then each other channel's)."""
    for cid, ch in channels.registry().items():
        with channels.use(cid):
            todo = refreshers() if cid == channels.MAIN else [
                (n, PUBLISHERS[n].refresh_if_needed) for n in ch.platforms if n in PUBLISHERS and store.get_tokens(n)]
            for name, fn in todo:
                try:
                    fn()
                except Exception as e:
                    log.exception("%s token refresh failed (%s)", name, cid)
                    where = "" if cid == channels.MAIN else f"?channel={cid}"
                    notify.error(f"{name} token refresh failed for {ch.name} ({e}); reconnect via /oauth/{name}/start{where}")


def _maintenance() -> None:
    """Twice a day: keep OAuth tokens fresh and delete old videos (never ones still to be posted)."""
    while True:
        if not lease.held():
            time.sleep(600)
            continue
        refresh_tokens()
        health.daily_checks()
        privacy.anonymise_old()  # viewer names leave post records after 90 days
        try:
            from .racing import ledger as racing_ledger

            racing_ledger.anonymise_idle()  # racing players with no bet in 90 days lose their name
        except Exception:
            log.exception("racing anonymising failed")
        try:
            legal.scan_comment_optouts()  # "#optout" comments
        except Exception:
            log.exception("#optout comment scan failed")
        keep ={Path(j["video"]).stem for j in scheduled_jobs() if j.get("video")}
        cutoff = time.time() - settings.keep_videos_days * 86400
        for f in settings.videos_dir.glob("*"):
            if f.stat().st_mtime < cutoff and f.stem not in keep:
                f.unlink(missing_ok=True)
        # cached host lines a script hasn't used for 60 days (re-rendering a video re-uses them)
        voice_cutoff = time.time() - 60 * 86400
        for f in (settings.data_dir / "voice").glob("*.mp3"):
            if f.stat().st_atime < voice_cutoff and f.stat().st_mtime < voice_cutoff:
                f.unlink(missing_ok=True)
        time.sleep(12 * 3600)


def _recover() -> None:
    """After a restart: a render that isn't due yet goes back to waiting for its slot. Anything else
    left mid-way (rendering, or posting with some platforms done) is resumed by _rescue_orphans once
    it has sat untouched for STALE, because during a deploy the old server may still be finishing it,
    and doing it twice could double-post. Slots render RENDER_LEAD_MINUTES early, so they still make it."""
    lead = timedelta(minutes=settings.render_lead_minutes)
    for job in store.list_jobs(200):
        if (job["status"] in ("queued", "rendering") and job.get("publish_at")
                and datetime.fromisoformat(job["publish_at"]) - lead > now()):
            job["status"] = "booked"  # the scheduler renders it nearer its slot
            store.save_job(job)


def start_background() -> None:
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    lease.claim()  # the newest server runs the background jobs from now on
    _recover()
    threading.Thread(target=health.setup, daemon=True, name="healthchecks").start()
    threading.Thread(target=_worker, daemon=True, name="worker").start()
    threading.Thread(target=_scheduler, daemon=True, name="scheduler").start()
    threading.Thread(target=_maintenance, daemon=True, name="maintenance").start()
    threading.Thread(target=metrics.run_forever, daemon=True, name="metrics").start()
