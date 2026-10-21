"""Discord webhook notifications (with the video attached when it fits)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

from .config import settings

log = logging.getLogger(__name__)
MAX_ATTACH = 9_500_000  # Discord's default upload limit is 10 MB


def send(content: str, embed: dict | None = None, attach: Path | None = None) -> None:
    if not settings.discord_webhook_url:
        log.info("discord (not configured): %s", content)
        return
    payload = {"content": content[:2000], "embeds": [embed] if embed else []}
    try:
        if attach and attach.exists() and attach.stat().st_size <= MAX_ATTACH:
            with attach.open("rb") as fh:
                r = httpx.post(
                    settings.discord_webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files={"files[0]": (attach.name, fh, "video/mp4")},
                    timeout=120,
                )
        else:
            r = httpx.post(settings.discord_webhook_url, json=payload, timeout=30)
        r.raise_for_status()
    except Exception:  # notifications must never break the pipeline
        log.exception("discord notification failed")


def error(msg: str) -> None:
    send(f":warning: **tech-shorts-bot**: {msg}")
