"""Farside's daily cycle, run by the server (docs/COLONY_PLAN.md §5b). Nothing here calls an AI:
the routines send the week plan and each day's adaptation; this reads, renders and posts.

  every COLONY_POLL_MINUTES  read new comments on the last few posts → inbox → sort (DeepSeek)
  the cut-off (T-90 min)     whatever the daily routine has sent by now is what plays
  T-COLONY_RENDER_LEAD (60)  read the follower count and yesterday's shares and saves → apply the day
                             → build the episode (the adaptation, else the plan, else a spare, else
                             the default) → render → Discord preview (block with POST /colony/block)
  the slot (COLONY_POST_TIME) post the Reel → keep what changed → queue the replies
  always                     send replies slowly (replies.py)

One job a day (DATA_DIR/colony/jobs/<date>.json), booked from the start date on. Only the server
holding the deploy lease runs it. COLONY_ENABLED switches the whole thing on.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .. import channels, lease, notify, store
from ..config import settings
from ..publish import instagram
from . import episode, inbox, plan, replies, rules, state, today

log = logging.getLogger(__name__)
_render_lock = threading.Lock()
_mine: set[str] = set()
MISSED_AFTER = timedelta(hours=6)
STALE = timedelta(minutes=20)
POLL_POSTS = 3  # the last few posts whose comments are read
WORKING = ("preparing", "rendering", "publishing")


class NotConnected(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def _dir() -> Path:
    d = settings.data_dir / "colony" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _chan_path() -> Path:
    return settings.data_dir / "colony" / "channel.json"


def channel_state() -> dict:
    p = _chan_path()
    return json.loads(p.read_text()) if p.exists() else {}


def _set_channel(**kw) -> dict:
    s = {**channel_state(), **kw}
    _chan_path().parent.mkdir(parents=True, exist_ok=True)
    tmp = _chan_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1))
    os.replace(tmp, _chan_path())
    return s


def save(job: dict) -> None:
    p = _dir() / f"{job['date']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1, default=str))
    os.replace(tmp, p)


def get(day: str) -> dict | None:
    p = _dir() / f"{day}.json"
    return json.loads(p.read_text()) if p.exists() else None


def recent(limit: int = 30) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(_dir().glob("*.json"), reverse=True)[:limit]]


def slot_for(day: date) -> datetime:
    h, m = (int(x) for x in settings.colony_post_time.split(":"))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=settings.tz).astimezone(timezone.utc)


def post_time(day: date) -> datetime:
    """When `day` posts: its booked time (the first day can be at any time), else the usual slot."""
    job = get(day.isoformat())
    return datetime.fromisoformat(job["publish_at"]) if job else slot_for(day)


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(settings.tz).strftime("%a %d %b %H:%M")


def can_publish() -> str | None:
    if not settings.publish_enabled:
        return "PUBLISH_ENABLED is off"
    if not instagram.configured():
        return "the Instagram app isn't configured"
    with channels.use(channels.COLONY):
        if not store.get_tokens("instagram"):
            return "Instagram isn't connected for Farside: /oauth/instagram/start?channel=colony"
    return None


def followers_now() -> int | None:
    """The connected account's follower count, or None if it can't be read."""
    try:
        with channels.use(channels.COLONY):
            if not store.get_tokens("instagram"):
                return None
            return instagram.followers()
    except Exception as e:
        log.warning("farside followers: %s", e)
        return None


# ------------------------------------------------------------------ starting


def start(first: date | None = None, at: datetime | None = None, restart: bool = False) -> dict:
    """Start the daily schedule from `first` (default: tomorrow, or today if its slot is over an
    hour away). `at` posts the first episode at that time instead (it renders straight away when
    that's sooner than the usual lead), and every day after at COLONY_POST_TIME. `restart` books
    it again, only while nothing has posted. Day 0 needs nothing from viewers: the crew, the pod
    and the signal going out."""
    if why := can_publish():
        raise NotConnected(why)
    if channel_state().get("started"):
        if not restart:
            raise ValueError(f"Farside already started on {channel_state()['start_date']}; see GET /colony/state "
                             "(restart=true books it again while nothing has posted)")
        if any(j["status"] in ("publishing", "done") for j in recent(50)):
            raise ValueError("can't restart: an episode has already posted")
        for p in _dir().glob("*.json"):
            p.unlink()
    today_local = datetime.now(settings.tz).date()
    if at is not None:
        first = at.astimezone(settings.tz).date()
        if at - now() < timedelta(minutes=10):
            raise ValueError("the first post must be at least 10 minutes away (it takes a few to render)")
    else:
        if first is None:
            first = today_local if slot_for(today_local) - now() > timedelta(hours=1) else today_local + timedelta(days=1)
        if slot_for(first) - now() < timedelta(minutes=settings.colony_render_lead_minutes + 5):
            raise ValueError("the first post must be at least an hour and five minutes away (or give `at`)")
    s = state.load()
    if s["followers"] == 0:
        n = followers_now()
        if n is not None:
            s["followers"] = n
            state.save(s)
    st = _set_channel(started=True, start_date=first.isoformat(), started_at=store.now_iso())
    job = book(first, at)
    notify.send(f":ringed_planet: **Farside** starts {_local(job['publish_at'])}: the first episode renders "
                f"up to {settings.colony_render_lead_minutes} minutes before, with a preview here.")
    return {**st, "first_post": job["publish_at"]}


def book(day: date, at: datetime | None = None) -> dict:
    job = get(day.isoformat())
    if job:
        return job
    job = {"id": f"farside-{day.isoformat()}", "date": day.isoformat(), "channel": channels.COLONY,
           "publish_at": (at or slot_for(day)).astimezone(timezone.utc).isoformat(), "status": "booked",
           "created_at": store.now_iso(), "results": {}}
    save(job)
    return job


# ------------------------------------------------------------------ reading comments


def poll() -> dict:
    """Read the last few posts' comments into the inbox and sort what's new."""
    n, errors = 0, []
    with channels.use(channels.COLONY):
        if not store.get_tokens("instagram"):
            return {"new": 0, "errors": ["not connected"]}
        try:
            own = instagram.own_name().lower()
        except Exception as e:
            return {"new": 0, "errors": [str(e)[:200]]}
        for job in [j for j in recent(10) if (j["results"].get("instagram") or {}).get("ok")][:POLL_POSTS]:
            media = job["results"]["instagram"]["media_id"]
            try:
                cs = [{**c, "platform": "instagram"} for c in instagram.comments(media, limit=5000)
                      if c["user"].lower() != own]
                n += len(inbox.add(cs, post=job["id"]))
            except Exception as e:
                errors.append(f"{job['id']}: {str(e)[:160]}")
    sorted_ = inbox.sort_pending()
    return {"new": n, "errors": errors, **sorted_}


def _yesterday_numbers(day: date) -> dict:
    """The previous post's shares and saves (they pay for today's building)."""
    prev = get((day - timedelta(days=1)).isoformat())
    res = (prev or {}).get("results", {}).get("instagram") or {}
    if not res.get("ok"):
        return {}
    try:
        with channels.use(channels.COLONY):
            m = instagram.metrics(res["media_id"])
        return {"shares": m.get("shares") or 0, "saves": m.get("saves") or 0}
    except Exception as e:
        log.warning("farside metrics: %s", e)
        return {}


# ------------------------------------------------------------------ the steps


def build(job: dict) -> tuple[dict, dict, dict, str, dict | None]:
    """Apply the day to the colony (once) and build its episode: (state, report, video spec, source, ep)."""
    day = date.fromisoformat(job["date"])
    s = state.load()
    if s["day"] == job["date"]:  # applied already (a re-render after a block)
        report = s["days"][job["date"]]
    else:
        prev, cut = today.deadline(day - timedelta(days=1)).isoformat(), today.deadline(day).isoformat()
        comments = [c for c in inbox.since(prev) if c["at"] <= cut and c.get("kind") != "not_ok"]
        followers = followers_now()
        s, report = rules.apply_day(s, day, comments, followers, _yesterday_numbers(day))
        state.save(s)
    ep, source = today.episode_for(day)
    spec = episode.build(s, report, ep)
    return s, report, spec, source, ep


def _render(job: dict, spec: dict, persist: bool = True) -> None:
    from PIL import Image

    from ..render.colony import video

    job["status"] = "rendering"
    if persist:
        save(job)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    out = settings.videos_dir / f"{job['id']}-{secrets.token_urlsafe(8)}.mp4"
    cover = out.with_suffix(".jpg")
    t0 = time.time()
    video.render(spec, out)
    Image.fromarray(video.frame_at(spec, min(spec["duration"] - 0.1, 3.0))).save(cover, quality=90)
    job.update(video=out.name, video_url=f"{settings.public_base_url}/media/{out.name}",
               cover_url=f"{settings.public_base_url}/media/{cover.name}",
               render={"duration": spec["duration"], "seconds": round(time.time() - t0, 1)})
    if persist:
        save(job)


def _summary(s: dict, report: dict, ep: dict | None, source: str) -> dict:
    who = lambda k: "@" + s["settlers"][k]["handle"] if k in s["settlers"] else k  # noqa: E731
    changed = list(((ep or {}).get("settlers") or {}).keys()) if source == "adapted" else []
    return {"source": source, "followers": s["followers"], "joined": report.get("joined", 0), "left": report.get("left", 0),
            "arrived": [who(k) for k in report["arrived"][:20]], "arrived_count": len(report["arrived"]),
            "surge": rules.surge(report, s["followers"]), "changed": changed,
            "parts": [f"{p['slot']}/{p['id']}" for p in (ep or {}).get("parts") or []] if source == "adapted" else [],
            "replies": len((ep or {}).get("replies") or []) if source == "adapted" else 0,
            "finished": report.get("finished"), "unlocked": report.get("unlocked", [])}


def _preview(job: dict) -> None:
    """The Discord preview: the video, who's in it and what changed, and how to block before it posts."""
    sm = job["summary"]
    lines = [f":ringed_planet: **Farside, {job['date']}** ({sm['source']}), posts {_local(job['publish_at'])} unless blocked",
             f"{sm['followers']:,} followers ({sm['joined']:+,} today){' · SURGE' if sm['surge'] else ''} · "
             f"{sm['arrived_count']} new settlers · {job['render']['duration']:.0f}s",
             f"Caption: {job.get('caption', '')[:300]}"]
    if sm["changed"]:
        lines.append("Looks changed: " + ", ".join(sm["changed"][:30]))
    if sm["parts"]:
        lines.append("New parts drawn: " + ", ".join(sm["parts"]))
    if sm["arrived"]:
        lines.append("Named in it: " + ", ".join(sm["arrived"][:12]))
    lines.append("Block someone or a part (re-renders): `POST /colony/block?user=@name` or `?part=pet/dragon`")
    video_file = settings.videos_dir / job["video"]
    notify.send("\n".join(lines), attach=video_file)
    for part in sm["parts"]:
        pic = settings.data_dir / "colony" / "kit-previews" / f"{part.replace('/', '-')}.png"
        if pic.exists():
            notify.send(f"New part `{part}`", attach=pic)


def prepare(job: dict) -> None:
    try:
        with _render_lock:
            job["status"] = "preparing"
            save(job)
            poll()
            s, report, spec, source, ep = build(job)
            job["caption"] = spec["caption"]
            job["summary"] = _summary(s, report, ep, source)
            job["episode"] = {"source": source, "ep": ep, "shots": [x["view"] for x in spec["shots"]]}
            _render(job, spec)
            job["status"] = "scheduled"
            save(job)
            _preview(job)
    except Exception as e:
        _fail(job, e, "preparing")


def _publish(job: dict) -> None:
    with channels.use(channels.COLONY):
        try:
            res = {"ok": True, **instagram.publish_reel(job["video_url"], job["caption"], job.get("cover_url"))}
        except Exception as e:
            log.exception("farside post failed")
            job["results"]["instagram"] = {"ok": False, "error": str(e)[:500]}
            return
    job["results"]["instagram"] = res
    job["published_at"] = store.now_iso()


def _after_post(job: dict) -> None:
    """Keep what changed, mark the comments answered, and queue the replies."""
    day = date.fromisoformat(job["date"])
    s = state.load()
    ep = (job.get("episode") or {}).get("ep")
    source = (job.get("episode") or {}).get("source")
    report = s["days"].get(job["date"]) or {}
    if source == "adapted":
        s = today.commit(s, ep, report)
        state.save(s)
    box = inbox.load()["comments"]
    items = []
    if source == "adapted":
        for r in (ep or {}).get("replies") or []:
            c = box.get(r["comment_id"])
            if c:
                items.append({"comment_id": c["id"], "user": c["user"], "text": r["text"]})
    else:  # no adaptation today: a welcome for everyone who moved in, so nobody is left unanswered
        firsts = {}
        for c in sorted(box.values(), key=lambda c: c["at"]):
            if c["settler"] in report.get("arrived", []) and c["settler"] not in firsts:
                firsts[c["settler"]] = c
        for c in firsts.values():
            items.append({"comment_id": c["id"], "user": c["user"],
                          "text": f"Welcome to Farside, @{c['user']}! You live here now. Comment FARM, BUILD, SCOUT, "
                                  f"GUARD or TINKER to pick your job, or tell us who you are."})
    inbox.mark_answered([i["comment_id"] for i in items], job["date"])
    job["replies_queued"] = replies.add(items)
    # the next day
    book(day + timedelta(days=1))


def post(job: dict) -> None:
    try:
        _publish(job)
        ok = (job["results"].get("instagram") or {}).get("ok")
        job.update(status="done" if ok else "failed", finished_at=store.now_iso())
        if not ok:
            job["error"] = job["results"]["instagram"]["error"]
        else:
            _after_post(job)
        save(job)
        ig = job["results"]["instagram"]
        notify.send(f":ringed_planet: **Farside {'posted' if ok else 'post FAILED'}** `{job['date']}`: "
                    f"{ig.get('url') or ig.get('media_id') if ok else ig.get('error')}"
                    + (f" · {job.get('replies_queued', 0)} replies queued" if ok else
                       f"\nRetry with POST /colony/jobs/{job['date']}/retry"))
    except Exception as e:
        _fail(job, e, "publishing")


def _fail(job: dict, e: Exception, step: str) -> None:
    log.exception("farside %s failed during %s", job["id"], step)
    job.update(status="failed", error=f"{step}: {e}"[:1000])
    save(job)
    notify.send(f":warning: **Farside** `{job['date']}` failed during {step}: {e}\n"
                f"Retry with POST /colony/jobs/{job['date']}/retry")


def retry(day: str) -> dict:
    job = get(day)
    if not job:
        raise ValueError(f"no Farside job for {day}")
    if job["status"] not in ("failed", "missed"):
        raise ValueError("only failed or missed days can be retried")
    job["retry"] = True
    if job.get("video") and (settings.videos_dir / job["video"]).exists():
        job.update(status="publishing", error=None, results={})
        save(job)
        _spawn(post, job)
    else:
        job.update(status="preparing", error=None)
        save(job)
        _spawn(prepare, job)
    return job


def rerender(day: str) -> dict | None:
    """After a block: render that day again if it hasn't posted and there's time."""
    job = get(day)
    if not job or job["status"] not in ("scheduled", "booked"):
        return job
    if datetime.fromisoformat(job["publish_at"]) - now() < timedelta(minutes=8):
        notify.send(f":warning: **Farside** `{day}`: too close to the post to render again; it goes out as it was rendered. "
                    "Cancel with DELETE /colony/jobs/{day} if it mustn't.")
        return job
    if job["status"] == "scheduled":
        job["status"] = "preparing"
        save(job)
        _spawn(prepare, job)
    return job


def _spawn(target, job: dict) -> None:
    _mine.add(job["id"])

    def run():
        try:
            target(job)
        finally:
            _mine.discard(job["id"])

    threading.Thread(target=run, daemon=True, name=f"farside-{job['date']}").start()


# ------------------------------------------------------------------ the schedule


def tick(t: datetime | None = None) -> None:
    t = t or now()
    lead = timedelta(minutes=settings.colony_render_lead_minutes)
    for job in recent(5):
        st = job["status"]
        if st not in ("booked", "scheduled"):
            continue
        due = datetime.fromisoformat(job["publish_at"])
        if t - due > MISSED_AFTER and not job.get("retry"):
            job.update(status="missed", error=f"the server was not running at {due.isoformat()}")
            save(job)
            notify.send(f":warning: **Farside** `{job['date']}` missed its slot. Retry: POST /colony/jobs/{job['date']}/retry")
            book(date.fromisoformat(job["date"]) + timedelta(days=1))
        elif st == "booked" and t >= due - lead:
            job["status"] = "preparing"
            save(job)
            _spawn(prepare, job)
        elif st == "scheduled" and t >= due:
            job["status"] = "publishing"
            save(job)
            _spawn(post, job)


def recover(stale: timedelta = STALE) -> None:
    cutoff = time.time() - stale.total_seconds()
    for job in recent(5):
        if job["status"] not in WORKING or job["id"] in _mine:
            continue
        p = _dir() / f"{job['date']}.json"
        if p.exists() and p.stat().st_mtime > cutoff:
            continue
        if job["status"] in ("preparing", "rendering"):
            job["status"] = "booked"
            save(job)
        else:
            job.update(status="failed", error="the server restarted while posting")
            save(job)
            notify.send(f":warning: **Farside**: the server restarted while posting `{job['date']}`; check "
                        f"@{settings.colony_handle} before retrying.")


def _loop() -> None:
    last_poll = last_tick = 0.0
    while True:
        try:
            if settings.colony_enabled and lease.held() and channel_state().get("started"):
                if time.time() - last_tick > 30:
                    last_tick = time.time()
                    recover()
                    tick()
                if time.time() - last_poll > settings.colony_poll_minutes * 60:
                    last_poll = time.time()
                    poll()
                with channels.use(channels.COLONY):
                    replies.send_due()
        except Exception:
            log.exception("farside tick failed")
        time.sleep(5)


def start_background() -> None:
    today.live_followers = followers_now
    threading.Thread(target=_loop, daemon=True, name="farside-schedule").start()


def preview(day: date | None = None) -> dict:
    """Render a day's episode as it stands now and send it to Discord, saving nothing (the colony,
    the inbox and the schedule are left as they were)."""
    day = day or datetime.now(settings.tz).date()
    job = {"id": f"farside-preview-{day.isoformat()}-{secrets.token_hex(2)}", "date": day.isoformat(),
           "publish_at": slot_for(day).isoformat(), "status": "rendering", "results": {}}

    def run():
        try:
            with _render_lock:
                s = state.load()
                if s["day"] == day.isoformat():
                    report = s["days"][s["day"]]
                else:  # apply_day works on a copy: nothing is saved
                    prev, cut = today.deadline(day - timedelta(days=1)).isoformat(), today.deadline(day).isoformat()
                    comments = [c for c in inbox.since(prev) if c["at"] <= cut and c.get("kind") != "not_ok"]
                    s, report = rules.apply_day(s, day, comments, followers_now(), {})
                ep, source = today.episode_for(day)
                spec = episode.build(s, report, ep)
                job["caption"] = spec["caption"]
                job["summary"] = _summary(s, report, ep, f"{source}, PREVIEW: nothing posted or saved")
                _render(job, spec, persist=False)
                _preview(job)
        except Exception as e:
            log.exception("farside preview failed")
            notify.send(f":warning: **Farside preview** failed: {e}")

    threading.Thread(target=run, daemon=True, name=job["id"]).start()
    return job
