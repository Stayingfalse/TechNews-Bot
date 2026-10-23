"""Rendering: every round type and opening draws, still images come out the right size, and a
short video encodes end to end (needs ffmpeg)."""
from __future__ import annotations

import copy
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from app.render.engine import Video, render_video
from app.render.slides import carousel_images, story_image
from app.render.theme import FPS, H, W
from app.spec import QuizSpec


def spec(quiz, **changes) -> QuizSpec:
    return QuizSpec.model_validate(dict(copy.deepcopy(quiz), **changes))


@pytest.mark.parametrize("intro", ["card", "quick", "banner"])
def test_every_scene_draws(quiz, intro):
    picked = {"user": "early_bird", "platform": "instagram", "comment_id": "c1", "text": "Disney villains!"}
    q = copy.deepcopy(quiz)
    q["rounds"][-1]["cliffhanger"] = True
    v = Video(spec(q, intro=intro, ask_theme=True, pause_hint=True, picked_by=picked),
              "@mediaquiz.daily", reveal={"answer": "Up", "note": "2009", "shoutouts": ["early_bird"]})
    for start, scene in zip(v.starts, v.scenes):  # the middle of every scene
        frame = v.frame(int((start + scene.duration / 2) * FPS))
        assert frame.size == (W, H)


def test_loop_ending_matches_the_start(quiz):
    v = Video(spec(quiz))
    first = np.asarray(v.frame(0).convert("RGB"), np.int16)
    last = np.asarray(v.frame(v.n_frames - 1).convert("RGB"), np.int16)
    assert np.abs(first - last).mean() < 1.0


def test_story_and_carousel_images(quiz, tmp_path):
    story = Image.open(story_image(spec(quiz, intro="banner"), tmp_path / "story.jpg"))
    assert story.size == (1080, 1920)
    slides = carousel_images(spec(quiz), tmp_path, "c")
    assert len(slides) == 10  # Instagram's limit: cover, 4 × (clue, answer), score card
    assert {Image.open(p).size for p in slides} == {(1080, 1350)}  # 4:5, the tallest a feed takes


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_short_video_encodes(quiz, tmp_path):
    q = copy.deepcopy(quiz)
    q["rounds"] = q["rounds"][:3]
    for r in q["rounds"]:
        r["think"] = 3.0
    out = tmp_path / "v.mp4"
    info = render_video(spec(q, intro="quick"), out, workers=2, cover_path=tmp_path / "c.jpg")
    assert info["voice"] == "off" and info["duration"] > 10
    streams = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(out)],
                             capture_output=True, text=True, check=True).stdout.split()
    assert sorted(streams) == ["audio", "video"]
