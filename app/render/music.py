"""Background music: a track from your own library, or a game-show loop synthesised from the seed.

The library is any .mp3/.m4a/.wav/.ogg/.flac files in MUSIC_DIR (default /data/music). Only add
tracks you have the rights to use on Instagram/YouTube (your own, or royalty-free with a licence
that allows social video). With no library the synth is used, so the bot never needs anything.
"""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np

from .audio import SR

EXTS = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"}


def library(music_dir: Path) -> list[Path]:
    if not music_dir.is_dir():
        return []
    return sorted(p for p in music_dir.iterdir() if p.suffix.lower() in EXTS and p.is_file())


def pick(choice: str, music_dir: Path, seed: int) -> Path | str | None:
    """Returns a library file, "synth", or None for silence. Unknown file names fall back to auto."""
    if choice == "none":
        return None
    if choice == "synth":
        return "synth"
    tracks = library(music_dir)
    if choice != "auto":
        for p in tracks:
            if p.name == choice or p.stem == choice:
                return p
    return random.Random(seed).choice(tracks) if tracks else "synth"


# --------------------------------------------------------------------------- synth

def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _tone(f: float, dur: float, harmonics, attack: float, decay: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    s = sum(a * np.sin(2 * np.pi * f * k * t) for k, a in harmonics)
    env = np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)
    return (s * env).astype(np.float32)


def _place(buf: np.ndarray, at: float, s: np.ndarray, gain: float = 1.0) -> None:
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(s))
    buf[i:j] += gain * s[: j - i]


PROGRESSIONS = [
    [0, 7, 9, 5],  # I V vi IV
    [9, 5, 0, 7],  # vi IV I V
    [0, 9, 5, 7],  # I vi IV V
    [0, 5, 9, 7],  # I IV vi V
]


def synth(duration: float, seed: int) -> np.ndarray:
    """A bouncy, loopable quiz-show bed: kick, clap, hats, bass, plucked arpeggio and a soft pad."""
    rng = random.Random(seed)
    bpm = rng.choice([112, 116, 120, 124, 128])
    beat = 60 / bpm
    root = 48 + rng.choice([0, 2, 3, 5, 7, 8, 10])  # C3..A#3
    prog = rng.choice(PROGRESSIONS)
    arp_shape = rng.choice([[0, 1, 2, 1], [0, 2, 1, 2], [0, 1, 2, 3], [2, 1, 0, 1]])
    n = int(SR * (duration + 1))
    out = np.zeros(n, np.float32)
    nr = np.random.default_rng(seed)

    tk = np.arange(int(SR * 0.3)) / SR
    kick = (np.sin(2 * np.pi * np.cumsum(np.linspace(130, 42, len(tk))) / SR) * np.exp(-tk / 0.09)).astype(np.float32)
    clap_n = int(SR * 0.18)
    clap = (nr.standard_normal(clap_n) * np.exp(-np.arange(clap_n) / (SR * 0.035))).astype(np.float32)
    clap = np.diff(clap, prepend=0)  # crude high-pass
    hat_n = int(SR * 0.05)
    hat = np.diff(nr.standard_normal(hat_n).astype(np.float32) * np.exp(-np.arange(hat_n) / (SR * 0.009)), prepend=0)

    bar = beat * 4
    bars = int(duration / bar) + 2
    cache: dict = {}
    for b in range(bars):
        t0 = b * bar
        deg = prog[b % len(prog)]
        minor = deg in (9, 2, 4)
        chord = [root + deg, root + deg + (3 if minor else 4), root + deg + 7]
        chord.append(chord[0] + 12)
        for k in range(4):  # drums
            _place(out, t0 + k * beat, kick, 0.55)
            _place(out, t0 + k * beat + beat / 2, hat, 0.10)
            if k in (1, 3):
                _place(out, t0 + k * beat, clap, 0.16)
        for k in range(8):  # bass: root on eighths, octave bounce
            m = chord[0] - 12 + (12 if k % 4 == 3 else 0)
            key = ("bass", m)
            s = cache.get(key)
            if s is None:
                s = cache[key] = _tone(_hz(m), beat * 0.48, [(1, 1), (2, 0.35), (3, 0.12)], 0.004, 0.12)
            _place(out, t0 + k * beat / 2, s, 0.30)
        for k in range(8):  # arp in eighths
            m = chord[arp_shape[k % 4]] + 24
            key = ("arp", m)
            s = cache.get(key)
            if s is None:
                s = cache[key] = _tone(_hz(m), beat * 0.6, [(1, 1), (3, 0.3), (5, 0.12)], 0.002, 0.09)
            _place(out, t0 + k * beat / 2, s, 0.10)
        for m in chord[:3]:  # pad
            key = ("pad", m)
            s = cache.get(key)
            if s is None:
                s = cache[key] = _tone(_hz(m + 12), bar, [(1, 1), (2, 0.5), (3, 0.25)], 0.25, 2.5)
            _place(out, t0, s, 0.035)

    out = out[: int(SR * duration)]
    fade_in, fade_out = int(SR * 0.3), int(SR * 1.2)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    peak = np.abs(out).max() + 1e-9
    return (out / peak * 0.32).astype(np.float32)
