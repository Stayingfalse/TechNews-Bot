"""Renders run below everything else on the box (RENDER_NICE, default 10), so other apps sharing the
server stay responsive while a video is made. It only matters when the CPU is busy: on an idle server
a render takes as long as before. 0 turns it off."""
from __future__ import annotations

import os
import shutil


def level() -> int:
    try:
        return max(0, min(19, int(os.environ.get("RENDER_NICE", "10"))))
    except ValueError:
        return 10


def lower() -> None:
    """Lower this process's priority: for render worker processes, never the web server itself."""
    if level():
        try:
            os.nice(level())
        except OSError:
            pass


def cmd(args: list[str]) -> list[str]:
    """A command line run at render priority (via `nice`, when it's installed)."""
    if level() and shutil.which("nice"):
        return ["nice", "-n", str(level()), *args]
    return args
