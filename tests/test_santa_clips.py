"""raosanta.uk's screen-recorded tutorials: clips of the site played in a phone."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.render.santa import scenes
from app.render.santa.video import Promo
from app.santa.spec import CLIPS, PromoSpec

WANTED = {"profile-wishlist", "join-workplace", "pick-up", "gifted", "thank-you", "friends-group"}


def spec(*segs, **kw):
    return PromoSpec.model_validate({"id": "clip-test", "format": "tutorial", "voice": False,
                                     "segments": [*segs, {"type": "end"}], **kw})


def test_the_recordings_are_there_at_phone_resolution():
    import json
    import subprocess

    assert WANTED <= {p.stem for p in CLIPS.glob("*.mp4")}
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                          "-of", "json", str(CLIPS / "pick-up.mp4")], capture_output=True, text=True, check=True)
    st = json.loads(out.stdout)["streams"][0]
    assert (st["width"], st["height"]) == (1080, 2400)


def test_unknown_clips_and_backwards_trims_are_refused():
    with pytest.raises(ValidationError, match="no clip 'nope'"):
        spec({"type": "clip", "name": "nope"})
    with pytest.raises(ValidationError, match="end must be after start"):
        spec({"type": "clip", "name": "pick-up", "start": 3, "end": 2})


def test_a_clip_plays_its_trim_and_holds_the_last_frame_for_the_voice():
    s = spec({"type": "clip", "name": "pick-up", "start": 1.0, "end": 4.0, "caption": "Pick up *three*", "say": "x"})
    quiet = Promo(s).scenes[0]
    assert quiet.duration == pytest.approx(scenes.ClipScene.PLAY_AT + 3.0 + 0.5)
    loud = Promo(s, {0: 8.0}).scenes[0]
    assert loud.duration == pytest.approx(scenes.SAY_AT + 8.0 + scenes.BREATH)
    from PIL import Image

    fg = Image.new("RGBA", (1080, 1920))
    loud.render(fg, loud.duration - 0.1)  # long after the clip ended: its last frame, not a blank
    assert fg.getbbox() is not None and loud._frame[0] == int(4.0 * 30)


def test_every_season_tutorial_with_a_clip_stays_under_the_limit():
    from app.santa import season

    items, probs = season.load(season.ROOT / "2026.json")
    assert probs == []
    with_clips = [it["spec"] for it in items if any(s.type == "clip" for s in it["spec"].segments)]
    assert len(with_clips) >= 7
    for s in with_clips:
        lens = {i: len(x.say) / 13.0 for i, x in enumerate(s.segments) if x.say}
        assert Promo(s, lens).duration < 40, s.id
