"""Phase 2: shouted words and the AI writer. The writer adapts the planned node to the comments'
totals; it never receives anything about a viewer; bad answers are corrected or fall back to the
plan; moderation can play the plan's text or write the day again without the shouted word."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.adventure import campaign, jobs, party, shouts, votes, writer
from app.config import settings
from app.publish import instagram

from test_adventure import ARC, _fake_cli, _posted_part4, _story_script  # noqa: F401
from test_adventure import client, ig, scheduled  # noqa: F401

AUTH = {"Authorization": "Bearer test-token"}
NAMES = ["ann_secret", "bob_hidden", "cat_private", "dan_unseen"]
COMMENTS = [
    {"user": "ann_secret", "text": "b sly torch join my real name is Ann Smith"},
    {"user": "bob_hidden", "text": "B! sly, TORCH please"},
    {"user": "cat_private", "text": "a bold torch"},
    {"user": "dan_unseen", "text": "join rope"},
]


# ------------------------------------------------------------------ shouted words


def test_only_listed_words_count_and_only_once_three_people_shout_them():
    assert shouts.shout_of("A sly TORCH!") == "torch" and shouts.shout_of("ropes") == "rope"
    assert shouts.shout_of("b sly join") is None and shouts.shout_of("hello there") is None
    t = votes.tally([{"user": u, "text": x} for u, x in [("a", "torch"), ("b", "torch rope"), ("a", "rope"), ("c", "b torch"),
                                                         ("d", "rope"), ("e", "wolf")]], ["x", "y"])
    assert t["shouts"] == [{"word": "torch", "n": 3, "first": ["a", "b", "c"]}]  # a's second shout and the lone wolf don't count


# ------------------------------------------------------------------ the episode with the writer


@pytest.fixture
def day(scheduled, monkeypatch):
    """Episode 1 about to be made, with the writer switched on and DeepSeek faked: `answers` is the
    queue of replies; `sent` collects every request body."""
    (rendered, posted) = scheduled
    node, seen = _fake_cli()

    def cli(cmd, path, timeout=60):
        payload = json.loads(open(path).read())
        if cmd == "validate-node":
            seen.append((cmd, payload))
            n = payload["node"]
            too_long = [k for k in ("story",) if len(n[k].split()) > 20]
            return {"ok": not too_long, "problems": [f"{k}: at most 20 words" for k in too_long]}
        out = node(cmd, path, timeout)
        if cmd == "resolve":
            n = payload["node"]
            out.update(story=n["story"], hook=n["hook"], after=(n.get("check") or {}).get("success") or n.get("after"))
        return out

    monkeypatch.setattr(jobs, "_node", cli)
    monkeypatch.setattr(jobs, "script", _story_script)
    monkeypatch.setattr(instagram, "comments", lambda media: list(COMMENTS))
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test")
    monkeypatch.setattr(settings, "adventure_writer", "deepseek")
    answers, sent = [], []

    def ask(messages):
        sent.append(json.loads(json.dumps(messages)))
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a, {"prompt_tokens": 1000, "completion_tokens": 100}

    monkeypatch.setattr(writer, "_ask", ask)
    monkeypatch.setattr(party, "moment_slot", lambda ep, size: None)  # no companion moment unless a test asks
    campaign.accept(ARC)
    slot = datetime(2030, 3, 7, 9, 0, tzinfo=settings.tz).astimezone(timezone.utc)
    first = jobs._book_next(_posted_part4(slot))

    def make():
        jobs.tick(datetime.fromisoformat(first["publish_at"]) - timedelta(minutes=60))
        return jobs.get(first["id"])
    return make, answers, sent, rendered, seen


def good(**over):
    out = {"hook": ["THE LOCK", "GIVES"], "story": "You kneel by the lock, torch held high. Brindle steadies the light.",
           "success": "A soft click. Your torch shows the stair.", "fail": "The pick snaps. Your torch gutters.", "after": None}
    return {**out, **over}


def test_the_writer_gets_story_data_and_totals_only_and_its_words_play(day, monkeypatch):
    make, answers, sent, rendered, _ = day
    # the companion with today's moment is Dan's (the only member who'll have one): find its story name
    monkeypatch.setattr(party, "moment_slot", lambda ep, size: 1 if size else None)
    answers.append(good())
    # the party needs Dan's companion's name in the story: make the answer use whatever the server drew
    real_adapt = writer.adapt

    def adapt(node, story, validate):
        name = story["party"][0]["name"] if story["party"] else "Nobody"
        answers[0]["story"] = f"You kneel by the lock, torch high. {name} steadies the light."
        return real_adapt(node, story, validate)

    monkeypatch.setattr(writer, "adapt", adapt)
    job = make()
    assert job["status"] == "scheduled", job.get("error")
    body = json.dumps(sent)
    for name in NAMES + ["Ann Smith", "my real name", "please"]:
        assert name.lower() not in body.lower(), name  # nothing a viewer is or wrote reaches the AI
    inp = job["writer"]["input"]
    assert inp["voices"]["shouted"] == [{"word": "torch", "times": 3}] and inp["voices"]["way"] == "sly"
    assert set(inp["party"][0]) == {"slot", "name", "cls"} and inp["companion_moment"]["slot"] == 1
    assert job["writer"]["status"] == "written" and job["spec"]["story"].startswith("You kneel by the lock, torch high.")
    assert job["spec"]["hook"] == ["THE LOCK", "GIVES"] and job["plan_node"]["story"] != job["spec"]["story"]
    assert job["spec"]["voices"]["shout"] == {"word": "torch", "n": 3}
    assert job["spec"]["credits"]["shouters"] == ["ann_secret", "bob_hidden", "cat_private"]
    assert {i["kind"] for i in job["moderation"]} >= {"shout", "word", "writer", "party", "rolled_by"}
    assert job["votes"]["shouts"] == [{"word": "torch", "n": 3}]  # the episode keeps totals only


def test_a_bad_answer_is_sent_back_with_its_problems_then_the_fix_plays(day):
    make, answers, sent, _, _ = day
    answers += [good(story="You kneel by the old lock and wait.", success="A soft click.", fail="The pick snaps."),  # no torch anywhere
                good(story="You kneel by the lock. " + "word " * 25),  # far too long
                good()]
    job = make()
    w = job["writer"]
    assert [bool(a["problems"]) for a in w["attempts"]] == [True, True, False] and w["status"] == "written"
    assert "torch" in w["attempts"][0]["problems"][0] and "20 words" in w["attempts"][1]["problems"][0]
    assert "Fix these problems" in sent[1][-1]["content"] and w["tokens"] == {"in": 3000, "out": 300}


def test_three_bad_answers_or_a_dead_api_play_the_plan(day, discord):
    make, answers, _, _, _ = day
    answers += [writer.WriterError("DeepSeek 503: busy")]
    job = make()
    assert job["writer"]["status"] == "fallback" and job["spec"]["story"] == job["plan_node"]["story"]
    assert "shout" not in job["spec"]["voices"] and not job["spec"]["credits"].get("shouters")  # the word isn't in the story
    assert any("plan plays as written" in m for m, _ in discord)


def test_without_a_key_the_writer_is_off(day, monkeypatch):
    make, answers, sent, _, _ = day
    monkeypatch.setattr(settings, "deepseek_api_key", "")
    job = make()
    assert job["writer"]["status"] == "off" and not sent and job["spec"]["story"] == job["plan_node"]["story"]


def test_moderation_can_play_the_plan_or_write_again_without_the_word(day, client, discord):
    make, answers, sent, rendered, _ = day
    answers.append(good())
    job = make()
    n = len(rendered)
    answers.append(good(story="You kneel by the lock and listen.", success="A soft click. The stair waits.",
                        fail="The pick snaps. Something stirs."))
    r = client.post(f"/adventure/moderation/{job['id']}/remove?key=word:torch", headers=AUTH)
    assert r.status_code == 200
    job = jobs.get(job["id"])
    assert len(rendered) == n + 1 and job["status"] == "scheduled"
    assert "torch" not in json.dumps(sent[-1]) .split("Today's input as json")[1] and job["writer"]["status"] == "written"
    assert job["spec"]["story"] == "You kneel by the lock and listen." and "shout" not in job["spec"]["voices"]
    assert not job["spec"]["credits"]["shouters"] and not job["credits"]["shouters"]
    r = client.post(f"/adventure/moderation/{job['id']}/remove?key=writer", headers=AUTH)
    job = jobs.get(job["id"])
    assert r.status_code == 200 and job["spec"]["story"] == job["plan_node"]["story"] and len(rendered) == n + 2
    q = client.get("/adventure/moderation", headers=AUTH).json()
    assert q and q[0]["job"] == job["id"]


def test_posting_credits_the_first_shouters_and_the_chronicle_lists_them(day, client):
    make, answers, _, _, _ = day
    answers.append(good())
    job = make()
    jobs.tick(datetime.fromisoformat(job["publish_at"]))
    creds = [c for c in party.load()["credits"] if c["kind"] == "shout"]
    assert [c["user"] for c in creds] == ["ann_secret", "bob_hidden", "cat_private"] and creds[0]["word"] == "torch"
    page = client.get("/chronicle").text
    assert "TORCH" in page and "@bob_hidden" in page and "lantern" in page  # the word list is on the page
    assert "shout" in client.get("/privacy").text
    s = campaign.state()
    assert s["history"][-1]["story"] == job["spec"]["story"] and s["history"][-1]["written"]


def test_trying_the_writer_saves_nothing(day, client):
    make, answers, sent, rendered, _ = day
    answers.append(good())
    before = {j["id"]: j["status"] for j in jobs.recent(20)}
    r = client.post("/adventure/writer/try", json={"pick": 1, "way": "sly", "shouts": ["torch"], "voters": 30}, headers=AUTH)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "written" and out["written"]["story"] == good()["story"] and out["node"] == "gate-lock"
    assert out["input"]["voices"]["rally"] == 2 and out["input"]["voices"]["shouted"] == [{"word": "torch", "times": 3}]
    assert {j["id"]: j["status"] for j in jobs.recent(20)} == before and not rendered and not party.load()["credits"]
    assert client.post("/adventure/writer/try", json={"shouts": ["bananas"]}, headers=AUTH).status_code == 422
    assert client.post("/adventure/writer/try", json={}).status_code == 401
