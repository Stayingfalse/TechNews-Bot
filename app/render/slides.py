"""Still images made from a quiz, for Instagram Stories and carousel posts."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..spec import QuizSpec
from .draw import blit, fit_size
from .engine import OUTRO, Video
from .scenes import IntroScene, OutroScene, RoundScene, _ribbon, _sticker
from .theme import FPS, SAFE_BOTTOM, SAFE_CX, SAFE_RIGHT, SAFE_TOP, SAFE_W

FEED_CROP = (0, 185, 1080, 1535)  # 4:5, the tallest image a feed carousel takes; keeps the safe area
MAX_ROUNDS = 4  # cover + 4 × (clue, answer) + the score card = 10 slides, Instagram's limit


def _frame(video: Video, t: float) -> Image.Image:
    return video.frame(min(video.n_frames - 1, int(t * FPS))).convert("RGBA")


def _cover_time(video: Video) -> float:
    first = video.scenes[0]
    return first.duration - OUTRO - 0.1 if isinstance(first, IntroScene) else 1.8


def _ribbon_fit(text: str, video: Video, size: int, **kw) -> Image.Image:
    return _ribbon(text, video.pal, fit_size(text, "sign", size, SAFE_W - 80, 1, 20), **kw)


def story_image(spec: QuizSpec, path: Path, brand: str = "") -> Path:
    """Today's title card with 'new quiz' banners: a story that sends followers to the Reel."""
    video = Video(spec.model_copy(update={"intro": "card"}), brand)  # always the title, whatever the Reel opens with
    img = _frame(video, _cover_time(video))
    pal = video.pal
    blit(img, _ribbon_fit("NEW QUIZ OUT NOW", video, 46, fill=pal.sign, color=pal.ink, angle=-4), SAFE_CX, SAFE_TOP + 40)
    blit(img, _ribbon_fit("TAP OUR PROFILE TO PLAY", video, 34, fill=pal.cool, color=pal.ink, angle=3), SAFE_CX, SAFE_BOTTOM + 60)
    img.convert("RGB").save(path, quality=90)
    return path


def carousel_images(spec: QuizSpec, out_dir: Path, stem: str, brand: str = "") -> list[Path]:
    """Cover, then each round's clue and answer, then the score card, as 4:5 JPEGs. A cliffhanger
    is played straight here: the carousel shows every answer."""
    data = spec.model_dump()
    data["rounds"] = [dict(r, cliffhanger=False, ask_comment=False) for r in data["rounds"][:MAX_ROUNDS]]
    data.update(intro="card", pause_hint=False, picked_by=None)
    video = Video(QuizSpec.model_validate(data), brand)
    pal = video.pal
    swipe = _sticker(["SWIPE FOR", "THE ANSWER"], pal, pal.hot, pal.paper, 7)
    shots: list[Image.Image] = []

    cover = _frame(video, _cover_time(video))
    blit(cover, _ribbon_fit("SWIPE TO PLAY", video, 40, fill=pal.sign, color=pal.ink, angle=-3), SAFE_CX, SAFE_BOTTOM - 40)
    shots.append(cover)
    for start, scene in zip(video.starts, video.scenes):
        if isinstance(scene, RoundScene):
            clue = _frame(video, start + scene.CLUE_IN + 1.0)
            blit(clue, swipe, SAFE_RIGHT - 104, 1300 - 4)
            shots += [clue, _frame(video, start + scene.reveal_at + 1.2)]
        elif isinstance(scene, OutroScene):
            shots.append(_frame(video, start + 2.2))

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for k, img in enumerate(shots[:10], 1):
        p = out_dir / f"{stem}-{k:02d}.jpg"
        img.convert("RGB").crop(FEED_CROP).save(p, quality=90)
        paths.append(p)
    return paths
