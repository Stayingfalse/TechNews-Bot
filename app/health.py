"""Early warnings: outside checks on healthchecks.io, and Discord warnings for things that run out.

With HEALTHCHECKS_API_KEY set, the server creates its checks on healthchecks.io itself (once; their
ping URLs are kept in health.json) and pings them:
  - heartbeat:  every 5 minutes; alerts when the server or its scheduler stops
  - daily-post: after each successful post (a failure on every platform pings /fail); alerts when
                nothing has posted by 12:45 local
  - weekly-batch: when the Monday routine books the next week; alerts when it hasn't by 22:00
The checks alert through every integration on the healthchecks.io project (email by default).

Discord warnings (twice a day): ElevenLabs credits running low, and an Instagram login close to
expiring because its refresh keeps failing. YouTube refresh failures are already reported.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from . import notify, store
from .config import settings

log = logging.getLogger(__name__)

API = "https://healthchecks.io/api/v3/checks/"
HEARTBEAT_EVERY = 300


def _checks() -> dict[str, dict]:
    """name -> how healthchecks.io should judge it."""
    h, m = (int(x) for x in settings.post_time.split(":"))
    tz = settings.tz.key
    return {
        "heartbeat": {"desc": "Pings every 5 minutes while the quiz server is up and scheduling.",
                      "timeout": 600, "grace": 300},
        "daily-post": {"desc": "Pings when the day's quiz posts (/fail when it failed everywhere).",
                       "schedule": f"{m} {h} * * *", "tz": tz, "grace": 45 * 60},
        "weekly-batch": {"desc": "Pings when the Monday routine books the next week.",
                         "schedule": "5 19 * * 1", "tz": tz, "grace": 3 * 3600},
    }


def setup() -> dict[str, str]:
    """Create (or find) the checks and remember their ping URLs. Safe to run on every start."""
    if not settings.healthchecks_api_key:
        return {}
    urls = store._read("health.json", {})
    for name, spec in _checks().items():
        body = {"name": f"quizbot {name}", "tags": "quizbot", "unique": ["name"], "channels": "*", **spec}
        try:
            r = httpx.post(API, json=body, headers={"X-Api-Key": settings.healthchecks_api_key}, timeout=20)
            r.raise_for_status()
            urls[name] = r.json()["ping_url"]
        except Exception as e:
            log.warning("healthchecks.io: couldn't set up %s: %s", name, e)
    store._write("health.json", urls)
    return urls


def ping(name: str, fail: bool = False) -> None:
    """Ping a check; never raises (monitoring must not break posting)."""
    url = store._read("health.json", {}).get(name)
    if not url:
        return
    try:
        httpx.get(url + ("/fail" if fail else ""), timeout=10)
    except Exception as e:
        log.warning("healthchecks.io ping %s failed: %s", name, e)


_last_beat = 0.0


def heartbeat() -> None:
    global _last_beat
    if time.time() - _last_beat >= HEARTBEAT_EVERY:
        _last_beat = time.time()
        ping("heartbeat")


# ------------------------------------------------------------------ Discord warnings

CREDITS_WARN = 2000  # about two weeks of voice-overs at 2 a week (~400 characters each, with some redos)


def _warn_once_a_day(key: str, message: str) -> None:
    state = store._read("health.json", {})
    today = datetime.now(settings.tz).date().isoformat()
    if state.get(f"warned:{key}") == today:
        return
    state[f"warned:{key}"] = today
    store._write("health.json", state)
    notify.error(message)


def check_elevenlabs() -> dict | None:
    """Credits left this period; warns in Discord when they're about to run out."""
    if not settings.elevenlabs_api_key:
        return None
    try:
        r = httpx.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": settings.elevenlabs_api_key}, timeout=20)
        r.raise_for_status()
        sub = r.json()
    except Exception as e:  # a key without the user-read permission can't see this; voice still works
        log.info("ElevenLabs subscription not readable: %s", e)
        return None
    left = sub.get("character_limit", 0) - sub.get("character_count", 0)
    reset = sub.get("next_character_count_reset_unix")
    when = datetime.fromtimestamp(reset, timezone.utc).astimezone(settings.tz).strftime("%a %d %b") if reset else "?"
    if left < CREDITS_WARN:
        _warn_once_a_day("elevenlabs", f"ElevenLabs credits are low: {left:,} characters left until {when} "
                                       f"(a voice-over takes ~300-400). Without credits, voice quizzes go out silent.")
    return {"left": left, "resets": when}


def check_logins() -> None:
    """An Instagram login refreshes when it has 20 days left; under 7 means refreshing keeps failing."""
    tok = store.get_tokens("instagram")
    if tok and tok.get("expires_at"):
        days = (tok["expires_at"] - time.time()) / 86400
        if days < 7:
            _warn_once_a_day("instagram-login", f"The Instagram login expires in {max(0, days):.0f} days and isn't "
                                                "renewing: reconnect it from the dashboard before posts start failing.")


def daily_checks() -> None:
    for fn in (check_elevenlabs, check_logins):
        try:
            fn()
        except Exception:
            log.exception("health check %s failed", fn.__name__)
