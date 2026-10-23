"""Instagram API with Instagram Login: publish a Reel (with the video's own music).

Docs: https://developers.facebook.com/docs/instagram-platform/content-publishing
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .. import store
from ..config import settings

log = logging.getLogger(__name__)

# basic + publish to post; insights for the dashboard's numbers; comments for replies
SCOPES = ("instagram_business_basic,instagram_business_content_publish,"
          "instagram_business_manage_insights,instagram_business_manage_comments")
CONTAINER_ATTEMPTS = 3  # fresh upload containers to try when Instagram's processing errors out


def graph() -> str:
    return f"https://graph.instagram.com/{settings.graph_version}"


def redirect_uri() -> str:
    return f"{settings.public_base_url}/oauth/instagram/callback"


def authorize_url(state: str, login: bool = False) -> str:
    q = {
        "client_id": settings.instagram_app_id,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "instagram_business_basic" if login else SCOPES,
        "state": state,
    }
    return f"https://www.instagram.com/oauth/authorize?{urlencode(q)}"


def _save(token: str, expires_in: int, user_id: str | None = None, permissions: list | None = None) -> dict:
    old = store.get_tokens("instagram") or {}
    data = {
        "access_token": token,
        "user_id": user_id or old.get("user_id"),
        "permissions": permissions if permissions is not None else old.get("permissions"),
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
    perms = short.get("permissions")
    if isinstance(perms, str):
        perms = perms.split(",")
    return _save(long["access_token"], long.get("expires_in", 5184000), str(short["user_id"]), perms or [])


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

    errors = []
    for attempt in range(1, CONTAINER_ATTEMPTS + 1):
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
        if status == "FINISHED":
            break
        errors.append(f"attempt {attempt}: {status}: {s.text}")
        # a bare ERROR is usually Instagram failing to fetch or transcode this time; a new container often works
        if status != "ERROR" or attempt == CONTAINER_ATTEMPTS:
            raise RuntimeError("Instagram processing failed. " + " | ".join(errors))
        log.warning("Instagram container %s ended with ERROR (attempt %d), retrying", container, attempt)
        time.sleep(30 * attempt)

    r = httpx.post(f"{graph()}/{uid}/media_publish", data={"creation_id": container, "access_token": token}, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram publish error: {r.text}")
    media_id = r.json()["id"]
    out = {"media_id": media_id}
    try:
        out["url"] = media_info(media_id).get("permalink")
    except Exception:  # the post went out; a missing link isn't worth failing over
        pass
    return out


def _get(path: str, fields: str) -> dict:
    tok = store.get_tokens("instagram")
    if not tok:
        raise RuntimeError("Instagram not connected: visit /oauth/instagram/start")
    r = httpx.get(f"{graph()}/{path}", params={"fields": fields, "access_token": tok["access_token"]}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram API error: {r.text[:300]}")
    return r.json()


def account() -> dict:
    """The account the stored token posts to."""
    return _get("me", "user_id,username,account_type")


def media_info(media_id: str) -> dict:
    return _get(media_id, "permalink,username,timestamp,media_type,media_product_type")


def configured() -> bool:
    return settings.instagram_enabled


def publish(video: Path, spec, job: dict) -> dict:
    # Instagram fetches the file itself from our public /media URL
    return publish_reel(job["video_url"], spec.full_caption(), job.get("cover_url"))


def metrics(media_id: str) -> dict:
    """Counts for one Reel. Likes and comments need only the basic permission; the rest come from
    insights, which need instagram_business_manage_insights (reconnect to grant it)."""
    out = {}
    base = _get(media_id, "like_count,comments_count")
    out["likes"], out["comments"] = base.get("like_count"), base.get("comments_count")
    tok = store.get_tokens("instagram")
    r = httpx.get(f"{graph()}/{media_id}/insights", timeout=30, params={
        "metric": "views,reach,saved,shares,total_interactions,ig_reels_avg_watch_time",
        "access_token": tok["access_token"]})
    if r.status_code >= 400:
        out["error"] = f"insights unavailable: {r.text[:160]}"
        return out
    names = {"views": "views", "reach": "reach", "saved": "saves", "shares": "shares",
             "total_interactions": "interactions", "ig_reels_avg_watch_time": "avg_watch_s"}
    for m in r.json().get("data", []):
        v = (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value"))
        if m.get("name") in names and v is not None:
            out[names[m["name"]]] = v / 1000 if m["name"] == "ig_reels_avg_watch_time" else v  # ms → s
    return out


def login_identity(code: str) -> str:
    """Sign-in: who approved? Returns the Instagram account ID without touching the posting token."""
    r = httpx.post("https://api.instagram.com/oauth/access_token", timeout=30, data={
        "client_id": settings.instagram_app_id, "client_secret": settings.instagram_app_secret,
        "grant_type": "authorization_code", "redirect_uri": redirect_uri(), "code": code})
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram sign-in failed: {r.text[:200]}")
    return str(r.json()["user_id"])


def connected_identity() -> str | None:
    tok = store.get_tokens("instagram")
    return str(tok["user_id"]) if tok and tok.get("user_id") else None


def comments(media_id: str, limit: int = 200) -> list[dict]:
    """Comments on a post, oldest first: {id, user, text, at}. Needs instagram_business_manage_comments."""
    tok = store.get_tokens("instagram")
    url, params, out = f"{graph()}/{media_id}/comments", {
        "fields": "id,text,username,timestamp", "limit": 50, "access_token": tok["access_token"]}, []
    while url and len(out) < limit:
        r = httpx.get(url, params=params, timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Instagram comments unavailable: {r.text[:200]}")
        d = r.json()
        out += [{"id": c["id"], "user": c.get("username", ""), "text": c.get("text", ""), "at": c.get("timestamp", "")}
                for c in d.get("data", [])]
        url, params = d.get("paging", {}).get("next"), None
    return sorted(out, key=lambda c: c["at"])


def reply(comment_id: str, message: str) -> str:
    tok = store.get_tokens("instagram")
    r = httpx.post(f"{graph()}/{comment_id}/replies", data={"message": message, "access_token": tok["access_token"]}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram reply failed: {r.text[:200]}")
    return r.json().get("id", "")


def comment(media_id: str, message: str) -> str:
    """A top-level comment on a post, as the account."""
    tok = store.get_tokens("instagram")
    r = httpx.post(f"{graph()}/{media_id}/comments", data={"message": message, "access_token": tok["access_token"]}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"Instagram comment failed: {r.text[:200]}")
    return r.json().get("id", "")


def own_name() -> str:
    try:
        return account().get("username", "")
    except Exception:
        return ""
