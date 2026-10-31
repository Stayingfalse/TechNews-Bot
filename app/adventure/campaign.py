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


# ------------------------------------------------------------------ the story map (dashboard)

_odds_cache: dict[str, dict] = {}


def _hero_odds(hero: dict | None) -> dict:
    """{skill: {dc: percent}} for this hero, from the engine (cached: it only changes with a new hero)."""
    if not hero:
        return {}
    key = json.dumps(hero, sort_keys=True)
    if key not in _odds_cache:
        try:
            _odds_cache[key] = {k: v.get("success_pct_by_dc") or {} for k, v in vocab(hero).get("skills", {}).items()}
        except Exception:
            return {}
    return _odds_cache[key]


def _local_date(iso: str | None) -> str | None:
    return datetime.fromisoformat(iso).astimezone(settings.tz).date().isoformat() if iso else None


def _episode0_chain(all_jobs: list[dict]) -> list[dict]:
    """The posted (and booked) Episode 0 parts of the current series, part 1 first."""
    by_from = {j["from_job"]: j for j in all_jobs if j.get("from_job") and j.get("status") not in ("cancelled",)}
    starts = [j for j in all_jobs if j.get("kind") == "episode0" and j.get("series") and (j.get("spec") or {}).get("part") == 1
              and j.get("publish_at") and j.get("status") not in ("cancelled", "failed", "missed")]
    if not starts:
        return []
    chain = [max(starts, key=lambda j: j["publish_at"])]
    while (nxt := by_from.get(chain[-1]["id"])) and nxt.get("kind") == "episode0":
        chain.append(nxt)
    return chain


def story_map() -> dict:
    """Every scene of the campaign so far and to come, how they connect, and the path the votes took.

    nodes: {id, kind (episode0|story|unwritten), date, title, status, ...details}
      status: played | ready (rendered, posting soon) | next (booked, its vote still open) |
              possible (still reachable) | missed (a path not taken) | upcoming (Episode 0, not yet booked)
    edges: {from, to, letter, label, status (taken|chosen|possible|missed), votes?, breaks?, default?}"""
    from . import jobs as jobs_mod
    all_jobs = jobs_mod.recent(500)
    by_id = {j["id"]: j for j in all_jobs}
    s = state()
    odds = _hero_odds(s["hero"])
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    LETTER = "ABC"

    def votes_on(job_id: str) -> dict | None:
        """The vote counted on a post: kept on the job made from it."""
        nxt = next((j for j in all_jobs if j.get("from_job") == job_id and j.get("votes")), None)
        return nxt["votes"] if nxt else None

    # Episode 0: one node per part, joined by the winning answer
    chain = _episode0_chain(all_jobs)
    first = datetime.fromisoformat(chain[0]["publish_at"]).astimezone(settings.tz).date() if chain else None
    for part in range(1, 5):
        job = chain[part - 1] if part <= len(chain) else None
        sc = (job or {}).get("script") or {}
        status = {"done": "played", "scheduled": "ready", "publishing": "ready"}.get((job or {}).get("status"), "next" if job else "upcoming")
        nodes[f"episode0-{part}"] = {
            "id": f"episode0-{part}", "kind": "episode0", "part": part, "title": f"Episode 0 · part {part}",
            "date": _local_date(job.get("publish_at")) if job else (first + timedelta(days=part - 1)).isoformat() if first else None,
            "status": status, "options": sc.get("options") or [], "default": sc.get("default"),
            "job": (job or {}).get("id"), "url": ((job or {}).get("results", {}).get("instagram") or {}).get("url"),
            "video_url": (job or {}).get("video_url"), "error": (job or {}).get("error")}
        if part > 1:
            v = votes_on(chain[part - 2]["id"]) if part - 2 < len(chain) else None
            edges.append({"from": f"episode0-{part - 1}", "to": f"episode0-{part}", "letter": LETTER[v["pick"]] if v else "",
                          "label": v["option"] if v else "the vote", "status": "taken" if v else "possible",
                          "votes": v and {"counts": v["counts"], "how": v["how"]}})

    # the story: every node of every arc
    arc_list = arcs()
    played = [h["node"] for h in s["history"]]
    pending = sorted((j for j in all_jobs if j.get("kind") == "story" and j.get("node")
                      and j.get("status") in ("preparing", "voicing", "rendering", "scheduled", "publishing")),
                     key=lambda j: j.get("publish_at") or "")
    for arc in arc_list:
        start = date.fromisoformat(arc["start_date"])
        for n in arc["nodes"]:
            ck = n.get("check")
            nodes[n["id"]] = {
                "id": n["id"], "kind": "story", "arc": arc["id"], "arc_title": arc["title"],
                "date": (start + timedelta(days=n["day"])).isoformat(), "title": " ".join(n["hook"]).title(),
                "scene": n["scene"].get("name") or n["scene"]["type"], "scene_type": n["scene"]["type"], "foe": n.get("foe"),
                "story": n["story"], "ask": n["ask"], "rest": bool(n.get("rest")), "after": n.get("after"),
                "check": ck and {**ck, "pct": odds.get(ck["skill"], {}).get(str(ck["dc"]))},
                "default": n["default"], "status": "missed"}
        for n in arc["nodes"]:
            for i, c in enumerate(n["choices"]):
                if c.get("next"):
                    targets = [c["next"]]
                else:  # the last day: the next arc picks it up, or it's still to be written
                    after = next((a for a in arc_list if n["id"] in a["links"]), None)
                    if after:
                        targets = [after["links"][n["id"]][i]]
                    else:
                        tbd = f"unwritten-{arc['id']}"
                        nodes.setdefault(tbd, {"id": tbd, "kind": "unwritten", "title": "Next week",
                                               "date": (start + timedelta(days=arc["days"])).isoformat(), "status": "possible",
                                               "story": "Not written yet: the weekly routine writes it on Tuesday at 00:05."})
                        targets = [tbd]
                for t in targets:
                    edges.append({"from": n["id"], "to": t, "letter": LETTER[i], "label": c["label"], "status": "missed",
                                  "breaks": c.get("breaks"), "default": i == n["default"]})
        if "episode0" in arc["links"]:
            for i, t in enumerate(arc["links"]["episode0"]):
                edges.append({"from": "episode0-4", "to": t, "letter": LETTER[i], "label": FIRST_CHOICES[i], "status": "missed",
                              "default": None})

    # the path taken: Episode 0, then each played episode, then whatever is being made now
    def mark_edge(a: str, b: str, pick: int | None, status: str, votes: dict | None = None) -> None:
        for e in edges:
            if e["from"] == a and e["to"] == b and (pick is None or e["letter"] == LETTER[pick]):
                e["status"] = status
                if votes:
                    e["votes"] = {"counts": votes.get("counts"), "how": votes.get("how")}
                return

    prev = "episode0-4"
    for h in s["history"]:
        job = by_id.get(h.get("job") or "") or {}
        roll = ((job.get("spec") or {}).get("check") or {}).get("roll")
        nodes.get(h["node"], {}).update(status="played", ep=h["ep"], success=h.get("success"), hearts=h.get("hearts"),
                                        roll=roll and {"total": roll.get("total"), "kept": roll.get("kept"), "mod": roll.get("mod"),
                                                       "ok": roll.get("ok"), "natural": roll.get("natural")},
                                        url=((job.get("results") or {}).get("instagram") or {}).get("url"))
        mark_edge(prev, h["node"], h.get("pick"), "taken", job.get("votes"))
        prev = h["node"]
    for j in pending:
        nodes.get(j["node"], {}).update(status="ready", ep=(j.get("spec") or {}).get("ep"), video_url=j.get("video_url"))
        mark_edge(prev, j["node"], (j.get("votes") or {}).get("pick"), "chosen", j.get("votes"))
        prev = j["node"]

    # what can still happen: everything reachable from where the story stands now
    at = prev if (s["history"] or pending) else ("episode0-4" if nodes.get("episode0-4") else None)
    frontier, seen = [at] if at else [], set()
    while frontier:
        cur = frontier.pop()
        for e in edges:
            if e["from"] == cur and e["status"] == "missed":
                e["status"] = "possible"
                if e["to"] not in seen:
                    seen.add(e["to"])
                    if nodes.get(e["to"], {}).get("status") == "missed":
                        nodes[e["to"]]["status"] = "possible"
                    frontier.append(e["to"])
    # tomorrow's options are being voted on now
    if at and nodes.get(at, {}).get("status") in ("played", "ready"):
        for e in edges:
            if e["from"] == at and e["status"] == "possible" and nodes.get(e["to"], {}).get("kind") != "episode0":
                nodes[e["to"]]["voting"] = True
    for n in nodes.values():  # Episode 0 parts are a fixed line, never "missed"
        if n["kind"] == "episode0" and n["status"] == "missed":
            n["status"] = "upcoming"

    return {"nodes": list(nodes.values()), "edges": edges, "at": at,
            "hero": s["hero"], "fear": s["fear"], "hearts": s["hearts"], "ep": s["ep"], "dead": s["dead"],
            "rules_broken": s["rules_broken"], "arcs": [{"id": a["id"], "title": a["title"], "start_date": a["start_date"],
                                                          "days": a["days"]} for a in arc_list]}
