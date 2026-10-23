from __future__ import annotations

import logging
import re
import secrets
import time
import datetime as dt
import hashlib
import hmac
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from urllib.parse import quote
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import metrics, notify, pipeline, store
from .config import settings
from .publish import LABELS, PUBLISHERS
from .render import music
from .render.engine import Video
from .spec import QuizSpec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.api_token:
        raise RuntimeError("API_TOKEN must be set")
    pipeline.start_background()
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
    # A sign-in cookie works for reading, the dashboard's refresh button, and changing single bookings
    # (move, edit, cancel). Booking batches and posting still need the API token. Changes also need the
    # dashboard's X-Quizbot header: another site can't send a custom header without a CORS preflight,
    # which this server never grants, so it can't ride on the cookie.
    cookie_ok = valid_session(request.cookies.get(SESSION_COOKIE, ""))
    if request.method in ("GET", "HEAD"):
        return cookie_ok
    dashboard_change = request.url.path == "/metrics/refresh" or (
        request.url.path.startswith("/schedule/") and request.method in ("PATCH", "DELETE"))
    return cookie_ok and dashboard_change and request.headers.get("x-quizbot") == "1"


def require_token(request: Request, authorization: str = Header(default=""), token: str = Query(default="")) -> None:
    if not settings.api_token or not is_authorised(request, authorization, token):
        raise HTTPException(401, "bad token; send the API token, or sign in at /login")


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
        if granted:  # what it was given, and what it asks for now but wasn't given (→ reconnect)
            mod = PUBLISHERS[name]
            wanted = (getattr(mod, "SCOPES", None) or mod.scopes()).replace(",", " ").split()
            out.update(granted=granted, missing=[w for w in wanted if w not in granted],
                       reconnect_url=f"/oauth/{name}/start")
        return out

    return {
        "publish_enabled": settings.publish_enabled,
        "platforms": {name: {"configured": PUBLISHERS[name].configured(), "token": tok(name), **_account(name)}
                      for name in settings.platforms},
        "tiktok_mode": settings.tiktok_mode,
        "post_time": f"{settings.post_time} {settings.tz.key}",
        "scheduled": [{k: j.get(k) for k in ("slot", "status", "id")} for j in pipeline.scheduled_jobs()],
        "music_tracks": [p.name for p in music.library(settings.music_dir)],
        "discord": bool(settings.discord_webhook_url),
        "recent_jobs": [{k: j.get(k) for k in ("id", "status", "created_at", "video_url", "error")} for j in store.list_jobs(5)],
    }


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
    if errors:
        raise HTTPException(409, {"errors": errors})
    job = pipeline.update_booking(job, day, at, change.spec)
    return {"job_id": job_id, **_booking(job), "date": job["slot"]}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404)
    return job


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


# ------------------------------------------------------------------ music library

MUSIC_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._()-]{0,100}$")
MAX_TRACK = 40 * 1024 * 1024


@app.get("/music", dependencies=[Depends(require_token)])
def list_music():
    return [{"name": p.name, "bytes": p.stat().st_size} for p in music.library(settings.music_dir)]


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
    if not MUSIC_NAME.match(name) or not path.is_file():
        raise HTTPException(404)
    path.unlink()
    return {"deleted": name}


# ------------------------------------------------------------------ OAuth (one-time browser setup)

_states: dict[str, tuple[str, float, str, str]] = {}  # state -> (provider, expiry, "connect"|"login", next)
PROVIDERS = PUBLISHERS


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = (Path(__file__).parent / "login.html").read_text()
    return HTMLResponse(html.replace("{{title}}", title).replace("{{body}}", body), status_code=status)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/dashboard"):
    """Sign in with the Instagram or YouTube account the bot posts to."""
    nxt = next if next.startswith("/") and not next.startswith("//") else "/dashboard"
    if valid_session(request.cookies.get(SESSION_COOKIE, "")):
        return RedirectResponse(nxt)
    buttons = "".join(
        f'<a class="btn {p}" href="/login/{p}?next={quote(nxt)}">Sign in with {LABELS[p]}</a>'
        for p in ("instagram", "youtube") if PUBLISHERS[p].configured() and store.get_tokens(p))
    if not buttons:
        buttons = '<p class="note">No account is connected yet. Use the API token for now.</p>'
    return _page("Sign in", f"<h1>Quiz bot</h1><p class='note'>Sign in with the account the bot posts to.</p>{buttons}")


@app.get("/login/{provider}")
def login_start(provider: str, next: str = "/dashboard"):
    if provider not in ("instagram", "youtube") or not store.get_tokens(provider):
        raise HTTPException(404)
    state = secrets.token_urlsafe(16)
    nxt = next if next.startswith("/") and not next.startswith("//") else "/dashboard"
    _states[state] = (provider, time.time() + 600, "login", nxt)
    return RedirectResponse(PROVIDERS[provider].authorize_url(state, login=True))


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login")
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/oauth/{provider}/start", dependencies=[Depends(require_token)])
def oauth_start(provider: str):
    mod = PROVIDERS.get(provider)
    if not mod:
        raise HTTPException(404)
    state = secrets.token_urlsafe(16)
    _states[state] = (provider, time.time() + 600, "connect", "")
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
    PROVIDERS[provider].exchange_code(code.removesuffix("#_"))
    if valid_session(request.cookies.get(SESSION_COOKIE, "")):  # started from the dashboard: go back there
        return RedirectResponse(f"/dashboard?connected={provider}")
    return f"<h2>{LABELS[provider]} connected ✔</h2><p>You can close this tab.</p>"


def _finish_login(provider: str, code: str, nxt: str):
    mod = PROVIDERS[provider]
    try:
        who, owner = mod.login_identity(code), mod.connected_identity()
    except Exception as e:
        # 400, not 5xx: Cloudflare swaps an origin 502 for its own "Bad gateway" page, hiding this message
        logging.getLogger(__name__).warning("%s sign-in failed: %s", provider, e)
        hint = (" The YouTube connection needs its new permissions first: sign in with Instagram, then press"
                " Reconnect YouTube on the dashboard."
                if provider == "youtube" and "scope" in str(e).lower() else "")
        return _page("Sign-in failed", f"<h1>Sign-in failed</h1><p class='note'>{escape(str(e)[:300])}{hint}</p>"
                     "<a class='btn plain' href='/login'>Try again</a>", 400)
    if not owner or not secrets.compare_digest(who, owner):
        return _page("Not this account", f"<h1>That's a different account</h1><p class='note'>Sign in with the "
                     f"{LABELS[provider]} account this bot posts to.</p><a class='btn plain' href='/login'>Try again</a>", 403)
    resp = RedirectResponse(nxt or "/dashboard")
    resp.set_cookie(SESSION_COOKIE, make_session(provider), max_age=SESSION_DAYS * 86400, httponly=True,
                    secure=settings.public_base_url.startswith("https"), samesite="lax", path="/")
    return resp
