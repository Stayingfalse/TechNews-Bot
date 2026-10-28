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


# ------------------------------------------------------------------ the story (weekly arcs)

from app.adventure import campaign  # noqa: E402

ARC = json.loads((settings.adventure_dir / "examples" / "arc-s1w1.json").read_text())
PART4 = ["Force the rusted gate", "Pick the old lock", "Search for another way"]


def _fake_cli(problems=None):
    """The renderer CLI, faked: validate-arc passes (or reports `problems`), resolve rolls plainly."""
    seen = []

    def node(cmd, path, timeout=60):
        payload = json.loads(open(path).read())
        seen.append((cmd, payload))
        if cmd == "validate-arc":
            return {"ok": not problems, "problems": problems or [], "arc": None if problems else payload["arc"]}
        if cmd == "vocab":
            return {"scenes": ["dungeon"], "hero": payload["hero"]}
        n, ctx = payload["node"], payload["ctx"]
        check, hearts = n.get("check"), ctx["hearts"]
        ok = check is None or ctx["dice"][0] >= check["dc"]
        if check and not ok and check.get("harm"):
            hearts -= 1
        return {"kind": "story", "ep": ctx["ep"], "node": n["id"], "recap": ctx["recap"], "hearts": {"before": ctx["hearts"], "after": hearts},
                "dead": hearts <= 0, "check": {"dc": check["dc"], "roll": {"total": ctx["dice"][0], "ok": ok}} if check else None,
                "choices": [{"label": c["label"]} for c in n["choices"]], "default": n["default"]}
    return node, seen


def _story_script(spec):
    if spec.get("kind") == "story":
        return {"text": f"ep {spec['ep']}", "check": "Check.", "roll": "Roll.", "tail": "Tail.", "caption": f"ep {spec['ep']}",
                "comment": "opts", "options": [c["label"] for c in spec["choices"]], "default": spec["default"]}
    return {**_script_for(spec), "options": PART4 if spec["part"] == 4 else _script_for(spec)["options"]}


@pytest.fixture
def story(scheduled, monkeypatch):
    node, seen = _fake_cli()
    monkeypatch.setattr(jobs, "_node", node)
    monkeypatch.setattr(jobs, "script", _story_script)
    monkeypatch.setattr(instagram, "comments", lambda media: [{"user": "ann", "text": "b"}, {"user": "bob", "text": "B!"}])
    return scheduled, seen


def _posted_part4(slot):
    """Episode 0 part 4, posted at `slot`, with the hero made."""
    job = {"id": "adv-part4", "kind": "episode0", "spec": {"kind": "episode0", "part": 4, "hero": {"cls": "rogue", "look": 0}},
           "script": _story_script({"part": 4}), "series": True, "publish": True, "voice": False, "status": "done",
           "publish_at": slot.isoformat(), "results": {"instagram": {"ok": True, "media_id": "m4"}}}
    jobs.save(job)
    campaign.note_episode0(job["spec"])
    return job


def test_the_first_arc_runs_from_after_episode0_to_tuesday(story):
    slot = datetime(2026, 10, 27, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)  # a Tuesday
    jobs.save({"id": "adv-part1", "kind": "episode0", "spec": {"kind": "episode0", "part": 1}, "series": True,
               "status": "done", "publish_at": slot.isoformat(), "results": {}})
    e = campaign.expected()
    assert (e["start_date"], e["days"]) == ("2026-10-31", 4)
    assert e["links_from"][0]["id"] == "episode0" and e["links_from"][0]["options"][1]["recap"] == "You chose to pick the old lock."

    assert campaign.accept(ARC)["ok"]
    e = campaign.expected()
    assert (e["start_date"], e["days"]) == ("2026-11-04", 7)  # Wednesday to Tuesday from now on
    assert [lf["id"] for lf in e["links_from"]] == ["the-whisper"] and "gate-lock" in e["known_ids"]


def test_an_arc_for_the_same_days_needs_replace_and_must_not_have_started(story):
    assert campaign.accept(ARC)["ok"]
    again = campaign.accept({**ARC, "title": "Again"})
    assert not again["ok"] and again["conflict"]
    assert campaign.accept({**ARC, "title": "Again"}, replace=True)["ok"] and campaign.arcs()[0]["title"] == "Again"
    campaign.save_state({**campaign.state(), "history": [{"node": "gate-lock"}]})
    assert "started playing" in campaign.accept(ARC, replace=True)["problems"][0]


def test_arc_endpoint_returns_every_problem(client, story, monkeypatch):
    monkeypatch.setattr(jobs, "_node", _fake_cli(["gate-lock: 95% to succeed", "day 2: needs 1-3 nodes, has 4"])[0])
    r = client.post("/adventure/arc", json=ARC, headers=AUTH)
    assert r.status_code == 422 and len(r.json()["detail"]["problems"]) == 2
    assert r.json()["detail"]["expected"]["links_from"][0]["id"] == "episode0"


def test_state_endpoint_has_what_the_routine_needs(client, story):
    _posted_part4(datetime(2030, 3, 7, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc))
    r = client.get("/adventure/state", headers=AUTH).json()
    assert r["state"]["hero"] == {"cls": "rogue", "look": 0} and r["next_arc"]["start_date"] == "2030-03-08"
    assert "Childe Rowland" in r["season_bible"] and r["example_arc"]["id"] == ARC["id"]
    assert r["vocab"]["hero"]["cls"] == "rogue" and r["voice"]["budget"] == settings.adventure_voice_budget


def test_dice_are_fair_looking_and_the_same_every_time():
    a, proof = campaign.dice(3, "gate-lock")
    assert a == campaign.dice(3, "gate-lock")[0] and proof == "1:3:gate-lock"
    assert all(1 <= d <= 20 for d in a) and a != campaign.dice(4, "gate-lock")[0]
    rolls = [campaign.dice(i, "x")[0][0] for i in range(400)]
    assert set(rolls) == set(range(1, 21))


def test_episode0_hands_over_to_the_story_and_the_story_follows_the_votes(story, discord):
    (rendered, posted), seen = story
    campaign.accept(ARC)
    slot = datetime(2030, 3, 7, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    part4 = _posted_part4(slot)
    first = jobs._book_next(part4)
    assert first["kind"] == "story" and "no arc" not in discord[-1][0]

    jobs.tick(datetime.fromisoformat(first["publish_at"]) - timedelta(minutes=60))
    ready = jobs.get(first["id"])
    assert ready["status"] == "scheduled", ready.get("error")
    assert ready["votes"]["pick"] == 1 and ready["node"] == "gate-lock" and ready["spec"]["ep"] == 1
    assert ready["spec"]["recap"]["line"] == "You chose to pick the old lock."
    assert ready["dice"]["rolled"] == campaign.dice(1, "gate-lock")[0]
    assert campaign.state()["ep"] == 0  # nothing is remembered until it posts

    jobs.tick(datetime.fromisoformat(first["publish_at"]))
    s = campaign.state()
    assert jobs.get(first["id"])["status"] == "done" and s["ep"] == 1 and s["node"] == "gate-lock"
    assert s["history"][0]["votes"] == [0, 2, 0]

    second = [j for j in jobs.recent() if j.get("from_job") == first["id"]][0]
    jobs.tick(datetime.fromisoformat(second["publish_at"]) - timedelta(minutes=60))
    second = jobs.get(second["id"])
    gate_lock = next(n for n in ARC["nodes"] if n["id"] == "gate-lock")
    assert second["node"] == gate_lock["choices"][1]["next"] and second["spec"]["ep"] == 2
    assert second["spec"]["recap"]["line"] == gate_lock["choices"][1]["recap"]


def test_no_arc_fails_loudly_and_retries_when_one_arrives(client, story, discord):
    slot = datetime.now(timezone.utc) + timedelta(minutes=30)
    part4 = _posted_part4(slot - timedelta(days=1))
    job = jobs._book_next(part4)
    assert "no arc says where" in discord[-1][0]
    jobs.tick(datetime.fromisoformat(job["publish_at"]) - timedelta(minutes=60))
    failed = jobs.get(job["id"])
    assert failed["status"] == "failed" and failed["error_code"] == "no_arc" and "Submit the arc" in discord[-1][0]

    arc = {**ARC, "start_date": campaign.expected()["start_date"]}
    r = client.post("/adventure/arc", json=arc, headers=AUTH)
    assert r.status_code == 201, r.text
    assert r.json()["retried"] == [job["id"]] and jobs.get(job["id"])["status"] == "booked"


def test_a_broken_rule_is_remembered_and_a_fallen_hero_stops_the_story(story, discord, monkeypatch):
    monkeypatch.setattr(campaign, "dice", lambda ep, node: ([3, 3], f"1:{ep}:{node}"))
    arc = json.loads(json.dumps(ARC))
    lock = next(n for n in arc["nodes"] if n["id"] == "gate-lock")
    lock["check"]["harm"] = True  # and the dice say 3
    campaign.accept(arc)
    campaign.save_state({**campaign.state(), "hearts": 1})
    slot = datetime(2030, 3, 7, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    job = jobs._book_next(_posted_part4(slot))
    jobs.tick(datetime.fromisoformat(job["publish_at"]) - timedelta(minutes=60))
    ready = jobs.get(job["id"])
    assert ready["spec"]["dead"] and ready["state_after"]["hearts"] == 0
    jobs.tick(datetime.fromisoformat(job["publish_at"]))
    s = campaign.state()
    assert s["dead"] and s["hearts"] == 0 and "hero has fallen" in discord[-1][0]
    assert not [j for j in jobs.recent() if j.get("from_job") == job["id"]]


def test_a_broken_rule_is_remembered(story):
    arc = json.loads(json.dumps(ARC))
    lock = next(n for n in arc["nodes"] if n["id"] == "gate-lock")  # where B leads
    lock["choices"][1]["breaks"] = "eat"
    campaign.accept(arc)
    slot = datetime(2030, 3, 7, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    first = jobs._book_next(_posted_part4(slot))
    jobs.tick(datetime.fromisoformat(first["publish_at"]) - timedelta(minutes=60))
    jobs.tick(datetime.fromisoformat(first["publish_at"]))
    second = [j for j in jobs.recent() if j.get("from_job") == first["id"]][0]
    jobs.tick(datetime.fromisoformat(second["publish_at"]) - timedelta(minutes=60))
    jobs.tick(datetime.fromisoformat(second["publish_at"]))
    assert campaign.state()["rules_broken"] == [{"rule": "eat", "choice": lock["choices"][1]["label"], "at": "gate-lock", "ep": 2}]


def test_the_first_arc_keeps_the_checks_episode0_promised(story):
    arc = json.loads(json.dumps(ARC))
    next(n for n in arc["nodes"] if n["id"] == "gate-lock")["check"]["dc"] = 13
    r = campaign.accept(arc)
    assert not r["ok"] and r["problems"] == ['gate-lock: Episode 0 promised sleight_of_hand DC 12 for "Pick the old lock"; its check must be exactly that']
