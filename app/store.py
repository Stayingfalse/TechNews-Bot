"""Tiny JSON-file persistence on the /data volume: jobs, history and OAuth tokens."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

_lock = threading.RLock()


def _path(name: str) -> Path:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / name


def _read(name: str, default: Any) -> Any:
    p = _path(name)
    if not p.exists():
        return default
    with _lock:
        return json.loads(p.read_text())


def _write(name: str, data: Any) -> None:
    p = _path(name)
    with _lock:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, p)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ jobs

def save_job(job: dict) -> None:
    with _lock:
        jobs = _read("jobs.json", {})
        job["updated_at"] = now_iso()
        jobs[job["id"]] = job
        # keep the last 200
        if len(jobs) > 200:
            for k in sorted(jobs, key=lambda k: jobs[k].get("created_at", ""))[:-200]:
                jobs.pop(k)
        _write("jobs.json", jobs)


def get_job(job_id: str) -> dict | None:
    return _read("jobs.json", {}).get(job_id)


def list_jobs(limit: int = 20) -> list[dict]:
    jobs = list(_read("jobs.json", {}).values())
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return jobs[:limit]


# ------------------------------------------------------------------ history (for avoiding repeats)

def add_history(entry: dict) -> None:
    with _lock:
        hist = _read("history.json", [])
        hist.append(entry)
        _write("history.json", hist[-1000:])


def update_history(job_id: str, platforms: dict) -> None:
    """Record a retry's outcome on the entry the first attempt wrote."""
    with _lock:
        hist = _read("history.json", [])
        for h in hist:
            if h.get("job_id") == job_id:
                h["platforms"] = platforms
        _write("history.json", hist)


def history(limit: int = 60) -> list[dict]:
    return _read("history.json", [])[-limit:]


# ------------------------------------------------------------------ tokens

def get_tokens(provider: str) -> dict | None:
    return _read("tokens.json", {}).get(provider)


def set_tokens(provider: str, data: dict) -> None:
    with _lock:
        all_tokens = _read("tokens.json", {})
        all_tokens[provider] = data
        _write("tokens.json", all_tokens)
        os.chmod(_path("tokens.json"), 0o600)
