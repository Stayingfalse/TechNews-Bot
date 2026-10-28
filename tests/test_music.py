"""The music library: the bundled CC0 tracks, uploads that replace them, and the switch that leaves them out."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.render import music

AUTH = {"Authorization": "Bearer test-token"}


def test_every_bundled_track_is_listed_with_its_licence():
    tracks = sorted(p.name for p in music.BUNDLED.glob("*.ogg"))
    licences = (music.BUNDLED / "LICENSES.md").read_text()
    assert len(tracks) >= 20
    assert tracks == sorted(re.findall(r"\| `([^`]+\.ogg)` \|", licences))  # no track without a source


def test_library_adds_the_bundled_tracks_and_an_upload_replaces_one(tmp_path, monkeypatch):
    (tmp_path / "bossa-nova.mp3").write_bytes(b"mine")
    (tmp_path / "my-theme.mp3").write_bytes(b"mine")
    lib = music.library(tmp_path)
    names = [p.name for p in lib]
    assert "my-theme.mp3" in names and "bossa-nova.mp3" in names and "bossa-nova.ogg" not in names
    assert "banana-track.ogg" in names and music.is_bundled(next(p for p in lib if p.name == "banana-track.ogg"))
    assert music.pick("bossa-nova", tmp_path, 1) == tmp_path / "bossa-nova.mp3"
    assert [p.name for p in music.library(tmp_path, bundled=False)] == ["bossa-nova.mp3", "my-theme.mp3"]
    assert music.pick("auto", tmp_path / "empty", 1, bundled=False) == "synth"
    assert music.pick("auto", tmp_path / "empty", 1) in music.library(tmp_path / "empty")


def test_music_endpoints_show_the_source_and_keep_bundled_tracks(monkeypatch):
    c = TestClient(app)
    rows = c.get("/music", headers=AUTH).json()
    assert {r["source"] for r in rows} == {"bundled"}
    assert c.delete("/music/bossa-nova.ogg", headers=AUTH).status_code == 409
    monkeypatch.setattr(settings, "music_bundled", False)
    assert c.get("/music", headers=AUTH).json() == []
