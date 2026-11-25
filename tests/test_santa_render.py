"""raosanta.uk promos: the spec, the carols, the scenes, the narrator's budget, previews and the
endpoints. One short real render; nothing talks to ElevenLabs or Discord."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import settings
from app.render.audio import SR
from app.render.santa import carols, scenes
from app.render.santa.video import Promo, render_promo
from app.santa import previews, voice
from app.santa.spec import PromoSpec

ROOT = Path(__file__).resolve().parents[1]
H = {"Authorization": "Bearer test-token"}


def spec(**kw) -> PromoSpec:
    base = {"id": "test-promo", "format": "pitch", "segments": [
        {"type": "title", "text": "Remote *team*?", "say": "Remote team?"},
        {"type": "end", "say": "Find us at raosanta dot UK."}]}
    return PromoSpec.model_validate(base | kw)


@pytest.mark.parametrize("name", sorted((ROOT / "examples" / "santa").glob("*.json")), ids=lambda p: p.stem)
def test_the_examples_are_valid_and_under_the_limit(name):
    s = PromoSpec.model_validate(json.loads(name.read_text()))
    assert 5 < Promo(s).duration < 45


@pytest.mark.parametrize("bad, why", [
    ({"segments": [{"type": "title", "text": "Hi \U0001F385"}, {"type": "end"}]}, "font"),
    ({"segments": [{"type": "title", "text": "Hi"}, {"type": "points", "items": ["a"]}]}, "end"),
    ({"format": "quiz"}, "question"),
    ({"format": "kudos"}, "kudos"),
    ({"music": "some-track.mp3"}, "music"),
    ({"segments": [{"type": "question", "question": "Q?", "options": ["a", "b"], "correct": 2}, {"type": "end"}]}, "correct"),
])
def test_bad_specs_are_refused(bad, why):
    with pytest.raises(ValidationError) as e:
        spec(**bad)
    assert why in str(e.value)


def test_only_tutorials_and_pitches_are_voiced_by_default():
    assert spec().voiced and spec(format="tutorial").voiced
    q = spec(format="quiz", segments=[{"type": "question", "question": "Q?", "options": ["a", "b"], "correct": 0},
                                      {"type": "end"}])
    assert not q.voiced
    assert not spec(voice=False).voiced


@pytest.mark.parametrize("name", sorted(carols.CAROLS))
def test_every_carol_fills_its_bars(name):
    carols.check(name)
    audio, got = carols.carol(6.0, 1, name)
    assert got == name and len(audio) == 6 * SR and 0.1 < np.abs(audio).max() <= 0.31


def test_counting_up():
    assert scenes.counted("1,200+", 0.5) == "600+"
    assert scenes.counted("38", 0.5) == "19"
    assert scenes.counted("£0", 0.3) == "£0"
    assert scenes.counted("1,200+", 1.0) == "1,200+"
    assert scenes.counted("Free", 0.2) == "Free"


def test_a_line_keeps_its_segment_on_screen_until_it_ends():
    s = spec()
    quiet = Promo(s)
    loud = Promo(s, {0: 6.0})
    assert loud.scenes[0].duration == pytest.approx(scenes.SAY_AT + 6.0 + scenes.BREATH)
    assert loud.duration > quiet.duration
    assert loud.say_times()[1] == pytest.approx(loud.starts[1] + scenes.SAY_AT)


def test_a_read_question_starts_its_countdown_after_it_is_asked():
    q = spec(format="quiz", segments=[{"type": "question", "question": "Which?", "options": ["a", "b"], "correct": 0,
                                       "think": 4, "say": "Which?"}, {"type": "end"}])
    sc = Promo(q, {0: 5.0}).scenes[0]
    assert sc.t_think >= scenes.SAY_AT + 5.0
    assert sc.duration >= sc.t_think + 4


def test_render_makes_a_looping_video_with_sound(tmp_path):
    s = spec(segments=[{"type": "title", "text": "Hi *there*", "seconds": 1.5}, {"type": "end", "seconds": 1.5}])
    out = tmp_path / "p.mp4"
    clip = (np.sin(np.arange(SR) / SR * 2 * np.pi * 220) * 0.3).astype(np.float32)
    info = render_promo(s, out, voice={0: clip}, cover_path=tmp_path / "p.jpg", workers=2)
    assert out.exists() and (tmp_path / "p.jpg").exists() and info["voice_lines"] == 1
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json",
                            str(out)], capture_output=True, text=True, check=True)
    streams = json.loads(probe.stdout)["streams"]
    assert {st["codec_type"] for st in streams} == {"video", "audio"}
    assert any(st.get("width") == 1080 and st.get("height") == 1920 for st in streams)
    promo = Promo(s, {0: 1.0})
    first, last = (np.asarray(promo.frame(i).convert("RGB"), np.int16) for i in (0, promo.n_frames - 1))
    assert np.abs(first - last).mean() < 4  # the last frame eases back to the first


def test_too_long_is_refused_before_rendering(tmp_path):
    with pytest.raises(ValueError, match="past the 3 s limit"):
        render_promo(spec(), tmp_path / "x.mp4", max_seconds=3)
    assert not (tmp_path / "x.mp4").exists()


# ---------------------------------------------------------------- narrator and budget

@pytest.fixture
def tts(monkeypatch):
    """ElevenLabs stand-in: writes a file per line and counts the calls."""
    calls = []

    def fetch(text, cfg):
        calls.append(text)
        p = voice.tts._cached(cfg.voice_id, text, cfg)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"mp3")
        return p

    monkeypatch.setattr(voice.tts, "_fetch", fetch)
    monkeypatch.setattr(voice.tts, "_decode", lambda p: np.zeros(SR, np.float32))
    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    return calls


def test_voice_lines_are_paid_for_once(tts):
    got, status = voice.lines(spec())
    assert status == "on" and sorted(got) == [0, 1] and len(tts) == 2
    assert voice.spent() == len("Remote team?") + len("Find us at raosanta dot UK.")
    got, status = voice.lines(spec())  # cached: nothing more spent
    assert status == "on" and voice.spent() == 39


def test_voice_is_skipped_rather_than_stopping_the_video(tts, monkeypatch):
    assert voice.lines(spec(voice=False)) == ({}, "off")
    monkeypatch.setattr(settings, "santa_voice_budget", 10)
    got, status = voice.lines(spec())
    assert got == {} and status.startswith("skipped:") and "budget" in status and not tts
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    assert voice.lines(spec()) == ({}, "skipped: no ELEVENLABS_API_KEY")


def test_voice_picks_the_named_narrator(monkeypatch):
    monkeypatch.setattr(settings, "santa_voices", {"lily": "L", "archie": "A"})
    assert voice.voice_id(spec()) == "L"
    assert voice.voice_id(spec(voice_name="Archie")) == "A"
    assert voice.voice_id(spec(voice_name="nobody")) == "L"


# ---------------------------------------------------------------- previews and endpoints

def test_a_preview_goes_to_discord_and_is_never_posted(monkeypatch, discord):
    def fake_render(s, out, **kw):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"video")
        assert kw["max_seconds"] == 45
        return {"duration": 12.0, "music": "jingle-bells", "voice_lines": 0}

    monkeypatch.setattr(previews, "render_promo", fake_render)
    job = previews.create(spec(voice=False, caption="Gift *anyone*"), background=False)
    assert job["status"] == "done" and job["voice"] == "off" and job["video_url"].endswith(".mp4")
    (msg, attach), = discord
    assert "not posted" in msg and "Gift *anyone*" in msg and attach.name == job["video"]
    assert previews.get(job["id"])["status"] == "done"


def test_a_failed_preview_says_why(monkeypatch, discord):
    monkeypatch.setattr(previews, "render_promo", lambda *a, **k: (_ for _ in ()).throw(ValueError("too long")))
    job = previews.create(spec(voice=False), background=False)
    assert job["status"] == "failed" and "too long" in job["error"]
    assert "failed" in discord[-1][0]


def test_endpoints(monkeypatch):
    from app.main import app

    made = []
    monkeypatch.setattr(previews, "create", lambda s: made.append(s) or {"id": "santa-x", "status": "queued"})
    c = TestClient(app)
    assert c.get("/santa/schema").status_code == 401
    sch = c.get("/santa/schema", headers=H).json()
    assert sch["voiced"] == ["tutorial", "pitch"] and "lily" in sch["voices"]
    r = c.post("/santa/preview", headers=H, json={"id": "x", "format": "pitch", "segments": []})
    assert r.status_code == 422 and any("segments" in p for p in r.json()["detail"])
    r = c.post("/santa/preview", headers=H, json=spec().model_dump())
    assert r.status_code == 202 and r.json()["id"] == "santa-x" and made[0].id == "test-promo"
    assert c.get("/santa/previews/nope", headers=H).status_code == 404
