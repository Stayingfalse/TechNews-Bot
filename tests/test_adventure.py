"""Adventure channel (preview only): the narrator's clips, their budget, and the render endpoint.
ElevenLabs and the Node renderer are mocked; adventure/ has its own tests for the drawing."""
from __future__ import annotations

import base64
import json

import pytest

from fastapi.testclient import TestClient

from app.adventure import jobs, voice
from app.config import settings
from app.main import app

ALIGN = {"characters": list("Hi."), "character_start_times_seconds": [0.0, 0.1, 0.2], "character_end_times_seconds": [0.1, 0.2, 0.3]}


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text = status, body or {}, json.dumps(body or {})

    def json(self):
        return self._body


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def eleven(monkeypatch):
    calls = []

    def post(url, **kw):
        calls.append((url, kw["json"]))
        return FakeResponse(200, {"audio_base64": base64.b64encode(b"ID3fake").decode(), "alignment": ALIGN})

    monkeypatch.setattr(settings, "elevenlabs_api_key", "k")
    monkeypatch.setattr(voice.httpx, "post", post)
    return calls


def test_clip_is_made_once_and_cached(eleven):
    mp3, align, made = voice.clip("[whispers] Hi.")
    assert made and mp3.read_bytes() == b"ID3fake" and json.loads(align.read_text())["alignment"] == ALIGN
    assert eleven[0][0].endswith(f"/text-to-speech/{settings.adventure_voice_id}/with-timestamps")
    assert eleven[0][1] == {"text": "[whispers] Hi.", "model_id": "eleven_v3"}
    _, _, again = voice.clip("[whispers] Hi.")
    assert not again and len(eleven) == 1  # cached: no second charge
    assert voice.spent() == len("[whispers] Hi.")  # tags are billed too


def test_budget_stops_new_clips(eleven, monkeypatch):
    monkeypatch.setattr(settings, "adventure_voice_budget", 20)
    voice.clip("a" * 15)
    with pytest.raises(voice.OutOfBudget):
        voice.clip("b" * 10)
    assert len(eleven) == 1


def test_no_key_means_no_voice(monkeypatch):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    with pytest.raises(voice.OutOfBudget):
        voice.clip("Hi.")


def test_job_voices_renders_and_previews(eleven, monkeypatch, discord):
    ran = []

    def node(*args, timeout=900):
        ran.append(args)
        if args[0] == "script":
            return {"text": "[whispers] Hi.", "chars": 14, "segments": []}
        out = args[args.index("--out") + 1]
        open(out, "wb").write(b"mp4")
        return {"out": out, "duration": 41.0, "frames": 1230, "seconds": 33.0, "cues": {"hook": 0.1}}

    monkeypatch.setattr(jobs, "_node", node)
    monkeypatch.setattr(jobs.threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: target(*args)})())
    job = jobs.submit({"kind": "episode0", "part": 1})
    done = jobs.get(job["id"])
    assert done["status"] == "done" and done["video_url"].startswith(f"{settings.public_base_url}/media/adv-")
    render = ran[1]
    assert "--audio" in render and "--align" in render  # voiced and timed to the voice
    assert done["voice_clip"]["new"] and done["voice_clip"]["chars"] == 14
    assert "Adventure preview" in discord[-1][0] and discord[-1][1] is not None


def test_job_without_budget_goes_out_silent(monkeypatch, discord):
    monkeypatch.setattr(settings, "elevenlabs_api_key", "")
    seen = []

    def node(*args, timeout=900):
        seen.append(args)
        if args[0] == "script":
            return {"text": "Hi.", "chars": 3, "segments": []}
        return {"out": "x", "duration": 30.0, "frames": 900, "seconds": 20.0, "cues": None}

    monkeypatch.setattr(jobs, "_node", node)
    monkeypatch.setattr(jobs.threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: target(*args)})())
    job = jobs.submit({"kind": "episode0", "part": 1})
    done = jobs.get(job["id"])
    assert done["status"] == "done" and "--audio" not in seen[1] and "skipped" in done["voice_clip"]


def test_endpoint_rejects_bad_spec(client, monkeypatch):
    def node(*args, timeout=900):
        raise RuntimeError('invalid spec: spec: part 3 needs "hero"')

    monkeypatch.setattr(jobs, "_node", node)
    r = client.post("/adventure/episode0?voice=false", json={"part": 3}, headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422 and "needs" in r.json()["detail"]


def test_credits_endpoint(client):
    r = client.get("/adventure/credits", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 200 and r.json()["budget"] == settings.adventure_voice_budget and r.json()["spent"] == 0


def test_tighten_shortens_long_pauses_and_moves_the_timestamps(tmp_path):
    import subprocess
    # 1 s tone, 3 s silence, 1 s tone
    src = tmp_path / "v.mp3"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-f", "lavfi", "-i", "sine=frequency=300:duration=1",
                    "-filter_complex", "[1:a]atrim=duration=3[s];[0:a][s][2:a]concat=n=3:v=0:a=1", str(src)], check=True)
    al = tmp_path / "v.json"
    al.write_text(json.dumps({"alignment": {"characters": ["a", "b"], "character_start_times_seconds": [0.1, 4.1],
                                            "character_end_times_seconds": [0.9, 4.9]}}))
    out, out_al = voice.tighten(src, al, 0.6)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
                               capture_output=True, text=True).stdout)
    assert 2.4 < dur < 2.9  # 5 s → about 2.6 s
    starts = json.loads(out_al.read_text())["alignment"]["character_start_times_seconds"]
    assert starts[0] == 0.1 and 1.5 < starts[1] < 1.8  # the second word moved up by the cut
    assert voice.tighten(src, al, 0.6) == (out, out_al)  # cached
