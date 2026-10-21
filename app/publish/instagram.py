"""Instagram API with Instagram Login: publish a Reel (with the video's own music).

Docs: https://developers.facebook.com/docs/instagram-platform/content-publishing
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .. import store
from ..config import settings

SCOPES = "instagram_business_basic,instagram_business_content_publish"


def graph() -> str:
    return f"https://graph.instagram.com/{settings.graph_version}"


def redirect_uri() -> str:
    return f"{settings.public_base_url}/oauth/instagram/callback"


def authorize_url(state: str) -> str:
    q = {
        "client_id": settings.instagram_app_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }
    return f"https://www.instagram.com/oauth/authorize?{urlencode(q)}"


def _save(token: str, expires_in: int, user_id: str | None = None) -> dict:
    old = store.get_tokens("instagram") or {}
    data = {
        "access_token": token,
        "user_id": user_id or old.get("user_id"),
        "expires_at": int(time.time()) + int(expires_in),
    }
    store.set_tokens("instagram", data)
    return data


def exchange_code(code: str) -> dict:
    r = httpx.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": settings.instagram_app_id,
            "client_secret": settings.instagram_app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri(),
            "code": code,
        },
        timeout=30,
    )
    r.raise_for_status()
    short = r.json()
    r = httpx.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": settings.instagram_app_secret,
            "access_token": short["access_token"],
        },
        timeout=30,
    )
    r.raise_for_status()
    long = r.json()
    return _save(long["access_token"], long.get("expires_in", 5184000), str(short["user_id"]))


def refresh_if_needed(force: bool = False) -> None:
    """Long-lived tokens last 60 days; refresh when under 20 days remain."""
    tok = store.get_tokens("instagram")
    if not tok:
        return
    if force or tok["expires_at"] - time.time() < 20 * 86400:
        r = httpx.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": tok["access_token"]},
            timeout=30,
        )
        r.raise_for_status()
        d = r.json()
        _save(d["access_token"], d.get("expires_in", 5184000))


def publish_reel(video_url: str, caption: str, cover_url: str | None = None) -> dict:
    tok = store.get_tokens("instagram")
    if not tok:
        raise RuntimeError("Instagram not connected: visit /oauth/instagram/start")
    token, uid = tok["access_token"], tok["user_id"]
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": token,
    }
    if cover_url:
        params["cover_url"] = cover_url
    r = httpx.post(f"{graph()}/{uid}/media", data=params, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram container error: {r.text}")
    container = r.json()["id"]

    status = None
    for _ in range(60):  # up to ~5 minutes
        time.sleep(5)
        s = httpx.get(f"{graph()}/{container}", params={"fields": "status_code,status", "access_token": token}, timeout=30)
        status = s.json().get("status_code")
        if status in ("FINISHED", "ERROR", "EXPIRED"):
            break
    if status != "FINISHED":
        raise RuntimeError(f"Instagram processing ended with {status}: {s.text}")

    r = httpx.post(f"{graph()}/{uid}/media_publish", data={"creation_id": container, "access_token": token}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram publish error: {r.text}")
    return {"media_id": r.json()["id"]}


def configured() -> bool:
    return settings.instagram_enabled


def publish(video: Path, spec, job: dict) -> dict:
    # Instagram fetches the file itself from our public /media URL
    return publish_reel(job["video_url"], spec.full_caption(), job.get("cover_url"))
