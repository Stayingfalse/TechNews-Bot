"""The colony's rules, done by code (docs/COLONY_PLAN.md §3-4): who has moved in, jobs, streaks and
ranks, recruits, the follower milestones, and what yesterday's shares and saves paid for. Pure
functions over a state dict; no network, no AI. `apply_day` is the only entry point that changes
the state, once per episode day.

A settler is a platform account ("instagram:<id>"), shown by handle. A comment is the dict
`cliffhanger.read_comments` returns: {id, user, uid, text, at, platform}.
"""
from __future__ import annotations

import copy
import re
from datetime import date, timedelta

# jobs: the word to comment, what the settler is drawn doing, the building it pushes up the queue
JOBS = {"farm": "farming", "build": "building", "scout": "scouting", "guard": "on guard", "tinker": "tinkering"}
JOB_WORD = re.compile(r"\b(farm|build|scout|guard|tinker)(?:ing|er|s)?\b", re.I)
MENTION = re.compile(r"(?<![\w.])@([a-z0-9._]{2,30})", re.I)

RANKS = [(0, "newcomer"), (3, "settler"), (7, "veteran"), (14, "elder")]  # streak days → rank

# The build tree: unlocked at a follower count, then paid for in materials (shares), supplies
# (saves) and the colony's own slow work. `job` moves it up the queue when that job is busiest.
BUILDINGS = [
    {"id": "dome", "name": "HABITAT DOME", "followers": 5, "cost": 14, "job": "build"},
    {"id": "condenser", "name": "CONDENSER", "followers": 10, "cost": 30, "job": "tinker"},
    {"id": "greenhouse", "name": "GREENHOUSE", "followers": 25, "cost": 55, "job": "farm"},
    {"id": "workshop", "name": "WORKSHOP", "followers": 40, "cost": 80, "job": "tinker"},
    {"id": "beacon", "name": "BEACON", "followers": 50, "cost": 110, "job": "scout"},
    {"id": "wall", "name": "STORM WALL", "followers": 100, "cost": 160, "job": "guard"},
    {"id": "market", "name": "MARKET", "followers": 250, "cost": 260, "job": "farm"},
    {"id": "district2", "name": "DISTRICT TWO", "followers": 500, "cost": 400, "job": "build"},
    {"id": "spaceport", "name": "SPACEPORT", "followers": 1000, "cost": 650, "job": "scout"},
]
BY_ID = {b["id"]: b for b in BUILDINGS}
SLOW_WORK = 2  # materials a day the colony makes by itself: nothing ever stalls completely
STOCK_CAP = 10  # materials kept while nothing is being built, so a new unlock isn't finished at once
RECRUIT_DAYS = 7  # a tagged friend must comment within this many days to count


def new_state() -> dict:
    return {"day": None, "followers": 0, "settlers": {}, "built": [], "queue": [], "building": None,
            "stock": 0, "pending_mentions": [], "blocked": [], "days": {}}


def key(c: dict) -> str:
    return f"{c.get('platform', 'instagram')}:{c.get('uid') or c['user'].lstrip('@').lower()}"


def rank_for(streak: int) -> str:
    return [r for n, r in RANKS if streak >= n][-1]


def _rank_index(r: str) -> int:
    return [x for _, x in RANKS].index(r)


def _job_in(text: str) -> str | None:
    m = JOB_WORD.search(text or "")
    return m.group(1).lower() if m else None


def apply_day(state: dict, day: date, comments: list[dict], followers: int | None,
              yesterday: dict | None = None, blocked=frozenset()) -> tuple[dict, dict]:
    """Move the colony on to `day` with the comments read since the last day, today's follower
    count (None: couldn't be read, keep the last one) and yesterday's post numbers
    ({"shares", "saves"}). Returns the new state and the day's report, which the episode is
    made from. A day already applied returns its stored report and changes nothing."""
    iso = day.isoformat()
    if iso in state["days"]:
        return state, state["days"][iso]
    s = copy.deepcopy(state)
    prev_day = date.fromisoformat(s["day"]) if s["day"] else None
    gone = set(s["blocked"]) | {b.lower() for b in blocked}
    report = {"day": iso, "arrived": [], "jobs": [], "ranked_up": [], "recruits": [], "left": 0, "joined": 0,
              "unlocked": [], "finished": None, "progress": None, "gained": {}, "featured": []}

    # followers: arrivals and departures as counts (who followed is never known)
    if followers is not None:
        diff = followers - s["followers"]
        report["joined"], report["left"] = max(0, diff), max(0, -diff)
        s["followers"] = followers

    # comments, by settler, in order
    by_key: dict[str, list[dict]] = {}
    for c in sorted(comments, key=lambda c: c["at"]):
        if c["user"].lstrip("@").lower() in gone:
            continue
        by_key.setdefault(key(c), []).append(c)
    tallies = {j: 0 for j in JOBS}
    for k, cs in by_key.items():
        handle = cs[-1]["user"].lstrip("@")
        st = s["settlers"].get(k)
        if st is None:
            st = s["settlers"][k] = {"handle": handle, "joined": iso, "job": None, "rank": "newcomer",
                                     "streak": 0, "last": None, "recruits": 0, "recruited_by": None,
                                     "comments": 0}
            report["arrived"].append(k)
        st["handle"] = handle
        st["comments"] += len(cs)
        # streak: commented on the previous episode day as well
        if st["last"] and prev_day and st["last"] == prev_day.isoformat():
            st["streak"] += 1
        elif st["last"] != iso:
            st["streak"] = 1
        st["last"] = iso
        new_rank = rank_for(st["streak"])
        if _rank_index(new_rank) > _rank_index(st["rank"]):
            st["rank"] = new_rank
            report["ranked_up"].append({"who": k, "rank": new_rank})
        # one job change a day: the last job word they wrote
        job = next((j for j in (_job_in(c["text"]) for c in reversed(cs)) if j), None)
        if job:
            tallies[job] += 1
            if job != st["job"]:
                st["job"] = job
                report["jobs"].append({"who": k, "job": job})
        for c in cs:  # tagged friends, for the recruiter badge
            for m in MENTION.findall(c["text"] or ""):
                if m.lower() != handle.lower():
                    s["pending_mentions"].append({"by": k, "friend": m.lower(), "on": iso})

    # recruits: a tagged friend who has now arrived
    keep = []
    handles = {k: st["handle"].lower() for k, st in s["settlers"].items()}
    arrived_handles = {handles[k]: k for k in report["arrived"]}
    for pm in s["pending_mentions"]:
        if pm["friend"] in arrived_handles and pm["by"] in s["settlers"] and pm["by"] != arrived_handles[pm["friend"]]:
            friend = arrived_handles.pop(pm["friend"])
            s["settlers"][friend]["recruited_by"] = pm["by"]
            s["settlers"][pm["by"]]["recruits"] += 1
            report["recruits"].append({"by": pm["by"], "friend": friend})
        elif date.fromisoformat(pm["on"]) > day - timedelta(days=RECRUIT_DAYS):
            keep.append(pm)
    s["pending_mentions"] = keep

    # milestones: unlock what the follower count has reached
    have = set(s["built"]) | set(s["queue"]) | ({s["building"]["id"]} if s["building"] else set())
    for b in BUILDINGS:
        if b["id"] not in have and s["followers"] >= b["followers"]:
            s["queue"].append(b["id"])
            report["unlocked"].append(b["id"])
    # the busiest job's building goes first
    busiest = max(tallies, key=lambda j: (tallies[j], -list(JOBS).index(j))) if any(tallies.values()) else None
    if busiest:
        s["queue"].sort(key=lambda bid: (BY_ID[bid]["job"] != busiest, BUILDINGS.index(BY_ID[bid])))
    else:
        s["queue"].sort(key=lambda bid: BUILDINGS.index(BY_ID[bid]))

    # resources: yesterday's shares and saves, the builders, and slow work
    y = yesterday or {}
    gained = {"shares": int(y.get("shares") or 0), "saves": int(y.get("saves") or 0),
              "builders": tallies["build"], "slow": SLOW_WORK}
    report["gained"] = gained
    s["stock"] += sum(gained.values())
    if not s["building"] and s["queue"]:
        s["building"] = {"id": s["queue"].pop(0), "paid": 0}
    if s["building"]:
        b = BY_ID[s["building"]["id"]]
        before = s["building"]["paid"]
        pay = min(s["stock"], b["cost"] - before)
        s["building"]["paid"] += pay
        s["stock"] -= pay
        report["progress"] = {"id": b["id"], "from": before / b["cost"], "to": s["building"]["paid"] / b["cost"]}
        if s["building"]["paid"] >= b["cost"]:
            s["built"].append(b["id"])
            report["finished"] = b["id"]
            s["building"] = {"id": s["queue"].pop(0), "paid": 0} if s["queue"] else None
    if not s["building"]:
        s["stock"] = min(s["stock"], STOCK_CAP)

    report["featured"] = featured(s, report)
    report["next"] = next_goal(s)
    s["day"] = iso
    s["days"][iso] = report
    return s, report


def featured(s: dict, report: dict, limit: int = 4) -> list[str]:
    """Who the episode shows by name: newcomers, then recruits, rank-ups and job changes."""
    order = (report["arrived"] + [r["by"] for r in report["recruits"]] + [r["who"] for r in report["ranked_up"]]
             + [j["who"] for j in report["jobs"]])
    out = []
    for k in order:
        if k not in out and k in s["settlers"]:
            out.append(k)
    return out[:limit]


def next_goal(s: dict) -> dict | None:
    """The next follower milestone, for the end of the episode ("12 more and we light the beacon")."""
    for b in BUILDINGS:
        if s["followers"] < b["followers"]:
            return {"id": b["id"], "name": b["name"], "at": b["followers"], "more": b["followers"] - s["followers"]}
    return None


def erase(s: dict, handle: str) -> bool:
    """Remove a settler entirely (privacy request): their record, mentions and report entries."""
    h = handle.lstrip("@").lower()
    keys = [k for k, st in s["settlers"].items() if st["handle"].lower() == h or k.endswith(":" + h)]
    for k in keys:
        del s["settlers"][k]
    s["pending_mentions"] = [m for m in s["pending_mentions"] if m["by"] not in keys and m["friend"] != h]
    for r in s["days"].values():
        r["arrived"] = [k for k in r["arrived"] if k not in keys]
        r["featured"] = [k for k in r["featured"] if k not in keys]
        r["jobs"] = [j for j in r["jobs"] if j["who"] not in keys]
        r["ranked_up"] = [x for x in r["ranked_up"] if x["who"] not in keys]
        r["recruits"] = [x for x in r["recruits"] if x["by"] not in keys and x["friend"] not in keys]
    return bool(keys)
