"""Game-show host voice-over (ElevenLabs text-to-speech).

The host reads the title, calls each round, announces each answer, asks for comments on a
cliffhanger, reads yesterday's cliffhanger answer and asks for the score at the end. Each line is
synthesised once and cached on disk, so a re-render costs nothing.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

from .audio import SR

log = logging.getLogger(__name__)

NUMBERS = ("one", "two", "three", "four", "five")


@dataclass
class VoiceConfig:
    api_key: str
    voice_id: str
    model: str
    cache_dir: Path


def _clean(text: str) -> str:
    return " ".join(text.replace("*", "").split())


def _spoken_answer(rnd) -> str:
    if rnd.type == "true_false":
        return "It's real!" if rnd.answer else "It's fake!"
    if rnd.type == "choice":
        return f"It's {rnd.options[rnd.correct]}!"
    if rnd.type == "odd_one_out":
        return f"The odd one out is {rnd.items[rnd.odd]}!"
    return f"It's... {rnd.answer}!"


def script(video) -> list[tuple[float, str]]:
    """(time in the video, line) for every host line."""
    from .scenes import IntroScene, OutroScene, RoundScene, YesterdayScene

    spec, out = video.spec, []
    for start, scene in zip(video.starts, video.scenes):
        if isinstance(scene, IntroScene):  # a short card has no room for both: title and round one run together
            out.append((start + 0.15, _clean(spec.title) + (" Round one!" if spec.intro == "quick" else "")))
        elif isinstance(scene, RoundScene):
            rnd = scene.item
            if scene.index == 1 and spec.intro == "banner":
                out.append((start + 0.1, f"{_clean(spec.title)} Round one!"))
            elif not (scene.index == 1 and spec.intro == "quick"):
                out.append((start + 0.1, f"Round {NUMBERS[scene.index - 1]}!"))
            if rnd.cliffhanger:
                out.append((start + scene.reveal_at + 0.1, "Comment your answer! I'll reveal it tomorrow."))
            else:
                out.append((start + scene.reveal_at + 0.15, _spoken_answer(rnd)))
        elif isinstance(scene, YesterdayScene):
            names = scene.item.get("shoutouts")
            line = f"Yesterday's cliffhanger? It was... {scene.item['answer']}!"
            if names:
                line += " Well done, " + (", ".join(names[:3]) + (" and the rest of you!" if len(names) > 3 else "!"))
            out.append((start + 0.2, line))
        elif isinstance(scene, OutroScene):
            out.append((start + 0.1, _clean(spec.outro)
                        + (" And comment a theme for next week!" if getattr(spec, "ask_theme", False) else "")))
    return out


def _fetch(text: str, cfg: VoiceConfig) -> Path:
    key = hashlib.sha1(f"{cfg.voice_id}|{cfg.model}|{text}".encode()).hexdigest()[:20]
    path = cfg.cache_dir / f"{key}.mp3"
    if path.exists():
        return path
    r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{cfg.voice_id}",
                   params={"output_format": "mp3_44100_128"}, timeout=60,
                   headers={"xi-api-key": cfg.api_key},
                   json={"text": text, "model_id": cfg.model,
                         "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.6}})
    if r.status_code >= 400:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(r.content)
    tmp.rename(path)
    return path


def _decode(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.float32)


def clips(video, cfg: VoiceConfig) -> list[tuple[float, np.ndarray]]:
    """The host's lines as (time, mono samples at SR). Raises if any line can't be made, so a
    video never goes out with half a voice-over."""
    return [(t, _decode(_fetch(text, cfg))) for t, text in script(video)]
