"""Discord webhook notifications (with the video attached when it fits)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from .config import settings

log = logging.getLogger(__name__)
MAX_ATTACH = 9_500_000  # Discord's default upload limit is 10 MB
MIME = {".mp4": "video/mp4", ".png": "image/png", ".jpg": "image/jpeg"}


def send(content: str, embed: dict | None = None, attach: Path | None = None) -> None:
    if not settings.discord_webhook_url:
        log.info("discord (not configured): %s", content)
        return
    # never ping: messages quote viewers' comments, which could say @everyone
    payload = {"content": content[:2000], "embeds": [embed] if embed else [], "allowed_mentions": {"parse": []}}
    try:
        if attach and attach.exists() and attach.stat().st_size <= MAX_ATTACH:
            with attach.open("rb") as fh:
                r = httpx.post(
                    settings.discord_webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": (attach.name, fh, MIME.get(attach.suffix.lower(), "application/octet-stream"))},
                    timeout=120,
                )
        else:
            r = httpx.post(settings.discord_webhook_url, json=payload, timeout=30)
        if r.status_code >= 400:
            log.error("discord notification failed: HTTP %s: %s", r.status_code, r.text[:300])
    except Exception as e:  # notifications must never break the pipeline
        # not log.exception: the traceback would print the webhook URL, which is its secret
        log.error("discord notification failed: %s", type(e).__name__)


def error(msg: str) -> None:
    send(f":warning: **Quiz bot**: {msg}")
