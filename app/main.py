from __future__ import annotations

import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import pipeline, store
from .config import settings
from .publish import instagram, tiktok
from .spec import StorySpec

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not settings.api_token:
        raise RuntimeError("API_TOKEN must be set")
    pipeline.start_background()
    yield


app = FastAPI(title="TechNews-Bot", lifespan=lifespan)
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
        "instagram_mode": settings.instagram_mode,
        "tiktok": {"configured": settings.tiktok_enabled, "token": tok("tiktok")},
        "instagram": {"configured": settings.instagram_enabled, "token": tok("instagram")},
        "discord": bool(settings.discord_webhook_url),
        "recent_jobs": [{k: j.get(k) for k in ("id", "status", "created_at", "video_url", "error")} for j in store.list_jobs(5)],
    }


@app.get("/schema", dependencies=[Depends(require_token)])
def schema():
    """JSON schema of the story spec, so the research routine always targets the current format."""
    return StorySpec.model_json_schema()


@app.post("/jobs", status_code=202, dependencies=[Depends(require_token)])
def create_job(spec: StorySpec, dry_run: bool = False, force: bool = False):
    if spec.topic_key and not force and not dry_run:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        for h in store.history(200):
            if h.get("topic_key") == spec.topic_key and h["date"] >= since:
                raise HTTPException(409, f"topic_key {spec.topic_key!r} already covered on {h['date']}")
    job = pipeline.submit(spec, dry_run=dry_run)
    return {"job_id": job["id"], "status": job["status"]}


@app.get("/jobs/{job_id}", dependencies=[Depends(require_token)])
def get_job(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(404)
    return job


@app.get("/history", dependencies=[Depends(require_token)])
def get_history(limit: int = 60):
    return store.history(limit)


# ------------------------------------------------------------------ OAuth (one-time browser setup)

_states: dict[str, tuple[str, float]] = {}
PROVIDERS = {"tiktok": tiktok, "instagram": instagram}


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
    return f"<h2>{provider.title()} connected ✔</h2><p>You can close this tab.</p>"
