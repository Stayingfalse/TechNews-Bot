"""The colony's state on disk: DATA_DIR/colony/state.json, written atomically, one writer at a time."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from ..config import settings
from . import rules

_lock = threading.RLock()


def _path() -> Path:
    d = settings.data_dir / "colony"
    d.mkdir(parents=True, exist_ok=True)
    return d / "state.json"


def load() -> dict:
    p = _path()
    return {**rules.new_state(), **json.loads(p.read_text())} if p.exists() else rules.new_state()


def save(s: dict) -> None:
    with _lock:
        p = _path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=1))
        os.replace(tmp, p)


def erase(handle: str) -> bool:
    """A privacy request: the settler leaves the colony and every record of them goes."""
    with _lock:
        s = load()
        hit = rules.erase(s, handle)
        if hit:
            save(s)
    from . import inbox

    return bool(inbox.erase(handle)) or hit


def block(handle: str) -> None:
    """Never show this person again (the moderation preview's Block)."""
    with _lock:
        s = load()
        rules.erase(s, handle)
        s["blocked"] = sorted(set(s["blocked"]) | {handle.lstrip("@").lower()})
        save(s)
