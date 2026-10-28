from __future__ import annotations

import logging
import re
import secrets
import threading
import time
import datetime as dt
import hashlib
import hmac
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, quote
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import health as monitoring  # "health" is the /health endpoint below
from . import channels, connections, legal, metrics, notify, pipeline, privacy, social, store, themes
from .adventure import campaign as adventure_campaign
from .adventure import jobs as adventure_jobs
from .adventure import voice as adventure_voice
from .adventure import votes as adventure_votes_mod
from .config import settings
from .publish import LABELS, PUBLISHERS
from .racing import jobs as racing_jobs
from .racing import ledger as racing_ledger
from .racing import races as racing_races
from .racing import replies as racing_replies
from .racing import web as racing_web
from .render import music
from .render.engine import Video
from .spec import QuizSpec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.api_token:
        raise RuntimeError("API_TOKEN must be set")
    pipeline.start_background()
    adventure_jobs.start()
    racing_jobs.start_background()
    yield


app = FastAPI(title="Quiz bot", lifespan=lifespan)
settings.videos_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.videos_dir), name="media")


SESSION_COOKIE = "quizbot_session"
SESSION_DAYS = 30


def _sign(value: str) -> str:
    return hmac.new(settings.api_token.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_session(provider: str) -> str:
    value = f"{provider}|{int(time.time()) + SESSION_DAYS * 86400}"
    return f"{value}|{_sign(value)}"


def valid_session(cookie: str) -> bool:
    try:
        provider, expiry, sig = cookie.split("|")
    except ValueError:
        return False
    return secrets.compare_digest(sig, _sign(f"{provider}|{expiry}")) and int(expiry) > time.time()


def is_authorised(request: Request, authorization: str = "", token: str = "") -> bool:
    supplied = authorization.removeprefix("Bearer ").strip() or token
    if settings.api_token and supplied and secrets.compare_digest(supplied, settings.api_token):
        return True
    # A sign-in cookie works for reading, the dashboard's refresh button, changing single bookings
    # (move, edit, cancel) and retrying a failed post. Booking batches and new posts still need the API
    # token. Changes also need the dashboard's X-Quizbot header: another site can't send a custom header
    # without a CORS preflight, which this server never grants, so it can't ride on the cookie.
    cookie_ok = valid_session(request.cookies.get(SESSION_COOKIE, ""))
    if request.method in ("GET", "HEAD"):
        return cookie_ok
    path = request.url.path
    dashboard_change = path == "/metrics/refresh" or (
        path.startswith("/schedule/") and request.method in ("PATCH", "DELETE")) or (
        request.method == "POST" and re.fullmatch(r"/jobs/[^/]+/retry|/privacy/requests/[^/]+/(approve|reject)", path) is not None)
    return cookie_ok and dashboard_change and request.headers.get("x-quizbot") == "1"


def require_token(request: Request, authorization: str = Header(default=""), token: str = Query(default="")) -> None:
    if not settings.api_token or not is_authorised(request, authorization, token):
        raise HTTPException(401, "bad token; send the API token, or sign in at /login")


# The bets domain (RACING_DOMAIN) serves the racing pages and the shared legal pages, nothing else;
# the racing pages exist on no other domain.
RACING_PAGES = re.compile(r"^/(|find|p/[^/]{1,64}|race/\d{1,6}|robots\.txt)$")
SHARED_PAGES = re.compile(r"^/(privacy(/.*)?|terms|data-deletion|health)$")


@app.middleware("http")
async def racing_domain(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0].lower()
    path = request.scope["path"]
    if settings.racing_domain and host == settings.racing_domain:
        if RACING_PAGES.match(path):
            request.scope["path"] = "/_racing" + path
        elif not SHARED_PAGES.match(path):
            return HTMLResponse(racing_web.not_found("There's no page here."), status_code=404)
    elif path.startswith("/_racing"):
        return HTMLResponse("Not Found", status_code=404)
    return await call_next(request)


@app.get("/_racing/", response_class=HTMLResponse, include_in_schema=False)
def racing_home():
    return racing_web.home()


@app.get("/_racing/find", include_in_schema=False)
def racing_find(name: str = ""):
    where = racing_web.find(name)
    if where:
        return RedirectResponse(quote(where), status_code=303)
    return HTMLResponse(racing_web.not_found(f"No punter called {name.strip()[:40]!r} yet. Comment a bet to join."), 404)


@app.get("/_racing/p/{name}", response_class=HTMLResponse, include_in_schema=False)
def racing_player(name: str):
    page = racing_web.player(name)
    if page is None:
        return HTMLResponse(racing_web.not_found("No punter by that name."), 404)
    return page


@app.get("/_racing/race/{no}", response_class=HTMLResponse, include_in_schema=False)
def racing_race_page(no: int):
    page = racing_web.race(no)
    if page is None:
        return HTMLResponse(racing_web.not_found(f"There's no race {no} yet."), 404)
    return page


@app.get("/_racing/robots.txt", include_in_schema=False)
def racing_robots():
    return HTMLResponse("User-agent: *\nDisallow: /p/\n", media_type="text/plain")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/status", dependencies=[Depends(require_token)])
def status():
    def tok(name):
        t = store.get_tokens(name)
        if not t:
            return None
        granted = t.get("permissions") or (t.get("scope") or "").split() or None
        out = {"expires_at": datetime.fromtimestamp(t["expires_at"], timezone.utc).isoformat()}
        # what it was given, and what it asks for now but wasn't given (→ reconnect); a connection made
        # before permissions were recorded is unknown, so it's offered a reconnect too
        wanted = PUBLISHERS[name].SCOPES.replace(",", " ").split()
        out.update(granted=granted, missing=[w for w in wanted if w not in (granted or [])],
                   permissions_unknown=not granted, reconnect_url=f"/oauth/{name}/start")
        return out

    return {
        "publish_enabled": settings.publish_enabled,
        "platforms": {name: {"configured": PUBLISHERS[name].configured(), "token": tok(name), **_account(name)}
                      for name in settings.platforms},
        "post_time": f"{settings.post_time} {settings.tz.key}",
        "scheduled": [{k: j.get(k) for k in ("slot", "status", "id")} for j in pipeline.scheduled_jobs()],
        "music_tracks": [p.name for p in music.library(settings.music_dir, settings.music_bundled)],
        "discord": bool(settings.discord_webhook_url),
        "voice_enabled": bool(settings.elevenlabs_api_key),
        "healthchecks": sorted(k for k in store._read("health.json", {}) if not k.startswith("warned:")),
        "voices": sorted(settings.voices),
        "instagram_stories": settings.instagram_stories,
        "instagram_carousels": f"{settings.carousel_day} {settings.carousel_time}" if settings.instagram_carousels else False,
        "recent_jobs": [{k: j.get(k) for k in ("id", "status", "created_at", "video_url", "error")} for j in store.list_jobs(5)],
        "channels": {cid: _channel_status(cid) for cid in channels.registry()},
    }


@app.get("/connections", dependencies=[Depends(require_token)])
def get_connections():
    """Every channel's accounts, each checked live: state (ok, broken, missing_permissions,
    expiring, not_connected, not_configured), which account it is, and its reconnect link."""
    return {"channels": [{"id": cid, "name": ch.name, "kind": ch.kind, "handle": ch.brand_handle}
                         for cid, ch in channels.registry().items()],
            "accounts": connections.report()}


def _channel_status(cid: str) -> dict:
    ch = channels.get(cid)
    with channels.use(cid):
        conns = {}
        for name in ch.platforms:
            if name not in PUBLISHERS:
                continue
            conns[name] = {"connected": bool(store.get_tokens(name)), **_account(name),
                           "connect_url": f"/oauth/{name}/start" + ("" if cid == channels.MAIN else f"?channel={cid}")}
    return {"name": ch.name, "kind": ch.kind, "handle": ch.brand_handle, "post_time": ch.post_time, "platforms": conns}


def _account(name: str) -> dict:
    """Which account a platform's token posts to, where the platform can say."""
    mod = PUBLISHERS[name]
    if not hasattr(mod, "account") or not store.get_tokens(name):
        return {}
    try:
        return {"account": mod.account()}
    except Exception as e:
        return {"account_error": str(e)[:200]}


@app.get("/instagram/media/{media_id}", dependencies=[Depends(require_token)])
def instagram_media(media_id: str):
    """Where a published Reel ended up (link, account, time)."""
    try:
        return PUBLISHERS["instagram"].media_info(media_id)
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@app.get("/schema", dependencies=[Depends(require_token)])
def schema():
    """JSON schema of the quiz spec, so the writing routine always targets the current format."""
    return QuizSpec.model_json_schema()


@app.post("/jobs", status_code=202, dependencies=[Depends(require_token)])
def create_job(spec: QuizSpec, dry_run: bool = False, force: bool = False, only: str = ""):
    """Render and publish one quiz now. `only` (e.g. "youtube") limits it to some platforms."""
    platforms = [p.strip() for p in only.split(",") if p.strip()] or None
    if platforms and set(platforms) - set(PUBLISHERS):
        raise HTTPException(400, f"only: use any of {sorted(PUBLISHERS)}")
    if vp := _voice_problem(spec):
        raise HTTPException(422, vp)
    if not force and not dry_run:
        repeats = _repeats(spec, _used_answers())
        if repeats:
            raise HTTPException(409, "answers already used recently, replace these rounds: " + "; ".join(repeats))
    job = pipeline.submit(spec, dry_run=dry_run, platforms=platforms)
    return {"job_id": job["id"], "status": job["status"]}


def _used_answers(exclude_jobs: set[str] = frozenset()) -> dict[str, str]:
    """answer -> where it was used: posted within REPEAT_DAYS, or held by a scheduled quiz."""
    since = (datetime.now(timezone.utc) - timedelta(days=settings.repeat_days)).isoformat()
    used = {a: f"posted {h['date'][:10]}" for h in store.history(1000) if h["date"] >= since for a in h.get("answers", [])}
    for j in pipeline.scheduled_jobs():
        if j["id"] not in exclude_jobs:
            for a in QuizSpec.model_validate(j["spec"]).answer_keys():
                used[a] = f"scheduled for {j['slot']}"
    return used


def _voice_problem(spec: QuizSpec) -> str | None:
    if spec.voice_name and spec.voice_name.lower() not in settings.voices:
        return f"voice_name {spec.voice_name!r} isn't one of {sorted(settings.voices)}"
    return None


def _repeats(spec: QuizSpec, used: dict[str, str]) -> list[str]:
    return [f"{a!r} ({used[a]})" for a in spec.answer_keys() if a in used]


# ------------------------------------------------------------------ weekly schedule

class ScheduleItem(BaseModel):
    date: dt.date | None = Field(default=None, description="Local date to post on; omit to take the next free day")
    time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$",
                             description="Local HH:MM; omit for POST_TIME. Use it for extra posts on a day.")
    spec: QuizSpec


class ScheduleRequest(BaseModel):
    items: list[ScheduleItem] = Field(min_length=1, max_length=14)
    replace: bool = Field(default=False, description="Replace quizzes already booked in those slots")


def _booking(j: dict) -> dict:
    spec = QuizSpec.model_validate(j["spec"])
    return {"time": pipeline.slot_key(j)[1], "publish_at": j["publish_at"], "status": j["status"], "job_id": j["id"],
            "title": spec.title, "theme": spec.theme, "video_url": j.get("video_url"), "tags": spec.tags,
            "intro": spec.intro, "cliffhanger": spec.rounds[-1].cliffhanger, "ask_theme": spec.ask_theme,
            "voice": (spec.voice_name or "default") if spec.voice else None,
            "picked_by": spec.picked_by.user if spec.picked_by else None,
            "rounds": [{"type": r.type, "answer": r.answer_text()} for r in spec.rounds]}


def _schedule_view(days: int = 14) -> dict:
    """One entry per day. A day is free when nothing is booked at POST_TIME; `bookings` lists
    everything that day, including extra posts at other times."""
    today = pipeline.today_local()
    first = today if datetime.now(timezone.utc) < pipeline.slot_time(today) else today + timedelta(days=1)
    by_day: dict[str, list[dict]] = {}
    for j in sorted(pipeline.booked_jobs(), key=lambda j: j["publish_at"]):
        by_day.setdefault(j["slot"], []).append(j)
    slots = []
    for k in range(days):
        day = first + timedelta(days=k)
        jobs = by_day.get(day.isoformat(), [])
        main_job = next((j for j in jobs if pipeline.slot_key(j)[1] == settings.post_time), None)
        slots.append({"date": day.isoformat(), "publish_at": pipeline.slot_time(day).isoformat(),
                      "status": main_job["status"] if main_job else "free",
                      "bookings": [_booking(j) for j in jobs]})
    return {"timezone": settings.tz.key, "post_time": settings.post_time, "first_open_date": first.isoformat(),
            "free_dates": [s["date"] for s in slots if s["status"] == "free"], "slots": slots}


@app.get("/schedule", dependencies=[Depends(require_token)])
def get_schedule(days: int = 14):
    """The next `days` posting days, with what's booked on each and which are free."""
    return _schedule_view(min(max(days, 1), 60))


@app.post("/schedule", status_code=202, dependencies=[Depends(require_token)])
def post_schedule(req: ScheduleRequest):
    """Book a batch of quizzes (e.g. next week's 7) into slots: one per day at POST_TIME by default,
    or at an item's own `time`. All-or-nothing: nothing is scheduled unless every item passes."""
    view = _schedule_view(60)
    first = date.fromisoformat(view["first_open_date"])
    now = datetime.now(timezone.utc)
    held = {pipeline.slot_key(j): j for j in pipeline.booked_jobs()}
    taken_dates = {i.date.isoformat() for i in req.items if i.date and not i.time}
    free = iter(d for d in view["free_dates"] if d not in taken_dates)
    plan, errors = [], []
    for n, item in enumerate(req.items):
        d = item.date or date.fromisoformat(next(free, None) or "1970-01-01")
        at = item.time or settings.post_time
        key = (d.isoformat(), at)
        if pipeline.slot_time(d, at) <= now:
            errors.append(f"item {n}: {d} {at} has already passed")
        elif d > first + timedelta(days=59):
            errors.append(f"item {n}: {d} is more than 60 days ahead")
        elif key in held and held[key]["status"] in ("done", "publishing"):
            errors.append(f"item {n}: {d} {at} has already been posted")
        elif key in held and not req.replace:
            errors.append(f"item {n}: {d} {at} already has `{held[key]['id']}` (send replace=true to swap it)")
        plan.append((d, at, item.spec))
    keys = [(d.isoformat(), at) for d, at, _ in plan]
    errors += [f"{d} {at} appears more than once in this batch" for d, at in sorted({k for k in keys if keys.count(k) > 1})]
    replaced = {held[k]["id"] for k in keys if k in held} if req.replace else set()
    used = _used_answers(exclude_jobs=replaced)
    for n, (d, at, spec) in enumerate(plan):
        try:  # lay out every scene now, so a quiz that can't render fails at booking, not at posting time
            Video(spec)
        except Exception as e:
            errors.append(f"item {n} ({d} {at}): can't be rendered: {type(e).__name__}: {e}"[:300])
        if rep := _repeats(spec, used):
            errors.append(f"item {n} ({d} {at}): answers already used: " + "; ".join(rep))
        if vp := _voice_problem(spec):
            errors.append(f"item {n} ({d} {at}): {vp}")
        for a in spec.answer_keys():
            used.setdefault(a, f"item {n} of this batch")
    if errors:
        raise HTTPException(409, {"errors": errors, "free_dates": view["free_dates"]})

    out = []
    for d, at, spec in plan:
        if (d.isoformat(), at) in held and req.replace:
            pipeline.cancel(held[(d.isoformat(), at)], "replaced")
        job = pipeline.submit(spec, slot=d, at=at)
        out.append({"date": d.isoformat(), "time": at, "publish_at": job["publish_at"], "job_id": job["id"]})
    _notify_booked(plan)
    if len(plan) >= 3:  # the weekly routine's batch (a one-off booking isn't)
        monitoring.ping("weekly-batch")
    return {"scheduled": out}


def _notify_booked(plan) -> None:
    lines = [f"**Booked {len(plan)} quiz{'zes' if len(plan) != 1 else ''}.** Each video is made "
             f"{settings.render_lead_minutes} min before it posts, with a preview here then."]
    for d, at, spec in sorted(plan, key=lambda p: (p[0], p[1])):
        answers = "; ".join(r.answer_text() for r in spec.rounds)
        lines.append(f"`{d:%a %d %b} {at}` **{spec.theme or 'General mix'}**: {spec.title.replace('*', '')}\n> {answers}")
    lines.append("To pull one: `DELETE /schedule/YYYY-MM-DD?time=HH:MM`")
    chunk = ""
    for line in lines:  # Discord caps a message at 2000 characters
        if chunk and len(chunk) + len(line) > 1900:
            notify.send(chunk)
            chunk = ""
        chunk += line[:1900] + "\n"
    notify.send(chunk)


@app.delete("/schedule/{day}", dependencies=[Depends(require_token)])
def delete_schedule(day: date, time: str | None = None):
    """Cancel a booked quiz (before it's posted). Pass ?time=HH:MM when the day has more than one."""
    jobs = [j for j in pipeline.scheduled_jobs() if j["slot"] == day.isoformat()
            and (time is None or pipeline.slot_key(j)[1] == time)]
    if not jobs:
        raise HTTPException(404, f"nothing scheduled on {day}" + (f" at {time}" if time else ""))
    if len(jobs) > 1:
        raise HTTPException(409, f"{len(jobs)} quizzes on {day}; pick one with ?time=" +
                            " or ?time=".join(pipeline.slot_key(j)[1] for j in jobs))
    job = jobs[0]
    if job["status"] == "publishing":
        raise HTTPException(409, "it's being posted right now")
    pipeline.cancel(job)
    return {"cancelled": job["id"], "date": day.isoformat(), "time": pipeline.slot_key(job)[1]}


class BookingChange(BaseModel):
    date: dt.date | None = Field(default=None, description="Move to this local date")
    time: str | None = Field(default=None, pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$", description="Move to this local HH:MM")
    spec: QuizSpec | None = Field(default=None, description="Replace the quiz's content")


@app.patch("/schedule/job/{job_id}", dependencies=[Depends(require_token)])
def change_booking(job_id: str, change: BookingChange):
    """Move a booked quiz to another slot and/or replace its content, with the same checks as booking."""
    job = store.get_job(job_id)
    if not job or not job.get("slot") or job["status"] in ("cancelled", "missed", "failed"):
        raise HTTPException(404, "no such booking")
    if job["status"] in ("done", "publishing"):
        raise HTTPException(409, "it has already been posted" if job["status"] == "done" else "it's being posted right now")
    if job["status"] in ("queued", "rendering"):
        raise HTTPException(409, "its video is being made right now; try again in a few minutes")
    day = change.date or date.fromisoformat(job["slot"])
    at = change.time or pipeline.slot_key(job)[1]
    errors = []
    if pipeline.slot_time(day, at) <= datetime.now(timezone.utc):
        errors.append(f"{day} {at} has already passed")
    clash = next((j for j in pipeline.booked_jobs() if j["id"] != job_id and pipeline.slot_key(j) == (day.isoformat(), at)), None)
    if clash:
        errors.append(f"{day} {at} already has `{clash['id']}`; move or cancel that one first")
    if change.spec is not None:
        try:
            Video(change.spec)
        except Exception as e:
            errors.append(f"can't be rendered: {type(e).__name__}: {e}"[:300])
        if rep := _repeats(change.spec, _used_answers(exclude_jobs={job_id})):
            errors.append("answers already used: " + "; ".join(rep))
        if vp := _voice_problem(change.spec):
            errors.append(vp)
    if errors:
        raise HTTPException(409, {"errors": errors})
    job = pipeline.update_booking(job, day, at, change.spec)
    return {"job_id": job_id, **_booking(job), "date": job["slot"]}


@app.get("/jobs/failed", dependencies=[Depends(require_token)])
def get_failed_jobs(days: int = 14):
    """Recent posts that didn't reach every platform, with each platform's error."""
    return [{"job_id": j["id"], "title": QuizSpec.model_validate(j["spec"]).title.replace("*", ""),
             "published_at": j["published_at"], "status": j["status"], "retrying": bool(j.get("retry")),
             "failed": pipeline.failures(j)} for j in pipeline.failed_jobs(days)]


@app.post("/jobs/{job_id}/retry", status_code=202, dependencies=[Depends(require_token)])
def retry_job(job_id: str):
    """Post a finished quiz again to the platforms it failed on. Its video is made again if it was deleted."""
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404)
    try:
        platforms = pipeline.retry(job)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return {"job_id": job_id, "retrying": platforms}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404)
    return job


@app.get("/jobs/{job_id}/comments", dependencies=[Depends(require_token)])
def job_comments(job_id: str):
    """The viewers' comments on a posted quiz, as the bot reads them (our own left out), with each
    one's theme reading: what a "comment a theme" post would take from it."""
    job = store.get_job(job_id)
    if not job or not job.get("results"):
        raise HTTPException(404, "no posted quiz with that id")
    from .cliffhanger import read_comments

    with channels.use(job.get("channel")):
        rows, readable, errors = read_comments(job)
    return {"job_id": job_id, "platforms_read": readable, "errors": errors,
            "comments": [{**c, "theme": themes._theme_text(c["text"])} for c in rows]}


@app.get("/comments/check", dependencies=[Depends(require_token)])
def comments_check(posts: int = Query(default=4, ge=1, le=10)):
    """Can the bot see viewers' comments? For each account's latest posts on Instagram: the comments it
    can read against the count Instagram reports. Fewer readable than reported (with none of ours)
    usually means the Meta app is still in Development mode."""
    from .publish import instagram

    def row(cid: str, job_id: str, media: str, title: str) -> dict:
        with channels.use(cid):
            try:
                reported = instagram._get(media, "comments_count").get("comments_count")
                rows = instagram.comments(media)
                own = instagram.own_name().lower()
                return {"job_id": job_id, "title": title, "reported": reported, "readable": len(rows),
                        "from_viewers": sum(c["user"].lower() != own for c in rows)}
            except Exception as e:
                return {"job_id": job_id, "title": title, "error": str(e)[:300]}

    out: dict[str, list] = {}
    quiz = [j for j in store.list_jobs(100) if j.get("status") == "done" and not j.get("dry_run")
            and (j.get("results", {}).get("instagram") or {}).get("media_id")]
    for cid in channels.registry():
        mine = [j for j in quiz if (j.get("channel") or channels.MAIN) == cid][:posts]
        out[cid] = [row(cid, j["id"], j["results"]["instagram"]["media_id"], j["spec"].get("title", "")) for j in mine]
    adv = [j for j in adventure_jobs.recent(30) if ((j.get("results") or {}).get("instagram") or {}).get("media_id")][:posts]
    out.setdefault(channels.ADVENTURE, []).extend(
        row(channels.ADVENTURE, j["id"], j["results"]["instagram"]["media_id"], j["id"]) for j in adv)
    return out


# ------------------------------------------------------------------ performance

@app.get("/metrics", dependencies=[Depends(require_token)])
def get_metrics():
    """Every posted quiz with its tags and per-platform numbers (latest + 1h/24h/7d snapshots)."""
    return metrics.report()


@app.post("/metrics/refresh", dependencies=[Depends(require_token)])
def refresh_metrics():
    """Fetch fresh numbers for every tracked post now, instead of waiting for the next round."""
    return {"updated": metrics.collect(force=True)}


class Insight(BaseModel):
    week_of: dt.date = Field(description="Monday of the week the findings cover")
    summary: str = Field(max_length=6000, description="What worked and what didn't, in plain words (markdown)")
    recommendations: list[str] = Field(default_factory=list, max_length=12,
                                       description="Concrete instructions for next week's batch")
    experiments: list[str] = Field(default_factory=list, max_length=6,
                                   description="What to test next week, one change each, with the tag to set")


@app.post("/insights", status_code=201, dependencies=[Depends(require_token)])
def post_insight(ins: Insight):
    """The weekly review stores its findings here; the Monday batch reads the latest."""
    rows = store._read("insights.json", [])
    rows.append({"at": store.now_iso(), **ins.model_dump(mode="json")})
    store._write("insights.json", rows[-52:])
    return {"stored": len(rows[-52:])}


@app.get("/insights", dependencies=[Depends(require_token)])
def get_insights(limit: int = 8):
    return store._read("insights.json", [])[-limit:][::-1]


@app.get("/insights/latest", dependencies=[Depends(require_token)])
def latest_insight():
    rows = store._read("insights.json", [])
    if not rows:
        raise HTTPException(404, "no review yet")
    return rows[-1]


@app.get("/dashboard")
def dashboard(request: Request, token: str = ""):
    """Performance dashboard. Signed-in browsers go straight in; others are sent to /login."""
    if not is_authorised(request, token=token):
        return RedirectResponse("/login?next=/dashboard")
    return FileResponse(Path(__file__).parent / "dashboard.html", media_type="text/html")


@app.get("/history", dependencies=[Depends(require_token)])
def get_history(limit: int = 60):
    return store.history(limit)


@app.post("/instagram/story/{job_id}", dependencies=[Depends(require_token)])
def instagram_story(job_id: str):
    """Post the "new quiz out now" story for a quiz that's already on Instagram (also a test that
    this account can post stories through the API)."""
    job = store.get_job(job_id)
    if not job or not job.get("results", {}).get("instagram", {}).get("ok"):
        raise HTTPException(404, "no quiz with that id is on Instagram")
    return social.post_story(job)


@app.post("/instagram/carousel", dependencies=[Depends(require_token)])
def instagram_carousel(job_id: str = "", dry_run: bool = True):
    """Make the swipe-to-play carousel for a quiz (default: this week's most viewed). dry_run=true
    (the default) only makes the slides and returns their URLs to look at; false posts it in the
    background (a couple of minutes) and Discord says how it went."""
    job = store.get_job(job_id) if job_id else social.carousel_pick()
    if not job or job.get("status") != "done":
        raise HTTPException(404, "no posted quiz to make a carousel from")
    if dry_run:
        return social.post_carousel(job, dry_run=True)
    threading.Thread(target=social.post_carousel, args=(job,), daemon=True, name="carousel").start()
    return {"job_id": job["id"], "posting": True, "result": f"see Discord, or GET /jobs/{job['id']} (carousel)"}


@app.get("/avatars", dependencies=[Depends(require_token)])
def list_avatars():
    """The profile pictures in rotation and which one was handed over last."""
    state = store._read("social.json", {})
    return {"pictures": [p.name for p in social.avatars()], "current": state.get("avatar"),
            "since": state.get("avatar_at"), "every_weeks": settings.avatar_every_weeks}


@app.post("/avatars/next", dependencies=[Depends(require_token)])
def next_avatar():
    """Send the next profile picture to Discord now (the rotation carries on from it)."""
    return social.send_next_avatar()


@app.post("/avatars/banner", dependencies=[Depends(require_token)])
def current_banner():
    """Put up the YouTube banner that matches the current profile picture (the rotation doesn't move)."""
    current = store._read("social.json", {}).get("avatar")
    pic = next((p for p in social.avatars() if p.name == current), None)
    banner = social._banner_for(pic) if pic else None
    if not banner:
        raise HTTPException(404, "no current picture with a matching banner-*.jpg")
    try:
        return {"banner": banner.name, "url": PUBLISHERS["youtube"].set_banner(banner)}
    except Exception as e:
        raise HTTPException(502, str(e)[:300])


@app.get("/", response_class=HTMLResponse)
def home():
    """The public home page: every account we run and all their videos, with the legal pages."""
    return legal.home_page()


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """The public privacy policy (GDPR), for the platforms' app review and anyone who asks."""
    return legal.privacy_page()


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    return legal.terms_page()


@app.get("/privacy/{name}.mp4")
def privacy_explainer(name: str):
    """The explainer videos shown on the privacy policy, one per channel."""
    path = legal.EXPLAINERS / f"{name}.mp4"
    if name not in legal.VIDEOS or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="video/mp4")


@app.get("/data-deletion")
def data_deletion():
    return RedirectResponse("/privacy#deletion")


# Viewers' self-service requests: no sign-in (they only name a public username), so a light
# per-address limit keeps the form from being used to flood the opt-out list.
_request_times: dict[str, list[float]] = {}
REQUESTS_PER_HOUR = 10


def _form_limited(request: Request) -> bool:
    # Cloudflare's header names the real visitor; the first X-Forwarded-For entry is whatever the client wrote
    ip = (request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
          or (request.client.host if request.client else "?"))
    now = time.time()
    recent = [t for t in _request_times.get(ip, []) if now - t < 3600]
    _request_times[ip] = recent + [now]
    if len(_request_times) > 5000:
        _request_times.clear()
    return len(recent) >= REQUESTS_PER_HOUR


async def _form(request: Request) -> dict[str, str]:
    body = (await request.body())[:10_000].decode("utf-8", "replace")
    return {k: v[0] for k, v in parse_qs(body).items()}


@app.get("/privacy/request", response_class=HTMLResponse)
def privacy_request_form():
    return legal.request_page()


@app.post("/privacy/request", response_class=HTMLResponse)
async def privacy_request(request: Request):
    form = await _form(request)
    user = re.sub(r"\s+", "", form.get("user", ""))
    platform, kind = form.get("platform", ""), form.get("kind", "")
    if _form_limited(request):
        return HTMLResponse(legal.request_page('<p class="err">Too many requests from here; please try again in an hour, or email us.</p>'), 429)
    if not re.fullmatch(r"@?[\w.\-]{1,60}", user) or platform not in ("instagram", "youtube") or kind not in ("opt-out", "delete"):
        return HTMLResponse(legal.request_page('<p class="err">Please enter your username (letters, numbers, dots, dashes and underscores) and pick the options.</p>'), 400)
    try:  # carried out once the named account comments the code (or the owner approves it)
        code = legal.open_request(kind, platform, user)
    except legal.TooManyPending:
        return HTMLResponse(legal.request_page('<p class="err">We have too many unconfirmed requests right now; please email us instead.</p>'), 503)
    return RedirectResponse(f"/privacy/status/{code}", 303)


@app.get("/privacy/status", response_class=HTMLResponse)
def privacy_status_query(code: str = ""):
    return legal.status_page(code[:20])


@app.get("/privacy/status/{code}", response_class=HTMLResponse)
def privacy_status(code: str):
    return legal.status_page(code[:20])


async def _meta_callback(request: Request, kind: str) -> str:
    data = legal.parse_signed_request((await _form(request)).get("signed_request", ""))
    if not data or not data.get("user_id"):
        raise HTTPException(400, "invalid signed_request")
    return legal.meta_user_removed(str(data["user_id"]), kind)


@app.post("/privacy/meta/deletion")
async def meta_data_deletion(request: Request):
    """Meta's data deletion request callback: answers with a status URL and confirmation code."""
    code = await _meta_callback(request, "delete")
    return {"url": f"{settings.public_base_url}/privacy/status/{code}", "confirmation_code": code}


@app.post("/privacy/meta/deauthorize")
async def meta_deauthorize(request: Request):
    """Meta's deauthorize callback: someone removed the app from their account."""
    await _meta_callback(request, "deauthorize")
    return {"ok": True}


@app.get("/privacy/requests", dependencies=[Depends(require_token)])
def privacy_requests_pending():
    """Form requests waiting for the viewer to comment their code (approve them by hand if they can't)."""
    return legal.pending()


@app.post("/privacy/requests/{code}/{action}", dependencies=[Depends(require_token)])
def privacy_request_settle(code: str, action: str):
    """approve: carry out a waiting request (you've checked it's them, e.g. they emailed); reject: close it."""
    if action not in ("approve", "reject"):
        raise HTTPException(404)
    req = (legal.approve if action == "approve" else legal.reject)(code[:20])
    if not req:
        raise HTTPException(404, "no waiting request with that code")
    return {"code": code.upper(), "status": req["status"], "done": req["done"]}


class PrivacyRequest(BaseModel):
    user: str = Field(min_length=1, max_length=80, description="The viewer's username, with or without @")


@app.post("/privacy/optout", dependencies=[Depends(require_token)])
def privacy_optout(req: PrivacyRequest):
    """A viewer objected: never read, show, credit or reply to them again."""
    privacy.opt_out(req.user)
    return {"opted_out": req.user}


@app.post("/privacy/erase", dependencies=[Depends(require_token)])
def privacy_erase(req: PrivacyRequest):
    """A viewer asked for deletion: remove them from every stored record, and opt them out."""
    return {"erased": req.user, "records_changed": privacy.erase(req.user)}


class CreditRequest(BaseModel):
    platform: str = Field(pattern="^(instagram|youtube)$")
    comment_id: str = Field(min_length=1, max_length=100)
    user: str = Field(min_length=1, max_length=80)
    text: str = Field(default="", max_length=200)
    message: str = Field(default="", max_length=300, description="The reply; defaults to the usual 'your theme won' one")


@app.post("/jobs/{job_id}/credit", dependencies=[Depends(require_token)])
def credit_theme(job_id: str, req: CreditRequest):
    """Credit a viewer for a posted quiz's theme after the fact: records them as `picked_by` and
    replies under their suggestion (for a pick that went out uncredited)."""
    from .publish import PUBLISHERS
    from .spec import PickedBy

    job = store.get_job(job_id)
    if not job or job.get("status") != "done":
        raise HTTPException(404, "no posted quiz with that id")
    if privacy.is_opted_out(req.user):
        raise HTTPException(409, "that viewer opted out")
    res = job.get("results", {}).get(req.platform, {})
    message = req.message or themes.REPLIES[req.platform].format(url=res.get("url") or "")
    with channels.use(job.get("channel")):
        try:
            PUBLISHERS[req.platform].reply(req.comment_id, message)
        except Exception as e:
            raise HTTPException(502, str(e)[:300])
    job["spec"]["picked_by"] = PickedBy(user=req.user.lstrip("@"), platform=req.platform, comment_id=req.comment_id,
                                        text=req.text).model_dump()
    job["picked_reply"] = {"ok": True, "user": req.user.lstrip("@"), "late": True, "at": store.now_iso()}
    store.save_job(job)
    return {"credited": req.user, "job_id": job_id, "reply": message}


@app.get("/themes/suggestions", dependencies=[Depends(require_token)])
def theme_suggestions(days: int = Query(default=8, ge=1, le=30)):
    """Themes viewers commented on the `ask_theme` posts of the last `days` days, grouped and ranked
    (most suggested first, then earliest). Credit a pick with the group's `first` entry as `picked_by`."""
    return themes.suggestions(days)


# ------------------------------------------------------------------ racing channel (Sixel Speedway)


@app.post("/racing/start", status_code=202, dependencies=[Depends(require_token)])
def racing_start(at: str = "", now: bool = False, restart: bool = False):
    """Launch the channel: open race 1 and book the launch video (rules + race 1's card) for
    `at` (HH:MM local or ISO; default the next RACING_POST_TIME), or with now=true as soon as it's
    rendered (race 1's video then posts at the next RACING_POST_TIME). restart=true starts over,
    only while nothing has been posted or bet. From then on it runs by itself.
    Needs the racing Instagram connected and PUBLISH_ENABLED; to see the look first, use /racing/preview."""
    try:
        job = racing_jobs.start(_when(at) if at else None, right_now=now, restart=restart)
    except racing_jobs.NotConnected as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return job


@app.get("/racing/state", dependencies=[Depends(require_token)])
def racing_state():
    rs = racing_races.all_races()
    q = racing_replies.queue()
    return {"state": racing_jobs.state(), "races": [racing_races.public(r) | {"bets": len(r.get("bets", []))} for r in rs[-5:]],
            "players": len(racing_ledger.players()), "table": racing_ledger.table(),
            "replies": {"waiting": len(q["items"]), "sent": len([i for i in q["sent"] if i.get("sent_at")]),
                        "paused_until": q.get("paused_until")},
            "themes": settings.racing_themes, "post_time": settings.racing_post_time, "domain": settings.racing_domain}


@app.get("/racing/races/{no}", dependencies=[Depends(require_token)])
def racing_race(no: int):
    r = racing_races.get(no)
    if not r:
        raise HTTPException(404, "no such race")
    return racing_races.public(r) | {"commenters": len(r.get("commenters", []))}


@app.get("/racing/jobs", dependencies=[Depends(require_token)])
def racing_jobs_list(limit: int = 20):
    return [{k: v for k, v in j.items() if k != "spec"} for j in racing_jobs.recent(limit)]


def _racing_job(job_id: str) -> dict:
    job = racing_jobs.get(job_id) if re.fullmatch(r"race-[\w-]+", job_id) else None
    if not job:
        raise HTTPException(404, "no such racing job")
    return job


@app.get("/racing/jobs/{job_id}", dependencies=[Depends(require_token)])
def racing_job(job_id: str):
    job = _racing_job(job_id)
    return {k: v for k, v in job.items() if k != "spec"}


@app.post("/racing/jobs/{job_id}/retry", status_code=202, dependencies=[Depends(require_token)])
def racing_retry(job_id: str):
    try:
        return racing_jobs.retry(_racing_job(job_id))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/racing/players", dependencies=[Depends(require_token)])
def racing_players(q: str = "", limit: int = 50):
    ps = sorted(racing_ledger.players().values(), key=lambda p: -p["balance"])
    if q:
        ps = [p for p in ps if q.lower().lstrip("@") in (p.get("name") or "").lower()]
    return ps[:limit]


@app.get("/racing/metrics", dependencies=[Depends(require_token)])
def racing_metrics():
    """Average views, comments, likes and bets per post, by theme: the A/B comparison."""
    return racing_jobs.metrics_by_theme()


@app.post("/racing/preview", status_code=202, dependencies=[Depends(require_token)])
def racing_preview(theme: str = "pitwall", format: str = ""):
    """Render a sample video in a theme and send it to Discord: the open race, or a new one in
    `format` (oval, gp, rally, figure8, endurance, drag). The race uses a throwaway seed, so it
    shows nothing about the real result."""
    try:
        return racing_jobs.preview(theme, format)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ music library

MUSIC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,100}$")
MAX_TRACK = 40 * 1024 * 1024


# ------------------------------------------------------------------ adventure channel (preview only)

def _when(at: str) -> datetime:
    """"HH:MM" (the next time it's that o'clock, local) or an ISO date-time, as UTC."""
    if re.fullmatch(r"\d{1,2}:\d{2}", at):
        h, m = (int(x) for x in at.split(":"))
        local = datetime.now(settings.tz)
        t = local.replace(hour=h, minute=m, second=0, microsecond=0)
        return (t if t > local else t + timedelta(days=1)).astimezone(timezone.utc)
    t = datetime.fromisoformat(at)
    return (t if t.tzinfo else t.replace(tzinfo=settings.tz)).astimezone(timezone.utc)


@app.post("/adventure/episode0", status_code=202, dependencies=[Depends(require_token)])
def adventure_episode0(spec: dict, voice: bool = True, publish: bool = False, at: str = "", series: bool = True):
    """Render an Episode 0 part (voiced unless voice=false) and send it to Discord.
    publish=true also posts it now to the adventure channel's Instagram, options as the first comment.
    at=09:00 (or an ISO time) books it instead: votes counted and rendered an hour before, posted at
    that time; with series (default) each part then books the next for the same time tomorrow.
    Body: {"part": 1} or e.g. {"part": 2, "fear": "wraith", "recap": {"pick": 2, "votes": [3, 2, 7]}}."""
    try:
        when = _when(at) if at else None
        job = adventure_jobs.submit({"kind": "episode0", **spec}, use_voice=voice, publish=publish, at=when,
                                    series=series and when is not None)
    except adventure_jobs.NotConnected as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    return {k: job.get(k) for k in ("id", "status", "voice", "publish", "series", "publish_at")} | {
        "chars": job["script"]["chars"], "script": job["script"]["text"], "caption": job["script"]["caption"]}


@app.delete("/adventure/jobs/{job_id}", dependencies=[Depends(require_token)])
def adventure_cancel(job_id: str):
    job = adventure_jobs.get(job_id) if re.fullmatch(r"adv-[\w-]+", job_id) else None
    if not job:
        raise HTTPException(404, "no such adventure job")
    if job["status"] not in ("booked", "scheduled"):
        raise HTTPException(409, f"it is {job['status']}; only booked or ready posts can be cancelled")
    adventure_jobs.cancel(job)
    return {"id": job_id, "status": "cancelled"}


@app.get("/adventure/jobs/{job_id}/votes", dependencies=[Depends(require_token)])
def adventure_votes(job_id: str):
    """The votes so far on a posted part (nothing is decided or saved)."""
    job = adventure_jobs.get(job_id) if re.fullmatch(r"adv-[\w-]+", job_id) else None
    media = job and (job.get("results", {}).get("instagram") or {}).get("media_id")
    if not media:
        raise HTTPException(404, "that job has no Instagram post")
    with channels.use(channels.ADVENTURE):
        own = PUBLISHERS["instagram"].own_name().lower()
        comments = [c for c in PUBLISHERS["instagram"].comments(media) if c["user"].lower() != own]
    t = adventure_votes_mod.tally(comments, job["script"]["options"])
    pick, how = adventure_votes_mod.decide(t["counts"], job["script"]["default"], job["id"])
    return t | {"leading": job["script"]["options"][pick], "how": how}


@app.get("/adventure/jobs", dependencies=[Depends(require_token)])
def adventure_jobs_list(limit: int = 20):
    return adventure_jobs.recent(limit)


@app.get("/adventure/jobs/{job_id}", dependencies=[Depends(require_token)])
def adventure_job(job_id: str):
    job = adventure_jobs.get(job_id) if re.fullmatch(r"adv-[\w-]+", job_id) else None
    if not job:
        raise HTTPException(404, "no such adventure job")
    return job


@app.get("/adventure/state", dependencies=[Depends(require_token)])
def adventure_state():
    """Everything the weekly story routine needs: the hero and what has happened, what the next arc
    must look like (dates, what it links from, ids taken), the season bible, an example arc, the
    scenes/foes/skills with this hero's odds at every DC, and the voice budget."""
    o = adventure_campaign.overview()
    try:
        o["vocab"] = adventure_campaign.vocab(o["state"]["hero"])
    except Exception as e:  # the routine can still write from the example
        o["vocab"] = {"error": str(e)[:300]}
    o["voice"] = {"month": adventure_voice.month(), "spent": adventure_voice.spent(), "budget": settings.adventure_voice_budget}
    o["post_time"] = settings.adventure_post_time
    return o


@app.post("/adventure/arc", status_code=201, dependencies=[Depends(require_token)])
def adventure_arc(arc: dict, replace: bool = False, dry_run: bool = False):
    """Submit the next weekly arc. Every problem comes back at once (422; 409 if an arc already
    covers those dates). dry_run=true only checks it. replace=true swaps an arc nothing has played yet."""
    if dry_run:
        r = adventure_campaign.validate(arc)
        if not r.get("ok"):
            raise HTTPException(422, {"problems": r.get("problems"), "expected": r["expected"]})
        return {"ok": True, "dry_run": True}
    r = adventure_campaign.accept(arc, replace=replace)
    if not r["ok"]:
        raise HTTPException(409 if r.get("conflict") else 422, {"problems": r["problems"], "expected": r.get("expected")})
    r["retried"] = adventure_jobs.retry_waiting()
    notify.send(f":scroll: **Adventure**: arc `{r['id']}` booked: {r['nodes']} scenes over {r['days']} days from {r['start_date']}.")
    return r


@app.get("/adventure/arcs/{arc_id}", dependencies=[Depends(require_token)])
def adventure_arc_get(arc_id: str):
    arc = next((a for a in adventure_campaign.arcs() if a["id"] == arc_id), None)
    if not arc:
        raise HTTPException(404, "no such arc")
    return arc


@app.get("/adventure/credits", dependencies=[Depends(require_token)])
def adventure_credits():
    return {"month": adventure_voice.month(), "spent": adventure_voice.spent(),
            "budget": settings.adventure_voice_budget, "voice_id": settings.adventure_voice_id,
            "model": settings.adventure_voice_model, "ledger": adventure_voice.ledger()}


@app.get("/music", dependencies=[Depends(require_token)])
def list_music():
    """The library: your uploads and the bundled CC0 tracks (assets/music/LICENSES.md)."""
    return [{"name": p.name, "bytes": p.stat().st_size, "source": "bundled" if music.is_bundled(p) else "uploaded"}
            for p in music.library(settings.music_dir, settings.music_bundled)]


@app.put("/music/{name}", status_code=201, dependencies=[Depends(require_token)])
async def upload_music(name: str, request: Request):
    """Upload a track as the raw request body: curl -T track.mp3 APP_URL/music/track.mp3"""
    if not MUSIC_NAME.match(name) or "." not in name or f".{name.rsplit('.', 1)[1].lower()}" not in music.EXTS:
        raise HTTPException(400, f"name must be a plain file name ending in one of {sorted(music.EXTS)}")
    settings.music_dir.mkdir(parents=True, exist_ok=True)
    path = settings.music_dir / name
    tmp = path.with_suffix(path.suffix + ".part")
    size = 0
    with tmp.open("wb") as fh:
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_TRACK:
                fh.close()
                tmp.unlink(missing_ok=True)
                raise HTTPException(413, "track larger than 40MB")
            fh.write(chunk)
    if size == 0:
        tmp.unlink(missing_ok=True)
        raise HTTPException(400, "empty body")
    tmp.replace(path)
    return {"name": name, "bytes": size}


@app.delete("/music/{name}", dependencies=[Depends(require_token)])
def delete_music(name: str):
    path = settings.music_dir / name
    if MUSIC_NAME.match(name) and not path.is_file() and (music.BUNDLED / name).is_file():
        raise HTTPException(409, "that's a bundled track: upload a file with the same name to replace it, "
                                 "or set MUSIC_BUNDLED=false to leave all of them out")
    if not MUSIC_NAME.match(name) or not path.is_file():
        raise HTTPException(404)
    path.unlink()
    return {"deleted": name}


# ------------------------------------------------------------------ OAuth (one-time browser setup)

# state -> (provider, expiry, "login", next page) or (provider, expiry, "connect", channel, switch)
_states: dict[str, tuple] = {}
PROVIDERS = PUBLISHERS


def _new_state(entry: tuple) -> str:
    """Remember an OAuth round trip, dropping expired ones (/login/... is public, so this must not grow)."""
    t = time.time()
    for k in [k for k, v in _states.items() if v[1] < t]:
        _states.pop(k, None)
    state = secrets.token_urlsafe(16)
    _states[state] = entry
    return state


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = (Path(__file__).parent / "login.html").read_text()
    return HTMLResponse(html.replace("{{title}}", title).replace("{{body}}", body), status_code=status)


def _connected_anywhere(provider: str) -> bool:
    return any(store.get_tokens(provider, channel=c) for c in channels.registry())


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/dashboard"):
    """Sign in with the Instagram or YouTube account the bot posts to."""
    nxt = next if next.startswith("/") and not next.startswith("//") else "/dashboard"
    if valid_session(request.cookies.get(SESSION_COOKIE, "")):
        return RedirectResponse(nxt)
    buttons = "".join(
        f'<a class="btn {p}" href="/login/{p}?next={quote(nxt)}">Sign in with {LABELS[p]}</a>'
        for p in ("instagram", "youtube") if PUBLISHERS[p].configured() and _connected_anywhere(p))
    if not buttons:
        buttons = '<p class="note">No account is connected yet. Use the API token for now.</p>'
    return _page("Sign in", f"<h1>Quiz bot</h1><p class='note'>Sign in with the account the bot posts to.</p>{buttons}")


@app.get("/login/{provider}")
def login_start(provider: str, next: str = "/dashboard"):
    if provider not in ("instagram", "youtube") or not _connected_anywhere(provider):
        raise HTTPException(404)
    nxt = next if next.startswith("/") and not next.startswith("//") else "/dashboard"
    state = _new_state((provider, time.time() + 600, "login", nxt))
    return RedirectResponse(PROVIDERS[provider].authorize_url(state, login=True))


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login")
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/oauth/{provider}/start", dependencies=[Depends(require_token)])
def oauth_start(provider: str, channel: str = channels.MAIN, switch: bool = False):
    """Connect (or reconnect) a channel's account on a platform. Works from the dashboard with the
    sign-in cookie. ?channel=adventure connects that channel's own account. A reconnect must approve
    the same account as before (switch=true connects a different one on purpose), and never one that
    another channel already posts to."""
    mod = PROVIDERS.get(provider)
    if not mod:
        raise HTTPException(404)
    if channel not in channels.registry():
        raise HTTPException(404, f"no channel {channel!r}; channels: {sorted(channels.registry())}")
    state = _new_state((provider, time.time() + 600, "connect", channel, switch))
    return RedirectResponse(mod.authorize_url(state))


@app.get("/oauth/{provider}/callback", response_class=HTMLResponse)
def oauth_callback(request: Request, provider: str, code: str = "", state: str = "", error: str = "",
                   error_description: str = ""):
    expected = _states.pop(state, None)
    if not expected or expected[0] != provider or expected[1] < time.time():
        raise HTTPException(400, "invalid or expired state; start again")
    if error or not code:
        raise HTTPException(400, f"{provider} returned an error: {error} {error_description}")
    if expected[2] == "login":
        return _finish_login(provider, code.removesuffix("#_"), expected[3])
    signed_in = valid_session(request.cookies.get(SESSION_COOKIE, ""))
    return _connect(provider, expected[3] or channels.MAIN, code.removesuffix("#_"),
                    switch=len(expected) > 4 and expected[4], signed_in=signed_in)


def _account_name(provider: str) -> str:
    acct = _account(provider).get("account") or {}
    return acct.get("username") or acct.get("title") or PROVIDERS[provider].connected_identity() or "an account"


def _stored_identity(provider: str, tok: dict | None) -> str | None:
    """Which account a saved connection belongs to, from what was saved (no network)."""
    if not tok:
        return None
    return str(tok.get("user_id") or tok.get("channel_id") or "") or None


def _identity(provider: str, channel: str) -> str | None:
    with channels.use(channel):
        try:
            return PROVIDERS[provider].connected_identity()
        except Exception:  # a dead connection still names its account in what was saved
            return _stored_identity(provider, store.get_tokens(provider))


def _connect(provider: str, channel: str, code: str, switch: bool = False, signed_in: bool = False):
    """Save a channel's connection. Refused (and the old one put back) when the approved account is
    one another channel posts to, or, on a reconnect, a different account from before."""
    mod, ch = PROVIDERS[provider], channels.get(channel)
    again = f"/oauth/{provider}/start" + ("" if channel == channels.MAIN else f"?channel={channel}")
    retry = f"<a class='btn {provider}' href='{escape(again)}'>Try again</a>"
    with channels.use(channel):
        previous = store.get_tokens(provider)
        before = _stored_identity(provider, previous)
        try:
            mod.exchange_code(code)
        except Exception as e:
            logging.getLogger(__name__).warning("%s connect failed (%s): %s", provider, channel, e)
            return _page("Not connected", f"<h1>Not connected</h1><p class='note'>{escape(str(e)[:300])}</p>{retry}", 400)
    who = _identity(provider, channel)
    clash = next((c for c in channels.registry() if c != channel and who and _identity(provider, c) == who), None)
    refused = None
    if clash:
        other = channels.get(clash)
        refused = _page("Wrong account", f"<h1>That's the {escape(other.name)} account</h1><p class='note'>You approved "
                        f"with the {LABELS[provider]} account that <b>{escape(other.name)}</b> posts to. Choose "
                        f"<b>@{escape(ch.brand_handle)}</b> instead when {LABELS[provider]} asks which account.</p>{retry}", 409)
    elif before and who and who != before and not switch:
        switch_url = again + ("&" if "?" in again else "?") + "switch=true"
        refused = _page("Different account", f"<h1>That's a different account</h1><p class='note'><b>{escape(ch.name)}</b> "
                        f"was connected to another {LABELS[provider]} account, so nothing was changed. Choose "
                        f"<b>@{escape(ch.brand_handle)}</b> when {LABELS[provider]} asks.</p>{retry}"
                        f"<a class='btn plain' href='{escape(switch_url)}'>Connect a different account on purpose</a>", 409)
    if refused:
        store.set_tokens(provider, previous, channel=channel)  # put back whatever was there
        return refused
    with channels.use(channel):
        name = _account_name(provider)
    notify.send(f":link: **{ch.name}**: {LABELS[provider]} connected as @{name}")
    if signed_in:  # started from the dashboard: go back there
        return RedirectResponse(f"/dashboard?connected={provider}&channel={channel}#accounts", status_code=303)
    expected = ch.brand_handle.lower().lstrip("@")
    note = "" if provider != "instagram" or not expected or name.lower().lstrip("@") == expected else (
        f"<p class='note'>Expected @{escape(expected)}. If that's wrong, sign in to the right account and start again.</p>")
    return _page("Connected", f"<h1>{LABELS[provider]} connected ✔</h1><p>@{escape(name)} is now connected to the "
                 f"<b>{escape(ch.name)}</b> channel.</p>{note}<p class='note'>You can close this tab.</p>")


def _finish_login(provider: str, code: str, nxt: str):
    mod = PROVIDERS[provider]
    try:
        who = mod.login_identity(code)
    except Exception as e:
        # 400, not 5xx: Cloudflare swaps an origin 502 for its own "Bad gateway" page, hiding this message
        logging.getLogger(__name__).warning("%s sign-in failed: %s", provider, e)
        hint = (" The YouTube connection needs its new permissions first: sign in with Instagram, then press"
                " Reconnect YouTube on the dashboard."
                if provider == "youtube" and "scope" in str(e).lower() else "")
        return _page("Sign-in failed", f"<h1>Sign-in failed</h1><p class='note'>{escape(str(e)[:300])}{hint}</p>"
                     "<a class='btn plain' href='/login'>Try again</a>", 400)
    # any channel's account will do: they're all yours, and the browser is often signed in to another one
    owners = [o for c in channels.registry() if (o := _identity(provider, c))]
    if not any(secrets.compare_digest(who, o) for o in owners):
        return _page("Not this account", f"<h1>That's a different account</h1><p class='note'>Sign in with one of the "
                     f"{LABELS[provider]} accounts this bot posts to.</p><a class='btn plain' href='/login'>Try again</a>", 403)
    resp = RedirectResponse(nxt or "/dashboard")
    resp.set_cookie(SESSION_COOKIE, make_session(provider), max_age=SESSION_DAYS * 86400, httponly=True,
                    secure=settings.public_base_url.startswith("https"), samesite="lax", path="/")
    return resp
