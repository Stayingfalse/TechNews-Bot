"""Parts drawn by the daily routine (docs/COLONY_PLAN.md §5a): when someone asks for something the
kit hasn't got, Claude draws it as data and the server adds it to the kit, so a request for a dragon
gets a dragon. Every part is checked here: it fits its slot's box, isn't empty, and its colours are
snapped to the house palette so it matches everything else.

A part:
    {"slot": "pet", "id": "dragon",
     "rows": ["..gg..", ".gggg>", "gg.ggg", "g...g."],      facing right, feet on the bottom row
     "frames": [[...rows...]],                              optional second frame (walking, flapping)
     "colors": {"g": "crys2", ">": "gold"}}                 a palette name, a suit/skin/hair name, or #rrggbb

Stored in DATA_DIR/colony/kit/<slot>/<id>.json. A blocked part is never drawn again (settlers who had
it fall back to the default for that slot)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import numpy as np

from ...config import settings
from .art import P, Sprite, hexc

# slot → (max width, max height): the box a part has to fit, in pixels
BOX = {"hat": (9, 8), "held": (7, 9), "back": (5, 10), "carrier": (11, 12), "pet": (10, 8), "costume": (15, 20)}
MAX_NEW_A_DAY = 5
ID = re.compile(r"^[a-z][a-z0-9_]{1,19}$")


def _palette() -> dict[str, np.ndarray]:
    from .kit import HAIRS, SKINS, SUITS
    pal = {k: v for k, v in P.items()}
    pal.update({f"suit_{k}": hexc(v) for k, v in SUITS.items()})
    pal.update({f"skin_{k}": hexc(v) for k, v in SKINS.items()})
    pal.update({f"hair_{k}": hexc(v) for k, v in HAIRS.items() if v})
    return pal


def palette_names() -> list[str]:
    return sorted(_palette())


def snap(color: str) -> np.ndarray | None:
    """A colour name, or #rrggbb snapped to the nearest house colour."""
    pal = _palette()
    if color in pal:
        return pal[color]
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", color or "")
    if not m:
        return None
    c = hexc(m.group(1))
    return min(pal.values(), key=lambda v: float(((v - c) ** 2).sum()))


def _dir(slot: str | None = None) -> Path:
    d = settings.data_dir / "colony" / "kit"
    if slot:
        d = d / slot
    d.mkdir(parents=True, exist_ok=True)
    return d


def check(part: dict, builtin: dict[str, list[str]], taken: set[tuple[str, str]] = frozenset()) -> list[str]:
    """Every problem with a part (empty list = it can be drawn)."""
    slot, pid = part.get("slot"), str(part.get("id", ""))
    w = f"parts.{slot}.{pid}"
    if slot not in BOX:
        return [f"{w}: slot must be one of {', '.join(BOX)}"]
    probs = []
    if not ID.fullmatch(pid):
        probs.append(f"{w}: id is 2-20 lower-case letters, digits or _, starting with a letter")
    if pid in builtin.get(slot if slot != "costume" else "body", []) or (slot, pid) in taken:
        probs.append(f"{w}: there's already a {slot} called {pid!r}: pick another id, or use it")
    colors = part.get("colors") or {}
    bad = [k for k, v in colors.items() if len(k) != 1 or k == "." or snap(str(v)) is None]
    if bad:
        probs.append(f"{w}: colors map single characters (not '.') to a palette name or #rrggbb; bad: {bad}")
    frames = [part.get("rows") or []] + list(part.get("frames") or [])[:1]
    mw, mh = BOX[slot]
    for fi, rows in enumerate(frames):
        f = f"{w}{' frame 2' if fi else ''}"
        if not rows or not all(isinstance(r, str) for r in rows):
            probs.append(f"{f}: rows is a list of strings")
            continue
        if len(rows) > mh or max(len(r) for r in rows) > mw:
            probs.append(f"{f}: at most {mw} wide and {mh} tall for a {slot}")
        used = {ch for r in rows for ch in r if ch != "."}
        missing = used - set(colors)
        if missing:
            probs.append(f"{f}: no colour for {''.join(sorted(missing))!r}")
        filled = sum(ch != "." for r in rows for ch in r)
        if filled < 4:
            probs.append(f"{f}: draw something (at least 4 pixels)")
    return probs


def save(part: dict, by: str | None, on: str) -> dict:
    rec = {**part, "requested_by": by, "added": on, "status": "new"}
    p = _dir(part["slot"]) / f"{part['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1))
    os.replace(tmp, p)
    _cache.clear()
    return rec


_cache: dict[str, dict] = {}


def all_parts() -> dict[tuple[str, str], dict]:
    """Every custom part that may be drawn (not blocked), by (slot, id)."""
    root = _dir()
    if _cache.get("__dir__") != str(root):  # a different data folder (tests): start again
        _cache.clear()
        _cache["__dir__"] = str(root)
    if len(_cache) == 1:
        for p in sorted(root.glob("*/*.json")):
            rec = json.loads(p.read_text())
            if rec.get("status") != "blocked":
                _cache[f"{rec['slot']}/{rec['id']}"] = rec
    return {tuple(k.split("/", 1)): v for k, v in _cache.items() if k != "__dir__"}


def ids(slot: str) -> list[str]:
    return [pid for (s, pid) in all_parts() if s == slot]


def get(slot: str, pid: str) -> dict | None:
    return all_parts().get((slot, pid))


def block(slot: str, pid: str) -> bool:
    p = _dir(slot) / f"{pid}.json"
    if not p.exists():
        return False
    rec = json.loads(p.read_text())
    rec["status"] = "blocked"
    p.write_text(json.dumps(rec, indent=1))
    _cache.clear()
    return True


def sprite(part: dict, frame: int = 0) -> Sprite:
    frames = [part["rows"]] + list(part.get("frames") or [])[:1]
    rows = frames[frame % len(frames)]
    w = max(len(r) for r in rows)
    return Sprite([r.ljust(w, ".") for r in rows], {k: snap(str(v)) for k, v in part["colors"].items()})


def preview(part: dict, path: Path) -> Path:
    """A big picture of the part on its own and on a settler, for the Discord preview."""
    from PIL import Image

    from .art import Canvas
    from .kit import compose
    look = {"costume": part["id"]} if part["slot"] == "costume" else {part["slot"]: part["id"]}
    c = Canvas(48, 26)
    c.rgb[:] = P["sky3"]
    c.sprite(sprite(part, 0), 2, 24 - len(part["rows"]))
    spr = compose(look, 0)
    c.sprite(spr, 22, 24 - spr.h)
    if part["slot"] == "pet":
        c.sprite(sprite(part, 1 if part.get("frames") else 0), 16, 24 - len(part["rows"]))
    c.rect(0, 24, 48, 2, P["grass1"])
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(c.rgb, 0, 255).astype("uint8")).resize((48 * 10, 26 * 10), Image.NEAREST).save(path)
    return path
