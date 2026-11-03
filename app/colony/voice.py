"""Farside's voices (docs/COLONY_PLAN.md §5d): a calm narrator reads the captions and the
decision, the founding crew speak in their own voices, and settlers get one of a small pool the
first time they speak, kept from then on. Each line is one ElevenLabs clip, cached by voice and
text. When a line is longer than its beat, the beat is stretched so nothing is cut off. Every
character spent counts against COLONY_VOICE_BUDGET a month; past it, or if ElevenLabs fails, the
episode goes out without voice.

`add(video, s)` returns the video spec retimed to its lines, and the lines as (time, samples)."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path

import httpx
import numpy as np

from ..config import settings
from ..render.audio import SR

log = logging.getLogger(__name__)
_lock = threading.Lock()
GAP = 0.25  # silence kept after a line before its beat ends
refused: set[str] = set()  # voices ElevenLabs wouldn't speak with (not on the account): reported in the preview
LEAD = 0.15  # a line starts this long into its beat


class OutOfBudget(Exception):
    pass


def enabled() -> bool:
    return bool(settings.elevenlabs_api_key) and settings.colony_voice


# ------------------------------------------------------------------ who speaks with which voice


def voice_for(who: str, s: dict) -> str:
    """The voice id for a crew name or a settler's handle (kept on the settler once chosen)."""
    crew = settings.colony_crew_voices
    if who.upper() in crew:
        return crew[who.upper()]
    key = next((k for k, st in s["settlers"].items() if st["handle"].lower() == who.lstrip("@").lower()), None)
    st = s["settlers"].get(key) if key else None
    if st and st.get("voice") in settings.colony_settler_voices.values():
        return st["voice"]
    pool = settings.colony_settler_voices
    look = (st or {}).get("look") or {}
    if look.get("body") == "old" and "old" in pool:
        vid = pool["old"]
    elif look.get("body") == "kid" and "young" in pool:
        vid = pool["young"]
    else:
        names = sorted(pool)
        vid = pool[names[int(hashlib.sha256(who.lower().encode()).hexdigest(), 16) % len(names)]]
    if st is not None:
        st["voice"] = vid  # kept when the colony is saved after the post
    return vid


# ------------------------------------------------------------------ what's said


def spoken(text: str) -> str:
    """On-screen text as it should be said: no highlight marks, @handles as words, sentence case."""
    t = text.replace("*", "").replace("|", " ")
    t = re.sub(r"@([a-z0-9._]+)", lambda m: re.sub(r"[._]+", " ", m.group(1)), t, flags=re.I)
    t = t.replace("+", "plus ").replace("=", "").replace("%", " percent").replace("#", "number ")
    t = " ".join(t.split()).lower()
    t = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), t)
    if t and t[-1] not in ".!?":
        t += "."
    return t


def lines(video: dict) -> list[dict]:
    """Every line to say: {shot, t0, t1, who ("" = narrator), text}, in time order."""
    out = []
    for i, shot in enumerate(video["shots"]):
        sp = shot["spec"]
        if shot["view"] == "inside" and sp.get("question"):
            q = sp["question"]
            ask = spoken(" ".join(q["lines"])) + " Comment " + ", or ".join(
                f"{c[0]} to {c[1].lower()}" for c in q["choices"]) + "."
            out.append({"shot": i, "t0": 0.0, "t1": shot["dur"], "who": "", "text": ask})
            continue
        for c in sp.get("captions", []):
            out.append({"shot": i, "t0": c["t0"], "t1": c["t1"], "who": "", "text": spoken(" ".join(c["lines"]))})
        for b in sp.get("bubbles", []):
            out.append({"shot": i, "t0": b["t0"], "t1": b["t1"], "who": b["who"], "text": spoken(b["text"])})
    return sorted(out, key=lambda x: (x["shot"], x["t0"], x["who"] != ""))


# ------------------------------------------------------------------ ElevenLabs


def _dir() -> Path:
    d = settings.data_dir / "colony" / "voice"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger() -> dict:
    p = settings.data_dir / "colony" / "credits.json"
    return json.loads(p.read_text()) if p.exists() else {}


def month() -> str:
    return datetime.now(settings.tz).strftime("%Y-%m")


def spent(m: str | None = None) -> int:
    return _ledger().get(m or month(), {}).get("chars", 0)


def _record(chars: int) -> None:
    with _lock:
        data = _ledger()
        row = data.setdefault(month(), {"chars": 0, "clips": 0})
        row["chars"] += chars
        row["clips"] += 1
        p = settings.data_dir / "colony" / "credits.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.replace(p)


def clip(voice: str, text: str) -> Path:
    model = settings.colony_voice_model
    path = _dir() / (hashlib.sha256(f"{voice}|{model}|{text}".encode()).hexdigest()[:24] + ".mp3")
    if path.exists():
        return path
    if spent() + len(text) > settings.colony_voice_budget:
        raise OutOfBudget(f"{len(text)} characters would pass this month's voice budget of "
                          f"{settings.colony_voice_budget:,} ({spent():,} used)")
    narrator = voice == settings.colony_narrator_voice

    def tts(vid):
        return httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}", timeout=90,
                          params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": settings.elevenlabs_api_key},
                          json={"text": text, "model_id": model,
                                "voice_settings": {"stability": 0.55 if narrator else 0.4, "similarity_boost": 0.8,
                                                   "style": 0.2 if narrator else 0.45}})

    r = tts(voice)
    if r.status_code in (400, 402, 403, 404) and voice != settings.colony_fallback_voice:
        # a library voice the account can't use: say it in the built-in voice, and report it
        log.warning("ElevenLabs refused voice %s (%s); using the fallback", voice, r.text[:160])
        refused.add(voice)
        r = tts(settings.colony_fallback_voice)
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    tmp = path.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.rename(path)
    _record(len(text))
    return path


def decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


# ------------------------------------------------------------------ fitting the video to the lines


TIMED = ("captions", "bubbles", "events", "progress", "parades")


def _shift_item(it: dict, at: float, extra: float, keys=("t0", "t1")) -> None:
    a, b = keys
    if it[a] >= at - 1e-6:
        it[a] += extra
        it[b] += extra
    elif it[b] >= at - 1e-6:
        it[b] += extra  # spans the moment: it stays up while the line finishes


def stretch(sp: dict, at: float, extra: float) -> None:
    """Make a shot `extra` seconds longer at time `at`: things from then on happen later, and
    whatever is on screen at that moment stays up longer."""
    for key in TIMED:
        for it in sp.get(key, []):
            _shift_item(it, at, extra)
    for name, (t0, t1) in list((sp.get("tags") or {}).items()) if isinstance(sp.get("tags"), dict) else []:
        it = {"t0": t0, "t1": t1}
        _shift_item(it, at, extra)
        sp["tags"][name] = (it["t0"], it["t1"])
    for b in sp.get("buildings", []):
        if "t0" in b:
            _shift_item(b, at, extra)
    for a in sp.get("arrivals", []):
        if a["land"] >= at:
            a["land"] += extra
    if sp.get("camera"):
        sp["camera"] = [(t + extra if t >= at else t, x) for t, x in sp["camera"]]
    if sp.get("beacon_ghost"):
        g = {"t0": sp["beacon_ghost"][0], "t1": sp["beacon_ghost"][1]}
        _shift_item(g, at, extra)
        sp["beacon_ghost"] = (g["t0"], g["t1"])
    if sp.get("building_now"):
        sp["building_now"] = (sp["building_now"][0], sp["building_now"][1] + extra)
    if "duration" in sp:
        sp["duration"] = round(sp["duration"] + extra, 3)


def add(video: dict, s: dict, max_total: float = 44.0) -> tuple[dict, list[tuple[float, np.ndarray]], dict]:
    """Voice the episode: (retimed video, [(time, samples)], info). Raises OutOfBudget or
    RuntimeError if any line can't be made, so an episode never goes out half-voiced."""
    refused.clear()
    todo = lines(video)
    made = []
    for ln in todo:
        vid = settings.colony_narrator_voice if not ln["who"] else voice_for(ln["who"], s)
        if ln["text"].strip(". "):
            made.append((ln, vid, decode(clip(vid, ln["text"]))))
    shots = video["shots"]
    offsets = [0.0] * len(shots)  # how much each shot has grown so far
    placed = []
    stretches = []  # (episode time, seconds added), in order
    last_end: dict[int, float] = {}
    for ln, vid, samples in made:
        i = ln["shot"]
        sp, extra_so_far = shots[i]["spec"], offsets[i]
        t0 = ln["t0"] + extra_so_far + LEAD
        t0 = max(t0, last_end.get(i, 0.0))  # never over the previous line
        need = len(samples) / SR
        end_by = ln["t1"] + extra_so_far - GAP
        if t0 + need > end_by:
            extra = round(t0 + need - end_by, 3)
            total = sum(sh["dur"] for sh in shots)
            extra = min(extra, max(0.0, max_total - total))
            if extra > 0:
                at = ln["t1"] + extra_so_far
                stretches.append((sum(sh["dur"] for sh in shots[:i]) + at, extra))
                stretch(sp, at, extra)
                shots[i]["dur"] = round(shots[i]["dur"] + extra, 3)
                offsets[i] += extra
        last_end[i] = t0 + need
        placed.append((i, t0, samples))
    starts = np.cumsum([0.0] + [sh["dur"] for sh in shots])[:-1]
    out = [(float(starts[i] + t), smp) for i, t, smp in placed]
    # the episode's sound effects move with the beats they belong to
    sfx = list(video.get("sfx", []))
    for at, extra in stretches:
        sfx = [(t + extra if t >= at - 1e-6 else t, k) for t, k in sfx]
    video["sfx"] = sfx
    video["duration"] = round(sum(sh["dur"] for sh in shots), 2)
    info = {"lines": len(made), "chars": sum(len(ln["text"]) for ln, _, _ in made), "stretched_s": round(sum(offsets), 2),
            "refused_voices": sorted(refused)}
    return video, out, info
