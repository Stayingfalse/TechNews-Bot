"""Shared fixtures. Every test gets an empty data folder; nothing talks to a real platform."""
from __future__ import annotations

import copy
import json
import os
import queue
import tempfile
from pathlib import Path

# settings are read once at import, so point them somewhere harmless first
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="quizbot-test-"))
os.environ.setdefault("API_TOKEN", "test-token")
os.environ.setdefault("PUBLIC_BASE_URL", "https://quiz.example")
for name in ("ELEVENLABS_API_KEY", "DISCORD_WEBHOOK_URL"):
    os.environ.pop(name, None)

import pytest  # noqa: E402

from app.config import settings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """A fresh /data for each test, an empty job queue, and Discord switched off."""
    from app import notify, pipeline

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(pipeline, "_queue", queue.Queue())
    monkeypatch.setattr(pipeline, "_mine", set())
    sent = []
    monkeypatch.setattr(notify, "send", lambda content, embed=None, attach=None: sent.append((content, attach)))
    return tmp_path


@pytest.fixture
def discord(monkeypatch):
    """What would have gone to Discord: a list of (message, attachment)."""
    from app import notify

    sent = []
    monkeypatch.setattr(notify, "send", lambda content, embed=None, attach=None: sent.append((content, attach)))
    return sent


@pytest.fixture
def quiz() -> dict:
    """The sample quiz spec (5 rounds, ending on an unscramble round)."""
    return copy.deepcopy(json.loads((ROOT / "examples" / "sample_quiz.json").read_text()))


@pytest.fixture
def platforms(monkeypatch):
    """Instagram and YouTube with every network call replaced. `calls` records what was sent;
    set `comments[platform]` to the comments a post should have."""
    from app.publish import instagram, youtube

    state = {"calls": [], "comments": {"instagram": [], "youtube": []}}
    for mod, name in ((instagram, "instagram"), (youtube, "youtube")):
        monkeypatch.setattr(mod, "configured", lambda: True)
        monkeypatch.setattr(mod, "comments", lambda media_id, *a, _n=name, **k: list(state["comments"][_n]))
        monkeypatch.setattr(mod, "reply", lambda cid, text, _n=name: state["calls"].append((_n, "reply", cid, text)) or "r1")
        monkeypatch.setattr(mod, "comment", lambda mid, text, _n=name: state["calls"].append((_n, "comment", mid, text)) or "c1")
    monkeypatch.setattr(instagram, "own_name", lambda: "mediaquiz.daily")
    monkeypatch.setattr(youtube, "connected_identity", lambda: "UC_OWN")
    return state
