"""Profile pictures and matching YouTube banners in the videos' game-show style: a sunburst set,
marquee bulbs and one big sign-painted centrepiece.

Avatars (1080×1080) keep everything inside the circle the platforms crop to. Banners (2560×1440)
keep the title and centrepiece inside the 1546×423 strip every device shows; TVs show the rest.

    python render_avatar.py assets/avatars     # writes avatar-*.png, banner-*.png and preview sheets
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from app.render.draw import disc, fit_size, ink_text, mix, slab, text_sprite
from app.render.emoji import emoji_sprite
from app.render.theme import PALETTES, Palette

S = 1080
C = S / 2
RAYS = 18


def _stage(pal: Palette, turn: float) -> Image.Image:
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    dx, dy = xx - C, yy - C
    ang = np.arctan2(dy, dx) + turn
    dist = np.sqrt(dx * dx + dy * dy)
    x = (ang * RAYS / (2 * np.pi)) % 2.0
    edge = 0.05
    ray = np.clip(x / edge, 0, 1) * np.clip((1 - x) / edge, 0, 1) * np.clip((dist - 90) / 200, 0, 1)
    stage, rayc = np.array(pal.stage, np.float32), np.array(pal.ray, np.float32)
    img = stage + (rayc - stage) * ray[..., None]
    img *= (1 - 0.25 * np.clip((dist - 300) / 300, 0, 1))[..., None]  # vignette towards the rim
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")


def _bulb(pal: Palette, lit: bool) -> Image.Image:
    s = 80
    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    if lit:
        d = ImageDraw.Draw(out)
        d.ellipse((s / 2 - 28, s / 2 - 28, s / 2 + 28, s / 2 + 28), fill=pal.bulb + (110,))
        out = out.filter(ImageFilter.GaussianBlur(8))
    d = ImageDraw.Draw(out)
    d.ellipse((s / 2 - 17, s / 2 - 17, s / 2 + 17, s / 2 + 17), fill=pal.ink + (255,))
    d.ellipse((s / 2 - 13, s / 2 - 13, s / 2 + 13, s / 2 + 13), fill=(pal.bulb if lit else mix(pal.ink, pal.bulb, 0.3)) + (255,))
    if lit:
        d.ellipse((s / 2 - 8, s / 2 - 9, s / 2 - 2, s / 2 - 3), fill=(255, 255, 255, 220))
    return out


def _ring(img: Image.Image, pal: Palette) -> None:
    """An ink band near the rim with a ring of bulbs, two in three lit, like the set's marquee."""
    d = ImageDraw.Draw(img)
    r_out, r_in = 492, 440
    d.ellipse((C - r_out, C - r_out, C + r_out, C + r_out), outline=pal.ink + (255,), width=r_out - r_in)
    on, off = _bulb(pal, True), _bulb(pal, False)
    n = 28
    for k in range(n):
        a = 2 * math.pi * k / n - math.pi / 2
        x, y = C + 466 * math.cos(a), C + 466 * math.sin(a)
        b = off if k % 3 == 2 else on
        img.alpha_composite(b, (int(x - b.width / 2), int(y - b.height / 2)))


def _centre(img: Image.Image, sprite: Image.Image, dy: float = 0) -> None:
    img.alpha_composite(sprite, (int(C - sprite.width / 2), int(C - sprite.height / 2 + dy)))


def _question(pal: Palette) -> Image.Image:
    """A huge sign-painted question mark."""
    return ink_text("?", "sign", 560, pal.sign, pal.ink, 12, 22)


def _score(pal: Palette) -> Image.Image:
    """'5/5' on the answer podium."""
    label = ink_text("5/5", "sign", 220, pal.paper, pal.ink, 9, 14)
    card = slab(label.width + 90, label.height + 60, pal.hot + (255,), pal.ink, radius=34, border=10, shadow=18).copy()
    card.alpha_composite(label, ((card.width - label.width) // 2, (card.height - label.height) // 2))
    return card.rotate(-6, resample=Image.BICUBIC, expand=True)


def _timer(pal: Palette) -> Image.Image:
    """The split-flap countdown at '05', with its bulb strip."""
    w, h = 250, 330
    out = Image.new("RGBA", (2 * w + 60, h + 120), (0, 0, 0, 0))
    for k, ch in enumerate("05"):
        flap = slab(w, h, pal.ink + (255,), pal.ink, radius=26, border=6, shadow=14).copy()
        d = ImageDraw.Draw(flap)
        d.rectangle((14, flap.height / 2 - 3, flap.width - 14, flap.height / 2 + 3), fill=mix(pal.ink, pal.stage, 0.6) + (255,))
        digit = ink_text(ch, "sign", 250, pal.sign if k else pal.paper, pal.ink, 0, 0)
        flap.alpha_composite(digit, ((flap.width - digit.width) // 2, (flap.height - digit.height) // 2 - 6))
        out.alpha_composite(flap, (k * (w + 40), 0))
    on, off = _bulb(pal, True), _bulb(pal, False)
    for k in range(5):
        b = on if k < 3 else off
        out.alpha_composite(b, (int(out.width / 2 + (k - 2) * 70 - b.width / 2), h + 40))
    return out


def _emoji(pal: Palette) -> Image.Image:
    """The emoji round: a thinking face on a paper disc with a sign-yellow '?' badge."""
    plate = disc(250, pal.paper + (255,), pal.ink, 12, 18).copy()
    face = emoji_sprite("🤔", 300)
    plate.alpha_composite(face, ((plate.width - face.width) // 2 - 6, (plate.height - face.height) // 2 - 6))
    badge = disc(78, pal.sign + (255,), pal.ink, 9, 10).copy()
    q = ink_text("?", "sign", 110, pal.ink, pal.ink, 0, 0)
    badge.alpha_composite(q, ((badge.width - q.width) // 2 - 4, (badge.height - q.height) // 2 - 4))
    out = Image.new("RGBA", (plate.width + 60, plate.height + 40), (0, 0, 0, 0))
    out.alpha_composite(plate, (0, 20))
    out.alpha_composite(badge, (out.width - badge.width, 0))
    return out


DESIGNS = [  # name, palette, centrepiece, sunburst turn
    ("question", "teatime", _question, 0.0),
    ("score", "primetime", _score, 0.12),
    ("timer", "jackpot", _timer, 0.05),
    ("emoji", "bingo", _emoji, 0.17),
]


BW, BH = 2560, 1440
SAFE_BW, SAFE_BH = 1546, 423  # shown on every device


def _wide_stage(pal: Palette, turn: float) -> Image.Image:
    """The sunburst across the banner, centred on the safe strip."""
    lw, lh = BW // 2, BH // 2  # half resolution, scaled up
    yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32) * 2
    dx, dy = xx - BW / 2, yy - BH / 2
    ang = np.arctan2(dy, dx) + turn
    dist = np.sqrt(dx * dx + dy * dy)
    x = (ang * 26 / (2 * np.pi)) % 2.0
    ray = np.clip(x / 0.05, 0, 1) * np.clip((1 - x) / 0.05, 0, 1) * np.clip((dist - 160) / 300, 0, 1)
    stage, rayc = np.array(pal.stage, np.float32), np.array(pal.ray, np.float32)
    img = stage + (rayc - stage) * ray[..., None]
    img *= (1 - 0.3 * np.clip((dist - 700) / 800, 0, 1))[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").resize((BW, BH), Image.BILINEAR).convert("RGBA")


def banner(pal_name: str, make, turn: float, handle: str = "@mediaquiz.daily") -> Image.Image:
    pal = PALETTES[pal_name]
    img = _wide_stage(pal, turn)
    cx, cy = BW / 2, BH / 2
    # marquee bulb rows framing the strip every device shows
    on, off = _bulb(pal, True), _bulb(pal, False)
    d = ImageDraw.Draw(img)
    for y in (cy - SAFE_BH / 2 - 34, cy + SAFE_BH / 2 + 34):
        d.rectangle((0, y - 26, BW, y + 26), fill=pal.ink + (255,))
        for k, x in enumerate(range(20, BW, 70)):
            b = off if k % 3 == 2 else on
            img.alpha_composite(b, (int(x - b.width / 2), int(y - b.height / 2)))
    # left: the avatar's centrepiece; right: the show's name and when it's on
    piece = make(pal)
    scale = 360 / max(piece.height, piece.width * 0.75)
    piece = piece.resize((int(piece.width * scale), int(piece.height * scale)), Image.LANCZOS)
    left = cx - SAFE_BW / 2 + 40
    img.alpha_composite(piece, (int(left), int(cy - piece.height / 2)))
    tx = left + piece.width + 60
    tw = cx + SAFE_BW / 2 - tx - 20
    title = "DAILY QUIZ"
    t = ink_text(title, "sign", fit_size(title, "sign", 170, int(tw), 1, 80), pal.sign, pal.ink, 8, 12)
    sub = "A new quiz every day at noon"
    s1 = ink_text(sub, "bold", fit_size(sub, "bold", 64, int(tw), 1, 36), pal.paper, pal.ink, 0, 5)
    h = text_sprite(handle, "semi", 48, mix(pal.paper, pal.stage, 0.25))
    total = t.height + s1.height + h.height - 10
    y = cy - total / 2
    for sprite in (t, s1, h):
        img.alpha_composite(sprite, (int(tx), int(y)))
        y += sprite.height - 5
    return img


def avatar(pal_name: str, make, turn: float) -> Image.Image:
    pal = PALETTES[pal_name]
    img = _stage(pal, turn)
    _centre(img, make(pal), dy=-6)
    _ring(img, pal)
    return img


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, pal, make, turn in DESIGNS:
        img = avatar(pal, make, turn).convert("RGB")
        img.save(out / f"avatar-{name}.png")
        tiles.append(img)
    # preview: each as the platforms show it (a circle), large and at feed-comment size
    sheet = Image.new("RGB", (len(tiles) * 300, 400), (245, 245, 245))
    mask = Image.new("L", (280, 280), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 279, 279), fill=255)
    small = Image.new("L", (56, 56), 0)
    ImageDraw.Draw(small).ellipse((0, 0, 55, 55), fill=255)
    for k, t in enumerate(tiles):
        sheet.paste(t.resize((280, 280), Image.LANCZOS), (k * 300 + 10, 10), mask)
        sheet.paste(t.resize((56, 56), Image.LANCZOS), (k * 300 + 122, 320), small)
    sheet.save(out / "avatars-preview.png")
    banners = []
    for name, pal, make, turn in DESIGNS:  # same name as the avatar it goes with
        b = banner(pal, make, turn).convert("RGB")
        b.save(out / f"banner-{name}.jpg", quality=90)  # YouTube takes up to 6 MB
        banners.append(b)
    sheet = Image.new("RGB", (2 * 660, 2 * 380), (245, 245, 245))
    for k, b in enumerate(banners):
        sheet.paste(b.resize((640, 360), Image.LANCZOS), ((k % 2) * 660 + 10, (k // 2) * 380 + 10))
    sheet.save(out / "banners-preview.png")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/avatars")
