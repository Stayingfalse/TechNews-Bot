"""Farside's voices (app/colony/voice.py): what's said, who says it, and the video stretched so
no line is cut off. ElevenLabs is faked with tones as long as the text needs."""
import numpy as np
import pytest

from app.colony import dryrun, episode, jobs, replay, rules, state, voice
from app.config import settings
from app.render.audio import SR, write_wav


@pytest.fixture
def tts(monkeypatch, tmp_path):
    """Each line becomes a tone of 0.07 s a character, so long lines are long."""
    calls = []
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")

    def fake(vid, text):
        calls.append((vid, text))
        path = tmp_path / f"{len(calls)}.wav"
        n = int(SR * 0.07 * len(text))
        write_wav((0.3 * np.sin(np.arange(n) * 0.05)).astype(np.float32), str(path))
        return path

    monkeypatch.setattr(voice, "clip", fake)
    return calls


def test_on_screen_text_is_said_as_words():
    assert voice.spoken("*@OLD.BARREL* GOT|HIS *BARREL*") == "Old barrel got his barrel."
    assert voice.spoken("*+1,000* NEW SETTLERS") == "Plus 1,000 new settlers."
    assert voice.spoken("IT LEAKS.|I LOVE IT.") == "It leaks. I love it."


def test_the_crew_keep_their_voices_and_a_settler_keeps_the_one_they_get():
    s, _ = dryrun.simulate()
    assert voice.voice_for("MAREN", s) == settings.colony_crew_voices["MAREN"]
    first = voice.voice_for("@nova.k", s)
    assert first in settings.colony_settler_voices.values() and voice.voice_for("nova.k", s) == first
    st = next(x for x in s["settlers"].values() if x["handle"] == "oldbarrel")
    st["look"] = {"body": "old", "carrier": "barrel"}
    st.pop("voice", None)
    assert voice.voice_for("@oldbarrel", s) == settings.colony_settler_voices["old"]


def test_every_line_fits_its_beat_and_the_rest_moves_with_it(tts):
    s, reports = dryrun.simulate()
    ep = replay.fake_claude({"planned": None, "date": "x", "people": [], "kit": {}})
    v = episode.build(s, reports[1])
    before = v["duration"]
    lines_before = voice.lines(v)
    v2, placed, info = voice.add(v, s)
    assert info["lines"] == len([ln for ln in lines_before if ln["text"].strip(". ")]) and placed
    assert v2["duration"] >= before
    side = v2["shots"][0]["spec"]
    caps = side["captions"]
    assert all(a["t0"] <= b["t0"] for a, b in zip(caps, caps[1:]))  # still in order
    for t, smp in placed:  # no line runs past the end, or into the next one
        assert t + len(smp) / SR <= v2["duration"] + 1e-3
    starts = sorted(t for t, _ in placed)
    ends = sorted(t + len(s_) / SR for t, s_ in placed)
    assert all(e <= s2 + 1e-3 for e, s2 in zip(ends, starts[1:]))
    assert v2["duration"] <= 44.0 + 1e-6


def test_the_narrator_reads_the_decision(tts):
    s, reports = dryrun.simulate()
    ep = {"beats": [{"type": "slot", "slot": "arrivals"},
                    {"type": "decision", "who": "MAREN", "lines": ["A SEALED DOOR"], "choices": [["A", "OPEN IT"], ["B", "LEAVE IT"]]}],
          "caption": "x"}
    v = episode.build(s, reports[2], ep)
    voice.add(v, s)
    assert any(t.endswith("Comment A to open it, or B to leave it.") for _, t in tts)


def test_no_budget_means_no_voice_not_no_episode(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    monkeypatch.setattr(settings, "colony_voice_budget", 5)
    s, reports = dryrun.simulate()
    v = episode.build(s, reports[1])
    job = {}
    spec, lines = jobs._voice(job, v, s)
    assert lines is None and spec is v and not job["voice"]["on"] and "budget" in job["voice"]["why"]


def test_voice_is_off_without_a_key(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    job = {}
    s, reports = dryrun.simulate()
    spec, lines = jobs._voice(job, episode.build(s, reports[0]), s)
    assert lines is None and "off" in job["voice"]["why"]


def test_the_voiced_episode_renders_with_the_voice_in_it(tts, tmp_path):
    from app.render.colony import sound

    s, reports = dryrun.simulate()
    v, lines, _ = voice.add(episode.build(s, reports[1]), s)
    wav = tmp_path / "a.wav"
    sound.write({"duration": v["duration"], "sfx": v["sfx"]}, wav, voice=lines)
    assert wav.stat().st_size > SR * v["duration"] * 2  # stereo 16-bit, the whole length


def test_a_refused_library_voice_falls_back_to_the_built_in_one(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    asked = []

    class R:
        def __init__(self, code):
            self.status_code, self.content, self.text = code, b"ID3fake", "voice not found"

    def post(url, **kw):
        vid = url.rsplit("/", 1)[1]
        asked.append(vid)
        return R(404 if vid == "LIBRARY" else 200)

    monkeypatch.setattr(voice.httpx, "post", post)
    voice.refused.clear()
    p = voice.clip("LIBRARY", "Hello.")
    assert asked == ["LIBRARY", settings.colony_fallback_voice] and p.exists() and "LIBRARY" in voice.refused
