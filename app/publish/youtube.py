"""YouTube Data API v3: upload the video as a Short (vertical and under 3 minutes, so YouTube
files it under Shorts automatically).

Uses scope `youtube.upload`. Videos uploaded by a Google Cloud project that hasn't passed
YouTube's API compliance audit are locked to private; see docs/SETUP.md.
Docs: https://developers.google.com/youtube/v3/guides/uploading_a_video
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .. import store
from ..config import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
SCOPES = "https://www.googleapis.com/auth/youtube.upload"
CATEGORY_ENTERTAINMENT = "24"


def configured() -> bool:
    return settings.youtube_enabled


def redirect_uri() -> str:
    return f"{settings.public_base_url}/oauth/youtube/callback"


def authorize_url(state: str) -> str:
    q = {
        "client_id": settings.youtube_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",  # we need a refresh token
        "prompt": "consent",  # and Google only returns one on a consent screen
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def _token_request(form: dict) -> dict:
    form = {"client_id": settings.youtube_client_id, "client_secret": settings.youtube_client_secret, **form}
    r = httpx.post(TOKEN_URL, data=form, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Google token error: {r.text[:300]}")
    tok = r.json()
    old = store.get_tokens("youtube") or {}
    data = {
        "access_token": tok["access_token"],
        # refresh responses don't repeat the refresh token
        "refresh_token": tok.get("refresh_token") or old.get("refresh_token"),
        "expires_at": int(time.time()) + int(tok.get("expires_in", 3600)) - 120,
    }
    if not data["refresh_token"]:
        raise RuntimeError("Google returned no refresh token; remove the app's access in your Google account and reconnect")
    store.set_tokens("youtube", data)
    return data


def exchange_code(code: str) -> dict:
    return _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})


def access_token() -> str:
    tok = store.get_tokens("youtube")
    if not tok:
        raise RuntimeError("YouTube not connected: visit /oauth/youtube/start")
    if time.time() >= tok["expires_at"]:
        tok = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    return tok["access_token"]


def refresh_if_needed() -> None:
    """Exercise the refresh token so a revoked or expired one is reported early."""
    tok = store.get_tokens("youtube")
    if tok:
        _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})


def _title(spec) -> str:
    title = re.sub(r"[<>]", "", spec.title.replace("*", "")).strip()
    if spec.theme and spec.theme.lower() not in title.lower():
        title = f"{title} | {spec.theme} quiz"
    return title[:100]


def publish(video: Path, spec, job: dict) -> dict:
    token = access_token()
    meta = {
        "snippet": {
            "title": _title(spec),
            "description": spec.full_caption()[:4900],
            "tags": [h.lstrip("#") for h in spec.hashtags][:15],
            "categoryId": CATEGORY_ENTERTAINMENT,
        },
        "status": {
            "privacyStatus": settings.youtube_privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    size = video.stat().st_size
    r = httpx.post(
        UPLOAD_URL,
        params={"uploadType": "resumable", "part": "snippet,status"},
        json=meta,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(size),
        },
        timeout=30,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube init error: {r.text[:500]}")
    session = r.headers["Location"]
    put = httpx.put(session, content=video.read_bytes(),
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "video/mp4"}, timeout=600)
    if put.status_code >= 400:
        raise RuntimeError(f"YouTube upload error: {put.text[:500]}")
    vid = put.json()["id"]
    return {"video_id": vid, "url": f"https://youtube.com/shorts/{vid}", "privacy": settings.youtube_privacy}
