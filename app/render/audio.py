"""Synthesised sound effects (no samples, no licensing), mixed over the music bed."""
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
    if kind in ("clock", "tock"):
        # woodblock: a damped resonance plus a click; "tock" is the higher, louder last-seconds version
        f = 1250 if kind == "clock" else 1650
        n = int(SR * 0.09)
        tt = np.arange(n) / SR
        s = np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 2.7 * tt)
        click = rng.standard_normal(n) * _env(n, 0.002)
        return (0.16 if kind == "clock" else 0.24) * (s * _env(n, 0.018) + 0.5 * click)
    if kind == "chime":
        n = int(SR * 0.9)
        out = np.zeros(n)
        for k, f in enumerate((1046.5, 1318.5, 1568.0, 2093.0)):
            i = int(SR * 0.06 * k)
            tt = np.arange(n - i) / SR
            out[i:] += (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * _env(n - i, 0.22)
        return 0.06 * out
    if kind == "reveal":
        s = _sine_sweep(220, 880, 0.12)
        n = len(s)
        return 0.22 * s * np.sin(np.pi * np.arange(n) / n)
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


VOICE_GAIN = 0.95
DUCK = 0.35  # music level while the host talks


def voice_track(lines: list[tuple[float, np.ndarray]], n: int) -> np.ndarray:
    """The host's lines placed in time; a line still going when the next starts is faded out under it."""
    out = np.zeros(n, np.float32)
    lines = sorted(lines, key=lambda x: x[0])
    for k, (t, clip) in enumerate(lines):
        i = int(t * SR)
        end = int(lines[k + 1][0] * SR) if k + 1 < len(lines) else n
        clip = clip[: max(0, min(len(clip), end - i, n - i))].copy()
        fade = min(len(clip), int(0.06 * SR))
        if fade:
            clip[-fade:] *= np.linspace(1, 0, fade)
        if 0 <= i < n:
            out[i:i + len(clip)] += clip
    return out


def duck_envelope(voice: np.ndarray) -> np.ndarray:
    """1 where the host is quiet, DUCK while they talk, with smooth 120 ms edges."""
    win = int(0.12 * SR)
    loud = (np.abs(voice) > 0.01).astype(np.float32)
    held = (_window_mean(loud, 3 * win) > 0).astype(np.float32)  # bridge the gaps between words
    return 1 - (1 - DUCK) * _window_mean(held, win)


def _window_mean(x: np.ndarray, w: int) -> np.ndarray:
    """Centred moving average over w samples (running sums, so long windows stay cheap)."""
    c = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
    lo = np.clip(np.arange(len(x)) - w // 2, 0, len(x))
    hi = np.clip(lo + w, 0, len(x))
    return ((c[hi] - c[lo]) / w).astype(np.float32)


def write_sfx_track(events: list[tuple[float, str]], duration: float, path: str, enabled: bool = True,
                    bed: np.ndarray | None = None, voice: np.ndarray | None = None) -> None:
    """Mix the effects, an optional mono music bed and the optional host voice (both at SR) into a
    stereo WAV. The bed ducks under the voice."""
    rng = np.random.default_rng(3)
    n = int(SR * duration) + SR
    mix = np.zeros(n, np.float32)
    if bed is not None:
        m = min(n, len(bed))
        mix[:m] += bed[:m] * (duck_envelope(voice)[:m] if voice is not None else 1)
    if enabled:
        cache: dict[str, np.ndarray] = {}
        for t, kind in events:
            s = cache.setdefault(kind, _make(kind, rng).astype(np.float32))
            i = int(t * SR)
            j = min(n, i + len(s))
            if 0 <= i < n:
                mix[i:j] += s[: j - i]
    if voice is not None:
        mix += voice[:n] * VOICE_GAIN
    mix = np.tanh(mix * 1.2) * 0.8  # soft limiter
    write_wav(mix, path)


def write_wav(mono: np.ndarray, path: str) -> None:
    pcm = (np.clip(mono, -1, 1) * 32767).astype(np.int16)
    stereo = np.repeat(pcm[:, None], 2, axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
