"""Synth sound for the colony: a slow, warm pad and a few soft effects. No samples, no licensing."""
from __future__ import annotations

import numpy as np

from ..audio import SR, write_wav

TWO_PI = 2 * np.pi


def _tone(freq: float, dur: float, decay: float, wave: str = "sine") -> np.ndarray:
    t = np.arange(int(SR * dur)) / SR
    ph = TWO_PI * freq * t
    x = np.sin(ph) if wave == "sine" else np.sign(np.sin(ph)) * 0.4
    return (x * np.exp(-t / decay)).astype(np.float32)


def pad(duration: float) -> np.ndarray:
    n = int(SR * duration)
    t = np.arange(n) / SR
    out = np.zeros(n, dtype=np.float32)
    chords = [(146.83, 220.0, 277.18), (130.81, 196.0, 261.63), (110.0, 164.81, 220.0), (123.47, 185.0, 246.94)]
    bar = 4.0
    for i, ch in enumerate(chords * int(duration // (bar * len(chords)) + 1)):
        s0 = int(i * bar * SR)
        if s0 >= n:
            break
        seg = t[s0:min(n, s0 + int(bar * 1.3 * SR))] - i * bar
        env = np.clip(seg / 1.2, 0, 1) * np.clip((bar * 1.3 - seg) / 1.2, 0, 1)
        for f in ch:
            for det in (0.997, 1.003):
                out[s0:s0 + len(seg)] += (np.sin(TWO_PI * f * det * seg) * env * 0.045).astype(np.float32)
    lfo = 0.75 + 0.25 * np.sin(TWO_PI * 0.11 * t)
    # a little arpeggio of glassy blips over the top
    for k in range(int(duration * 2)):
        s0 = int(k * 0.5 * SR)
        f = [587.33, 880.0, 739.99, 659.25][k % 4] * (1 if (k // 8) % 2 == 0 else 0.75)
        b = _tone(f, 0.4, 0.12) * 0.03
        out[s0:s0 + len(b)] += b[: max(0, n - s0)]
    return out * lfo.astype(np.float32)


def effect(kind: str) -> np.ndarray:
    if kind == "land":
        t = np.arange(int(SR * 0.5)) / SR
        f = 120 * np.exp(-t * 6) + 40
        thud = np.sin(TWO_PI * np.cumsum(f) / SR) * np.exp(-t * 9)
        noise = np.random.default_rng(3).standard_normal(len(t)) * np.exp(-t * 14) * 0.25
        return ((thud + noise) * 0.5).astype(np.float32)
    if kind == "chime":
        return (_tone(1046.5, 1.2, 0.4) + _tone(1568.0, 1.2, 0.3) * 0.6) * 0.18
    return _tone(1318.5, 0.18, 0.05, "square") * 0.12


def write(spec: dict, path, voice: list | None = None) -> None:
    """The bed and effects, and (if given) the voice lines as (time, samples), with the music
    ducked under them."""
    from ..audio import duck_envelope, voice_track

    n = int(SR * spec["duration"])
    mix = pad(spec["duration"])[:n]
    for at, kind in spec.get("sfx", []):
        fx = effect(kind)
        s0 = int(at * SR)
        mix[s0:s0 + len(fx)] += fx[: max(0, n - s0)]
    if voice:
        v = voice_track(voice, n)
        mix = mix * duck_envelope(v)[: len(mix)] + v * 1.1
    write_wav(np.clip(np.tanh(mix * 1.1) * 0.9, -1, 1), str(path))
