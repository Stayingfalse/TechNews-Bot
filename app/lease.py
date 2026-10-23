"""Which server process runs the background jobs.

A deploy starts the new server before stopping the old one, and both see the same /data volume.
The newest process takes the lease when it starts; an older one that finds the lease gone stops
scheduling, so the two never claim the same quiz (or post the weekly carousel twice).
"""
from __future__ import annotations

import uuid

from . import store

ME = uuid.uuid4().hex


def claim() -> None:
    store._write("lease.json", {"holder": ME, "at": store.now_iso()})


def held() -> bool:
    """True while this process holds the lease (refreshing it as a heartbeat)."""
    if store._read("lease.json", {}).get("holder") != ME:
        return False
    claim()
    return True
