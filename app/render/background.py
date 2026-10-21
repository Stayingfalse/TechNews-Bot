"""The set: a flat stage colour, a slowly turning sunburst and a frame of chasing marquee bulbs.

Everything is a pure function of time so frames can be rendered in parallel.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .theme import H, W, Palette

LOW = 2  # sunburst is computed at half resolution
RAYS = 22
BURST_CENTER = (W * 0.46, 860)
BULB_STEP = 66
BULB_INSET = 30


def _mix(a, b, x):
    return tuple(int(p + (q - p) * x) for p, q in zip(a, b))


class Background:
    def __init__(self, pal: Palette, seed: int = 7):
        self.pal = pal
        self.spin = 3.0 + (seed % 5) * 0.4  # degrees per second
        self.phase = (seed % 360) * math.pi / 180
        lw, lh = W // LOW, H // LOW
        yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32)
        dx, dy = xx * LOW - BURST_CENTER[0], yy * LOW - BURST_CENTER[1]
        self.angle = np.arctan2(dy, dx)
        dist = np.sqrt(dx * dx + dy * dy)
        # rays fade into the stage near the centre and darken a touch towards the corners
        self.core = np.clip((dist - 120) / 260, 0, 1)
        self.shade = 1 - 0.22 * np.clip((dist - 700) / 900, 0, 1)
        self.bulbs = self._bulb_positions()
        self.bulb_on, self.bulb_off = self._bulb_sprites()

    def _bulb_positions(self) -> list[tuple[float, float]]:
        x0, y0, x1, y1 = BULB_INSET, BULB_INSET, W - BULB_INSET, H - BULB_INSET
        pts = []
        nx, ny = round((x1 - x0) / BULB_STEP), round((y1 - y0) / BULB_STEP)
        for i in range(nx):
            pts.append((x0 + (x1 - x0) * i / nx, y0))
        for i in range(ny):
            pts.append((x1, y0 + (y1 - y0) * i / ny))
        for i in range(nx):
            pts.append((x1 - (x1 - x0) * i / nx, y1))
        for i in range(ny):
            pts.append((x0, y1 - (y1 - y0) * i / ny))
        return pts

    def _bulb_sprites(self) -> tuple[Image.Image, Image.Image]:
        s = 64
        on = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(on)
        d.ellipse((s / 2 - 22, s / 2 - 22, s / 2 + 22, s / 2 + 22), fill=self.pal.bulb + (90,))
        on = on.filter(ImageFilter.GaussianBlur(7))
        d = ImageDraw.Draw(on)
        d.ellipse((s / 2 - 13, s / 2 - 13, s / 2 + 13, s / 2 + 13), fill=self.pal.ink + (255,))
        d.ellipse((s / 2 - 10, s / 2 - 10, s / 2 + 10, s / 2 + 10), fill=self.pal.bulb + (255,))
        d.ellipse((s / 2 - 6, s / 2 - 7, s / 2 - 1, s / 2 - 2), fill=(255, 255, 255, 220))
        off = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(off)
        d.ellipse((s / 2 - 13, s / 2 - 13, s / 2 + 13, s / 2 + 13), fill=self.pal.ink + (255,))
        d.ellipse((s / 2 - 10, s / 2 - 10, s / 2 + 10, s / 2 + 10), fill=_mix(self.pal.ink, self.pal.bulb, 0.28) + (255,))
        return on, off

    def render(self, t: float, energy: float = 0.0) -> Image.Image:
        """energy 0..1 brightens the rays and lights every bulb (used on cuts and reveals)."""
        rot = self.phase + math.radians(self.spin * t)
        x = ((self.angle + rot) * RAYS / (2 * math.pi)) % 2.0
        # anti-aliased stripe: 1 inside a ray, 0 between rays
        edge = 0.06
        ray = np.clip((x - 0) / edge, 0, 1) * np.clip((1 - x) / edge, 0, 1)
        ray *= self.core
        stage = np.array(self.pal.stage, np.float32)
        ray_col = np.array(_mix(self.pal.ray, self.pal.sign, 0.18 * energy), np.float32)
        img = stage + (ray_col - stage) * ray[..., None]
        img *= self.shade[..., None]
        small = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
        frame = small.resize((W, H), Image.BILINEAR).convert("RGBA")

        chase = int(t * 7)
        all_on = energy > 0.35
        for k, (bx, by) in enumerate(self.bulbs):
            lit = all_on or (k + chase) % 3 == 0
            spr = self.bulb_on if lit else self.bulb_off
            frame.alpha_composite(spr, (int(bx - spr.width / 2), int(by - spr.height / 2)))
        return frame
