"""Pixel-art drawing for the colony: a 180×320 screen (×6 = 1080×1920) over a wider world the
camera pans across, a fixed palette, sprites written as text, ordered dithering, and a light map so
the colony glows at night. All drawn here, no tilesets."""
from __future__ import annotations

import numpy as np

from . import pixfont

W, H, SCALE = 180, 320, 6

# Instagram's caption, buttons and header cover the edges: text and anything that matters stays
# inside this box (screen pixels).
SAFE = (8, 37, 152, 252)  # x0, y0, x1, y1


def hexc(h: str) -> np.ndarray:
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


P = {k: hexc(v) for k, v in {
    # sky, top to horizon (dusk on the far side)
    "sky0": "07061a", "sky1": "100b2e", "sky2": "1a1248", "sky3": "28195e", "sky4": "3d2471",
    "sky5": "5c327f", "sky6": "864585", "sky7": "b65d80", "sky8": "e0806f",
    "star": "fff6e0", "star2": "9ec8ff",
    "ridge0": "2c1c4c", "ridge1": "21163b", "ridge2": "1a1130",
    "grass0": "9b5ce0", "grass1": "6b3aa8", "grass2": "4c2a80",
    "soil0": "3a2850", "soil1": "302143", "soil2": "281b38", "soil3": "20162d", "soil4": "181022",
    "tunnel": "0e0915", "rock": "4a3a63",
    "rim": "a8f2ff", "glass": "2f7088", "hi": "ffffff",
    "warm0": "ffe2a0", "warm1": "ffb45a", "warm2": "ff7a30", "coil": "ff4a24",
    "metal0": "d4d7e0", "metal1": "9aa0b4", "metal2": "60667c", "metal3": "3c4052",
    "wood0": "9a6638", "wood1": "6e4626", "iron": "4a4858",
    "beard": "f4f0e8", "eye": "1a1020",
    "crys0": "62f5e2", "crys1": "f56ad0", "crys2": "b0ff80",
    "planet0": "e3a06a", "planet1": "c9754f", "planet2": "f0c48c", "planet3": "a85a46", "ring": "eed8a8",
    "sun": "fff3d6",
    "ui": "fff6e0", "ink": "140a20", "gold": "ffd23f", "bar": "5ef2a0", "barbg": "2a1d40",
}.items()}

SUITS = ["e8e2d0", "f2a33a", "4fb3a8", "d65a5a", "7aa0e8", "e6d34a", "b07ad6", "9be07a"]
SKINS = ["f1c9a5", "d9a47a", "a86b48", "6e4430"]

BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32) + 0.5) / 16


def bayer(w: int, h: int) -> np.ndarray:
    return np.tile(BAYER, (h // 4 + 1, w // 4 + 1))[:h, :w]


class Canvas:
    def __init__(self, w: int = W, h: int = H):
        self.w, self.h = w, h
        self.rgb = np.zeros((h, w, 3), dtype=np.float32)
        self.world = np.zeros((h, w), dtype=bool)  # pixels the light map applies to
        self.alpha = np.zeros((h, w), dtype=bool)  # pixels drawn on at all
        self._bayer = bayer(w, h)

    def _set(self, ys, xs, world):
        self.world[ys, xs] = world
        self.alpha[ys, xs] = True

    # -- primitives
    def rect(self, x, y, w, h, col, world=True):
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(self.w, int(x + w)), min(self.h, int(y + h))
        if x1 > x0 and y1 > y0:
            self.rgb[y0:y1, x0:x1] = col
            self._set(slice(y0, y1), slice(x0, x1), world)

    def px(self, x, y, col, world=True):
        x, y = int(x), int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            self.rgb[y, x] = col
            self._set(y, x, world)

    def mask(self, m: np.ndarray, x, y, col, world=True, alpha: float = 1.0):
        x, y = int(x), int(y)
        h, w = m.shape
        sx0, sy0 = max(0, -x), max(0, -y)
        sx1, sy1 = min(w, self.w - x), min(h, self.h - y)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        sub = m[sy0:sy1, sx0:sx1]
        ys, xs = slice(y + sy0, y + sy1), slice(x + sx0, x + sx1)
        region = self.rgb[ys, xs]
        if alpha >= 1:
            region[sub] = col
        else:
            region[sub] = region[sub] * (1 - alpha) + np.asarray(col) * alpha
        self.world[ys, xs][sub] = world
        self.alpha[ys, xs][sub] = True

    def dither_mask(self, m: np.ndarray, x, y, col, amount: float, world=True):
        """Paint `col` over `m` on a Bayer pattern covering `amount` (0-1) of it: pixel-art transparency."""
        x, y = int(x), int(y)
        h, w = m.shape
        yy = (np.arange(h) + y) % 4
        xx = (np.arange(w) + x) % 4
        self.mask(m & (BAYER[yy][:, xx] < amount), x, y, col, world)

    def sprite(self, spr: "Sprite", x, y, flip=False, world=True, cols: dict | None = None):
        for key, m in spr.layers.items():
            col = (cols or {}).get(key, spr.cols.get(key))
            if col is None:
                continue
            self.mask(m[:, ::-1] if flip else m, x, y, col, world)

    def text(self, s: str, x, y, col=None, scale=1, outline=True, center=False):
        m = pixfont.mask(s, scale)
        if center:
            x = x - m.shape[1] // 2
        if outline:
            o = _dilate(np.pad(m, scale), scale)
            self.mask(o, x - scale, y - scale, P["ink"], world=False)
        self.mask(m, x, y, P["ui"] if col is None else col, world=False)
        return m.shape[1]

    def disc(self, cx, cy, r) -> tuple[np.ndarray, int, int]:
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        return (xx * xx + yy * yy) <= r * r + r * 0.6, int(cx - r), int(cy - r)

    def paste(self, other: "Canvas", ox: int):
        """Copy what's drawn on `other` (a wider world canvas) in, `ox` world pixels from its left."""
        a = other.alpha[:, ox:ox + self.w]
        self.rgb[a] = other.rgb[:, ox:ox + self.w][a]
        self.world[a] = other.world[:, ox:ox + self.w][a]
        self.alpha |= a

    # -- output
    def light(self, lights: list[tuple], ambient: float, warm=None):
        """Darken the world to `ambient`, brighten around each (x, y, radius, strength), stepped with
        dithering so it stays pixel art, and tint the lit parts warm."""
        warm = P["warm1"] if warm is None else warm
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        L = np.full((self.h, self.w), ambient, dtype=np.float32)
        for (lx, ly, r, s) in lights:
            if lx + r < 0 or lx - r > self.w:
                continue
            d = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / r
            L += np.clip(1 - d, 0, 1) ** 1.6 * s
        steps = 6
        q = np.clip(np.floor(L * steps + self._bayer) / steps, 0, 1.25)
        lit = np.clip(q - ambient, 0, None)[..., None]
        out = self.rgb * np.minimum(q, 1)[..., None] + warm * lit * 0.22
        self.rgb = np.where(self.world[..., None], out, self.rgb)

    def frame(self) -> np.ndarray:
        img = np.clip(self.rgb, 0, 255).astype(np.uint8)
        return img.repeat(SCALE, 0).repeat(SCALE, 1)


def _dilate(m: np.ndarray, r: int) -> np.ndarray:
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


class Sprite:
    """A sprite written as rows of characters; each character is a colour layer."""

    def __init__(self, rows: list[str], cols: dict[str, np.ndarray]):
        w = max(len(r) for r in rows)
        grid = np.array([list(r.ljust(w, ".")) for r in rows])
        self.h, self.w = grid.shape
        self.cols = cols
        self.layers = {k: grid == k for k in set(grid.flat) if k != "."}


def settler(frame: int, suit: str, skin: str) -> Sprite:
    legs = [["..L.L..", "..L.L..", ".BB.BB."],
            ["...L...", "..L.L..", ".B...B."]][frame % 2]
    rows = ["..GGG..",
            ".GhggG.",
            ".GgssG.",
            ".GgsEG.",
            "..GGG..",
            ".PSSSA.",
            ".PSSSA.",
            ".PSSS..",
            "..SSS.."] + legs
    return Sprite(rows, {"G": P["rim"], "g": P["glass"], "h": P["hi"], "s": hexc(skin), "E": P["eye"],
                         "P": P["metal2"], "S": hexc(suit), "A": hexc(suit) * 0.8, "L": hexc(suit) * 0.7,
                         "B": P["metal3"]})


def barrel_elder() -> Sprite:
    rows = ["..GGGGG..",
            ".GhsssgG.",
            ".GsEsEsG.",
            ".GsssssG.",
            ".GWWWWWG.",
            "..GWWWG..",
            ".RRRRRRR.",
            ".rrrrrrr.",
            ".IIIIIII.",
            ".rrrrrrr.",
            ".rrrrrrr.",
            ".IIIIIII.",
            "..rrrrr.."]
    return Sprite(rows, {"G": P["rim"], "g": P["glass"], "h": P["hi"], "s": hexc(SKINS[0]), "E": P["eye"],
                         "W": P["beard"], "R": P["wood1"], "r": P["wood0"], "I": P["iron"]})


CRATE = Sprite(["#####", "#x#x#", "##x##", "#x#x#", "#####"], {"#": P["wood0"], "x": P["wood1"]})

CAPSULE = Sprite(["...MM...",
                  "..MmmM..",
                  ".MmmmmM.",
                  ".MmOOmM.",
                  "MmmOOmmM",
                  "MmmmmmmM",
                  "MddddddM",
                  ".D....D."], {"M": P["metal1"], "m": P["metal0"], "O": P["warm1"], "d": P["metal2"],
                                "D": P["metal3"]})
