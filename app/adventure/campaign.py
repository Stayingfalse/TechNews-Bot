"""The campaign: the hero's state, the weekly arcs the routine writes, and which node each day plays.

An arc (adventure/packages/shared/src/arc.ts) is a few days of story nodes, one layer per day; each
node's choices lead to the next day's nodes, and the last day's choices are picked up by the next
arc's `links`. The first arc links from Episode 0's last vote ("episode0"). Which node plays is
decided by the votes alone: the dates only say when the routine must have written the next arc.

Files in DATA_DIR/adventure: state.json (the hero and what has happened) and arcs/<id>.json."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from ..config import settings

TUESDAY = 1  # arcs end on the day before the weekly routine's Wednesday start
# Episode 0 part 4's question, as engine/episode0.ts shows it (with these odds on screen)
FIRST_CHOICES = ["Force the rusted gate", "Pick the old lock", "Search for another way"]
FIRST_CHECKS = [{"skill": "athletics", "dc": 12}, {"skill": "sleight_of_hand", "dc": 12}, {"skill": "perception", "dc": 10}]


class NoArc(Exception):
    """No accepted arc says where the story goes next."""


def _dir() -> Path:
    d = settings.data_dir / "adventure"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(p)


# ------------------------------------------------------------------ state

def state() -> dict:
    p = _dir() / "state.json"
    s = json.loads(p.read_text()) if p.exists() else {}
    return {"season": 1, "hero": None, "fear": None, "hearts": 3, "ep": 0, "arc": None, "node": None, "dead": False,
            "rules_broken": [], "history": [], **s}


def save_state(s: dict) -> None:
    _write(_dir() / "state.json", s)


def note_episode0(spec: dict) -> None:
    """Episode 0's votes as they're counted: the foe the viewers fear and the hero they made."""
    s = state()
    if spec.get("fear"):
        s["fear"] = spec["fear"]
    if spec.get("hero"):
        s["hero"] = spec["hero"]
    save_state(s)


# ------------------------------------------------------------------ arcs

def _arcs_dir() -> Path:
    d = _dir() / "arcs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def arcs() -> list[dict]:
    """Accepted arcs, oldest first."""
    found = [json.loads(f.read_text())["arc"] for f in _arcs_dir().glob("*.json")]
    return sorted(found, key=lambda a: a["start_date"])


def _arc(arc_id: str) -> dict | None:
    p = _arcs_dir() / f"{arc_id}.json"
    return json.loads(p.read_text())["arc"] if p.exists() else None


def _node_of(arc: dict, node_id: str) -> dict:
    return next(n for n in arc["nodes"] if n["id"] == node_id)


def _played() -> set[str]:
    """Nodes already played (or being prepared): their arc can no longer be replaced."""
    from . import jobs
    ids = {h["node"] for h in state()["history"]}
    ids |= {j["node"] for j in jobs.recent(60) if j.get("node") and j.get("status") not in ("cancelled", "failed", "missed")}
    return ids


def _episode0_end() -> date | None:
    """The local date Episode 0's last part posts on, from the booked series."""
    from . import jobs
    for j in jobs.recent(200):
        if j.get("kind") == "episode0" and j.get("publish_at") and j.get("series") and j.get("status") not in ("cancelled", "failed", "missed"):
            when = datetime.fromisoformat(j["publish_at"]).astimezone(settings.tz).date()
            return when + timedelta(days=4 - int(j["spec"].get("part", 1)))
    return None


def _until_tuesday(start: date) -> int:
    return (TUESDAY - start.weekday()) % 7 + 1


def expected(replacing: str | None = None) -> dict:
    """What the next arc must look like: its dates, what it links from, the hero, the ids taken."""
    done = [a for a in arcs() if a["id"] != replacing]
    if done:
        last = done[-1]
        start = date.fromisoformat(last["start_date"]) + timedelta(days=last["days"])
        tail = [n for n in last["nodes"] if n["day"] == last["days"] - 1]
        links_from = [{"id": n["id"], "choices": len(n["choices"]), "arc": last["id"],
                       "options": [{"label": c["label"], "recap": c["recap"]} for c in n["choices"]]} for n in tail]
    else:
        end = _episode0_end()
        start = (end or datetime.now(settings.tz).date()) + timedelta(days=1)
        links_from = [{"id": "episode0", "choices": 3, "arc": None,
                       "options": [{"label": label, "recap": f"You chose to {label[0].lower()}{label[1:]}.", "check": FIRST_CHECKS[i]}
                                   for i, label in enumerate(FIRST_CHOICES)]}]
    s = state()
    return {"start_date": start.isoformat(), "days": _until_tuesday(start), "links_from": links_from, "hero": s["hero"],
            "known_ids": sorted({n["id"] for a in done for n in a["nodes"]})}


def _run_node(*args: str, payload: dict, timeout: int = 60) -> dict:
    from . import jobs
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(payload, fh)
    try:
        return jobs._node(*args, fh.name, timeout=timeout)
    finally:
        os.unlink(fh.name)


def validate(raw: dict, replacing: str | None = None) -> dict:
    ctx = expected(replacing)
    ctx_for_node = {k: ctx[k] for k in ("start_date", "days", "hero", "known_ids")}
    ctx_for_node["links_from"] = [{"id": lf["id"], "choices": lf["choices"]} for lf in ctx["links_from"]]
    r = _run_node("validate-arc", payload={"arc": raw, "context": ctx_for_node})
    if r.get("ok") and "episode0" in raw.get("links", {}):
        # Episode 0 showed these checks and their odds: the nodes they lead to must keep them
        nodes = {n["id"]: n for n in raw["nodes"]}
        for i, nid in enumerate(raw["links"]["episode0"]):
            got = {k: (nodes[nid].get("check") or {}).get(k) for k in ("skill", "dc")}
            if got != FIRST_CHECKS[i]:
                r["problems"].append(f"{nid}: Episode 0 promised {FIRST_CHECKS[i]['skill']} DC {FIRST_CHECKS[i]['dc']} for "
                                     f"\"{FIRST_CHOICES[i]}\"; its check must be exactly that")
        r["ok"] = not r["problems"]
    return {**r, "expected": ctx}


def accept(raw: dict, replace: bool = False) -> dict:
    """Validate and store an arc. {"ok": False, "problems": [...]} when it isn't bookable."""
    same = next((a for a in arcs() if a["start_date"] == raw.get("start_date") or a["id"] == raw.get("id")), None)
    if same and not replace:
        return {"ok": False, "conflict": True, "problems": [f"arc {same['id']} already covers {same['start_date']}; pass replace=true to swap it"]}
    if same and {n["id"] for n in same["nodes"]} & _played():
        return {"ok": False, "conflict": True, "problems": [f"arc {same['id']} has started playing; it can't be replaced"]}
    r = validate(raw, replacing=same["id"] if same else None)
    if not r.get("ok"):
        return {"ok": False, "problems": r.get("problems", ["invalid arc"]), "expected": r["expected"]}
    arc = r["arc"]
    if same:
        (_arcs_dir() / f"{same['id']}.json").unlink(missing_ok=True)
    _write(_arcs_dir() / f"{arc['id']}.json", {"arc": arc, "accepted_at": datetime.now(settings.tz).isoformat()})
    return {"ok": True, "id": arc["id"], "start_date": arc["start_date"], "days": arc["days"], "nodes": len(arc["nodes"])}


# ------------------------------------------------------------------ the day's node

def next_node(prev_spec: dict, prev_node: dict | None, pick: int, label: str) -> tuple[dict, dict, dict]:
    """(arc, node, the choice that led here) for the vote `pick` on the previous post."""
    if prev_spec.get("kind") == "episode0":
        arc = next((a for a in arcs() if "episode0" in a["links"]), None)
        if not arc:
            raise NoArc("no arc links from Episode 0 yet")
        choice = {"label": label, "recap": f"You chose to {label[0].lower()}{label[1:]}.", "next": None}
        return arc, _node_of(arc, arc["links"]["episode0"][pick]), choice
    arc = _arc(prev_node["arc"])
    node = _node_of(arc, prev_node["node"])
    choice = node["choices"][pick]
    if choice.get("next"):
        return arc, _node_of(arc, choice["next"]), choice
    after = next((a for a in arcs() if node["id"] in a["links"]), None)
    if not after:
        raise NoArc(f"no arc follows {arc['id']} yet (links from {node['id']})")
    return after, _node_of(after, after["links"][node["id"]][pick]), choice


def covers_next(job: dict) -> bool:
    """Whether every way tomorrow's vote could go has a node waiting."""
    try:
        spec = job["spec"]
        n = len(job["script"]["options"])
        prev = {"arc": job.get("arc"), "node": job.get("node")}
        for pick in range(n):
            next_node(spec, prev if spec.get("kind") == "story" else None, pick, job["script"]["options"][pick])
        return True
    except (NoArc, StopIteration, KeyError, IndexError, TypeError):
        return False


def dice(ep: int, node_id: str) -> tuple[list[int], str]:
    """Two d20s nobody can predict without the server's secret, the same on every retry."""
    s = state()
    proof = f"{s['season']}:{ep}:{node_id}"
    out, i = [], 0
    while len(out) < 2:
        b = hmac.new(settings.api_token.encode(), f"{proof}:{i}".encode(), hashlib.sha256).digest()
        for x in b:
            if x < 240 and len(out) < 2:  # 240 = 12 × 20: no bias
                out.append(x % 20 + 1)
        i += 1
    return out, proof


def build_story(prev_job: dict, pick: int, counts: list[int]) -> dict:
    """The spec (and everything to remember) for today's story episode."""
    opts = prev_job["script"]["options"]
    prev_node = {"arc": prev_job.get("arc"), "node": prev_job.get("node")}
    arc, node, choice = next_node(prev_job["spec"], prev_node, pick, opts[pick])
    s = state()
    if s["dead"]:
        raise RuntimeError("the hero has fallen; a new hero's Episode 0 comes first")
    if not s["hero"]:
        raise RuntimeError("no hero yet (Episode 0 parts 3 and 4 make one)")
    ep = s["ep"] + 1
    rolled, proof = dice(ep, node["id"])
    ctx = {"ep": ep, "hero": s["hero"], "hearts": s["hearts"], "dice": rolled,
           "recap": {"pick": pick, "votes": counts, "label": opts[pick], "line": choice["recap"]}}
    spec = _run_node("resolve", payload={"node": node, "ctx": ctx})
    broken = choice.get("breaks")
    return {"spec": spec, "arc": arc["id"], "node": node["id"], "dice": {"rolled": rolled, "proof": proof},
            "state_after": {"ep": ep, "arc": arc["id"], "node": node["id"], "hearts": spec["hearts"]["after"], "dead": spec["dead"],
                            "broke": {"rule": broken, "choice": opts[pick], "at": prev_node["node"] or "episode0"} if broken else None,
                            "ok": (spec.get("check") or {}).get("roll", {}).get("ok")}}


def commit(job: dict) -> dict:
    """The episode went out: the story moves on."""
    a, s = job["state_after"], state()
    s.update(ep=a["ep"], arc=a["arc"], node=a["node"], hearts=a["hearts"], dead=a["dead"])
    if a.get("broke"):
        s["rules_broken"].append({**a["broke"], "ep": a["ep"]})
    s["history"].append({"ep": a["ep"], "arc": a["arc"], "node": a["node"], "date": datetime.now(settings.tz).date().isoformat(),
                         "pick": (job.get("votes") or {}).get("pick"), "votes": (job.get("votes") or {}).get("counts"),
                         "success": a.get("ok"), "hearts": a["hearts"], "job": job["id"]})
    save_state(s)
    return s


# ------------------------------------------------------------------ for the routine

def season_bible(season: int) -> str:
    p = settings.adventure_dir / "seasons" / f"season{season}.md"
    return p.read_text() if p.exists() else ""


def vocab(hero: dict | None) -> dict:
    """Scenes, foes, skills (with this hero's odds at every DC) and limits, from the engine itself."""
    return _run_node("vocab", payload={"hero": hero})


def overview() -> dict:
    s = state()
    path = []
    for h in s["history"][-14:]:
        arc = _arc(h["arc"])
        n = _node_of(arc, h["node"]) if arc else {}
        path.append({**h, "story": n.get("story"), "hook": n.get("hook")})
    return {
        "state": {k: v for k, v in s.items() if k != "history"},
        "recent": path,
        "next_arc": expected(),
        "arcs": [{"id": a["id"], "title": a["title"], "start_date": a["start_date"], "days": a["days"]} for a in arcs()],
        "season_bible": season_bible(s["season"]),
        "example_arc": json.loads((settings.adventure_dir / "examples" / "arc-s1w1.json").read_text())
        if (settings.adventure_dir / "examples" / "arc-s1w1.json").exists() else None,
    }
