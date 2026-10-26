"""The narrator: one ElevenLabs clip per video, with character timestamps so the renderer can time
every beat to the voice. Clips are cached by their text, and every character spent is recorded
against a monthly budget."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import httpx

from ..config import settings

log = logging.getLogger(__name__)
_lock = threading.Lock()


class OutOfBudget(Exception):
    pass


def _dir() -> Path:
    d = settings.data_dir / "adventure" / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger_path() -> Path:
    return settings.data_dir / "adventure" / "credits.json"


def month() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m")


def ledger() -> dict:
    p = _ledger_path()
    return json.loads(p.read_text()) if p.exists() else {}


def spent(m: str | None = None) -> int:
    return ledger().get(m or month(), {}).get("chars", 0)


def _record(chars: int, key: str) -> None:
    with _lock:
        data, m = ledger(), month()
        row = data.setdefault(m, {"chars": 0, "clips": []})
        row["chars"] += chars
        row["clips"].append({"key": key, "chars": chars, "at": datetime.now(settings.tz).isoformat(timespec="seconds")})
        p = _ledger_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(p)


def clip(text: str) -> tuple[Path, Path, bool]:
    """(mp3, alignment json, made now?) for a script. Cached clips cost nothing."""
    voice, model = settings.adventure_voice_id, settings.adventure_voice_model
    key = hashlib.sha256(f"{voice}|{model}|{text}".encode()).hexdigest()[:24]
    mp3, align = _dir() / f"{key}.mp3", _dir() / f"{key}.json"
    if mp3.exists() and align.exists():
        return mp3, align, False
    if not settings.elevenlabs_api_key:
        raise OutOfBudget("ELEVENLABS_API_KEY is not set")
    if spent() + len(text) > settings.adventure_voice_budget:
        raise OutOfBudget(f"{len(text)} characters would pass this month's budget ({spent()}/{settings.adventure_voice_budget} used)")
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": settings.elevenlabs_api_key},
        json={"text": text, "model_id": model},
        timeout=180,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    body = r.json()
    alignment = body.get("alignment") or body.get("normalized_alignment")
    if not alignment:
        raise RuntimeError("ElevenLabs returned no alignment")
    mp3.write_bytes(base64.b64decode(body["audio_base64"]))
    align.write_text(json.dumps({"alignment": alignment}))
    _record(len(text), key)
    log.info("adventure voice: %d characters, clip %s", len(text), key)
    return mp3, align, True


def _silences(mp3: Path, min_len: float) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(mp3), "-af", f"silencedetect=noise=-40dB:d={min_len}", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))


def tighten(mp3: Path, align: Path, max_gap: float = 0.6) -> tuple[Path, Path]:
    """Shorten every pause longer than `max_gap` to `max_gap` (the narrator's [long pause] runs to
    3-4 s), and move the alignment's timestamps to match. Cached next to the clip."""
    tag = f"-t{int(max_gap * 100)}"
    out, out_align = mp3.with_name(mp3.stem + tag + ".mp3"), align.with_name(align.stem + tag + ".json")
    if out.exists() and out_align.exists():
        return out, out_align
    cuts = [(a + max_gap / 2, b - max_gap / 2) for a, b in _silences(mp3, max_gap + 0.2) if b - a > max_gap]
    if not cuts:
        return mp3, align
    keep, t = [], 0.0
    for a, b in cuts:
        keep.append((t, a))
        t = b
    filters = [f"[0:a]atrim=start={a:.3f}" + (f":end={b:.3f}" if b else "") + f",asetpts=PTS-STARTPTS[k{i}]"
               for i, (a, b) in enumerate(keep + [(t, None)])]
    n = len(keep) + 1
    graph = ";".join(filters) + ";" + "".join(f"[k{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[o]"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-filter_complex", graph, "-map", "[o]",
                    "-c:a", "libmp3lame", "-b:a", "128k", str(out)], check=True)

    def shift(x: float) -> float:
        removed = 0.0
        for a, b in cuts:
            if x >= b:
                removed += b - a
            elif x > a:
                return round(a - removed, 3)  # inside a removed stretch: snap to where it was cut
        return round(x - removed, 3)

    data = json.loads(align.read_text())
    al = data["alignment"]
    for k in ("character_start_times_seconds", "character_end_times_seconds"):
        al[k] = [shift(x) for x in al[k]]
    out_align.write_text(json.dumps(data))
    log.info("adventure voice: %d pauses shortened, %.1fs removed", len(cuts), sum(b - a for a, b in cuts))
    return out, out_align
