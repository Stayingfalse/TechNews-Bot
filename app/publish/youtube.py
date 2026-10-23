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
# upload to post; readonly + analytics for the dashboard's numbers; force-ssl for comment replies
SCOPES = " ".join("https://www.googleapis.com/auth/" + s for s in (
    "youtube.upload", "youtube.readonly", "yt-analytics.readonly", "youtube.force-ssl"))
CATEGORY_ENTERTAINMENT = "24"


def configured() -> bool:
    return settings.youtube_enabled


def redirect_uri() -> str:
    return f"{settings.public_base_url}/oauth/youtube/callback"


def authorize_url(state: str, login: bool = False) -> str:
    q = {
        "client_id": settings.youtube_client_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",  # we need a refresh token
        "prompt": "consent",  # and Google only returns one on a consent screen
        "state": state,
    }
    if login:  # sign-in only needs to see which channel this is; no refresh token, no consent screen
        q.update(scope="https://www.googleapis.com/auth/youtube.readonly", access_type="online",
                 prompt="select_account")
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
        "scope": tok.get("scope") or old.get("scope"),
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


def metrics(video_id: str, published: str) -> dict:
    """Counts for one Short (needs youtube.readonly), plus watch time from YouTube Analytics
    (needs yt-analytics.readonly and the YouTube Analytics API enabled; it lags 1-2 days)."""
    token = access_token()
    h = {"Authorization": f"Bearer {token}"}
    r = httpx.get("https://www.googleapis.com/youtube/v3/videos", headers=h, timeout=30,
                  params={"part": "statistics", "id": video_id})
    if r.status_code >= 400:
        return {"error": f"stats unavailable: {r.text[:160]}"}
    items = r.json().get("items") or []
    if not items:
        return {"error": "video not found (deleted or private to another channel)"}
    st = items[0]["statistics"]
    out = {"views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
           "comments": int(st.get("commentCount", 0))}
    end = time.strftime("%Y-%m-%d", time.gmtime())
    a = httpx.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=h, timeout=30, params={
        "ids": "channel==MINE", "startDate": published[:10], "endDate": end,
        "metrics": "averageViewDuration,averageViewPercentage,shares,subscribersGained",
        "filters": f"video=={video_id}"})
    if a.status_code < 400 and a.json().get("rows"):
        avd, avp, shares, subs = a.json()["rows"][0]
        out.update(avg_watch_s=avd, avg_view_pct=avp, shares=shares, followers_gained=subs)
    elif a.status_code >= 400:
        out["note"] = f"watch time unavailable: {a.text[:120]}"
    return out


def _channel_id(token: str) -> str:
    r = httpx.get("https://www.googleapis.com/youtube/v3/channels", timeout=30,
                  params={"part": "id", "mine": "true"}, headers={"Authorization": f"Bearer {token}"})
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube channel lookup failed: {r.text[:200]}")
    items = r.json().get("items") or []
    if not items:
        raise RuntimeError("that Google account has no YouTube channel")
    return items[0]["id"]


def login_identity(code: str) -> str:
    """Sign-in: which channel did they pick? Uses a throwaway token; the posting token is untouched."""
    r = httpx.post(TOKEN_URL, timeout=30, data={
        "client_id": settings.youtube_client_id, "client_secret": settings.youtube_client_secret,
        "code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})
    if r.status_code >= 400:
        raise RuntimeError(f"Google sign-in failed: {r.text[:200]}")
    return _channel_id(r.json()["access_token"])


def connected_identity() -> str | None:
    """The channel the bot posts to (looked up once with the posting token, then remembered)."""
    tok = store.get_tokens("youtube")
    if not tok:
        return None
    if not tok.get("channel_id"):
        tok["channel_id"] = _channel_id(access_token())  # needs youtube.readonly on the posting token
        store.set_tokens("youtube", {**store.get_tokens("youtube"), "channel_id": tok["channel_id"]})
    return tok["channel_id"]
