from __future__ import annotations

import logging
import re
import secrets
import time
import datetime as dt
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import pipeline, store
from .config import settings
from .publish import LABELS, PUBLISHERS
from .render import music
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


def require_token(authorization: str = Header(default=""), token: str = Query(default="")) -> None:
    supplied = authorization.removeprefix("Bearer ").strip() or token
    if not settings.api_token or not secrets.compare_digest(supplied, settings.api_token):
        raise HTTPException(401, "bad token")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/status", dependencies=[Depends(require_token)])
def status():
    def tok(name):
        t = store.get_tokens(name)
        return None if not t else {"expires_at": datetime.fromtimestamp(t["expires_at"], timezone.utc).isoformat()}

    return {
        "publish_enabled": settings.publish_enabled,
        "platforms": {name: {"configured": PUBLISHERS[name].configured(), "token": tok(name)} for name in settings.platforms},
        "tiktok_mode": settings.tiktok_mode,
        "post_time": f"{settings.post_time} {settings.tz.key}",
        "scheduled": [{k: j.get(k) for k in ("slot", "status", "id")} for j in pipeline.scheduled_jobs()],
        "music_tracks": [p.name for p in music.library(settings.music_dir)],
        "discord": bool(settings.discord_webhook_url),
        "recent_jobs": [{k: j.get(k) for k in ("id", "status", "created_at", "video_url", "error")} for j in store.list_jobs(5)],
    }


@app.get("/schema", dependencies=[Depends(require_token)])
def schema():
    """JSON schema of the quiz spec, so the writing routine always targets the current format."""
    return QuizSpec.model_json_schema()


@app.post("/jobs", status_code=202, dependencies=[Depends(require_token)])
def create_job(spec: QuizSpec, dry_run: bool = False, force: bool = False):
    """Render and publish one quiz now."""
    if not force and not dry_run:
        repeats = _repeats(spec, _used_answers())
        if repeats:
            raise HTTPException(409, "answers already used recently, replace these rounds: " + "; ".join(repeats))
    job = pipeline.submit(spec, dry_run=dry_run)
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
    spec: QuizSpec


class ScheduleRequest(BaseModel):
    items: list[ScheduleItem] = Field(min_length=1, max_length=14)
    replace: bool = Field(default=False, description="Replace quizzes already scheduled on those dates")


def _schedule_view(days: int = 14) -> dict:
    today = pipeline.today_local()
    first = today if datetime.now(timezone.utc) < pipeline.slot_time(today) else today + timedelta(days=1)
    held = {j["slot"]: j for j in pipeline.booked_jobs()}
    slots = []
    for k in range(days):
        d = (first + timedelta(days=k)).isoformat()
        j = held.get(d)
        slots.append({"date": d, "publish_at": pipeline.slot_time(first + timedelta(days=k)).isoformat(),
                      **({"status": j["status"], "job_id": j["id"], "title": j["spec"]["title"],
                          "theme": j["spec"].get("theme", ""), "video_url": j.get("video_url")} if j else {"status": "free"})})
    return {"timezone": settings.tz.key, "post_time": settings.post_time, "first_open_date": first.isoformat(),
            "free_dates": [s["date"] for s in slots if s["status"] == "free"], "slots": slots}


@app.get("/schedule", dependencies=[Depends(require_token)])
def get_schedule(days: int = 14):
    """The next `days` posting slots, with what's booked in each and which are free."""
    return _schedule_view(min(max(days, 1), 60))


@app.post("/schedule", status_code=202, dependencies=[Depends(require_token)])
def post_schedule(req: ScheduleRequest):
    """Book a batch of quizzes (e.g. next week's 7) into daily slots. All-or-nothing: nothing is
    scheduled unless every item passes."""
    view = _schedule_view(60)
    first = date.fromisoformat(view["first_open_date"])
    held = {j["slot"]: j for j in pipeline.booked_jobs()}
    free = iter(d for d in view["free_dates"] if not any(i.date and i.date.isoformat() == d for i in req.items))
    plan, errors = [], []
    for n, item in enumerate(req.items):
        d = item.date or date.fromisoformat(next(free, None) or "1970-01-01")
        if d < first:
            errors.append(f"item {n}: {d} has passed or its slot is already gone (first open date is {first})")
        elif d > first + timedelta(days=59):
            errors.append(f"item {n}: {d} is more than 60 days ahead")
        elif d.isoformat() in held and held[d.isoformat()]["status"] in ("done", "publishing"):
            errors.append(f"item {n}: {d} has already been posted")
        elif d.isoformat() in held and not req.replace:
            errors.append(f"item {n}: {d} already has `{held[d.isoformat()]['id']}` (send replace=true to swap it)")
        plan.append((d, item.spec))
    dates = [d.isoformat() for d, _ in plan]
    errors += [f"{d} appears more than once in this batch" for d in sorted({d for d in dates if dates.count(d) > 1})]
    replaced = {held[d]["id"] for d in dates if d in held} if req.replace else set()
    used = _used_answers(exclude_jobs=replaced)
    for n, (d, spec) in enumerate(plan):
        if rep := _repeats(spec, used):
            errors.append(f"item {n} ({d}): answers already used: " + "; ".join(rep))
        for a in spec.answer_keys():
            used.setdefault(a, f"item {n} of this batch")
    if errors:
        raise HTTPException(409, {"errors": errors, "free_dates": view["free_dates"]})

    out = []
    for d, spec in plan:
        if d.isoformat() in held and req.replace:
            pipeline.cancel(held[d.isoformat()], "replaced")
        job = pipeline.submit(spec, slot=d)
        out.append({"date": d.isoformat(), "publish_at": job["publish_at"], "job_id": job["id"]})
    return {"scheduled": out}


@app.delete("/schedule/{day}", dependencies=[Depends(require_token)])
def delete_schedule(day: date):
    """Cancel the quiz booked for a date (before it's posted)."""
    job = next((j for j in pipeline.scheduled_jobs() if j["slot"] == day.isoformat()), None)
    if not job:
        raise HTTPException(404, f"nothing scheduled on {day}")
    if job["status"] == "publishing":
        raise HTTPException(409, "it's being posted right now")
    pipeline.cancel(job)
    return {"cancelled": job["id"], "date": day.isoformat()}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404)
    return job


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

_states: dict[str, tuple[str, float]] = {}
PROVIDERS = PUBLISHERS


@app.get("/oauth/{provider}/start", dependencies=[Depends(require_token)])
def oauth_start(provider: str):
    mod = PROVIDERS.get(provider)
    if not mod:
        raise HTTPException(404)
    state = secrets.token_urlsafe(16)
    _states[state] = (provider, time.time() + 600)
    return RedirectResponse(mod.authorize_url(state))


@app.get("/oauth/{provider}/callback", response_class=HTMLResponse)
def oauth_callback(provider: str, code: str = "", state: str = "", error: str = "", error_description: str = ""):
    expected = _states.pop(state, None)
    if not expected or expected[0] != provider or expected[1] < time.time():
        raise HTTPException(400, "invalid or expired state; start again")
    if error or not code:
        raise HTTPException(400, f"{provider} returned an error: {error} {error_description}")
    PROVIDERS[provider].exchange_code(code.removesuffix("#_"))
    return f"<h2>{LABELS[provider]} connected ✔</h2><p>You can close this tab.</p>"
