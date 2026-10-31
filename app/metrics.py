"""Per-post performance numbers from every platform and every channel, for the dashboard and the
weekly reviews.

Every post (quizzes, adventure episodes, races) is snapshotted at about 1 hour, 24 hours and 7 days
old, and its latest numbers are refreshed every few hours until it is 14 days old. Each is fetched
"as" its own channel, so the right account's token is used. Stored in metrics.json on the /data
volume, keyed by job id.

A post, whichever channel made it, is read the same way (`posts()`): its channel, title, length,
`tags` to compare by, `extra` (the channel's own counts: votes for the adventure, bets for racing)
and per-platform `results`.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from . import channels, store
from .config import settings
from .publish import PUBLISHERS
from .spec import QuizSpec

log = logging.getLogger(__name__)
_lock = threading.Lock()

SNAPSHOTS = {"1h": 1, "24h": 24, "7d": 168}  # name -> hours after posting
REFRESH_HOURS = 4
TRACK_DAYS = 14


def _age_hours(published_at: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(published_at)).total_seconds() / 3600


def posted_jobs() -> list[dict]:
    """Quizzes that went out to at least one platform, newest first."""
    jobs = [j for j in store.list_jobs(200)
            if j.get("status") == "done" and not j.get("dry_run") and j.get("published_at")
            and any(r.get("ok") for r in j.get("results", {}).values())]
    return sorted(jobs, key=lambda j: j["published_at"], reverse=True)


def tags_for(job: dict) -> dict[str, str]:
    """Labels to compare posts by: the routine's own experiment tags plus ones read off the quiz."""
    spec = QuizSpec.model_validate(job["spec"])
    types = sorted({r.type for r in spec.rounds})
    posted = datetime.fromisoformat(job.get("publish_at") or job["published_at"]).astimezone(settings.tz)
    secs = job.get("render", {}).get("duration") or 0
    auto = {
        "theme": spec.theme or "General mix",
        "rounds": str(len(spec.rounds)),
        "format": f"all {types[0]}" if len(types) == 1 else "mixed",
        "slot": posted.strftime("%H:%M"),
        "weekday": posted.strftime("%a"),
        "length": "under 30 s" if secs < 30 else "30-45 s" if secs < 45 else "45 s+",
        "palette": spec.palette,
        "music": str(job.get("render", {}).get("music") or spec.music),
        "test": "yes" if job["id"].startswith("test-") else "no",
        "intro": spec.intro,
        "cliffhanger": "yes" if spec.rounds[-1].cliffhanger else "no",
        "reveals_yesterday": "yes" if job.get("reveal") else "no",
        "ask_comment": "yes" if any(r.ask_comment for r in spec.rounds) else "no",
        "pause_hint": "yes" if spec.pause_hint else "no",
        "ask_theme": "yes" if spec.ask_theme else "no",
        "voice": "yes" if job.get("render", {}).get("voice") == "on" else "no",
        "voice_name": _voice_name(job),
        "picked_theme": "yes" if spec.picked_by else "no",
    }
    return {**auto, **spec.tags}


def _voice_name(job: dict) -> str:
    r = job.get("render", {})
    if r.get("voice") != "on":
        return "none"
    if r.get("voice_name"):
        return r["voice_name"]
    # rendered before voices were named: it spoke with the default voice
    return {v: k for k, v in settings.voices.items()}.get(settings.elevenlabs_voice_id, "default")


def _when(job: dict) -> datetime:
    return datetime.fromisoformat(job.get("publish_at") or job["published_at"]).astimezone(settings.tz)


def _length(secs: float) -> str:
    return "under 30 s" if secs < 30 else "30-45 s" if secs < 45 else "45 s+"


def _posted(job: dict) -> bool:
    return bool(job.get("published_at")) and not job.get("dry_run") and any(
        r.get("ok") for r in (job.get("results") or {}).values())


def _quiz_posts() -> list[dict]:
    out = []
    for job in posted_jobs():
        spec = QuizSpec.model_validate(job["spec"])
        out.append({"id": job["id"], "channel": channels.MAIN, "published_at": job["published_at"],
                    "slot": job.get("slot"), "title": spec.title.replace("*", ""),
                    "duration": job.get("render", {}).get("duration") or 0, "results": job["results"],
                    "tags": tags_for(job), "extra": {},
                    "rounds": [{"type": r.type, "answer": r.answer_text()} for r in spec.rounds]})
    return out


def _adventure_posts() -> list[dict]:
    from .adventure import jobs as adv

    all_jobs = adv.recent(1000)
    votes = {j["votes"]["from_job"]: j["votes"] for j in all_jobs if j.get("votes")}  # counted on the next part
    out = []
    for job in all_jobs:
        if not _posted(job):
            continue
        spec, r, vc = job.get("spec") or {}, job.get("render") or {}, job.get("voice_clip") or {}
        story = spec.get("kind") == "story"
        when = _when(job)
        tags = {
            "kind": "story" if story else "episode0",
            "episode": f"Episode {spec.get('ep')}" if story else f"Episode 0 part {spec.get('part')}",
            "slot": when.strftime("%H:%M"), "weekday": when.strftime("%a"), "length": _length(r.get("duration") or 0),
            "voice": "yes" if vc.get("chars") else "no",
            "hook": job.get("hook_style") or ("title" if story else "episode0"),
            "check": "yes" if spec.get("check") else "no",
            "hero_dies": "yes" if spec.get("dead") else "no",
            "test": "no",
        }
        if job.get("votes"):
            tags["followed_vote"] = job["votes"].get("how", "")
        v = votes.get(job["id"])
        extra = ({"votes": sum(v["counts"]), "voters": v.get("voters", 0), "comments_read": v.get("comments", 0)}
                 if v else {})
        out.append({"id": job["id"], "channel": channels.ADVENTURE, "published_at": job["published_at"],
                    "slot": when.strftime("%Y-%m-%d"), "title": adv._title(job).replace(" part", ", part"),
                    "duration": r.get("duration") or 0, "results": job["results"], "tags": tags, "extra": extra})
    return out


def _racing_posts() -> list[dict]:
    from .racing import jobs as rjobs, races

    out = []
    for job in rjobs.recent(1000):
        if job.get("kind") == "preview" or not _posted(job):
            continue
        r = job.get("render") or {}
        when = _when(job)
        card = races.get(job["card"]) or {}
        ran = races.get(job["run"]) if job.get("run") else None
        tags = {
            "kind": job.get("kind", ""), "theme": job.get("theme", ""),
            "intro": job.get("intro") or "classic",
            "race_format": (ran or {}).get("format") or "none", "card_format": card.get("format") or "",
            "slot": when.strftime("%H:%M"), "weekday": when.strftime("%a"), "length": _length(r.get("duration") or 0),
            "league_table": "yes" if job.get("bonus") else "no", "test": "no",
        }
        extra = {}
        if card.get("status") == "run":  # the bets placed under this post are settled with the card's race
            taken = [b for b in card.get("bets", []) if not b.get("refused")]
            extra = {"bets": len(taken), "bettors": len({b["pid"] for b in taken}), "staked": sum(b["stake"] for b in taken),
                     "new_players": card.get("new_players", 0), "comments_read": card.get("comments_read", 0)}
        title = "Launch: how to play" if job.get("kind") == "launch" else f"Race {job.get('run')} + card for race {job['card']}"
        out.append({"id": job["id"], "channel": channels.RACING, "published_at": job["published_at"],
                    "slot": when.strftime("%Y-%m-%d"), "title": title, "duration": r.get("duration") or 0,
                    "results": job["results"], "tags": tags, "extra": extra, "legacy": job.get("metrics") or {}})
    return out


def posts(channel: str | None = None) -> list[dict]:
    """Posts that went out to at least one platform, newest first; one channel's, or every channel's."""
    makers = {channels.MAIN: _quiz_posts, channels.ADVENTURE: _adventure_posts, channels.RACING: _racing_posts}
    out = []
    for ch, make in makers.items():
        if channel in (None, ch):
            try:
                out += make()
            except Exception:  # one channel's broken record must not hide the others' numbers
                log.exception("metrics: reading %s posts failed", ch)
    return sorted(out, key=lambda p: p["published_at"], reverse=True)


def _fetch(platform: str, job: dict) -> dict:
    """job: a post from posts() (or a quiz job): needs `results` and `published_at`."""
    res = job["results"][platform]
    mod = PUBLISHERS[platform]
    if platform == "instagram":
        return mod.metrics(res["media_id"])
    if platform == "youtube":
        return mod.metrics(res["video_id"], job["published_at"])
    return {"error": "metrics not supported yet"}


def collect(force: bool = False) -> int:
    """Take the snapshots that are due. Returns how many platform posts were updated."""
    data = store._read("metrics.json", {})
    updated = 0
    for post in posts():
        age = _age_hours(post["published_at"])
        if age > TRACK_DAYS * 24 and not force:
            continue
        entry = data.setdefault(post["id"], {})
        for platform, res in post["results"].items():
            if not res.get("ok") or platform not in PUBLISHERS or not PUBLISHERS[platform].configured():
                continue
            rec = entry.setdefault(platform, {"snapshots": {}})
            due = [name for name, h in SNAPSHOTS.items() if age >= h and name not in rec["snapshots"]]
            # numbers a channel took itself before this collected every channel (racing kept 24h/7d)
            for name in list(due):
                old = (post.get("legacy") or {}).get(name)
                if old and platform == "instagram":
                    rec["snapshots"][name] = {**old, "at": old.get("at") or post["published_at"], "age_h": SNAPSHOTS[name]}
                    due.remove(name)
            last = rec.get("latest", {}).get("at")
            stale = not last or _age_hours(last) >= REFRESH_HOURS
            if not (force or due or stale):
                continue
            try:
                with channels.use(post["channel"]):
                    m = _fetch(platform, post)
            except Exception as e:  # one platform failing must not stop the rest
                log.warning("metrics %s %s: %s", post["id"], platform, e)
                m = {"error": str(e)[:200]}
            m["at"] = store.now_iso()
            m["age_h"] = round(age, 1)
            rec["latest"] = m
            for name in due:
                rec["snapshots"][name] = m
            updated += 1
    if updated:
        with _lock:
            store._write("metrics.json", data)
    return updated


def _derived(m: dict, duration: float) -> dict:
    views = m.get("views") or 0
    acts = sum(m.get(k) or 0 for k in ("likes", "comments", "shares", "saves"))
    out = {}
    if views:
        out["engagement_per_1k"] = round(acts / views * 1000, 1)
        out["comments_per_1k"] = round((m.get("comments") or 0) / views * 1000, 1)
    if m.get("avg_watch_s") and duration:
        out["watched_pct"] = round(min(100.0, m["avg_watch_s"] / duration * 100), 1)
    elif m.get("avg_view_pct"):
        out["watched_pct"] = round(m["avg_view_pct"], 1)
    return out


def report(channel: str | None = channels.MAIN) -> list[dict]:
    """Every post of a channel (None: every channel) with its tags, extras and per-platform numbers
    (latest + snapshots), newest first. Quizzes also list their rounds."""
    data = store._read("metrics.json", {})
    out = []
    for post in posts(channel):
        duration = post["duration"]
        platforms = {}
        for p, res in post["results"].items():
            if not res.get("ok"):
                continue
            rec = data.get(post["id"], {}).get(p, {})
            latest = rec.get("latest", {})
            platforms[p] = {"url": res.get("url"), "latest": {**latest, **_derived(latest, duration)},
                            "snapshots": {k: {**v, **_derived(v, duration)} for k, v in rec.get("snapshots", {}).items()}}
        row = {"job_id": post["id"], "channel": post["channel"], "published_at": post["published_at"],
               "slot": post.get("slot"), "title": post["title"], "duration_s": duration}
        if "rounds" in post:
            row["rounds"] = post["rounds"]
        out.append({**row, "tags": post["tags"], "extra": post.get("extra", {}), "platforms": platforms})
    return out


def summary() -> dict:
    """Each channel at a glance: posts, and per platform the median views and averages at 24 hours
    (posts of different ages aren't comparable on their latest numbers)."""
    import statistics

    out = {}
    rows = report(None)
    for ch in channels.registry().values():
        mine = [r for r in rows if r["channel"] == ch.id and r["tags"].get("test") != "yes"]
        per: dict[str, dict] = {}
        for platform in sorted({p for r in mine for p in r["platforms"]}):
            day = [r["platforms"][platform]["snapshots"].get("24h") for r in mine if platform in r["platforms"]]
            day = [d for d in day if d and d.get("views") is not None]
            avg = lambda k: round(statistics.mean(v), 1) if (v := [d[k] for d in day if d.get(k) is not None]) else None
            per[platform] = {"posts_with_24h": len(day),
                             "median_views_24h": statistics.median([d["views"] for d in day]) if day else None,
                             "avg_watched_pct_24h": avg("watched_pct"), "avg_watch_s_24h": avg("avg_watch_s"),
                             "comments_per_1k_24h": avg("comments_per_1k"), "engagement_per_1k_24h": avg("engagement_per_1k"),
                             "total_views_latest": sum((r["platforms"][platform]["latest"].get("views") or 0)
                                                       for r in mine if platform in r["platforms"])}
        out[ch.id] = {"name": ch.name, "kind": ch.kind, "handle": ch.brand_handle, "posts": len(mine),
                      "first_post": mine[-1]["published_at"] if mine else None, "platforms": per}
    return out


def run_forever() -> None:
    from . import lease

    while True:
        try:
            n = collect() if lease.held() else 0
            if n:
                log.info("metrics: updated %d platform posts", n)
        except Exception:
            log.exception("metrics collection failed")
        time.sleep(15 * 60)
