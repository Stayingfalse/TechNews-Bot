"""An explainer video, in the quizzes' style, of how the bot uses viewers' comments (for platform app
reviews and to show viewers). Usernames are examples. Real frames from the renderer show what lands
on screen.

    python render_explainer.py out/how-we-use-comments.mp4
"""
from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from app.render import music
from app.render.audio import write_sfx_track
from app.render.background import Background
from app.render.draw import blit, clamp, disc, ease_out_back, ease_out_cubic, fit_size, ink_text, mix, prog, slab, text_sprite, wrap_words
from app.render.engine import Video
from app.render.theme import FPS, H, PALETTES, SAFE_BOTTOM, SAFE_CX, SAFE_TOP, SAFE_W, W, font
from app.spec import QuizSpec

PAL = PALETTES["teatime"]
HANDLE = "@mediaquiz.daily"
SLIDE = 6.0
ROOT = Path(__file__).resolve().parent


# ------------------------------------------------------------------ pieces

def sign(text: str, size: int, color=None) -> Image.Image:
    return ink_text(text, "sign", size, color or PAL.sign, PAL.ink, 4, 8)


def heading(text: str) -> Image.Image:
    return sign(text, fit_size(text, "sign", 78, SAFE_W, 1, 40))


def step_ribbon(n: int) -> Image.Image:
    label = ink_text(f"STEP {n}", "sign", 32, PAL.ink, PAL.ink, 0, 0)
    r = slab(label.width + 50, label.height + 22, PAL.sign + (255,), PAL.ink, radius=8, border=5, shadow=7).copy()
    r.alpha_composite(label, ((r.width - label.width) // 2, (r.height - label.height) // 2))
    return r.rotate(-3, resample=Image.BICUBIC, expand=True)


def paragraph(text: str, size: int = 44, width: int = SAFE_W - 40, color=None) -> Image.Image:
    lines = [" ".join(w for w in ln) for ln in wrap_words(text, "semi", size, width)]
    sprites = [ink_text(ln, "semi", size, color or PAL.paper, PAL.ink, 0, 4) for ln in lines]
    out = Image.new("RGBA", (max(s.width for s in sprites), sum(s.height - 8 for s in sprites) + 8), (0, 0, 0, 0))
    y = 0
    for s in sprites:
        out.alpha_composite(s, ((out.width - s.width) // 2, y))
        y += s.height - 8
    return out


def comment_card(user: str, text: str, width: int = SAFE_W - 40, own: bool = False, mark: str = "") -> Image.Image:
    """A comment as a card in the quiz's style (not a copy of any app's design)."""
    av = 38
    grey = mix(PAL.ink, PAL.paper, 0.45)
    name = text_sprite(user, "bold", 32, PAL.ink)
    size = 38
    lines = wrap_words(text, "semi", size, width - 2 * av - 90)
    body = [text_sprite(" ".join(ln), "semi", size, PAL.ink) for ln in lines]
    h = max(2 * av + 30, name.height + sum(b.height for b in body) + 30)
    card = slab(width, h, (PAL.cool if own else PAL.paper) + (255,), PAL.ink, radius=26, border=5, shadow=8).copy()
    face = disc(av, (PAL.sign if own else PAL.hot) + (255,), PAL.ink, 4, 0)
    initial = ink_text(user.lstrip("@")[0].upper(), "sign", int(av * 1.0), PAL.ink if own else PAL.paper, PAL.ink, 2, 0)
    face.alpha_composite(initial, ((face.width - initial.width) // 2 - 2, (face.height - initial.height) // 2))
    card.alpha_composite(face, (8 + 18, 8 + (h - face.height) // 2))
    x, y = 8 + 18 + face.width + 16, 8 + 14
    card.alpha_composite(name, (x, y))
    y += name.height - 2
    for b in body:
        card.alpha_composite(b, (x, y))
        y += b.height - 4
    if mark:
        badge = disc(30, ((60, 190, 110) if mark == "yes" else (225, 70, 60)) + (255,), PAL.ink, 4, 4).copy()
        d = ImageDraw.Draw(badge)
        c = badge.width / 2 - 2
        if mark == "yes":
            d.line([(c - 13, c + 1), (c - 3, c + 11), (c + 14, c - 10)], fill=(255, 255, 255, 255), width=7)
        else:
            d.line([(c - 11, c - 11), (c + 11, c + 11)], fill=(255, 255, 255, 255), width=7)
            d.line([(c - 11, c + 11), (c + 11, c - 11)], fill=(255, 255, 255, 255), width=7)
        card.alpha_composite(badge, (card.width - badge.width - 20, (card.height - badge.height) // 2))
    return card


def phone(frame: Image.Image, height: int = 980) -> Image.Image:
    """A frame from a quiz video in a rounded frame, as it would play."""
    w = int(height * W / H)
    shot = frame.convert("RGBA").resize((w, height), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, height - 1), 34, fill=255)
    out = slab(w + 24, height + 24, PAL.ink + (255,), PAL.ink, radius=44, border=4, shadow=12).copy()
    out.paste(shot, (12 + 12, 12 + 12), mask)
    return out


def bullets(items: list[str]) -> Image.Image:
    rows = []
    for it in items:
        dot = disc(16, PAL.sign + (255,), PAL.ink, 3, 0)
        txt = ink_text(it, "semi", fit_size(it, "semi", 44, SAFE_W - 120, 1, 30), PAL.paper, PAL.ink, 0, 4)
        row = Image.new("RGBA", (SAFE_W, max(dot.height, txt.height) + 16), (0, 0, 0, 0))
        row.alpha_composite(dot, (10, (row.height - dot.height) // 2))
        row.alpha_composite(txt, (70, (row.height - txt.height) // 2))
        rows.append(row)
    out = Image.new("RGBA", (SAFE_W, sum(r.height for r in rows)), (0, 0, 0, 0))
    y = 0
    for r in rows:
        out.alpha_composite(r, (0, y))
        y += r.height
    return out


# ------------------------------------------------------------------ the slides

def quiz_frames():
    """Real frames: a cliffhanger round, the next day's shout-outs, a viewer-picked title card."""
    base = json.loads((ROOT / "examples" / "sample_quiz.json").read_text())
    cliff = copy.deepcopy(base)
    cliff["rounds"][-1]["cliffhanger"] = True
    v = Video(QuizSpec.model_validate(cliff), HANDLE)
    last = v.scenes[-2]
    cliff_frame = v.frame(int((v.starts[-2] + last.reveal_at + 1.4) * FPS))
    v = Video(QuizSpec.model_validate(base), HANDLE, reveal={"answer": "Toy Story", "note": "", "shoutouts": ["quiz_fan_22", "popcorn.amy"]})
    yesterday = v.frame(int((v.starts[-2] + 3.2) * FPS))
    picked = dict(base, theme="Disney villains", title="You picked it: *Disney* villains!",
                  picked_by={"user": "popcorn.amy", "platform": "instagram", "comment_id": "x", "text": "Disney villains please!"})
    v = Video(QuizSpec.model_validate(picked), HANDLE)
    title = v.frame(int((v.scenes[0].duration - 0.4) * FPS))
    return cliff_frame, yesterday, title


class Slide:
    def __init__(self, items):
        self.items = items  # (sprite, cx, cy, appear_at)

    def draw(self, img: Image.Image, t: float) -> None:
        for sprite, cx, cy, at in self.items:
            p = prog(t, at, 0.45)
            if p <= 0:
                continue
            out = clamp((t - (SLIDE - 0.35)) / 0.35)
            s = ease_out_back(p, 1.8) * (1 - 0.1 * out)
            blit(img, sprite, cx, cy + (1 - ease_out_cubic(p)) * 40, scale=s, alpha=clamp(p * 2) * (1 - out))


def build():
    cliff_frame, yesterday, title = quiz_frames()
    top = SAFE_TOP + 40
    slides = [
        Slide([(sign(HANDLE, 54, PAL.paper), SAFE_CX, top + 140, 0.1),
               (sign("HOW WE USE", 110), SAFE_CX, 760, 0.35),
               (sign("YOUR COMMENTS", 96), SAFE_CX, 880, 0.55),
               (paragraph("The quiz is a game you play in the comments. Here's exactly what the bot does with them."), SAFE_CX, 1120, 0.9)]),
        Slide([(step_ribbon(1), SAFE_CX, top, 0.05), (heading("YOU COMMENT YOUR ANSWER"), SAFE_CX, top + 110, 0.15),
               (phone(cliff_frame, 760), SAFE_CX, 860, 0.4),
               (comment_card("quiz_fan_22", "Toy Story!"), SAFE_CX, 1330, 1.4)]),
        Slide([(step_ribbon(2), SAFE_CX, top, 0.05), (heading("THE BOT CHECKS THE ANSWERS"), SAFE_CX, top + 110, 0.15),
               (paragraph("It reads the public comments under that video through the platform's official API."), SAFE_CX, top + 260, 0.4),
               (comment_card("quiz_fan_22", "Toy Story!", mark="yes"), SAFE_CX, 820, 0.9),
               (comment_card("popcorn.amy", "toy story, easy", mark="yes"), SAFE_CX, 1010, 1.3),
               (comment_card("movie_mike", "Shrek?", mark="no"), SAFE_CX, 1200, 1.7)]),
        Slide([(step_ribbon(3), SAFE_CX, top, 0.05), (heading("SHOUT-OUTS TOMORROW"), SAFE_CX, top + 110, 0.15),
               (phone(yesterday, 800), SAFE_CX, 880, 0.4),
               (paragraph("The first right answers are named in the next video."), SAFE_CX, 1380, 1.4, )]),
        Slide([(step_ribbon(4), SAFE_CX, top, 0.05), (heading("A REPLY UNDER YOUR COMMENT"), SAFE_CX, top + 110, 0.15),
               (comment_card("quiz_fan_22", "Toy Story!"), SAFE_CX, 700, 0.4),
               (comment_card(HANDLE, "You got it! You're in today's quiz", width=SAFE_W - 120, own=True), SAFE_CX + 40, 900, 1.0),
               (paragraph("So you know you made it, with a link to the new video on YouTube."), SAFE_CX, 1180, 1.6)]),
        Slide([(step_ribbon(5), SAFE_CX, top, 0.05), (heading("PICK NEXT WEEK'S THEME"), SAFE_CX, top + 110, 0.15),
               (comment_card("popcorn.amy", "Disney villains please!"), SAFE_CX, top + 260, 0.4),
               (phone(title, 760), SAFE_CX, 1110, 1.1)]),
        Slide([(heading("YOUR DATA"), SAFE_CX, top + 60, 0.1),
               (bullets(["Only public comments under our videos", "Never your messages or profile",
                         "Names leave our records after 90 days", "Opt out or delete any time",
                         "Nothing sold, no ads"]), SAFE_CX, 860, 0.4),
               (sign("quiz.cezz.co.uk/privacy", 52, PAL.paper), SAFE_CX, 1300, 1.3)]),
    ]
    return slides


def render(out: Path) -> None:
    slides = build()
    duration = SLIDE * len(slides)
    bg = Background(PAL, seed=5)
    n = int(duration * FPS)
    with tempfile.TemporaryDirectory() as tmp:
        wav = str(Path(tmp) / "a.wav")
        events = [(k * SLIDE + 0.05, "whoosh") for k in range(len(slides))]
        events += [(k * SLIDE + at, "pop") for k, s in enumerate(slides) for _, _, _, at in s.items]
        write_sfx_track(events, duration, wav, bed=music.synth(duration, 11))
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-i", wav, "-filter_complex", "[1:a]loudnorm=I=-16:TP=-1.5,aresample=48000[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-t", f"{duration:.2f}", "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for i in range(n):
            t = i / FPS
            k = min(len(slides) - 1, int(t // SLIDE))
            frame = bg.render(t, 0.0)
            slides[k].draw(frame, t - k * SLIDE)
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("ffmpeg failed")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "out/how-we-use-comments.mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    render(target)
    print(target)
