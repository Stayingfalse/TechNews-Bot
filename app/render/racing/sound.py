"""Synth sound for the race videos: no voice, no samples, no licensing.

- engines: one low-passed, detuned saw per car whose pitch follows its speed
- effects: interface blips, start lights, spins, turbos, a blown engine, overtakes, the flag
- a bed: a pulsing synth loop, quieter while the race runs

Themes can tune it through `Theme.sound` (e.g. {"blip": 1800} for the blip's pitch).
"""
from __future__ import annotations

import numpy as np

from ..audio import SR

TWO_PI = 2 * np.pi


def _env(n: int, decay: float) -> np.ndarray:
    return np.exp(-np.arange(n) / (SR * decay)).astype(np.float32)


def _sweep(f0: float, f1: float, dur: float, wave: str = "sine") -> np.ndarray:
    n = int(SR * dur)
    ph = np.cumsum(np.linspace(f0, f1, n)) / SR
    if wave == "square":
        return np.sign(np.sin(TWO_PI * ph)).astype(np.float32)
    return np.sin(TWO_PI * ph).astype(np.float32)


def _smooth(x: np.ndarray, w: int) -> np.ndarray:
    c = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
    return ((c[w:] - c[:-w]) / w).astype(np.float32)


def effect(kind: str, rng: np.random.Generator, tune: dict) -> np.ndarray:
    blip = tune.get("blip", 1600)
    if kind == "blip":
        s = _sweep(blip, blip * 0.95, 0.05, "square")
        return 0.05 * s * _env(len(s), 0.015)
    if kind == "boot":
        s = _sweep(60, 3000, 0.5) * 0.3 + rng.standard_normal(int(SR * 0.5)).astype(np.float32) * 0.2
        return 0.12 * s * np.linspace(0, 1, len(s), dtype=np.float32) ** 2
    if kind == "light":
        s = _sweep(440, 440, 0.18, "square")
        return 0.07 * s * _env(len(s), 0.08)
    if kind == "go":
        s = _sweep(880, 880, 0.45, "square")
        return 0.08 * s * _env(len(s), 0.25)
    if kind == "spin":
        s = _sweep(900, 140, 0.7)
        sq = _smooth(rng.standard_normal(int(SR * 0.7) + 15).astype(np.float32), 16)[: len(s)]
        return (0.12 * s + 0.25 * sq) * _env(len(s), 0.3)
    if kind == "turbo":
        s = _sweep(200, 1400, 0.5, "square")
        return 0.04 * s * np.linspace(0.2, 1, len(s), dtype=np.float32) * _env(len(s), 0.6)
    if kind == "blowup":
        n = int(SR * 0.9)
        boom = _sweep(90, 30, 0.9) * _env(n, 0.25)
        crack = rng.standard_normal(n).astype(np.float32) * _env(n, 0.08)
        return 0.35 * boom + 0.2 * crack
    if kind == "whoosh":
        n = int(SR * 0.3)
        s = _smooth(rng.standard_normal(n + 7).astype(np.float32), 8)[:n]
        return 0.25 * s * np.sin(np.linspace(0, np.pi, n, dtype=np.float32)) ** 2
    if kind in ("flag", "reveal"):
        out = np.zeros(int(SR * 0.9), np.float32)
        for k, f in enumerate((523.3, 659.3, 784.0, 1046.5)):
            s = _sweep(f, f, 0.5, "square") * _env(int(SR * 0.5), 0.15)
            i = int(SR * 0.09 * k)
            out[i:i + len(s)] += s[: len(out) - i]
        return 0.05 * out
    if kind == "pit":  # wheel guns
        out = np.zeros(int(SR * 0.5), np.float32)
        for k in range(4):
            n = int(SR * 0.07)
            s = _sweep(2400, 1800, 0.07, "square") * _env(n, 0.02) + rng.standard_normal(n).astype(np.float32) * 0.3 * _env(n, 0.01)
            i = int(SR * 0.11 * k)
            out[i:i + n] += s
        return 0.05 * out
    if kind == "puncture":
        n = int(SR * 0.6)
        s = _smooth(rng.standard_normal(n + 31).astype(np.float32), 32)[:n]
        return 0.6 * s * _env(n, 0.25) + 0.08 * _sweep(300, 120, 0.6) * _env(n, 0.2)
    if kind == "tangle":
        n = int(SR * 0.5)
        crunch = rng.standard_normal(n).astype(np.float32) * _env(n, 0.06)
        return 0.25 * crunch + 0.15 * _sweep(160, 60, 0.5) * _env(n, 0.15)
    if kind == "jumpstart":
        s = _sweep(220, 220, 0.6, "square")
        return 0.07 * s * _env(len(s), 0.4)
    if kind == "amber":
        s = _sweep(660, 660, 0.12, "square")
        return 0.06 * s * _env(len(s), 0.05)
    if kind == "card":
        s = _sweep(blip * 0.5, blip * 0.75, 0.12, "square")
        return 0.05 * s * _env(len(s), 0.06)
    raise ValueError(kind)


def engines(dist: np.ndarray, start: float, fps: int, total: float, out_at: dict[int, float]) -> np.ndarray:
    """dist: (frames, cars) laps covered. One growling saw per car, pitch from speed."""
    n = int(SR * total)
    out = np.zeros(n, np.float32)
    speed = np.diff(dist, axis=0, prepend=dist[:1]) * fps  # laps/s per frame
    base = np.median(speed[speed > 0]) if (speed > 0).any() else 0.2
    frames_t = start + np.arange(len(dist)) / fps
    i0, i1 = int(start * SR), min(n, int(frames_t[-1] * SR))
    ts = np.arange(i0, i1) / SR
    for j in range(dist.shape[1]):
        rel = np.interp(ts, frames_t, speed[:, j] / base)
        f = 55 + 70 * np.clip(rel, 0, 1.6) + 6 * j  # each car a slightly different note
        ph = np.cumsum(f) / SR
        saw = 2 * (ph % 1) - 1 + 0.5 * (2 * ((ph * 1.01) % 1) - 1)
        amp = 0.035 * np.clip(rel, 0, 1.2)
        out[i0:i1] += _smooth(np.concatenate([saw * amp, np.zeros(11, np.float32)]).astype(np.float32), 12)[: i1 - i0]
    return out


def bed(total: float, seed: int, race: tuple[float, float] | None) -> np.ndarray:
    """A pulsing loop: bass on eighths, a hat, a two-chord pad. Ducks under the race."""
    rng = np.random.default_rng(seed)
    n = int(SR * total)
    out = np.zeros(n, np.float32)
    bpm = int(rng.choice([118, 122, 126]))
    beat = 60 / bpm
    roots = [rng.choice([41, 43, 45]), 0]
    roots[1] = roots[0] + int(rng.choice([3, 5, -2]))
    hat_n = int(SR * 0.04)
    hat = np.diff(rng.standard_normal(hat_n).astype(np.float32), prepend=0) * _env(hat_n, 0.008)
    k = 0
    while k * beat / 2 < total:
        t = k * beat / 2
        root = roots[(k // 16) % 2]
        f = 440 * 2 ** ((root - 69 + (12 if k % 4 == 2 else 0)) / 12)
        s = _sweep(f, f, beat * 0.45, "square") * _env(int(SR * beat * 0.45), 0.08)
        i = int(t * SR)
        m = min(len(s), n - i)
        out[i:i + m] += 0.06 * _smooth(np.concatenate([s, np.zeros(5, np.float32)]), 6)[:m]
        if k % 2 == 1:
            m = min(hat_n, n - i)
            out[i:i + m] += 0.05 * hat[:m]
        k += 1
    if race:
        a, b = race
        ts = np.arange(n) / SR
        duck = 1 - 0.65 * np.clip(np.minimum((ts - a) / 0.5, (b - ts) / 0.5), 0, 1)
        out *= duck.astype(np.float32)
    fade = int(SR * 0.4)
    out[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
    return out


def mix(total: float, events: list[tuple[float, str]], tune: dict, seed: int,
        race: dict | None = None, race_span: tuple[float, float] | None = None) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * total)
    out = bed(total, seed, race_span)
    cache: dict[str, np.ndarray] = {}
    for t, kind in events:
        s = cache.setdefault(kind, effect(kind, rng, tune))
        i = int(t * SR)
        m = min(len(s), n - i)
        if 0 <= i < n and m > 0:
            out[i:i + m] += s[:m]
    if race is not None and race_span:
        out += engines(np.array(race["dist"]), race_span[0], 30, total,
                       {e["car"]: e["t"] for e in race["events"] if e["kind"] == "blowup"})
    peak = float(np.abs(out).max() or 1)
    return out / max(peak, 1.0) * 0.9
