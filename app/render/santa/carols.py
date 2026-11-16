"""Christmas music made in code: public-domain carols on a glockenspiel, over sleigh bells, a soft
bass and a pad. No samples and no licences (the tunes are traditional, or from 1857).

Each carol is a melody of (MIDI note or None for a rest, beats) and one chord per bar. A video picks one by its seed
and a tempo; the tune loops for as long as the video runs, fading out at the end.
"""
from __future__ import annotations

import random

import numpy as np

from ..audio import SR
from ..music import _hz, _place

# chord roots as semitones above C, and whether they're minor
C, D, F, G, A = (0, False), (2, False), (5, False), (7, False), (9, True)

CAROLS: dict[str, dict] = {
    # James Lord Pierpont, 1857: the chorus
    "jingle-bells": {"beats": 4, "melody": [
        (76, 1), (76, 1), (76, 2), (76, 1), (76, 1), (76, 2), (76, 1), (79, 1), (72, 1.5), (74, 0.5), (76, 4),
        (77, 1), (77, 1), (77, 1.5), (77, 0.5), (77, 1), (76, 1), (76, 1), (76, 0.5), (76, 0.5),
        (76, 1), (74, 1), (74, 1), (76, 1), (74, 2), (79, 2),
        (76, 1), (76, 1), (76, 2), (76, 1), (76, 1), (76, 2), (76, 1), (79, 1), (72, 1.5), (74, 0.5), (76, 4),
        (77, 1), (77, 1), (77, 1), (77, 1), (77, 1), (76, 1), (76, 1), (76, 0.5), (76, 0.5),
        (79, 1), (79, 1), (77, 1), (74, 1), (72, 4)],
        "chords": [C, C, C, C, F, C, D, G, C, C, C, C, F, C, G, C]},
    # traditional Welsh
    "deck-the-halls": {"beats": 4, "melody": [
        (79, 1.5), (77, 0.5), (76, 1), (74, 1), (72, 1), (74, 1), (76, 1), (72, 1),
        (74, 0.5), (76, 0.5), (77, 0.5), (74, 0.5), (76, 1.5), (74, 0.5), (72, 1), (71, 1), (72, 2)] * 2,
        "chords": [C, C, G, C] * 2},
    # traditional English (3/4, from the pickup)
    "we-wish-you": {"beats": 3, "melody": [
        (None, 2), (67, 1),
        (72, 1), (72, 0.5), (74, 0.5), (72, 0.5), (71, 0.5), (69, 1), (69, 1), (69, 1),
        (74, 1), (74, 0.5), (76, 0.5), (74, 0.5), (72, 0.5), (71, 1), (67, 1), (67, 1),
        (76, 1), (76, 0.5), (77, 0.5), (76, 0.5), (74, 0.5), (72, 1), (69, 1), (67, 0.5), (67, 0.5),
        (69, 1), (74, 1), (71, 1), (72, 3)],
        "chords": [G, C, F, D, G, A, F, G, C]},
}


def _tone(f: float, dur: float, partials, attack: float, decay: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    s = sum(a * np.sin(2 * np.pi * f * k * t) for k, a in partials)
    return (s * np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)).astype(np.float32)


GLOCK = [(1, 1.0), (2.76, 0.32), (5.4, 0.12)]  # a struck bar's inharmonic partials
PAD = [(1, 1.0), (2, 0.45), (3, 0.2)]
BASS = [(1, 1.0), (2, 0.3)]


def check(name: str) -> None:
    """Every carol's melody fills its bars exactly (a typo shifts the whole tune)."""
    c = CAROLS[name]
    total = sum(b for _, b in c["melody"])
    assert total == c["beats"] * len(c["chords"]), f"{name}: {total} beats for {len(c['chords'])} bars"


def carol(duration: float, seed: int, name: str | None = None) -> tuple[np.ndarray, str]:
    """(mono samples at SR, the carol's name)."""
    rng = random.Random(seed)
    name = name or rng.choice(sorted(CAROLS))
    c = CAROLS[name]
    beat = 60 / rng.choice([132, 138, 144]) if c["beats"] == 4 else 60 / rng.choice([150, 160])
    bar = beat * c["beats"]
    tune_len = bar * len(c["chords"])
    n = int(SR * (duration + 1))
    out = np.zeros(n, np.float32)
    noise = np.random.default_rng(seed)
    bell_n = int(SR * 0.07)
    bell = np.diff(noise.standard_normal(bell_n).astype(np.float32), prepend=0)
    bell *= np.exp(-np.arange(bell_n) / (SR * 0.016)).astype(np.float32)
    cache: dict = {}

    def note(kind, m, dur, partials, attack, decay):
        key = (kind, m, round(dur, 3))
        if key not in cache:
            cache[key] = _tone(_hz(m), dur, partials, attack, decay)
        return cache[key]

    start = 0.0
    while start < duration:
        t = start
        for m, beats in c["melody"]:
            if m is not None:  # None: a rest
                _place(out, t, note("glock", m + 12, min(beats * beat + 0.4, 2.0), GLOCK, 0.002, 0.45), 0.16)
            t += beats * beat
        for k, (root, minor) in enumerate(c["chords"]):
            t0 = start + k * bar
            chord = [48 + root, 48 + root + (3 if minor else 4), 48 + root + 7]
            for m in chord:
                _place(out, t0, note("pad", m + 12, bar, PAD, 0.3, 2.2), 0.03)
            for b in range(c["beats"]):
                m = chord[0] - 12 if b % 2 == 0 else chord[2] - 12
                _place(out, t0 + b * beat, note("bass", m, beat * 0.9, BASS, 0.005, 0.25), 0.22)
                for h in (0, 0.5):  # sleigh bells on the eighths, accented on the beat
                    _place(out, t0 + (b + h) * beat, bell, 0.09 if h == 0 else 0.05)
        start += tune_len

    out = out[: int(SR * duration)]
    fade_in, fade_out = int(SR * 0.2), min(len(out), int(SR * 1.2))
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    return (out / (np.abs(out).max() + 1e-9) * 0.3).astype(np.float32), name
