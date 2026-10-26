"""Render an adventure video in the background: script → voice → Node renderer → Discord preview.

Jobs are small JSON files in DATA_DIR/adventure/jobs. One adventure render runs at a time."""
from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .. import notify, store
from ..config import settings
from . import voice

log = logging.getLogger(__name__)
_render_lock = threading.Lock()


def _jobs_dir() -> Path:
    d = settings.data_dir / "adventure" / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(job: dict) -> None:
    p = _jobs_dir() / f"{job['id']}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1))
    tmp.replace(p)


def get(job_id: str) -> dict | None:
    p = _jobs_dir() / f"{job_id}.json"
    return json.loads(p.read_text()) if p.exists() else None


def recent(limit: int = 20) -> list[dict]:
    files = sorted(_jobs_dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    return [json.loads(f.read_text()) for f in files]


def _node(*args: str, timeout: int = 900) -> dict:
    """Run the renderer CLI; it prints a one-line JSON summary on stdout."""
    env = {**os.environ, "ADVENTURE_CACHE": str(settings.data_dir / "adventure" / "maps")}
    cmd = ["node", "--import", "tsx", "packages/renderer/src/cli.ts", *args]
    r = subprocess.run(cmd, cwd=settings.adventure_dir, env=env, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr.strip().splitlines() or ["renderer failed"])[-1][:500])
    return json.loads(r.stdout.strip().splitlines()[-1])


def script(spec: dict) -> dict:
    """The voice-over script for a spec (also validates the spec)."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        return _node("script", fh.name, timeout=60)
    finally:
        os.unlink(fh.name)


def submit(spec: dict, use_voice: bool = True) -> dict:
    job = {"id": f"adv-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}", "kind": spec.get("kind"), "spec": spec,
           "voice": use_voice, "status": "queued", "created_at": store.now_iso()}
    job["script"] = script(spec)  # fails fast on a bad spec
    save(job)
    threading.Thread(target=_run, args=(job,), daemon=True, name=f"adventure-{job['id']}").start()
    return job


def _run(job: dict) -> None:
    try:
        with _render_lock:
            _work(job)
    except Exception as e:
        log.exception("adventure job %s failed", job["id"])
        job.update(status="failed", error=str(e)[:1000])
        save(job)
        notify.send(f":warning: **Adventure**: `{job['id']}` failed: {e}")


def _work(job: dict) -> None:
    spec, text = job["spec"], job["script"]["text"]
    audio: list[str] = []
    if job["voice"]:
        job["status"] = "voicing"
        save(job)
        try:
            mp3, align, made = voice.clip(text)
            try:
                mp3, align = voice.tighten(mp3, align, settings.adventure_max_pause)
            except Exception:  # long pauses are better than no video
                log.exception("adventure voice: could not shorten pauses")
            audio = ["--audio", str(mp3), "--align", str(align)]
            job["voice_clip"] = {"file": mp3.name, "chars": len(text), "new": made, "month_spent": voice.spent()}
        except voice.OutOfBudget as e:
            job["voice_clip"] = {"skipped": str(e)}  # goes out without narration
    job["status"] = "rendering"
    save(job)
    settings.videos_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{job['id']}-{secrets.token_urlsafe(8)}"
    out = settings.videos_dir / f"{stem}.mp4"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        workers = str(max(1, min(os.cpu_count() or 1, int(os.environ.get("RENDER_WORKERS", "4")))))
        summary = _node(fh.name, "--out", str(out), "--workers", workers, *audio)
    finally:
        os.unlink(fh.name)
    url = f"{settings.public_base_url}/media/{out.name}"
    job.update(status="done", video=out.name, video_url=url, render=summary, finished_at=store.now_iso())
    save(job)
    vc = job.get("voice_clip") or {}
    said = (f"voice {vc['chars']} chars ({'new' if vc.get('new') else 'cached'}; {vc['month_spent']}/{settings.adventure_voice_budget} this month)"
            if "chars" in vc else f"no voice ({vc.get('skipped', 'off')})")
    notify.send(f":crossed_swords: **Adventure preview** `{job['id']}`: Episode 0 part {spec.get('part')}, "
                f"{summary['duration']:.1f}s, rendered in {summary['seconds']:.0f}s, {said}\n{url}", attach=out)
