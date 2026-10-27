"""The Dungeon crawl's explainer video: how @dungeoncrawlergram uses viewers' comments (votes), in the
adventure's own look (parchment cards, wax seals, Cinzel and Alegreya). Real stills come from the
adventure renderer; usernames are examples.

    (cd adventure && npm ci)
    python render_explainer_adventure.py out/how-we-use-votes.mp4
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
ADV = ROOT / "adventure"
FONTS = ADV / "fonts"
AUDIO = ADV / "assets" / "audio"
W, H, FPS = 1080, 1920, 30
SLIDE = 6.0
CX, TOP, SAFE_W = 540, 300, 900
HANDLE = "@dungeoncrawlergram"

PAPER = (241, 228, 198)
PAPER_DARK = (222, 203, 160)
INK = (52, 36, 24)
SEAL = (158, 32, 30)
GOLD = (214, 170, 82)
CREAM = (250, 240, 214)
GREEN = (54, 128, 72)
NIGHT = (24, 18, 14)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


# ------------------------------------------------------------------ pieces

def text(s: str, name: str, size: int, color, shadow: bool = True) -> Image.Image:
    f = font(name, size)
    l, t, r, b = f.getbbox(s)
    out = Image.new("RGBA", (r - l + 16, b - t + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    if shadow:
        d.text((8 - l + 3, 8 - t + 4), s, font=f, fill=(0, 0, 0, 170))
    d.text((8 - l, 8 - t), s, font=f, fill=color)
    return out


def fit(s: str, name: str, size: int, width: int) -> int:
    while size > 20 and font(name, size).getlength(s) > width:
        size -= 2
    return size


def title(s: str, size: int = 84, color=GOLD) -> Image.Image:
    return text(s, "Cinzel-Black", fit(s, "Cinzel-Black", size, SAFE_W), color)


def wrap(s: str, name: str, size: int, width: int) -> list[str]:
    f, lines, cur = font(name, size), [], ""
    for w in s.split():
        if cur and f.getlength(f"{cur} {w}") > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur]


def paragraph(s: str, size: int = 44, color=CREAM, width: int = SAFE_W - 40) -> Image.Image:
    rows = [text(ln, "Alegreya-Medium", size, color) for ln in wrap(s, "Alegreya-Medium", size, width)]
    out = Image.new("RGBA", (max(r.width for r in rows), sum(r.height - 10 for r in rows) + 10), (0, 0, 0, 0))
    y = 0
    for r in rows:
        out.alpha_composite(r, ((out.width - r.width) // 2, y))
        y += r.height - 10
    return out


def card(w: int, h: int, fill=PAPER, border=INK) -> Image.Image:
    out = Image.new("RGBA", (w + 16, h + 16), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((10, 12, w + 8, h + 10), 18, fill=(0, 0, 0, 140))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(5)))
    d = ImageDraw.Draw(out)
    d.rounded_rectangle((2, 2, w, h), 18, fill=fill, outline=border, width=4)
    d.rounded_rectangle((12, 12, w - 10, h - 10), 12, outline=PAPER_DARK, width=2)
    return out


def seal(letter: str, r: int = 34, color=SEAL) -> Image.Image:
    out = Image.new("RGBA", (2 * r + 8, 2 * r + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.ellipse((4, 6, 2 * r + 4, 2 * r + 6), fill=(0, 0, 0, 120))
    d.ellipse((2, 2, 2 * r + 2, 2 * r + 2), fill=color, outline=tuple(int(c * 0.6) for c in color), width=4)
    t = text(letter, "Cinzel-Black", int(r * 1.05), CREAM, shadow=False)
    out.alpha_composite(t, (r + 2 - t.width // 2, r + 2 - t.height // 2))
    return out


def comment(user: str, body: str, width: int = SAFE_W - 40, own: bool = False, vote: str = "", dim: bool = False) -> Image.Image:
    """A comment on a parchment card (not a copy of any app's design); `vote` shows what it counted as."""
    name = text(user, "Alegreya-Bold", 34, INK, shadow=False)
    lines = [text(ln, "Alegreya-Medium", 38, INK, shadow=False) for ln in wrap(body, "Alegreya-Medium", 38, width - 260)]
    h = max(120, name.height + sum(l.height - 8 for l in lines) + 30)
    c = card(width, h, fill=(232, 216, 176) if own else PAPER)
    av = seal(user.lstrip("@")[0].upper(), 32, GOLD if own else (92, 70, 52))
    c.alpha_composite(av, (22, (h - av.height) // 2 + 2))
    x, y = 22 + av.width + 16, 16
    c.alpha_composite(name, (x, y))
    y += name.height - 8
    for l in lines:
        c.alpha_composite(l, (x, y))
        y += l.height - 8
    if vote:
        tag = seal(vote, 30, GREEN if vote in "ABC" else (120, 110, 100)) if len(vote) == 1 else text(vote, "Alegreya-Bold", 30, (120, 100, 80), shadow=False)
        c.alpha_composite(tag, (c.width - tag.width - 30, (h - tag.height) // 2 + 2))
    if dim:
        c.putalpha(c.getchannel("A").point(lambda a: int(a * 0.55)))
    return c


def phone(path: Path, height: int = 900) -> Image.Image:
    w = int(height * W / H)
    shot = Image.open(path).convert("RGBA").resize((w, height), Image.LANCZOS)
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, height - 1), 34, fill=255)
    out = Image.new("RGBA", (w + 40, height + 44), (0, 0, 0, 0))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((8, 14, w + 32, height + 38), 44, fill=(0, 0, 0, 170))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
    ImageDraw.Draw(out).rounded_rectangle((4, 4, w + 28, height + 28), 44, fill=(30, 22, 16), outline=GOLD, width=4)
    out.paste(shot, (16, 16), mask)
    return out


def ribbon(s: str) -> Image.Image:
    t = text(s, "Cinzel-Bold", 34, CREAM, shadow=False)
    w, h = t.width + 80, t.height + 26
    out = Image.new("RGBA", (w, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.polygon([(0, 4), (w, 4), (w - 24, h // 2 + 4), (w, h + 4), (0, h + 4), (24, h // 2 + 4)], fill=SEAL)
    out.alpha_composite(t, ((w - t.width) // 2, (h - t.height) // 2 + 4))
    return out


def bullets(items: list[str]) -> Image.Image:
    rows = []
    for it in items:
        s = Image.new("RGBA", (36, 36), (0, 0, 0, 0))
        ImageDraw.Draw(s).ellipse((4, 4, 32, 32), fill=GOLD, outline=INK, width=3)
        t = text(it, "Alegreya-Medium", fit(it, "Alegreya-Medium", 44, SAFE_W - 90), CREAM)
        row = Image.new("RGBA", (SAFE_W, max(s.height, t.height) + 18), (0, 0, 0, 0))
        row.alpha_composite(s, (6, (row.height - s.height) // 2))
        row.alpha_composite(t, (60, (row.height - t.height) // 2))
        rows.append(row)
    out = Image.new("RGBA", (SAFE_W, sum(r.height for r in rows)), (0, 0, 0, 0))
    y = 0
    for r in rows:
        out.alpha_composite(r, (0, y))
        y += r.height
    return out


# ------------------------------------------------------------------ motion

def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def ease(p: float) -> float:
    return 1 - (1 - p) ** 3


class Slide:
    def __init__(self, items):
        self.items = items  # (sprite, cx, cy, appear_at)

    def draw(self, img: Image.Image, t: float) -> None:
        fade_out = clamp((t - (SLIDE - 0.4)) / 0.4)
        for sprite, cx, cy, at in self.items:
            p = clamp((t - at) / 0.5)
            if p <= 0:
                continue
            a = ease(p) * (1 - fade_out)
            s = sprite
            if a < 1:
                s = sprite.copy()
                s.putalpha(sprite.getchannel("A").point(lambda v: int(v * a)))
            y = int(cy + (1 - ease(p)) * 36 - s.height / 2)
            img.alpha_composite(s, (int(cx - s.width / 2), y))


def background(still: Path) -> Image.Image:
    """The dungeon map, blurred and darkened, a little larger than the frame so it can drift."""
    bg = Image.open(still).convert("RGB").resize((W + 120, H + 120), Image.LANCZOS).filter(ImageFilter.GaussianBlur(14))
    dark = Image.new("RGB", bg.size, NIGHT)
    bg = Image.blend(bg, dark, 0.62).convert("RGBA")
    vign = Image.new("L", bg.size, 0)
    ImageDraw.Draw(vign).ellipse((-300, -200, bg.width + 300, bg.height + 200), fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(160))
    black = Image.new("RGBA", bg.size, (0, 0, 0, 255))
    return Image.composite(bg, black, vign)


# ------------------------------------------------------------------ the slides

def stills(tmp: Path) -> dict[str, Path]:
    """Real frames from Episode 0, rendered by the adventure renderer."""
    shots = {"title": ("episode0-part1", 2), "rules": ("episode0-part1", 16), "vote": ("episode0-part1", 38),
             "map": ("episode0-part1", 8), "result": ("episode0-part4", 4), "next": ("episode0-part4", 34)}
    for part in {p for p, _ in shots.values()}:
        ats = ",".join(str(t) for p, t in shots.values() if p == part)
        subprocess.run(["npm", "run", "-s", "render", "--", f"examples/{part}.json", "--png", str(tmp), "--at", ats],
                       cwd=ADV, check=True, capture_output=True)
    return {k: tmp / f"{p.split('-')[1]}-t{float(t):.1f}.png" for k, (p, t) in shots.items()}


def build(shot: dict[str, Path]) -> list[Slide]:
    top = TOP
    return [
        Slide([(text(HANDLE, "Cinzel-Bold", 50, CREAM), CX, top + 60, 0.1),
               (title("HOW WE USE", 104), CX, 700, 0.35),
               (title("YOUR COMMENTS", 92), CX, 820, 0.55),
               (paragraph("The dungeon crawl is a story you steer in the comments. Here's exactly what the bot does with them."), CX, 1080, 0.9)]),
        Slide([(ribbon("STEP 1"), CX, top - 10, 0.05), (title("YOU VOTE A, B OR C", 72), CX, top + 100, 0.15),
               (phone(shot["vote"], 820), CX, 905, 0.4),
               (comment("dice_goblin", "B! goblins all the way"), CX, 1400, 1.5)]),
        Slide([(ribbon("STEP 2"), CX, top - 10, 0.05), (title("8AM: THE VOTES ARE COUNTED", 64), CX, top + 100, 0.15),
               (paragraph("The bot reads the public comments under yesterday's episode through Instagram's official API."), CX, top + 250, 0.4),
               (comment("dice_goblin", "B! goblins all the way", vote="B"), CX, 730, 0.9),
               (comment("mapmaker.jo", "c", vote="C"), CX, 900, 1.2),
               (comment("dice_goblin", "actually A?", vote="1st vote counts", dim=True), CX, 1070, 1.6),
               (comment("quietbard", "this art is lovely", vote="not a vote", dim=True), CX, 1240, 2.0),
               (paragraph("One vote per account: your first. Ties are settled by a fair, fixed draw.", 40), CX, 1440, 2.6)]),
        Slide([(ribbon("STEP 3"), CX, top - 10, 0.05), (title("ONLY THE TOTALS ARE KEPT", 64), CX, top + 100, 0.15),
               (phone(shot["result"], 740), CX, 870, 0.4),
               (paragraph("Your vote is counted, then your comment is let go. Names aren't stored, shown or read out.", 42), CX, 1340, 1.4)]),
        Slide([(ribbon("STEP 4"), CX, top - 10, 0.05), (title("9AM: THE STORY GOES ON", 68), CX, top + 100, 0.15),
               (phone(shot["next"], 820), CX, 905, 0.4),
               (paragraph("The winning choice happens, with a real dice roll, and you vote again.", 42), CX, 1400, 1.4)]),
        Slide([(title("YOUR DATA", 96), CX, top + 60, 0.1),
               (bullets(["Only public comments under our posts", "Your vote is counted; your name isn't kept",
                         "Never your messages or profile", "#optout opts you out of both our channels",
                         "Nothing sold, no ads"]), CX, 860, 0.4),
               (text("quiz.cezz.co.uk/privacy", "Cinzel-Bold", 52, GOLD), CX, 1300, 1.3)]),
    ]


def render(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shot = stills(tmp)
        slides = build(shot)
        bg = background(shot["map"])
        duration = SLIDE * len(slides)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
               "-i", str(AUDIO / "old_tower_inn.mp3"), "-i", str(AUDIO / "dungeon_ambience.ogg"),
               "-filter_complex", f"[1:a]volume=0.55,afade=t=in:d=1,afade=t=out:st={duration - 2}:d=2[m];"
                                  f"[2:a]aloop=loop=-1:size=2e9,volume=0.35[amb];[m][amb]amix=inputs=2:duration=first,"
                                  "loudnorm=I=-18:TP=-1.5,aresample=48000[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-t", f"{duration:.2f}", "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for i in range(int(duration * FPS)):
            t = i / FPS
            k = min(len(slides) - 1, int(t // SLIDE))
            dx, dy = int(60 + 50 * (t / duration - 0.5)), int(60 - 40 * (t / duration - 0.5))
            frame = bg.crop((dx, dy, dx + W, dy + H))
            slides[k].draw(frame, t - k * SLIDE)
            proc.stdin.write(frame.convert("RGB").tobytes())
        proc.stdin.close()
        if proc.wait():
            raise SystemExit("ffmpeg failed")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "out/how-we-use-votes.mp4")
    target.parent.mkdir(parents=True, exist_ok=True)
    render(target)
    print(target)
