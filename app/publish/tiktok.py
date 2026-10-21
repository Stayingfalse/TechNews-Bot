"""TikTok Content Posting API.

TIKTOK_MODE=draft: upload to the creator's inbox (scope `video.upload`, no app audit needed); you
tap post. TIKTOK_MODE=direct: post straight to the profile (scope `video.publish`); until TikTok
audits the app, direct posts can only be private (SELF_ONLY).
Docs: https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .. import store
from ..config import settings

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com/v2"


def scopes() -> str:
    return "user.info.basic,video.upload" + (",video.publish" if settings.tiktok_mode == "direct" else "")


def redirect_uri() -> str:
    return f"{settings.public_base_url}/oauth/tiktok/callback"


def authorize_url(state: str) -> str:
    q = {
        "client_key": settings.tiktok_client_key,
        "scope": scopes(),
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(q)}"


def _save(tok: dict) -> dict:
    now = int(time.time())
    data = {
        "access_token": tok["access_token"],
        "refresh_token": tok["refresh_token"],
        "open_id": tok.get("open_id"),
        "scope": tok.get("scope"),
        "expires_at": now + int(tok.get("expires_in", 86400)) - 300,
        "refresh_expires_at": now + int(tok.get("refresh_expires_in", 31536000)),
    }
    store.set_tokens("tiktok", data)
    return data


def _token_request(form: dict) -> dict:
    form = {"client_key": settings.tiktok_client_key, "client_secret": settings.tiktok_client_secret, **form}
    r = httpx.post(f"{API}/oauth/token/", data=form, timeout=30)
    r.raise_for_status()
    tok = r.json()
    if "access_token" not in tok:
        raise RuntimeError(f"TikTok token error: {tok}")
    return _save(tok)


def exchange_code(code: str) -> dict:
    return _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})


def access_token() -> str:
    tok = store.get_tokens("tiktok")
    if not tok:
        raise RuntimeError("TikTok not connected: visit /oauth/tiktok/start")
    if time.time() >= tok["expires_at"]:
        tok = _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})
    return tok["access_token"]


def refresh_if_needed() -> None:
    """Called daily so the 365-day refresh token keeps rolling even on quiet days."""
    if store.get_tokens("tiktok"):
        tok = store.get_tokens("tiktok")
        _token_request({"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]})


def _post_info(headers: dict, caption: str) -> dict:
    r = httpx.post(f"{API}/post/publish/creator_info/query/", headers=headers, timeout=30)
    r.raise_for_status()
    options = r.json().get("data", {}).get("privacy_level_options", [])
    privacy = settings.tiktok_privacy if settings.tiktok_privacy in options else "SELF_ONLY"
    if privacy not in options and options:
        privacy = options[0]
    return {"title": caption[:2200], "privacy_level": privacy, "disable_comment": False,
            "disable_duet": False, "disable_stitch": False, "video_cover_timestamp_ms": 1500}


def upload(video_path: Path, caption: str = "") -> dict:
    """Draft upload or direct post, per TIKTOK_MODE."""
    size = video_path.stat().st_size
    if size > 64 * 1024 * 1024:
        raise RuntimeError("video over 64MB; chunked upload not implemented")
    headers = {"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json; charset=UTF-8"}
    body: dict = {"source_info": {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}}
    direct = settings.tiktok_mode == "direct"
    if direct:
        body["post_info"] = _post_info(headers, caption)
        url = f"{API}/post/publish/video/init/"
    else:
        url = f"{API}/post/publish/inbox/video/init/"
    r = httpx.post(url, json=body, headers=headers, timeout=30)
    r.raise_for_status()
    res = r.json()
    if res.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"TikTok init error: {res['error']}")
    publish_id, upload_url = res["data"]["publish_id"], res["data"]["upload_url"]

    put = httpx.put(
        upload_url,
        content=video_path.read_bytes(),
        headers={"Content-Type": "video/mp4", "Content-Range": f"bytes 0-{size - 1}/{size}"},
        timeout=300,
    )
    put.raise_for_status()

    status = None
    for _ in range(40):
        time.sleep(3)
        s = httpx.post(f"{API}/post/publish/status/fetch/", json={"publish_id": publish_id}, headers=headers, timeout=30)
        if s.status_code == 200:
            status = s.json().get("data", {}).get("status")
            if status in ("SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"):
                break
    if status == "FAILED":
        raise RuntimeError(f"TikTok processing failed: {s.json()}")
    out = {"publish_id": publish_id, "status": status, "mode": settings.tiktok_mode}
    if direct:
        out["privacy"] = body["post_info"]["privacy_level"]
    return out


def configured() -> bool:
    return settings.tiktok_enabled


def publish(video: Path, spec, job: dict) -> dict:
    return upload(video, spec.full_caption())
