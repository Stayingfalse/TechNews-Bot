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


# ------------------------------------------------------------------ the channel's own Instagram

from app import channels, main, pipeline, store  # noqa: E402
from app.publish import instagram  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture
def ig(monkeypatch):
    """Instagram with the quiz connected as user 111; approving saves whichever user `who` names."""
    monkeypatch.setattr(settings, "instagram_app_id", "app")
    monkeypatch.setattr(settings, "instagram_app_secret", "secret")
    store.set_tokens("instagram", {"access_token": "quiz", "user_id": "111", "expires_at": 9e9}, channel="main")
    who = {"id": "222", "name": "dungeoncrawlergram"}
    monkeypatch.setattr(instagram, "exchange_code", lambda code: store.set_tokens(
        "instagram", {"access_token": f"tok-{who['id']}", "user_id": who["id"], "expires_at": 9e9}))
    monkeypatch.setattr(instagram, "account", lambda: {"username": who["name"] if store.get_tokens("instagram")["user_id"] == who["id"] else "mediaquiz.daily"})
    return who


def _connect(client, provider="instagram", channel="adventure"):
    r = client.get(f"/oauth/{provider}/start?channel={channel}", headers=AUTH, follow_redirects=False)
    assert r.status_code == 307
    state = r.headers["location"].split("state=")[1].split("&")[0]
    return client.get(f"/oauth/{provider}/callback?code=abc&state={state}")


def test_connecting_the_adventure_channel_leaves_the_quiz_alone(client, ig, discord):
    r = _connect(client)
    assert r.status_code == 200 and "@dungeoncrawlergram is now connected" in r.text
    assert store.get_tokens("instagram", channel="adventure")["user_id"] == "222"
    assert store.get_tokens("instagram", channel="main")["access_token"] == "quiz"  # untouched
    assert "connected as @dungeoncrawlergram" in discord[-1][0]


def test_the_quiz_account_is_refused_for_the_adventure_channel(client, ig):
    ig["id"] = "111"  # approved while signed in to the quiz's account
    r = _connect(client)
    assert r.status_code == 409 and "quiz" in r.text
    assert store.get_tokens("instagram", channel="adventure") is None
    assert store.get_tokens("instagram", channel="main")["access_token"] == "quiz"


def test_unknown_channel_is_refused(client):
    assert client.get("/oauth/instagram/start?channel=nope", headers=AUTH, follow_redirects=False).status_code == 404


def test_status_shows_each_channels_account(client, ig):
    _connect(client)
    ch = client.get("/status", headers=AUTH).json()["channels"]
    assert ch["adventure"]["platforms"]["instagram"]["account"]["username"] == "dungeoncrawlergram"
    assert ch["adventure"]["platforms"]["instagram"]["connect_url"] == "/oauth/instagram/start?channel=adventure"
    assert ch["main"]["platforms"]["instagram"]["account"]["username"] == "mediaquiz.daily"


def test_tokens_are_refreshed_for_every_channel(client, ig, monkeypatch):
    _connect(client)
    seen = []
    monkeypatch.setattr(instagram, "refresh_if_needed", lambda force=False: seen.append(store.get_tokens("instagram")["user_id"]))
    monkeypatch.setattr(settings, "platforms", ["instagram"])
    pipeline.refresh_tokens()
    assert sorted(seen) == ["111", "222"]


def _fake_node(*args, timeout=900):
    if args[0] == "script":
        return {"text": "Hi.", "chars": 3, "segments": [], "caption": "Part 1 #dungeoncrawl", "comment": "A) x · B) y · C) z"}
    open(args[args.index("--out") + 1], "wb").write(b"mp4")
    return {"out": "x", "duration": 55.0, "frames": 1650, "seconds": 170.0, "cues": None}


def test_posting_needs_the_channel_connected(client, monkeypatch):
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(jobs, "_node", _fake_node)
    r = client.post("/adventure/episode0?voice=false&publish=true", json={"part": 1}, headers=AUTH)
    assert r.status_code == 409


def test_posting_goes_to_the_adventure_account(client, ig, monkeypatch, discord):
    _connect(client)
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(jobs, "_node", _fake_node)
    monkeypatch.setattr(jobs.threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: target(*args)})())
    posted = []

    def publish_reel(url, caption, cover_url=None):
        posted.append((store.get_tokens("instagram")["access_token"], caption))
        return {"media_id": "m1", "url": "https://instagram.com/p/x"}

    monkeypatch.setattr(instagram, "publish_reel", publish_reel)
    monkeypatch.setattr(instagram, "comment", lambda media, text: posted.append((media, text)) or "c1")
    r = client.post("/adventure/episode0?voice=false&publish=true", json={"part": 1}, headers=AUTH)
    assert r.status_code == 202
    job = jobs.get(r.json()["id"])
    assert job["status"] == "done" and job["results"]["instagram"]["ok"] and job["results"]["instagram"]["comment_id"] == "c1"
    assert posted[0] == ("tok-222", "Part 1 #dungeoncrawl")  # the adventure account's token, not the quiz's
    assert posted[1] == ("m1", "A) x · B) y · C) z")
    assert "Posted to @dungeoncrawlergram" in discord[-1][0]


# ------------------------------------------------------------------ votes

from datetime import datetime, timedelta, timezone  # noqa: E402

from app.adventure import votes  # noqa: E402

FEARS = ["Rattling skeletons", "Sneaky goblins", "Shrieking wraiths"]


@pytest.mark.parametrize("text,pick", [
    ("B", 1), ("b!", 1), ("(c)", 2), ("A 💀", 0), ("  c.", 2),
    ("B - the goblins are scarier", 1), ("C: wraiths for sure", 2),
    ("option b", 1), ("I pick c", 2), ("team A all the way", 0), ("going with b please", 1),
    ("goblins!!", 1), ("definitely the wraiths", 2), ("Skeletons give me the creeps", 0),
    ("a or b", None), ("B and C", None), ("what a twist", None), ("love this channel", None),
    ("B, actually no, skeletons", None), ("@friend b", 1), ("ABC", None), ("", None),
])
def test_votes_are_read_from_comments(text, pick):
    assert votes.parse(text, FEARS) == pick


def test_each_account_counts_once_and_first_vote_wins():
    comments = [{"user": "ann", "text": "b"}, {"user": "bob", "text": "nice"}, {"user": "ANN", "text": "c"},
                {"user": "bob", "text": "C!"}, {"user": "cat", "text": "wraiths"}]
    t = votes.tally(comments, FEARS)
    assert t["counts"] == [0, 1, 2] and t["comments"] == 5 and len(t["voters"]) == 3


def test_decide_uses_default_and_breaks_ties_the_same_way_every_time():
    assert votes.decide([0, 0, 0], 1, "k") == (1, "default")
    assert votes.decide([1, 4, 2], 0, "k") == (1, "votes")
    first = votes.decide([3, 3, 0], 2, "job-1")
    assert first[1] == "tie-break" and first[0] in (0, 1) and votes.decide([3, 3, 0], 2, "job-1") == first


def test_next_part_is_built_from_the_vote():
    p1 = {"kind": "episode0", "part": 1, "seed": 12}
    p2 = jobs.next_spec(p1, 2, [1, 0, 5])
    assert p2["part"] == 2 and p2["fear"] == "wraith" and p2["recap"] == {"pick": 2, "votes": [1, 0, 5]}
    p3 = jobs.next_spec(p2, 0, [4, 1, 1])
    assert p3["hero"] == {"cls": "fighter", "look": 0} and p3["fear"] == "wraith"
    p4 = jobs.next_spec(p3, 2, [0, 0, 0])
    assert p4["hero"] == {"cls": "fighter", "look": 2} and p4["recap"]["pick"] == 2


# ------------------------------------------------------------------ the schedule

def _script_for(spec):
    part = spec["part"]
    return {"text": f"part {part}", "chars": 6, "segments": [], "caption": f"cap {part}", "comment": f"opts {part}",
            "options": FEARS if part == 1 else ["Fighter", "Rogue", "Wizard"], "default": 0 if part == 1 else 1}


@pytest.fixture
def scheduled(client, ig, monkeypatch, discord):
    _connect(client)
    monkeypatch.setattr(settings, "publish_enabled", True)
    monkeypatch.setattr(jobs, "script", _script_for)
    rendered, posted = [], []

    def render(job):
        rendered.append(job["spec"])
        job.update(video="v.mp4", video_url="https://x/v.mp4", render={"duration": 55.0, "seconds": 170.0})

    monkeypatch.setattr(jobs, "_render", render)
    monkeypatch.setattr(jobs.threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: target(*args)})())

    def publish_reel(url, caption, cover_url=None):
        posted.append((store.get_tokens("instagram")["access_token"], caption))
        return {"media_id": f"m{len(posted)}", "url": f"https://instagram.com/p/{len(posted)}"}

    monkeypatch.setattr(instagram, "publish_reel", publish_reel)
    monkeypatch.setattr(instagram, "comment", lambda media, text: "c")
    monkeypatch.setattr(instagram, "own_name", lambda: "dungeoncrawlergram")
    monkeypatch.setattr(instagram, "comments", lambda media: [
        {"user": "dungeoncrawlergram", "text": "A"},  # our own comment never counts
        {"user": "ann", "text": "c"}, {"user": "bob", "text": "wraiths!"}, {"user": "cat", "text": "b"}])
    return rendered, posted


def test_a_booked_part_is_prepared_an_hour_early_posted_on_time_and_books_the_next(scheduled, discord):
    rendered, posted = scheduled
    slot = datetime(2030, 3, 4, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    job = jobs.submit({"kind": "episode0", "part": 1}, at=slot, series=True)
    assert job["status"] == "booked" and job["publish"]

    jobs.tick(slot - timedelta(minutes=61))
    assert jobs.get(job["id"])["status"] == "booked" and not rendered
    jobs.tick(slot - timedelta(minutes=60))
    assert jobs.get(job["id"])["status"] == "scheduled" and rendered[0]["part"] == 1 and not posted
    jobs.tick(slot)
    done = jobs.get(job["id"])
    assert done["status"] == "done" and posted == [("tok-222", "cap 1")]

    nxt = [j for j in jobs.recent() if j.get("from_job") == job["id"]][0]
    assert nxt["status"] == "booked" and nxt["spec"] == {"kind": "episode0", "part": 2}
    assert datetime.fromisoformat(nxt["publish_at"]).astimezone(settings.tz).strftime("%d %H:%M") == "05 09:00"

    # next morning at 08:00: votes counted (ann c, bob wraiths, cat b; ours ignored) → wraiths win
    jobs.tick(datetime.fromisoformat(nxt["publish_at"]) - timedelta(minutes=60))
    ready = jobs.get(nxt["id"])
    assert ready["status"] == "scheduled"
    assert ready["votes"]["counts"] == [0, 1, 2] and ready["votes"]["pick"] == 2 and ready["votes"]["how"] == "votes"
    assert ready["spec"]["fear"] == "wraith" and ready["spec"]["recap"] == {"pick": 2, "votes": [0, 1, 2]}
    assert any("Adventure votes" in m for m, _ in discord)


def test_a_missed_slot_is_skipped_and_reported(scheduled, discord):
    slot = datetime.now(timezone.utc) + timedelta(hours=1)
    job = jobs.submit({"kind": "episode0", "part": 1}, at=slot, series=True)
    jobs.tick(slot + timedelta(hours=7))
    assert jobs.get(job["id"])["status"] == "missed" and "missed" in discord[-1][0]


def test_a_restart_prepares_again_but_never_reposts_blindly(scheduled, discord):
    slot = datetime.now(timezone.utc) + timedelta(hours=3)
    a = jobs.submit({"kind": "episode0", "part": 1}, at=slot)
    b = jobs.submit({"kind": "episode0", "part": 1}, at=slot + timedelta(days=1))
    a["status"], b["status"] = "rendering", "publishing"
    jobs.save(a)
    jobs.save(b)
    jobs.recover()
    assert jobs.get(a["id"])["status"] == "booked"
    assert jobs.get(b["id"])["status"] == "failed" and "check" in discord[-1][0]


def test_booking_endpoint_takes_a_local_time(client, scheduled):
    r = client.post("/adventure/episode0?at=09:00", json={"part": 1}, headers=AUTH)
    assert r.status_code == 202, r.text
    at = datetime.fromisoformat(r.json()["publish_at"]).astimezone(settings.tz)
    assert at.strftime("%H:%M") == "09:00" and r.json()["series"] and r.json()["status"] == "booked"
    assert client.delete(f"/adventure/jobs/{r.json()['id']}", headers=AUTH).json()["status"] == "cancelled"
