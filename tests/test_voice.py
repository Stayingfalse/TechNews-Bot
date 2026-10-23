"""Host voice-over: what the host says, voice fallback and labelling, and the mix."""
from __future__ import annotations

import subprocess

import numpy as np
import pytest

from app.config import settings
from app.render import voice
from app.render.audio import SR, duck_envelope, voice_track
from app.render.engine import Video
from app.spec import QuizSpec


def test_script(quiz):
    lines = voice.script(Video(QuizSpec.model_validate(dict(quiz, intro="quick", voice=True)),
                               reveal={"answer": "Up", "note": "", "shoutouts": ["early_bird", "TubeFan"]}))
    said = [text for _, text in lines]
    assert said[0] == "Only real film fans get 5 out of 5! Round one!"  # "5/5" read out, title as a sentence
    assert "It's... The Lion King!" in said and "It's real!" in said and "It's Toy Story!" in said
    assert any("Well done, early bird, TubeFan!" in s for s in said)  # names read without underscores
    assert [t for t, _ in lines] == sorted(t for t, _ in lines)


@pytest.fixture
def beep(tmp_path):
    p = tmp_path / "beep.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=0.4", str(p)], check=True)
    return p.read_bytes()


def test_refused_voice_falls_back_and_is_labelled(tmp_path, beep, monkeypatch):
    calls, refused = [], {settings.voices["alex"]}

    class Resp:
        def __init__(self, code):
            self.status_code, self.content, self.text = code, beep, "library voices need a paid plan"

    monkeypatch.setattr(voice, "_tts", lambda vid, body, cfg: calls.append(vid) or Resp(402 if vid in refused else 200))
    names = {v: k for k, v in settings.voices.items()}

    def speak():
        cfg = voice.VoiceConfig("key", settings.voices["alex"], "eleven_v3", tmp_path / "cache")
        voice._fetch("Round one!", cfg)
        return [names[v] for v in cfg.used]

    assert speak() == ["liam"]  # free plan: Liam steps in, and the video says so
    assert speak() == ["liam"]
    assert calls.count(voice.FALLBACK_VOICE) == 1  # the fallback line is reused...
    refused.clear()
    assert speak() == ["alex"]  # ...but never filed under Alex, who is tried again


def test_voice_ids_keep_their_case():
    assert settings.voices["alex"] == "dEc1rkm0ul0kDedEuETS"


def test_lines_never_overlap_and_music_ducks():
    clip = np.full(SR, 0.5, np.float32)  # each line 1 s long
    track = voice_track([(0.0, clip), (0.5, clip)], 3 * SR)
    assert np.abs(track[int(0.45 * SR)]) < 0.6  # the first line fades out under the second, not on top
    env = duck_envelope(track)
    assert env[int(0.7 * SR)] == pytest.approx(0.35, abs=0.01) and env[int(2.8 * SR)] == pytest.approx(1.0)
