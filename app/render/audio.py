"""Synthesised sound effects (no samples, no licensing). The trending sound is added in-app later,
so these are kept subtle; turn the original audio down in the app if they clash."""
from __future__ import annotations

import wave

import numpy as np

SR = 48000


def _env(n: int, decay: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (SR * decay))


def _sine_sweep(f0: float, f1: float, dur: float) -> np.ndarray:
    n = int(SR * dur)
    f = np.linspace(f0, f1, n)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def _lowpass(x: np.ndarray, cutoff: np.ndarray) -> np.ndarray:
    """One-pole low-pass with a per-sample cutoff (Hz)."""
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc = (1 - a[i]) * x[i] + a[i] * acc
        y[i] = acc
    return y


def _make(kind: str, rng: np.random.Generator) -> np.ndarray:
    if kind == "pop":
        s = _sine_sweep(950, 520, 0.07)
        return 0.22 * s * _env(len(s), 0.018)
    if kind == "tick":
        s = _sine_sweep(2400, 2200, 0.018)
        return 0.06 * s * _env(len(s), 0.004)
    if kind in ("whoosh", "swipe"):
        dur = 0.38 if kind == "whoosh" else 0.22
        n = int(SR * dur)
        x = np.linspace(0, 1, n)
        cutoff = 300 + 5200 * np.sin(np.pi * x) ** 2
        s = _lowpass(rng.standard_normal(n), cutoff)
        s *= np.sin(np.pi * x) ** 1.5
        return (0.5 if kind == "whoosh" else 0.35) * s / (np.abs(s).max() + 1e-9) * 0.35
    if kind == "impact":
        s = _sine_sweep(110, 38, 0.5)
        n = len(s)
        click = rng.standard_normal(n) * _env(n, 0.006) * 0.3
        return 0.5 * (s * _env(n, 0.12) + click)
    if kind == "ding":
        n = int(SR * 0.7)
        tt = np.arange(n) / SR
        s = np.sin(2 * np.pi * 1320 * tt) + 0.45 * np.sin(2 * np.pi * 1980 * tt) + 0.2 * np.sin(2 * np.pi * 2640 * tt)
        return 0.09 * s * _env(n, 0.16)
    if kind == "shimmer":
        n = int(SR * 0.6)
        tt = np.arange(n) / SR
        s = sum(np.sin(2 * np.pi * f * tt + k) for k, f in enumerate((2093, 2637, 3136, 4186)))
        return 0.03 * s * np.sin(np.pi * tt / tt[-1])
    raise ValueError(kind)


def write_sfx_track(events: list[tuple[float, str]], duration: float, path: str, enabled: bool = True) -> None:
    rng = np.random.default_rng(3)
    n = int(SR * duration) + SR
    mix = np.zeros(n, np.float32)
    if enabled:
        cache: dict[str, np.ndarray] = {}
        for t, kind in events:
            s = cache.setdefault(kind, _make(kind, rng).astype(np.float32))
            i = int(t * SR)
            j = min(n, i + len(s))
            if 0 <= i < n:
                mix[i:j] += s[: j - i]
    mix = np.tanh(mix * 1.2) * 0.8  # soft limiter
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
