"""raosanta.uk's narrator: each segment's `say` line from ElevenLabs, cached by its text (a cached
line costs nothing), with every character spent recorded against SANTA_VOICE_BUDGET a month.

`lines()` never stops a video: no key, a format that isn't voiced, an exhausted budget or an
ElevenLabs error all give no voice-over and say why, and the video goes out with music and text.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path

import numpy as np

from ..config import settings
from ..render import voice as tts
from .spec import PromoSpec

log = logging.getLogger(__name__)
_lock = threading.Lock()


def _dir() -> Path:
    d = settings.data_dir / "santa"
    d.mkdir(parents=True, exist_ok=True)
    return d


def month() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m")


def ledger() -> dict:
    p = _dir() / "credits.json"
    return json.loads(p.read_text()) if p.exists() else {}


def spent(m: str | None = None) -> int:
    return ledger().get(m or month(), {}).get("chars", 0)


def _record(chars: int, key: str) -> None:
    with _lock:
        data, m = ledger(), month()
        row = data.setdefault(m, {"chars": 0, "videos": []})
        row["chars"] += chars
        row["videos"].append({"id": key, "chars": chars, "at": datetime.now(settings.tz).isoformat(timespec="seconds")})
        p = _dir() / "credits.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(p)


def voice_id(spec: PromoSpec) -> str:
    voices = settings.santa_voices
    if spec.voice_name and spec.voice_name.lower() in voices:
        return voices[spec.voice_name.lower()]
    return next(iter(voices.values()), tts.FALLBACK_VOICE)


def _config(spec: PromoSpec) -> tts.VoiceConfig:
    return tts.VoiceConfig(settings.elevenlabs_api_key, voice_id(spec), settings.santa_voice_model, _dir() / "voice")


def lines(spec: PromoSpec) -> tuple[dict[int, np.ndarray], str]:
    """({segment index: samples}, status): status is "on", "off" or "skipped: why"."""
    said = {i: s.say for i, s in enumerate(spec.segments) if s.say}
    if not spec.voiced or not said:
        return {}, "off"
    if not settings.elevenlabs_api_key:
        return {}, "skipped: no ELEVENLABS_API_KEY"
    cfg = _config(spec)
    new = sum(len(t) for t in said.values() if not tts._cached(cfg.voice_id, t, cfg).exists())
    if new and spent() + new > settings.santa_voice_budget:
        return {}, f"skipped: {new} characters would pass this month's budget ({spent()}/{settings.santa_voice_budget} used)"
    out = {}
    for i, t in said.items():
        fresh = not tts._cached(cfg.voice_id, t, cfg).exists()
        try:
            out[i] = tts._decode(tts._fetch(t, cfg))
        except Exception as e:  # never stop a post: it goes out with music and text
            log.warning("santa voice-over failed: %s", e)
            return {}, f"skipped: {e}"[:200]
        finally:
            if fresh and tts._cached(cfg.voice_id, t, cfg).exists():
                _record(len(t), spec.id)  # each line as it's paid for, so a failure later still counts it
    return out, "on"
