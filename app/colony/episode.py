"""A day's report → the side-on video spec, with captions from templates: the episode that goes
out when no AI has adapted the day (docs/COLONY_PLAN.md §5b, "neither"), and the base the daily
writer starts from. People first (arrivals, jobs, ranks, recruits), then the build, then the next
goal and the ask (§1a, §5)."""
from __future__ import annotations

from ..render.colony import scene
from ..render.colony.art import SKINS, SUITS
from . import rules

DRAWN = {"dome", "condenser", "greenhouse", "workshop", "beacon"}  # buildings the side-on view can draw
SITE_X = {"dome": scene.DOME[0], "condenser": scene.CONDENSER_X, "greenhouse": scene.GREEN[0],
          "workshop": scene.WORKSHOP_X, "beacon": scene.BEACON_X}
CREW = [  # the founding crew, there before any viewer
    {"name": "MAREN", "suit": "e8e2d0", "skin": SKINS[1], "job": "sit", "x": 54},
    {"name": "TOLU", "suit": "f2a33a", "skin": SKINS[3], "job": "sit", "x": 68, "flip": True},
    {"name": "BASK", "suit": "4fb3a8", "skin": SKINS[0]},
    {"name": "IKO", "suit": "d65a5a", "skin": SKINS[2]},
]
ARRIVAL_X = [(84, -8), (122, 12), (140, -14)]
JOB_LINE = {"farm": "*FARMING*", "build": "*BUILDING*", "scout": "*SCOUTING*", "guard": "ON *GUARD*",
            "tinker": "*TINKERING*"}
BEAT = 2.6


def hl(text: str) -> str:
    """Highlight every word (captions mark gold words with *word*)."""
    return " ".join(f"*{w}*" for w in text.split())


def _h(s: dict, k: str) -> str:
    return "@" + s["settlers"][k]["handle"]


def _cam_for(x: int) -> int:
    return max(0, min(scene.WW - 180, x - 90))


def build(s: dict, report: dict, seed: int = 7) -> dict:
    t = 0.0
    caps, tags, sfx, arrivals = [], {}, [], []
    cam = [(0, 0)]
    people = s["settlers"]

    # 1. arrivals: up to three capsules by name, the rest as a number
    named = [k for k in report["arrived"] if k in people][:3]
    for i, k in enumerate(named):
        x, walk = ARRIVAL_X[i]
        rng = abs(hash(k))
        arrivals.append({"name": people[k]["handle"], "x": x, "land": 1.6 + i * 1.1, "walk": walk,
                         "suit": SUITS[rng % len(SUITS)], "skin": SKINS[(rng // 7) % len(SKINS)]})
        sfx.append((1.6 + i * 1.1, "land"))
    extra = len(report["arrived"]) - len(named)
    if named:
        t_end = 1.6 + len(named) * 1.1 + 1.6
        first = ["*1* SIGNAL" if len(named) == 1 else f"*{len(report['arrived'])}* SIGNALS", "*ANSWERED*"]
        caps.append({"lines": first, "t0": 0.0, "t1": t_end})
        t = t_end
        if extra > 0:
            caps.append({"lines": [f"+{extra} MORE", "MOVED IN"], "t0": t, "t1": t + BEAT})
            t += BEAT
    else:
        caps.append({"lines": ["ANOTHER NIGHT", "ON *FARSIDE*"], "t0": 0.0, "t1": 2.6})
        t = 2.6

    # 2. the people: recruits, rank-ups, job changes (three beats at most)
    beats = []
    for r in report["recruits"]:
        if r["by"] in people and r["friend"] in people:
            beats.append((r["by"], [_h(s, r["by"]), "BROUGHT", "*" + _h(s, r["friend"]) + "*"]))
    for r in report["ranked_up"]:
        if r["who"] in people and r["rank"] != "newcomer":
            beats.append((r["who"], [_h(s, r["who"]), "IS NOW A", f"*{r['rank'].upper()}*"]))
    for j in report["jobs"]:
        if j["who"] in people:
            beats.append((j["who"], [_h(s, j["who"]), "IS NOW", JOB_LINE[j["job"]]]))
    for who, lines in beats[:3]:
        caps.append({"lines": lines, "t0": t, "t1": t + BEAT})
        tags[people[who]["handle"]] = (t, t + BEAT)
        sfx.append((t, "blip"))
        t += BEAT

    # 3. the build
    buildings = [{"kind": b} for b in s["built"] if b in DRAWN]
    prog = report.get("progress")
    progress = []
    if prog:
        b = rules.BY_ID[prog["id"]]
        t0 = t
        if prog["id"] in DRAWN:
            fill_to = 1.0 if report.get("finished") == prog["id"] else prog["to"]
            buildings = [x for x in buildings if x["kind"] != prog["id"]]
            buildings.append({"kind": prog["id"], "from": prog["from"], "to": fill_to, "t0": t0 + 0.4, "t1": t0 + 4.4})
            x = SITE_X[prog["id"]]
            cam += [(t0, cam[-1][1]), (t0 + 1.0, _cam_for(x))]
        g = report["gained"]
        if report.get("finished") == prog["id"]:
            lines = ["THE", hl(b["name"]), "IS *DONE*"]
        elif g.get("shares"):
            pct = int(round((prog["to"] - prog["from"]) * 100))
            lines = [f"*+{pct}%* TODAY", f"*{g['shares']}* SHARES HELPED"]
        else:
            lines = ["WORK GOES ON", hl(b["name"])]
        caps.append({"lines": lines, "t0": t0, "t1": t0 + 5.0})
        progress.append({"label": b["name"], "from": prog["from"], "to": prog["to"] if report.get("finished") != prog["id"] else 1.0,
                         "right": "{pct}", "t0": t0, "t1": t0 + 5.4, "fill_s": 4.0})
        sfx.append((t0, "chime"))
        t += 5.4

    # 4. the next goal, and the ask
    nxt = report.get("next")
    beacon_ghost = None
    if nxt:
        caps.append({"lines": [f"*{nxt['more']}* MORE", "UNLOCK THE", hl(nxt["name"])], "t0": t, "t1": t + 3.6})
        progress.append({"label": "NEXT: " + nxt["name"], "from": s["followers"] / nxt["at"], "to": s["followers"] / nxt["at"],
                         "right": f"{s['followers']}/{nxt['at']}", "t0": t, "t1": t + 6.6})
        if nxt["id"] == "beacon":
            beacon_ghost = (t, t + 6.6)
            cam += [(t, cam[-1][1]), (t + 1.0, _cam_for(scene.BEACON_X))]
        t += 3.6
    caps.append({"lines": ["COMMENT TO", "*MOVE IN*"], "t0": t, "t1": t + 3.0})
    sfx.append((t, "blip"))
    t += 3.0

    # who's drawn: the crew, the people in today's beats first (so they're outside and tagged), the rest
    order = rules.featured(s, report, limit=12) + [k for k in people if k not in report["featured"]]
    settlers = [dict(c) for c in CREW]
    seen = set()
    for k in order:
        if k in seen or k in named:
            continue
        seen.add(k)
        st = people[k]
        row = {"name": st["handle"]}
        if st.get("job") == "build":
            row.update(job="carry", phase=len(settlers) * 13)
        settlers.append(row)
    for i in range(max(0, min(s["followers"], 30) - len(settlers))):  # followers who've never commented
        settlers.append({"name": f"~{i}"})
    return {
        "seed": seed, "count": max(0, s["followers"] - len(named)), "settlers": settlers[:40],
        "buildings": buildings, "heaters": [61], "camera": cam, "arrivals": arrivals, "tags": tags,
        "progress": progress, "beacon_ghost": beacon_ghost, "captions": caps, "duration": round(t, 2), "sfx": sfx,
        "building_now": (0, t),
    }
