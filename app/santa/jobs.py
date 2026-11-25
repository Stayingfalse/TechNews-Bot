"""raosanta.uk's bookings. The season plan (season.py: santa_season/<year>.json) books each promo
into a free slot of the 22-hour pattern (schedule.py) a few days ahead; one-offs can be booked
with POST /santa/book. From then on the server runs each one:

    booked ──(SANTA_RENDER_LEAD_MINUTES before)──► preparing: check the slot still keeps clear
      of the other channels (nudge it if not), fill in the site's live figures, voice, render,
      preview to Discord ──► scheduled ──(at the slot)──► publishing: Instagram Reel + YouTube
      Short ──► done (or failed: POST /santa/jobs/{id}/retry)

A booking more than MISSED_AFTER late (the server was down) is marked missed, not posted late.
Nothing posts while SANTA_ENABLED or PUBLISH_ENABLED is off: the loop doesn't run, or the post
is recorded as not sent. Stored in DATA_DIR/santa/jobs/<id>.json.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from .. import channels, lease, notify, slots, store
from ..config import settings
from ..publish import PUBLISHERS
from ..render.santa.video import render_promo
from . import previews, schedule, source, voice
from .spec import MAX_SECONDS, PromoSpec

log = logging.getLogger(__name__)
ACTIVE = ("booked", "preparing", "scheduled", "publishing")
MISSED_AFTER = timedelta(hours=2)
STALE = timedelta(minutes=25)  # in progress this long untouched: the process doing it died
LOW_AHEAD = timedelta(hours=48)  # warn (once a day) when nothing is booked this far ahead
_mine: set[str] = set()


def now() -> datetime:
    return datetime.now(timezone.utc)


def _dir() -> Path:
    d = settings.data_dir / "santa" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(job: dict) -> None:
    job["updated_at"] = store.now_iso()
    p = _dir() / f"{job['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1, default=str))
    os.replace(tmp, p)


def get(job_id: str) -> dict | None:
    if not re.fullmatch(r"[\w-]+", job_id or ""):
        return None
    p = _dir() / f"{job_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def all_jobs() -> list[dict]:
    return sorted((json.loads(p.read_text()) for p in _dir().glob("*.json")), key=lambda j: j["publish_at"])


def active() -> list[dict]:
    return [j for j in all_jobs() if j["status"] in ACTIVE]


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(settings.tz).strftime("%a %d %b %H:%M")


# ---------------------------------------------------------------- booking

def free_slots(count: int, t: datetime | None = None) -> list[dict]:
    """The next `count` pattern slots that are free, not skipped, and far enough off to render."""
    t = t or now()
    taken = {j["planned"] for j in active()}
    soonest = t + timedelta(minutes=settings.santa_render_lead_minutes + 10)
    out = []
    for row in schedule.upcoming(count + len(taken) + 30, after=t):
        if row.get("skipped") or row["planned"] in taken or datetime.fromisoformat(row["at"]) < soonest:
            continue
        out.append(row)
        if len(out) == count:
            break
    return out


def check_batch(items: list, replace: bool = False) -> tuple[list[PromoSpec], list[str]]:
    """The specs, and every problem with the batch (all-or-nothing)."""
    from pydantic import ValidationError

    specs, probs = [], []
    for k, item in enumerate(items):
        try:
            specs.append(PromoSpec.model_validate(item))
        except ValidationError as e:
            probs += [f"items[{k}].{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()]
    ids = [s.id for s in specs]
    probs += [f"id {i!r} is used twice in this batch" for i in sorted({i for i in ids if ids.count(i) > 1})]
    used = {j["spec"]["id"]: j for j in all_jobs() if j["status"] != "cancelled"}
    for s in specs:
        prior = used.get(s.id)
        if prior and not (replace and prior["status"] == "booked"):
            probs.append(f"id {s.id!r} was already booked ({prior['status']}, {_local(prior['publish_at'])}); give it a new id")
    return specs, probs


def book(items: list, replace: bool = False) -> list[dict]:
    """Book a batch into the next free slots, in order. `replace` first cancels everything still
    only booked (not yet being made). Raises ValueError with every problem; nothing is booked then."""
    specs, probs = check_batch(items, replace)
    if not specs and not probs:
        probs.append("items: send at least one promo")
    if probs:
        raise ValueError(probs)
    if replace:
        for j in active():
            if j["status"] == "booked":
                cancel(j, "replaced by a new batch")
    rows = free_slots(len(specs))
    if len(rows) < len(specs):
        raise ValueError([f"only {len(rows)} free slots found for {len(specs)} promos"])
    return book_into(list(zip(specs, rows)), "by hand")


def book_into(pairs: list[tuple[PromoSpec, dict]], source: str) -> list[dict]:
    """Book each spec into its slot row (from free_slots), and say so in Discord."""
    out = []
    for spec, row in pairs:
        job = {"id": f"santa-{datetime.fromisoformat(row['at']).astimezone(settings.tz):%Y%m%d-%H%M}-{secrets.token_hex(2)}",
               "channel": channels.SANTA, "status": "booked", "created_at": store.now_iso(), "booked_by": source,
               "planned": row["planned"], "publish_at": row["at"], "spec": spec.model_dump(), "results": {}}
        save(job)
        out.append(job)
    if out:
        lines = [f"`{_local(j['publish_at'])}` {j['spec']['format']}: {j['spec']['id']}" for j in out]
        notify.send(f":santa: **raosanta.uk**: {len(out)} promo(s) booked ({source})\n" + "\n".join(lines))
    return out


def cancel(job: dict, reason: str = "cancelled") -> dict:
    if job["status"] not in ("booked", "scheduled", "failed", "missed"):
        raise ValueError(f"it's {job['status']}: too late to cancel")
    job.update(status="cancelled", error=reason)
    save(job)
    _drop_video(job)
    return job


# ---------------------------------------------------------------- making and posting

def can_publish() -> str | None:
    if not settings.publish_enabled:
        return "PUBLISH_ENABLED is off"
    with channels.use(channels.SANTA):
        missing = [p for p in settings.santa_platforms if p in PUBLISHERS and not store.get_tokens(p)]
    if missing:
        return " and ".join(missing) + " not connected for raosanta.uk: /oauth/{platform}/start?channel=santa"
    return None


def _recheck_slot(job: dict, t: datetime) -> None:
    """Another channel may have booked near this slot since: nudge it clear if there's room."""
    at = datetime.fromisoformat(job["publish_at"])
    others = slots.busy(at - timedelta(hours=4), at + timedelta(hours=4), exclude=channels.SANTA)
    new, hit = schedule._place(at, others)
    if hit and new and new - timedelta(minutes=settings.santa_render_lead_minutes) >= t - timedelta(minutes=1):
        job.update(publish_at=new.isoformat(), moved_from=at.isoformat(), moved_for=sorted({b.label for b in hit}))
        notify.send(f":santa: **raosanta.uk** `{job['id']}` moved to {_local(job['publish_at'])} to keep clear of "
                    + ", ".join(job["moved_for"]))
    elif hit:
        notify.send(f":warning: **raosanta.uk** `{job['id']}` at {_local(job['publish_at'])} is close to "
                    + ", ".join(sorted({b.label for b in hit})) + "; no free time near it, so it stays.")


def prepare(job: dict) -> None:
    """Live figures, narrator, render, preview. Then it waits for its slot."""
    try:
        spec = PromoSpec.model_validate(job["spec"])
        if source.uses_figures(spec):
            try:
                spec, job["left_out"] = source.fill(spec, source.fetch())
            except ValueError as e:  # nothing left to show: play another promo from the plan instead
                from . import season

                day = datetime.fromisoformat(job["publish_at"]).astimezone(settings.tz).date()
                other = season.substitute(day, exclude=spec.id)
                if not other:
                    raise
                job.update(replaced=spec.id, replaced_why=str(e)[:300], spec=other.model_dump())
                save(job)  # the first promo's id is free again, for a day its figures show
                notify.send(f":santa: **raosanta.uk** `{job['id']}`: {spec.id} has no figures to show yet, so "
                            f"{other.id} plays instead.")
                spec = other
        job["filled"] = spec.model_dump()
        with previews._render_lock:
            lines, job["voice"] = voice.lines(spec)
            name = f"{job['id']}-{secrets.token_hex(6)}"
            out = settings.videos_dir / f"{name}.mp4"
            job["render"] = render_promo(spec, out, voice=lines, images_dir=previews.images_dir(),
                                         cover_path=out.with_suffix(".jpg"), max_seconds=MAX_SECONDS)
        base = f"{settings.public_base_url}/media"
        job.update(status="scheduled", video=out.name, video_url=f"{base}/{out.name}", cover_url=f"{base}/{out.stem}.jpg")
        save(job)
        r = job["render"]
        msg = [f":santa: **raosanta.uk** ready: `{spec.id}` ({spec.format}) posts **{_local(job['publish_at'])}**",
               f"{r['duration']} s · music: {r['music']} · voice: {job['voice']}"]
        if job.get("left_out"):
            msg.append("Left out (no figure): " + "; ".join(job["left_out"])[:400])
        if why := can_publish():
            msg.append(f":warning: it won't post as things stand: {why}")
        msg.append(f"> {spec.caption[:500]}" if spec.caption else "")
        msg.append(f"To stop it: `DELETE /santa/jobs/{job['id']}`")
        notify.send("\n".join(m for m in msg if m), attach=out)
    except Exception as e:
        _fail(job, e, "preparing")


def _publisher_spec(spec: PromoSpec):
    """What the shared publishers read from a spec: title, theme, hashtags, full caption."""
    return SimpleNamespace(title=spec.youtube_title(), theme=None, hashtags=spec.hashtags, full_caption=spec.full_caption)


def post(job: dict) -> None:
    try:
        spec = PromoSpec.model_validate(job.get("filled") or job["spec"])
        video = settings.videos_dir / job.get("video", "")
        if not job.get("video") or not video.exists():
            raise RuntimeError("the video is gone (cleaned up or never made); retry makes it again")
        if why := can_publish():
            raise RuntimeError(why)
        with channels.use(channels.SANTA):
            for name in settings.santa_platforms:
                if name not in PUBLISHERS or (job["results"].get(name) or {}).get("ok"):
                    continue
                try:
                    job["results"][name] = {"ok": True, **PUBLISHERS[name].publish(video, _publisher_spec(spec), job)}
                except Exception as e:
                    log.exception("raosanta.uk %s post failed", name)
                    job["results"][name] = {"ok": False, "error": str(e)[:500]}
                save(job)
        res = job["results"]
        ok = [n for n, r in res.items() if r.get("ok")]
        job["status"] = "done" if len(ok) == len(res) else "failed"
        if ok and not job.get("published_at"):  # a retry keeps the first posting time
            job["published_at"] = store.now_iso()
        if job["status"] == "done":
            _drop_video(job)
        save(job)
        lines = [f"{n}: {r.get('url') or r.get('media_id')}" if r.get("ok") else f"{n} FAILED: {r.get('error')}" for n, r in res.items()]
        notify.send(f":santa: **raosanta.uk {'posted' if job['status'] == 'done' else 'post had problems'}** "
                    f"`{spec.id}`\n" + "\n".join(lines)
                    + ("" if job["status"] == "done" else f"\nRetry: `POST /santa/jobs/{job['id']}/retry`"))
    except Exception as e:
        _fail(job, e, "publishing")


def retry(job: dict) -> dict:
    """Post a failed or missed job again: now, to the platforms that don't have it yet. The video
    is made again first if it's gone."""
    if job["status"] not in ("failed", "missed"):
        raise ValueError(f"it's {job['status']}; only failed or missed posts can be retried")
    job.update(status="preparing" if not (settings.videos_dir / job.get("video", "x")).exists() else "publishing",
               error=None, publish_at=now().isoformat(), retry=True)
    save(job)
    _spawn(_retry, job)
    return job


def _retry(job: dict) -> None:
    if job["status"] == "preparing":
        prepare(job)
        job = get(job["id"]) or job
        if job["status"] != "scheduled":
            return
        job["status"] = "publishing"
        save(job)
    post(job)


def _drop_video(job: dict) -> None:
    if job.get("video"):
        (settings.videos_dir / job["video"]).unlink(missing_ok=True)
        (settings.videos_dir / f"{Path(job['video']).stem}.jpg").unlink(missing_ok=True)


def _fail(job: dict, e: Exception, step: str) -> None:
    log.exception("raosanta.uk %s failed while %s", job["id"], step)
    job.update(status="failed", error=f"{step}: {e}"[:600])
    save(job)
    notify.send(f":warning: **raosanta.uk** `{job['id']}` failed while {step}: {str(e)[:300]}\n"
                f"Retry: `POST /santa/jobs/{job['id']}/retry`")


def _spawn(target, job: dict) -> None:
    _mine.add(job["id"])

    def run():
        try:
            target(job)
        finally:
            _mine.discard(job["id"])

    threading.Thread(target=run, daemon=True, name=f"santa-{job['id']}").start()


# ---------------------------------------------------------------- the loop

def tick(t: datetime | None = None) -> None:
    t = t or now()
    lead = timedelta(minutes=settings.santa_render_lead_minutes)
    for job in active():
        due = datetime.fromisoformat(job["publish_at"])
        if job["status"] in ("booked", "scheduled") and t - due > MISSED_AFTER:
            job.update(status="missed", error=f"the server wasn't running at {_local(job['publish_at'])}")
            save(job)
            _drop_video(job)
            notify.send(f":warning: **raosanta.uk** `{job['id']}` missed its slot ({_local(job['publish_at'])}). "
                        f"Post it now: `POST /santa/jobs/{job['id']}/retry`")
        elif job["status"] == "booked" and t >= due - lead:
            _recheck_slot(job, t)
            job["status"] = "preparing"
            save(job)
            _spawn(prepare, job)
        elif job["status"] == "scheduled" and t >= due:
            job["status"] = "publishing"
            save(job)
            _spawn(post, job)
    _warn_if_low(t)


def _warn_if_low(t: datetime) -> None:
    from . import season

    if any(t < datetime.fromisoformat(j["publish_at"]) <= t + LOW_AHEAD for j in active()):
        return
    if season.finished(t):  # the plan has nothing left to give: the season is over, not stuck
        return
    st = schedule.state()
    today = t.astimezone(settings.tz).date().isoformat()
    if st.get("low_warned") == today:
        return
    store._write(schedule.STATE, st | {"low_warned": today})
    notify.send(":warning: **raosanta.uk**: nothing is booked for the next 48 hours. The season plan has no promo "
                "whose dates fit those slots (GET /santa/season), or it has problems.")


def recover(stale: timedelta = STALE) -> None:
    """Jobs left mid-way by a process that died: preparing goes back to booked (made again);
    publishing is marked failed rather than risk posting twice."""
    for job in active():
        if job["id"] in _mine or job["status"] not in ("preparing", "publishing"):
            continue
        if now() - datetime.fromisoformat(job.get("updated_at") or job["created_at"]) < stale:
            continue
        if job["status"] == "preparing":
            job["status"] = "booked"
            save(job)
        else:
            _fail(job, RuntimeError("the server restarted while posting; check the accounts before retrying"), "publishing")


def _loop() -> None:
    from . import season

    last_sync = 0.0
    while True:
        try:
            if settings.santa_enabled and lease.held():
                recover()
                if time.time() - last_sync > 15 * 60:
                    last_sync = time.time()
                    season.sync()
                tick()
        except Exception:
            log.exception("raosanta.uk tick failed")
        time.sleep(30)


def start_background() -> None:
    threading.Thread(target=_loop, daemon=True, name="santa-schedule").start()
