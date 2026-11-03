"""Whose request gets done (docs/COLONY_PLAN.md §1a).

Every open request gets a score: likes on the comment count most (the audience votes for what it
wants to see), then days waiting (so everyone's turn comes), then the settler's streak and rank
(loyalty), less a penalty for anyone featured in the last week (so it spreads around). A seeded
fraction breaks ties fairly.

Each day:
- three spotlights get a moment on screen: the top score, a newcomer picked by a fair draw (so
  someone with no likes yet can win), and whoever has waited longest;
- up to GRANT_MAX are granted (their look changes, and they walk in the "granted today" parade);
- everyone else is told their place in the queue.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date, datetime

GRANT_MAX = 25
LIKE_W, WAIT_W, FEATURED_PENALTY, FEATURED_DAYS = 3.0, 2.0, 8.0, 7
RANK_BONUS = {"newcomer": 0, "settler": 1, "veteran": 2, "elder": 3}


def _frac(*key) -> float:
    return int(hashlib.sha256("|".join(map(str, key)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def score(c: dict, st: dict, day: date) -> dict:
    waited = max(0, (day - datetime.fromisoformat(c["at"]).date()).days)
    recent = any((day - date.fromisoformat(d)).days < FEATURED_DAYS for d in st.get("featured_on") or [])
    likes = int(c.get("likes") or 0)
    total = (LIKE_W * likes + WAIT_W * waited + min(st.get("streak", 0), 7) + RANK_BONUS.get(st.get("rank"), 0)
             - (FEATURED_PENALTY if recent else 0) + _frac(day, c["id"]))
    return {"comment_id": c["id"], "key": c["settler"], "handle": "@" + st["handle"], "likes": likes,
            "waited": waited, "recent": recent, "score": round(total, 3)}


def choose(s: dict, requests: list[dict], newcomers: set[str], day: date) -> dict:
    """{"ranked", "spotlights", "grant", "queue"}: one row per settler, scored by their best request
    and carrying all of them (`comment_ids`)."""
    best: dict[str, dict] = {}
    for c in requests:
        st = s["settlers"].get(c["settler"])
        if not st:
            continue
        row = score(c, st, day)
        ids = (best.get(c["settler"]) or {}).get("comment_ids", []) + [c["id"]]
        if c["settler"] not in best or row["score"] > best[c["settler"]]["score"]:
            best[c["settler"]] = row
        best[c["settler"]]["comment_ids"] = ids  # a person brings all their open requests
    ranked = sorted(best.values(), key=lambda r: -r["score"])
    spots, taken = [], set()

    def take(row, why):
        if row and row["key"] not in taken:
            taken.add(row["key"])
            spots.append({**row, "why": why})

    take(ranked[0] if ranked else None, "most wanted (likes, waiting, loyalty)")
    fresh = [r for r in ranked if r["key"] in newcomers and r["key"] not in taken]
    if fresh:  # a fair draw, the same for anyone re-running today
        take(random.Random(f"farside-newcomer-{day.isoformat()}").choice(sorted(fresh, key=lambda r: r["key"])),
             "newcomer draw")
    rest = [r for r in ranked if r["key"] not in taken]
    if rest:
        take(max(rest, key=lambda r: (r["waited"], r["score"])), "waited longest")
    grant = spots + [r for r in ranked if r["key"] not in taken][:GRANT_MAX - len(spots)]
    granted = {r["key"] for r in grant}
    queue = [{"comment_id": r["comment_id"], "handle": r["handle"], "position": i + 1}
             for i, r in enumerate(r for r in ranked if r["key"] not in granted)]
    return {"ranked": ranked, "spotlights": spots, "grant": grant, "queue": queue}
