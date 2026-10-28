"""The daily cycle, run by the server alone (no AI, no routine):

  every RACING_POLL_MINUTES while a race is open: read new comments on the post carrying its
      card → queue bet replies (and "betting has closed" under older posts)
  RACING_CLOSE_MINUTES before the slot (18:00): close race N → read its comments → run the sealed
      race → settle → on Sundays the weekly bonus and the league table → open race N+1 →
      render (hook · race N · result · [table] · card N+1) → Discord preview
  the slot (19:00): post the Reel, the example bet as the first comment → book tomorrow

`start()` launches the channel: race 1 opens and the launch video (rules + race 1's card) is
booked. Jobs are JSON files in DATA_DIR/racing/jobs; one render at a time; only the server holding
the deploy lease runs the schedule.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .. import channels, lease, notify, privacy, store
from ..config import settings
from ..publish import instagram
from . import ledger, races, replies, sim, video

log = logging.getLogger(__name__)
_render_lock = threading.Lock()
MISSED_AFTER = timedelta(hours=6)
STALE = timedelta(minutes=20)  # in progress this long untouched, and not ours: the process doing it died
_mine: set[str] = set()  # jobs this process is preparing or posting
LATE_REPLY_HOURS = 48  # answer bets left under an old post for this long after it closed
WORKING = ("preparing", "rendering", "publishing")


class NotConnected(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def _jobs_dir() -> Path:
    d = settings.data_dir / "racing" / "jobs"
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


def state() -> dict:
    return ledger._read("state.json", {})


def _set_state(**kw) -> dict:
    s = {**state(), **kw}
    ledger._write("state.json", s)
    return s


def _local(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(settings.tz).strftime("%a %d %b %H:%M")


def next_slot(after: datetime | None = None) -> datetime:
    """The next RACING_POST_TIME (local) at least 20 minutes away, in UTC."""
    after = after or now()
    h, m = (int(x) for x in settings.racing_post_time.split(":"))
    local = after.astimezone(settings.tz)
    slot = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if slot - local < timedelta(minutes=20):
        slot += timedelta(days=1)
    return slot.astimezone(timezone.utc)


def _tomorrow(slot: datetime) -> datetime:
    """The same local time the next day (across clock changes)."""
    local = slot.astimezone(settings.tz)
    return (local + timedelta(days=1)).replace(hour=local.hour, minute=local.minute).astimezone(timezone.utc)


def closes_for(slot: datetime) -> datetime:
    return slot - timedelta(minutes=settings.racing_close_minutes)


def theme_for(race_no: int) -> str:
    """Videos take turns through RACING_THEMES (an A/B test when there are two or more)."""
    themes = settings.racing_themes or ["pitwall"]
    return themes[race_no % len(themes)]


def can_publish() -> str | None:
    if not settings.publish_enabled:
        return "PUBLISH_ENABLED is off"
    if not instagram.configured():
        return "the Instagram app isn't configured"
    with channels.use(channels.RACING):
        if not store.get_tokens("instagram"):
            return "Instagram isn't connected for the racing channel: /oauth/instagram/start?channel=racing"
    return None


def _spawn(target, job: dict, name: str) -> None:
    """Run a step in its own thread, remembered as ours while it runs (so recover() leaves it be)."""
    _mine.add(job["id"])

    def run() -> None:
        try:
            target(job)
        finally:
            _mine.discard(job["id"])

    threading.Thread(target=run, args=(), daemon=True, name=name).start()


def _new_id(kind: str) -> str:
    return f"race-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"


# ------------------------------------------------------------------ launch


def start(at: datetime | None = None, right_now: bool = False, restart: bool = False) -> dict:
    """Open race 1 and book the launch video: at `at` (default the next RACING_POST_TIME, with race 1
    in the video the day after), or with `right_now` as soon as it's rendered, race 1 then running
    at the next RACING_POST_TIME. Refuses if the channel has already started (unless `restart` and
    nothing has been posted or bet yet), or can't post (a started channel that can't post would sit
    with race 1 open forever; try the look with preview() instead)."""
    if state().get("started"):
        if not restart:
            raise ValueError("Sixel Speedway has already started; see GET /racing/state")
        if why := _posted_anything():
            raise ValueError(f"can't restart: {why}")
        _wipe()
    if why := can_publish():
        raise NotConnected(why)
    if right_now:
        slot, first_race = now() + timedelta(minutes=1), next_slot()
    else:
        slot = at or next_slot()
        if slot <= now() + timedelta(minutes=10):
            raise ValueError("pick a time at least 10 minutes ahead")
        first_race = _tomorrow(slot)
    stats = sim.initial_stats()
    race1 = races.open_race(1, stats, store.now_iso(), closes_for(first_race).isoformat())
    _set_state(started=True, launched_at=slot.isoformat(), stats=stats)
    job = _book("launch", card=1, run=None, slot=slot)
    job["next_slot"] = first_race.isoformat()  # when race 1's own video posts
    save(job)
    notify.send(f":checkered_flag: **Sixel Speedway**: race 1 is open (seal `{race1['seal'][:12]}…`, odds "
                f"{' · '.join(race1['odds'])}). The launch video posts {_local(job['publish_at'])}.")
    return job


def _posted_anything() -> str | None:
    """Why the channel can't be started again: something went out, or someone has played."""
    if any(r.get("post") for r in races.all_races()):
        return "a video has been posted"
    if any(j.get("status") in ("publishing", "done") and j.get("kind") != "preview" for j in recent(500)):
        return "a video has been posted or is posting"
    if ledger.players():
        return "people have already played"
    return None


def _wipe() -> None:
    """Back to before the launch: race records, booked jobs and the channel's state."""
    for p in races._dir().glob("*.json"):
        p.unlink()
    for job in recent(500):
        if job.get("kind") != "preview":
            (_jobs_dir() / f"{job['id']}.json").unlink(missing_ok=True)
    ledger._write("state.json", {})


def _book(kind: str, card: int, run: int | None, slot: datetime, publish: bool = True) -> dict:
    job = {"id": _new_id(kind), "kind": kind, "card": card, "run": run, "theme": theme_for(card),
           "channel": channels.RACING, "publish": publish, "publish_at": slot.isoformat(),
           "status": "booked", "created_at": store.now_iso(), "results": {}}
    save(job)
    return job


# ------------------------------------------------------------------ reading comments


def read_comments(race: dict) -> tuple[list[dict], str | None]:
    """The comments on the post carrying a race's card, without ours or opted-out accounts."""
    media = (race.get("post") or {}).get("media_id")
    if not media:
        return [], "no post"
    try:
        own, out = instagram.own_name().lower(), privacy.opted_out()
        cs = [{**c, "platform": "instagram"} for c in instagram.comments(media, limit=5000)]
        return [c for c in cs if c["user"].lower() != own and privacy._key(c["user"]) not in out], None
    except Exception as e:
        return [], str(e)[:300]


def poll(t: datetime | None = None) -> int:
    """Queue replies for new bets on the open race, and "closed" replies on recently closed ones."""
    if not settings.racing_replies:
        return 0
    t = t or now()
    queued = 0
    done = replies.known()
    for race in races.all_races()[-3:]:
        if not race.get("post"):
            continue
        open_ = race["status"] == "open"
        if not open_ and t - datetime.fromisoformat(race["closes_at"]) > timedelta(hours=LATE_REPLY_HOURS):
            continue
        with channels.use(channels.RACING):
            comments, err = read_comments(race)
        if err:
            continue
        items = []
        if open_:
            for row in ledger.provisional([c for c in comments if c["at"] < race["closes_at"]]):
                if row["comment"]["id"] in done:
                    continue
                r = replies.for_bet(row, race)
                if r:
                    items.append({"comment_id": row["comment"]["id"], "platform": "instagram", "kind": r[0],
                                  "text": r[1], "race": race["no"], "pid": row["pid"]})
        else:
            told = set(race.get("told_closed", []))
            from .bets import parse

            for c in comments:
                if c["at"] < race["closes_at"] or c["id"] in done or not parse(c["text"]):
                    continue
                pid = ledger.pid_for("instagram", c.get("uid", ""), c["user"])
                if pid in told:
                    continue
                told.add(pid)
                items.append({"comment_id": c["id"], "platform": "instagram", "kind": "closed", "pid": pid,
                              "text": replies.text("closed", c["id"], no=race["no"], next=race["no"] + 1),
                              "race": race["no"]})
            if told != set(race.get("told_closed", [])):
                race["told_closed"] = sorted(told)
                races.save(race)
        queued += replies.add(items)
    return queued


# ------------------------------------------------------------------ the steps


def _week(slot: datetime) -> str:
    y, w, _ = slot.astimezone(settings.tz).isocalendar()
    return f"{y}-W{w:02d}"


def _run_race(job: dict) -> dict:
    """Close race N, read its bets, run it, settle. Safe to repeat: a race already run isn't re-run."""
    race = races.get(job["run"])
    if race["status"] == "run":
        return race
    comments, err = read_comments(race)
    comments = [c for c in comments if c["at"] < race["closes_at"]]
    if err:
        notify.send(f":warning: **Sixel Speedway**: couldn't read the bets on race {race['no']} ({err}); it runs with none.")
    race["status"] = "closed"
    races.save(race)
    result = races.run(race)
    settled = ledger.settle(race, comments, result["order"][0], race["odds"])
    race.update(status="run", result=result, bets=settled["bets"], commenters=settled["commenters"],
                new_players=settled["new_players"], comments_read=len(comments), read_error=err,
                ran_at=store.now_iso(), revealed=True)
    races.save(race)
    return race


def _sunday(job: dict, slot: datetime) -> dict | None:
    """On Sundays: the weekly bonus, then the league table for the video."""
    local = slot.astimezone(settings.tz)
    if local.weekday() != 6:
        return None
    since = (slot - timedelta(days=7)).isoformat()
    activity: dict[str, int] = {}
    for r in races.all_races():
        if r.get("status") == "run" and r.get("ran_at", "") >= since:
            for pid in r.get("commenters", []):
                activity[pid] = activity.get(pid, 0) + 1
    launched = datetime.fromisoformat(state().get("launched_at", slot.isoformat()))
    doubled = slot - launched < timedelta(weeks=settings.racing_launch_weeks)
    bonus = ledger.weekly_bonus(_week(slot), activity, doubled)
    job["bonus"] = bonus
    tb = ledger.table(since=since)
    tb["week"] = f"WEEK {local.isocalendar()[1]}"
    return tb


def _open_next(job: dict, ran: dict, slot: datetime) -> dict:
    nxt = races.get(ran["no"] + 1)
    if nxt:
        return nxt
    stats = sim.drift(ran["stats"], int(ran["seed"], 16) % (2 ** 32))
    _set_state(stats=stats)
    return races.open_race(ran["no"] + 1, stats, store.now_iso(), closes_for(_tomorrow(slot)).isoformat())


def build(job: dict) -> dict:
    """Everything up to the video spec: for a race job, run and settle race N and open N+1."""
    slot = datetime.fromisoformat(job["publish_at"])
    if job["kind"] == "launch":
        return video.spec(job["theme"], races.get(job["card"]))
    ran = _run_race(job)
    table = _sunday(job, slot)
    nxt = _open_next(job, ran, slot)
    job["card"] = nxt["no"]
    bust = ledger.table()["bust"]
    return video.spec(job["theme"], nxt, ran, {"bets": ran["bets"]}, table, bust)


def _render(job: dict, spec: dict) -> None:
    from ..render.racing.engine import render

    job["status"] = "rendering"
    save(job)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    out = settings.videos_dir / f"{job['id']}-{secrets.token_urlsafe(8)}.mp4"
    cover = out.with_suffix(".jpg")
    job["render"] = render(spec, out, cover_path=cover)
    job.update(video=out.name, video_url=f"{settings.public_base_url}/media/{out.name}",
               cover_url=f"{settings.public_base_url}/media/{cover.name}")
    save(job)


def caption(job: dict) -> str:
    card = races.get(job["card"])
    fmt = sim.FORMATS[card["format"]]
    lines = [f"🏁 Race {card['no']} is open: {fmt['name']}, {fmt['laps']} lap{'s' if fmt['laps'] > 1 else ''} of "
             f"{card['track']['name']}. Comment a car and a stake, like 4 250 "
             f"(= §250 on 4 BLUE STREAK). Each comment is a bet. New here? You start with §1,000.",
             f"Bets close {_local(card['closes_at'])}. The race runs in the next video."]
    if job["kind"] == "race":
        ran = races.get(job["run"])
        win = ran["result"]["order"][0]
        lines.append(f"Race {ran['no']}: {win} {sim.CARS[win - 1]['name']} won at {ran['odds'][win - 1]}. "
                     f"Its seed: {ran['seed']} (check it against the seal at {settings.racing_domain}/race/{ran['no']}).")
    lines += [f"Race {card['no']} seal: {card['seal']}",
              f"Every bet, balance and seed check: {settings.racing_domain}",
              "Play money, no prizes. #racing #motorsport #sixelspeedway"]
    return "\n\n".join(lines)


FIRST_COMMENT = "Bet like this 👉 4 250 = §250 on 4 BLUE STREAK. One comment, one bet. Odds and form are on the race card."


def _publish(job: dict) -> None:
    try:
        res = {"ok": True, **instagram.publish_reel(job["video_url"], caption(job), job.get("cover_url"))}
    except Exception as e:
        log.exception("racing post failed")
        job["results"]["instagram"] = {"ok": False, "error": str(e)[:500]}
        return
    try:
        res["comment_id"] = instagram.comment(res["media_id"], FIRST_COMMENT)
    except Exception as e:
        res["comment_error"] = str(e)[:300]
    job["results"]["instagram"] = res
    job["published_at"] = store.now_iso()
    card = races.get(job["card"])
    card["post"] = {"job": job["id"], "media_id": res["media_id"], "url": res.get("url"), "posted_at": job["published_at"]}
    races.save(card)


def _report(job: dict, spec: dict | None = None) -> None:
    r = job.get("render") or {}
    ig = job["results"].get("instagram")
    what = "Launch video" if job["kind"] == "launch" else f"Race {job['run']} + card for race {job['card']}"
    extra = ""
    if job["kind"] == "race":
        ran = races.get(job["run"])
        bets = [b for b in ran.get("bets", []) if not b.get("refused")]
        win = ran["result"]["order"][0]
        extra = (f"\nWinner {win} {sim.CARS[win - 1]['name']} at {ran['odds'][win - 1]} · {len(bets)} bets, "
                 f"§{sum(b['stake'] for b in bets):,} staked, {ran.get('new_players', 0)} new players")
        if job.get("bonus") and not job["bonus"].get("already"):
            extra += f"\nWeekly bonus: §{job['bonus']['paid']:,} to {job['bonus']['players']} players"
    if ig:
        title = "Sixel Speedway post" if ig.get("ok") else "Sixel Speedway post FAILED"
        where = f"\n{ig.get('url') or ig.get('media_id')}" if ig.get("ok") else f"\n{ig['error']}"
    else:
        title, where = "Sixel Speedway ready", f"\nPosts at {_local(job['publish_at'])}" if job.get("publish") else ""
    video_file = settings.videos_dir / job["video"] if job.get("video") else None
    notify.send(f":checkered_flag: **{title}** `{job['id']}` ({job['theme']}): {what}, {r.get('duration', 0):.1f}s, "
                f"rendered in {r.get('seconds', 0):.0f}s{extra}{where}\n{job.get('video_url', '')}",
                attach=video_file if not ig else None)


def _fail(job: dict, e: Exception, step: str) -> None:
    log.exception("racing job %s failed during %s", job["id"], step)
    job.update(status="failed", error=f"{step}: {e}"[:1000])
    save(job)
    notify.send(f":warning: **Sixel Speedway**: `{job['id']}` failed during {step}: {e}")


def prepare(job: dict) -> None:
    try:
        with _render_lock, channels.use(channels.RACING):
            spec = build(job)
            job["spec"] = spec
            _render(job, spec)
            job["status"] = "scheduled" if job.get("publish") else "done"
            save(job)
            _report(job)
    except Exception as e:
        _fail(job, e, "preparing")


def post(job: dict) -> None:
    try:
        with channels.use(channels.RACING):
            _publish(job)
            ok = (job["results"].get("instagram") or {}).get("ok")
            job.update(status="done" if ok else "failed", finished_at=store.now_iso())
            if not ok:
                job["error"] = job["results"]["instagram"]["error"]
            save(job)
            _report(job)
            if ok:
                after = job.get("next_slot") or _tomorrow(datetime.fromisoformat(job["publish_at"])).isoformat()
                nxt = _book("race", card=job["card"] + 1, run=job["card"], slot=datetime.fromisoformat(after))
                notify.send(f":calendar: **Sixel Speedway**: race {job['card']} takes bets until "
                            f"{_local(races.get(job['card'])['closes_at'])}; its video posts {_local(nxt['publish_at'])}.")
    except Exception as e:
        _fail(job, e, "publishing")


def retry(job: dict) -> dict:
    """A failed or missed post: post the video now (rendering it again if it's gone)."""
    if job.get("status") not in ("failed", "missed"):
        raise ValueError("only failed or missed jobs can be retried")
    job["retry"] = True  # posts as soon as it's ready, however long ago its slot was
    if not job.get("video") or not (settings.videos_dir / job["video"]).exists():
        job.update(status="preparing", error=None)  # not "booked": the next tick would prepare it a second time
        save(job)
        _spawn(prepare, job, f"racing-{job['id']}")
    else:
        job.update(status="publishing", error=None, results={})
        save(job)
        _spawn(post, job, f"racing-post-{job['id']}")
    return job


def preview(theme: str, fmt: str = "") -> dict:
    """A sample video in any theme, sent to Discord: the open race (or a new one in `fmt`) run with
    a throwaway seed (never its real one, so the preview can't give the result away) and the bets
    so far, nothing saved."""
    from ..render.racing.themes import get as get_theme

    get_theme(theme)  # unknown themes and formats fail before the thread starts
    if fmt and fmt not in sim.FORMATS:
        raise ValueError(f"unknown format {fmt!r}; formats: {sorted(sim.FORMATS)}")
    job = {"id": f"race-preview-{time.strftime('%Y%m%d-%H%M%S')}", "kind": "preview", "theme": theme, "format": fmt,
           "status": "rendering", "results": {}, "publish_at": now().isoformat()}

    def run() -> None:
        try:
            with _render_lock, channels.use(channels.RACING):
                live = next((r for r in reversed(races.all_races()) if r["status"] == "open"), None)
                if fmt or not live:
                    live = None
                    card = races.draft(1, state().get("stats") or sim.initial_stats(), store.now_iso(),
                                       closes_for(next_slot()).isoformat(), fmt or None)
                else:
                    card = live
                comments, _ = read_comments(live) if live else ([], None)
                fake = {**card, "seed": sim.new_seed()}
                fake["result"] = races.run(fake)
                rows = [r for r in ledger.provisional(comments) if r["bet"] and r["stake"]]
                bets = [{"pid": r["pid"], "name": r["comment"]["user"], "car": r["bet"]["car"], "stake": r["stake"],
                         "asked": r["bet"]["stake"], "odds": card["odds"][r["bet"]["car"] - 1],
                         "returned": sim.payout(r["stake"], card["odds"][r["bet"]["car"] - 1])
                         if r["bet"]["car"] == fake["result"]["order"][0] else 0} for r in rows]
                tb = ledger.table(since=(now() - timedelta(days=7)).isoformat())
                tb["week"] = "PREVIEW"
                spec = video.spec(theme, card, fake, {"bets": bets}, tb, tb["bust"])
                _render(job, spec)
                job["status"] = "done"
                notify.send(f":test_tube: **Sixel Speedway preview** ({theme}, {sim.FORMATS[card['format']]['name']}): "
                            f"not a real result, the race uses a "
                            f"throwaway seed. {job['render']['duration']:.1f}s, rendered in {job['render']['seconds']:.0f}s\n"
                            f"{job['video_url']}", attach=settings.videos_dir / job["video"])
        except Exception as e:
            log.exception("racing preview failed")
            notify.send(f":warning: **Sixel Speedway preview** ({theme}) failed: {e}")

    threading.Thread(target=run, daemon=True, name=job["id"]).start()
    return job


# ------------------------------------------------------------------ schedule


def _lead(job: dict) -> timedelta:
    return timedelta(minutes=settings.racing_close_minutes if job["kind"] == "race" else 30)


def tick(t: datetime | None = None) -> None:
    t = t or now()
    for job in recent(200):
        if job.get("status") not in ("booked", "scheduled"):
            continue
        due = datetime.fromisoformat(job["publish_at"])
        if t - due > MISSED_AFTER and not job.get("retry"):
            job.update(status="missed", error=f"the server was not running at {due.isoformat()}")
            save(job)
            notify.send(f":warning: **Sixel Speedway**: `{job['id']}` missed its slot ({_local(job['publish_at'])}). "
                        f"Retry it with POST /racing/jobs/{job['id']}/retry.")
        elif job["status"] == "booked" and t >= due - _lead(job):
            job["status"] = "preparing"
            save(job)
            _spawn(prepare, job, f"racing-{job['id']}")
        elif job["status"] == "scheduled" and t >= due:
            job["status"] = "publishing"
            save(job)
            _spawn(post, job, f"racing-post-{job['id']}")


def recover(stale: timedelta = STALE) -> None:
    """Jobs left mid-way by a process that died. Only ones untouched for `stale` and not ours: during
    a deploy the old server is still finishing its own, and preparing a race twice settles it twice."""
    cutoff = time.time() - stale.total_seconds()
    for job in recent(200):
        st = job.get("status")
        if st not in WORKING or job["id"] in _mine:
            continue
        p = _jobs_dir() / f"{job['id']}.json"
        if p.exists() and p.stat().st_mtime > cutoff:
            continue
        if st in ("preparing", "rendering"):
            job["status"] = "booked"  # races already run aren't re-run (_run_race checks)
            save(job)
        elif st == "publishing":
            job.update(status="failed", error="the server restarted while posting")
            save(job)
            notify.send(f":warning: **Sixel Speedway**: the server restarted while posting `{job['id']}`; check "
                        f"@{settings.racing_handle} before retrying.")


METRIC_AGES = {"24h": 24, "7d": 168}


def refresh_metrics(t: datetime | None = None) -> None:
    """Each post's numbers at 24 hours and 7 days, for comparing themes (GET /racing/metrics)."""
    t = t or now()
    for job in recent(200):
        ig = (job.get("results") or {}).get("instagram") or {}
        if not ig.get("ok") or not job.get("published_at"):
            continue
        age = (t - datetime.fromisoformat(job["published_at"])).total_seconds() / 3600
        for name, hours in METRIC_AGES.items():
            if age >= hours and name not in job.get("metrics", {}):
                try:
                    with channels.use(channels.RACING):
                        job.setdefault("metrics", {})[name] = instagram.metrics(ig["media_id"])
                    save(job)
                except Exception:
                    log.exception("racing metrics for %s failed", job["id"])


def metrics_by_theme() -> dict:
    """Average numbers per theme, with how many bets each video's card drew."""
    out: dict[str, dict] = {}
    for job in recent(500):
        m = (job.get("metrics") or {}).get("7d") or (job.get("metrics") or {}).get("24h")
        if not m:
            continue
        card = races.get(job["card"]) or {}
        g = out.setdefault(job["theme"], {"posts": 0, "views": 0, "comments": 0, "likes": 0, "bets": 0})
        g["posts"] += 1
        for k in ("views", "comments", "likes"):
            g[k] += m.get(k) or 0
        g["bets"] += len([b for b in card.get("bets", []) if not b.get("refused")])
    for g in out.values():
        for k in ("views", "comments", "likes", "bets"):
            g[f"avg_{k}"] = round(g[k] / g["posts"], 1)
    return out


def _loop() -> None:
    last_poll = last_tick = 0.0
    while True:
        try:
            if lease.held() and state().get("started"):
                if time.time() - last_tick > 30:
                    last_tick = time.time()
                    recover()
                    tick()
                if time.time() - last_poll > settings.racing_poll_minutes * 60:
                    last_poll = time.time()
                    poll()
                    refresh_metrics()
                with channels.use(channels.RACING):
                    replies.send_due()
        except Exception:
            log.exception("racing tick failed")
        time.sleep(5)


def start_background() -> None:
    threading.Thread(target=_loop, daemon=True, name="racing-schedule").start()
