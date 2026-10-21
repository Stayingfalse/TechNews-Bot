"""Animated background: drifting colour blobs, a scrolling grid, particles and a vignette.

Everything is a pure function of time so frames can be rendered in parallel.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .theme import H, W, Palette

LOW_W, LOW_H = W // 5, H // 5
GRID = 90


class Background:
    def __init__(self, pal: Palette, seed: int = 7):
        self.pal = pal
        rng = np.random.default_rng(seed)
        yy, xx = np.mgrid[0:LOW_H, 0:LOW_W].astype(np.float32)
        self.xx, self.yy = xx / LOW_W, yy / LOW_H
        self.phase = rng.uniform(0, 2 * math.pi, size=6)
        n = 46
        self.p_xy = rng.uniform(0, 1, size=(n, 2))
        self.p_v = rng.uniform(-0.012, 0.012, size=(n, 2)) + np.array([0, -0.02])
        self.p_r = rng.uniform(1.5, 4.0, size=n)
        self.p_a = rng.uniform(40, 140, size=n)
        self.p_tw = rng.uniform(0, 2 * math.pi, size=n)
        self._grid = self._make_grid()
        self._vignette = self._make_vignette()

    def _make_grid(self) -> Image.Image:
        img = Image.new("RGBA", (W + GRID, H + GRID), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = self.pal.text + (14,)
        for x in range(0, W + GRID, GRID):
            d.line((x, 0, x, H + GRID), fill=c, width=1)
        for y in range(0, H + GRID, GRID):
            d.line((0, y, W + GRID, y), fill=c, width=1)
        return img

    def _make_vignette(self) -> Image.Image:
        yy, xx = np.mgrid[0:LOW_H, 0:LOW_W].astype(np.float32)
        dx, dy = (xx / LOW_W - 0.5) * 1.3, (yy / LOW_H - 0.5)
        d = np.sqrt(dx * dx + dy * dy)
        a = np.clip((d - 0.35) / 0.45, 0, 1) ** 1.6 * 200
        small = Image.fromarray(a.astype(np.uint8), "L").resize((W, H), Image.BICUBIC)
        v = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        v.putalpha(small)
        return v

    def render(self, t: float, energy: float = 0.0) -> Image.Image:
        """energy 0..1 briefly brightens the blobs (used on scene cuts)."""
        ph = self.phase
        bg = np.array(self.pal.bg, np.float32)
        out = np.broadcast_to(bg, (LOW_H, LOW_W, 3)).copy()
        blobs = [
            (0.30 + 0.22 * math.sin(t * 0.37 + ph[0]), 0.28 + 0.12 * math.sin(t * 0.29 + ph[1]), 0.42, self.pal.blob1),
            (0.72 + 0.20 * math.sin(t * 0.31 + ph[2]), 0.70 + 0.14 * math.sin(t * 0.23 + ph[3]), 0.46, self.pal.blob2),
            (0.50 + 0.30 * math.sin(t * 0.19 + ph[4]), 0.50 + 0.25 * math.sin(t * 0.27 + ph[5]), 0.30, self.pal.accent),
        ]
        boost = 1.0 + 0.6 * energy
        for i, (cx, cy, r, col) in enumerate(blobs):
            dx = (self.xx - cx) * 0.5625  # aspect correct (W/H)
            dy = self.yy - cy
            g = np.exp(-(dx * dx + dy * dy) / (r * r * 0.18))
            k = (0.85 if i < 2 else 0.22) * boost
            out += g[..., None] * (np.array(col, np.float32) * k)
        out = np.clip(out, 0, 255).astype(np.uint8)
        frame = Image.fromarray(out, "RGB").resize((W, H), Image.BICUBIC).convert("RGBA")

        off = int((t * 18) % GRID)
        frame.alpha_composite(self._grid.crop((0, off, W, off + H)))

        dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(dots)
        pos = (self.p_xy + self.p_v * t) % 1.0
        tw = 0.6 + 0.4 * np.sin(t * 2.2 + self.p_tw)
        for (px, py), r, a, k in zip(pos, self.p_r, self.p_a, tw):
            x, y = px * W, py * H
            col = self.pal.accent2 + (int(a * k),)
            d.ellipse((x - r, y - r, x + r, y + r), fill=col)
        frame.alpha_composite(dots)

        frame.alpha_composite(self._vignette)
        return frame
