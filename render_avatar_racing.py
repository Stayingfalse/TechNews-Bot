"""Profile picture options for Sixel Speedway, in the videos' Pit Wall look: navy, the six car
colours, Inter. Everything sits inside the circle Instagram crops to.

    python render_avatar_racing.py assets/avatars/racing   # avatar-*.png and a preview sheet
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from app.racing import tracks
from app.render.racing.themes.base import fit_track, font, point_at
from app.render.racing.themes.pitwall import COLOURS, NAVY, PANEL, WHITE, YELLOW

S = 1080
C = S / 2
CARS = ["red", "green", "yellow", "blue", "magenta", "cyan"]
SEED = 43  # a generated Grand Prix circuit that fills a square nicely


def base() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (S, S), NAVY)
    d = ImageDraw.Draw(im)
    for k in range(0, S, 60):  # the videos' faint broadcast grid
        d.line([(k, 0), (k, S)], fill=(14, 19, 40))
        d.line([(0, k), (S, k)], fill=(14, 19, 40))
    return im, d


def car(d, x: float, y: float, r: float, colour: str, no: int | None = None) -> None:
    d.ellipse([x - r, y - r, x + r, y + r], fill=COLOURS[colour], outline=WHITE, width=max(4, int(r / 6)))
    if no:
        ink = NAVY if colour in ("green", "yellow", "cyan") else WHITE
        d.text((x, y + 2), str(no), font=font("black", int(r * 1.15)), fill=ink, anchor="mm")


def track_mark() -> Image.Image:
    """A generated circuit with the six cars chasing round it."""
    im, d = base()
    pts = fit_track(tracks.generate("gp", SEED).pts, (170, 170, 910, 910))
    for x, y in pts:  # a run of discs: smooth edges where a very wide line would be ragged
        d.ellipse([x - 55, y - 55, x + 55, y + 55], fill=(40, 48, 84))
    for x, y in pts:
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(150, 160, 200))
    x, y, a = point_at(pts, 0)
    nx, ny = -math.sin(a), math.cos(a)
    d.line([(x - 52 * nx, y - 52 * ny), (x + 52 * nx, y + 52 * ny)], fill=WHITE, width=16)
    for j, c in enumerate(CARS):
        x, y, _ = point_at(pts, 0.06 + j * 0.065)
        car(d, x, y, 58, c)
    return im


def monogram() -> Image.Image:
    """SS in heavy type over a racing stripe, the six colours underneath."""
    im, d = base()
    d.rounded_rectangle([250, 300, 830, 640], 40, fill=PANEL)
    d.text((C, 470), "SS", font=font("black", 330), fill=WHITE, anchor="mm")
    d.rectangle([250, 600, 830, 640], fill=YELLOW)
    for j, c in enumerate(CARS):
        x = 300 + j * 96
        d.rounded_rectangle([x, 690, x + 76, 760], 14, fill=COLOURS[c])
    return im


def tower() -> Image.Image:
    """A timing tower: six cars in order, the way every race video shows them."""
    im, d = base()
    for j, c in enumerate(["cyan", "yellow", "red", "green", "magenta", "blue"]):
        y = 250 + j * 98
        d.rounded_rectangle([230, y, 850, y + 84], 18, fill=PANEL if j % 2 else (28, 36, 66))
        d.text((290, y + 42), str(j + 1), font=font("mono-bold", 58), fill=YELLOW if j == 0 else WHITE, anchor="mm")
        d.rounded_rectangle([350, y + 14, 372, y + 70], 6, fill=COLOURS[c])
        d.rounded_rectangle([400, y + 30, 400 + [420, 360, 330, 300, 270, 230][j], y + 54], 12, fill=(70, 80, 120))
    return im


def roundel() -> Image.Image:
    """The game's money, §, as a race-number roundel, ringed by the six cars."""
    im, d = base()
    d.ellipse([290, 290, 790, 790], fill=YELLOW)
    d.text((C, C + 10), "§", font=font("black", 360), fill=NAVY, anchor="mm")
    for j, c in enumerate(CARS):
        a = -math.pi / 2 + (j + 0.5) * 2 * math.pi / 6 + math.pi / 6
        car(d, C + 335 * math.cos(a), C + 335 * math.sin(a), 52, c)
    return im


OPTIONS = {"track": track_mark, "monogram": monogram, "tower": tower, "roundel": roundel}


def circle(img: Image.Image, size: int) -> Image.Image:
    """How it looks cropped to a circle at `size` px, on Instagram's dark background."""
    small = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    out = Image.new("RGB", (size, size), (0, 0, 0))
    out.paste(small, (0, 0), mask)
    return out


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    made = {}
    for name, fn in OPTIONS.items():
        made[name] = fn()
        made[name].save(out / f"avatar-{name}.png")
    sheet = Image.new("RGB", (len(made) * 340 + 20, 520), (0, 0, 0))
    d = ImageDraw.Draw(sheet)
    for i, (name, img) in enumerate(made.items()):
        x = 20 + i * 340
        sheet.paste(circle(img, 300), (x, 20))
        sheet.paste(circle(img, 110), (x, 350))  # profile header size
        sheet.paste(circle(img, 44), (x + 130, 383))  # next to a comment
        d.text((x, 480), name, font=font("semi", 28), fill=(200, 205, 230))
    sheet.save(out / "avatars-preview.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "assets/avatars/racing")
