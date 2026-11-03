"""The render worker (app/render_worker.py) and its client (app/render/remote.py): videos made on
another host from everything this server sends, and rendered here instead whenever that fails."""
from __future__ import annotations

import io
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from app import render_worker
from app.config import settings
from app.render import engine, remote
from app.render import voice as host
from app.render.engine import Video
from app.spec import QuizSpec


@pytest.fixture
def worker(monkeypatch):
    """The worker app in-process; the client's HTTP calls are routed to it."""
    monkeypatch.setattr(render_worker, "TOKEN", "w-secret")
    monkeypatch.setattr(settings, "render_url", "https://worker.example")
    monkeypatch.setattr(settings, "render_token", "w-secret")
    monkeypatch.setattr(remote, "_warned", {"at": 0.0})
    client = TestClient(render_worker.app)
    seen = []

    def post(url, content, headers, timeout):
        seen.append(url)
        return client.post(url.removeprefix(settings.render_url), content=content, headers=headers)

    monkeypatch.setattr(remote.httpx, "post", post)
    return {"client": client, "urls": seen}


def fake_render(calls):
    """Stands in for render_video on the worker: records what it was given, writes a 'video'."""
    def render(spec, out, *, brand="", cover_path=None, reveal=None, voice=None, track=None, **_):
        lines = host.fetch_all(Video(spec, brand, reveal), voice) if voice else []
        calls.append({"spec": spec, "brand": brand, "reveal": reveal, "track": track,
                      "track_bytes": track.read_bytes() if hasattr(track, "read_bytes") else None,
                      "lines": [p.read_bytes() for p in lines], "used": set(voice.used) if voice else set()})
        out.write_bytes(b"MP4" + spec.id.encode())
        cover_path.write_bytes(b"JPG")
        return {"duration": 1.0, "voice": "on" if voice else "off", "voice_id": ",".join(sorted(voice.used)) if voice else ""}
    return render


def test_without_a_worker_nothing_is_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "render_url", "")
    monkeypatch.setattr(remote.httpx, "post", lambda *a, **k: pytest.fail("no worker configured"))
    assert remote.racing({}, tmp_path / "v.mp4", tmp_path / "c.jpg") is None


def test_the_worker_wants_its_token(worker):
    assert worker["client"].post("/render", content=b"x", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert worker["client"].post("/render", content=b"x").status_code == 401
    assert worker["client"].get("/health").json() == {"ok": True, "worker": True, "busy": False}


def test_a_quiz_goes_with_its_host_lines_and_uploaded_music(worker, quiz, tmp_path, monkeypatch):
    """The lines are made here (the worker has no ElevenLabs key) and an uploaded track sent along,
    so the worker's video sounds exactly like one made here."""
    calls = []
    monkeypatch.setattr(engine, "render_video", fake_render(calls))
    spec = QuizSpec.model_validate(dict(quiz, voice=True, music="mine.mp3"))
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "mine.mp3").write_bytes(b"MY TRACK")
    cfg = host.VoiceConfig("el-key", "voice-a", "eleven_v3", tmp_path / "voice")
    cfg.cache_dir.mkdir()
    reveal = {"answer": "Up", "note": "", "shoutouts": []}
    lines = host.script(Video(spec, "@b", reveal))
    for i, (_, text) in enumerate(lines):  # already cached, so nothing calls ElevenLabs; the last
        voice = host.FALLBACK_VOICE if i == len(lines) - 1 else "voice-a"  # one was refused and fell back
        host._cached(voice, text, cfg).write_bytes(f"line {i}".encode())

    def tts(voice_id, body, cfg):  # only the refused line is asked for again, and refused again
        assert voice_id == "voice-a" and body["text"].endswith(lines[-1][1])
        return httpx.Response(402, text="library voice")

    monkeypatch.setattr(host, "_tts", tts)

    info = remote.quiz(spec, tmp_path / "v.mp4", tmp_path / "c.jpg", brand="@b", music_dir=music_dir,
                       bundled_music=True, reveal=reveal, voice=cfg)
    assert info["rendered_by"] == "worker" and info["voice"] == "on"
    assert set(info["voice_id"].split(",")) == {"voice-a", host.FALLBACK_VOICE}
    assert (tmp_path / "v.mp4").read_bytes() == b"MP4" + spec.id.encode() and (tmp_path / "c.jpg").read_bytes() == b"JPG"
    [call] = calls
    assert call["spec"] == spec and call["brand"] == "@b" and call["reveal"]["answer"] == "Up"
    assert call["track"].name == "mine.mp3" and call["track_bytes"] == b"MY TRACK"
    assert call["lines"] == [f"line {i}".encode() for i in range(len(lines))]


def test_a_bundled_track_is_named_not_sent(worker, quiz, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(engine, "render_video", fake_render(calls))
    spec = QuizSpec.model_validate(dict(quiz, music="bossa-nova"))
    info = remote.quiz(spec, tmp_path / "v.mp4", tmp_path / "c.jpg", brand="", music_dir=tmp_path,
                       bundled_music=True, reveal=None, voice=None)
    assert info and calls[0]["track"].name == "bossa-nova.ogg" and calls[0]["track"].parent.name == "music"


def test_any_failure_there_means_rendering_here(worker, quiz, tmp_path, monkeypatch, discord):
    def broken(*a, **k):
        raise RuntimeError("out of memory")

    monkeypatch.setattr(engine, "render_video", broken)
    spec = QuizSpec.model_validate(quiz)
    out = tmp_path / "v.mp4"
    assert remote.quiz(spec, out, tmp_path / "c.jpg", brand="", music_dir=tmp_path, bundled_music=True,
                       reveal=None, voice=None) is None
    assert not out.exists()
    assert len(discord) == 1 and "out of memory" in discord[0][0]

    def down(*a, **k):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(remote.httpx, "post", down)
    assert remote.racing({"x": 1}, out, tmp_path / "c.jpg") is None
    assert len(discord) == 1  # one Discord warning an hour; the rest are only logged


def test_the_pipeline_renders_here_when_the_worker_fails(worker, quiz, tmp_path, monkeypatch):
    from app import pipeline

    monkeypatch.setattr(remote, "quiz", lambda *a, **k: None)
    made = []

    def local(spec, out, **k):
        made.append(spec.id)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"local")
        k["cover_path"].write_bytes(b"jpg")
        return {"duration": 1.0, "voice": "off"}

    monkeypatch.setattr(pipeline, "render_video", local)
    monkeypatch.setattr(pipeline, "_publish", lambda job: None)
    job = {"id": "j1", "spec": quiz, "status": "queued", "results": {}, "dry_run": True, "retry": True, "reveal": None}
    pipeline._render(job)
    assert made == [quiz["id"]] and job["video"].endswith(".mp4")


def test_a_busy_worker_turns_the_next_render_away(worker):
    assert render_worker._busy.acquire(blocking=False)
    try:
        r = worker["client"].post("/render", content=remote.pack("request.json", {"kind": "racing", "spec": {}}),
                                  headers={"Authorization": "Bearer w-secret"})
        assert r.status_code == 503
    finally:
        render_worker._busy.release()


def test_files_cannot_escape_the_worker_folder(worker):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("request.json", json.dumps({"kind": "racing", "spec": {}}))
        z.writestr("../../escape.txt", "x")
    r = worker["client"].post("/render", content=buf.getvalue(), headers={"Authorization": "Bearer w-secret"})
    assert r.status_code == 400
    assert render_worker._busy.acquire(blocking=False)  # released again after a bad request
    render_worker._busy.release()


def test_adventure_narration_files_go_along(worker, tmp_path, monkeypatch):
    from app.adventure import jobs

    mp3, align = tmp_path / "n.mp3", tmp_path / "n.json"
    mp3.write_bytes(b"NARRATION")
    align.write_text('{"words": []}')
    got = {}

    def node(spec_path, *args):
        a = list(args)
        got["spec"] = json.loads(open(spec_path).read())
        got["audio"] = open(a[a.index("--daily") + 1], "rb").read()
        got["align"] = open(a[a.index("--align") + 1]).read()
        got["flags"] = [x for x in a if x.startswith("--")]
        open(a[a.index("--out") + 1], "wb").write(b"ADV")
        return {"duration": 30.0, "seconds": 12}

    monkeypatch.setattr(jobs, "_node", node)
    out = tmp_path / "out" / "a.mp4"
    info = remote.adventure({"kind": "story", "ep": 3}, out, ["--daily", str(mp3), "--align", str(align)])
    assert info["rendered_by"] == "worker" and out.read_bytes() == b"ADV"
    assert got["spec"] == {"kind": "story", "ep": 3} and got["audio"] == b"NARRATION" and got["align"] == '{"words": []}'
    assert got["flags"] == ["--out", "--workers", "--daily", "--align"]


def test_racing_goes_to_the_worker(worker, tmp_path, monkeypatch):
    from app.render.racing import engine as racing_engine

    def render(spec, out, cover_path=None):
        out.write_bytes(json.dumps(spec).encode())
        cover_path.write_bytes(b"JPG")
        return {"duration": 20.0, "seconds": 5}

    monkeypatch.setattr(racing_engine, "render", render)
    info = remote.racing({"theme": "pitwall", "seed": 7}, tmp_path / "r.mp4", tmp_path / "r.jpg")
    assert info["rendered_by"] == "worker" and json.loads((tmp_path / "r.mp4").read_text())["seed"] == 7


@pytest.mark.slow
def test_a_real_quiz_video_comes_back_whole(worker, quiz, tmp_path):
    """The real encode on the worker: the video and cover that come back are the ones it made."""
    import subprocess

    q = dict(quiz, rounds=[dict(r, think=3.0) for r in quiz["rounds"][:3]], intro="quick")
    spec = QuizSpec.model_validate(q)
    out = tmp_path / "v.mp4"
    info = remote.quiz(spec, out, tmp_path / "c.jpg", brand="", music_dir=tmp_path, bundled_music=True,
                       reveal=None, voice=None)
    assert info and info["rendered_by"] == "worker" and info["bytes"] == out.stat().st_size
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True, check=True).stdout.split()
    assert sorted(streams) == ["audio", "video"] and (tmp_path / "c.jpg").stat().st_size > 1000


def test_a_farside_episode_goes_with_its_voice(worker, tmp_path, monkeypatch):
    import numpy as np

    from app.render.colony import video as colony_video

    got = {}

    def render(spec, out, voice=None):
        got["spec"], got["voice"] = spec, voice
        out.write_bytes(b"FARSIDE")

    monkeypatch.setattr(colony_video, "render", render)
    monkeypatch.setattr(colony_video, "frame_at", lambda spec, t: np.zeros((4, 4, 3), np.uint8))
    lines = [(1.5, np.linspace(-1, 1, 100, dtype=np.float32)), (7.25, np.ones(50, np.float32))]
    info = remote.colony({"duration": 30.0, "shots": []}, tmp_path / "f.mp4", tmp_path / "f.jpg", lines)
    assert info["rendered_by"] == "worker" and (tmp_path / "f.mp4").read_bytes() == b"FARSIDE"
    assert (tmp_path / "f.jpg").stat().st_size > 0 and got["spec"]["duration"] == 30.0
    assert [t for t, _ in got["voice"]] == [1.5, 7.25]
    assert all(np.array_equal(a, b) for (_, a), (_, b) in zip(got["voice"], lines))
