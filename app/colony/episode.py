"""A day → the video: the episode's beats in order (app/colony/plan.py), with the slots filled from
the day's report (docs/COLONY_PLAN.md §5b). With no plan, the default beats play: arrivals,
people, the build, the next goal, the ask. That's the episode when no AI has run at all.

The result is a list of shots: one side-on shot for everything up to a decision, then the
decision inside a dome. `render/colony/video.py` turns it into the mp4."""
from __future__ import annotations

import re

from ..render.colony import scene
from ..render.colony.art import SKINS, SUITS
from . import plan as planmod
from . import rules

DRAWN = {"dome", "condenser", "greenhouse", "workshop", "beacon"}  # buildings the side-on view can draw
SITE_X = {"dome": scene.DOME[0], "condenser": scene.CONDENSER_X, "greenhouse": scene.GREEN[0],
          "workshop": scene.WORKSHOP_X, "beacon": scene.BEACON_X}
CREW = [  # the founding crew, there before any viewer
    {"name": "MAREN", "suit": "e8e2d0", "skin": SKINS[1], "job": "sit", "x": 54},
    {"name": "TOLU", "suit": "f2a33a", "skin": SKINS[3], "job": "sit", "x": 68, "flip": True},
    {"name": "BASK", "suit": "4fb3a8", "skin": SKINS[0], "job": "carry", "phase": 0},
    {"name": "IKO", "suit": "d65a5a", "skin": SKINS[2], "job": "sit", "x": 162, "flip": True},
]
CREW_LOOKS = {"MAREN": {"suit": "white", "skin": "s2", "hair": "white"},
              "TOLU": {"suit": "orange", "skin": "s4", "hat": "cap"},
              "BASK": {"suit": "teal", "skin": "s1", "back": "pack"},
              "IKO": {"suit": "red", "skin": "s3", "held": "wrench", "hair": "bun"}}
ARRIVAL_X = [(84, -8), (122, 12), (140, -14)]
SPOT_X = [96, 112, 128, 144]  # where featured settlers stand for their moment (in the first screen)
JOB_LINE = {"farm": "*FARMING*", "build": "*BUILDING*", "scout": "*SCOUTING*", "guard": "ON *GUARD*",
            "tinker": "*TINKERING*"}
BEAT = 2.6
PARADE_MAX = 12  # people shown walking in the parade (the caption counts them all)
DEFAULT_BEATS = [{"type": "slot", "slot": s} for s in ("arrivals", "people", "build", "next", "ask")]


def hl(text: str) -> str:
    """Highlight every word (captions mark gold words with *word*)."""
    return " ".join(f"*{w}*" for w in text.split())


def _cam_for(x: int) -> int:
    return max(0, min(scene.WW - 180, x - 90))


def _by_handle(s: dict) -> dict[str, str]:
    return {st["handle"].lower(): k for k, st in s["settlers"].items()}


def look_for(s: dict, k: str, ep: dict | None) -> dict:
    """A settler's look: today's adaptation, else what they had, else one drawn from their key."""
    st = s["settlers"][k]
    new = ((ep or {}).get("settlers") or {}).get("@" + st["handle"]) or ((ep or {}).get("settlers") or {}).get(st["handle"])
    if new and new.get("look"):
        return new["look"]
    if st.get("look"):
        return st["look"]
    h = sum(ord(ch) * (i + 1) for i, ch in enumerate(k))
    from ..render.colony import kit
    return {"suit": kit.KIT["suit"][h % len(kit.KIT["suit"])], "skin": ["s1", "s2", "s3", "s4"][(h // 7) % 4],
            "hair": ["short", "long", "none", "bun", "ginger"][(h // 31) % 5]}


def resolve(who: str, s: dict, report: dict) -> tuple[str, str | None] | None:
    """A beat's WHO → (display name, settler key or None for crew); None if nobody fits."""
    if who in planmod.CREW:
        return who, None
    m = re.fullmatch(r"\$([1-4])", who)
    if m:
        i = int(m.group(1)) - 1
        f = report.get("featured") or []
        return ("@" + s["settlers"][f[i]]["handle"], f[i]) if i < len(f) and f[i] in s["settlers"] else None
    k = _by_handle(s).get(who.lstrip("@").lower())
    return ("@" + s["settlers"][k]["handle"], k) if k else None


def build(s: dict, report: dict, ep: dict | None = None, seed: int = 7) -> dict:
    beats = list((ep or {}).get("beats") or DEFAULT_BEATS)
    if (ep or {}).get("settlers") and not any(b.get("slot") == "granted" for b in beats):
        # everyone whose look changed gets their walk past, before the build (or the end)
        at = next((i for i, b in enumerate(beats) if b.get("slot") in ("build", "next", "ask") or b.get("type") == "decision"),
                  len(beats))
        beats.insert(at, {"type": "slot", "slot": "granted"})
    if not any(b.get("type") == "slot" and b.get("slot") == "ask" for b in beats) and \
            not any(b.get("type") == "decision" for b in beats):
        beats = list(beats) + [{"type": "slot", "slot": "ask"}]
    people = s["settlers"]
    t = 0.0
    caps, tags, bubbles, sfx, arrivals, events, progress, parades = [], {}, [], [], [], [], [], []
    paraded: set[str] = set()
    cam = [(0, 0)]
    beacon_ghost = None
    spotted: dict[str, int] = {}  # settler key → their spot
    buildings = [{"kind": b} for b in s["built"] if b in DRAWN]
    if s.get("building") and s["building"]["id"] in DRAWN and s["building"]["paid"] > 0 and not report.get("progress"):
        bid = s["building"]["id"]
        buildings.append({"kind": bid, "from": s["building"]["paid"] / rules.BY_ID[bid]["cost"]})
    decision = None
    big = rules.surge(report, s["followers"])
    named = [k for k in report["arrived"] if k in people][:2 if big else 3]
    if big:  # the planet shot comes first: make room for it, keeping people's moments
        beats = list(beats)
        # a big day can run long (up to the hard limit): the new people will likely be back tomorrow
        budget = planmod.MAX_SECONDS - SURGE_SECS - 1
        if (ep or {}).get("settlers") and not any(b.get("slot") == "granted" for b in beats):
            at = next((i for i, b in enumerate(beats) if b.get("slot") in ("build", "next", "ask")), len(beats))
            beats.insert(at, {"type": "slot", "slot": "granted"})
        budget += 4  # what a surge day saves on arrivals and the build (two capsules, a shorter build)
        for kind in ("caption", "crew", "event", "say", "people", "next"):
            while planmod.estimate({"beats": beats}) > budget:
                i = next((i for i, b in enumerate(beats) if (b.get("type") == kind and kind != "people") or
                          (kind == "crew" and b.get("type") == "say" and b.get("who") in planmod.CREW) or
                          (b.get("type") == "slot" and b.get("slot") == kind)), None)
                if i is None:
                    break
                beats.pop(i)

    def cam_to(x):
        cam.extend([(t, cam[-1][1]), (t + 0.9, x)])

    def spot(k):
        if k not in spotted and k not in named:
            spotted[k] = SPOT_X[len(spotted) % len(SPOT_X)]

    for b in beats:
        kind = b.get("type")
        secs = float(b.get("secs", BEAT))
        if kind == "slot" and b["slot"] == "arrivals":
            for i, k in enumerate(named):
                x, walk = ARRIVAL_X[i]
                lk = look_for(s, k, ep)
                arrivals.append({"name": people[k]["handle"], "x": x, "land": t + 1.6 + i * 1.1, "walk": walk, "look": lk})
                sfx.append((t + 1.6 + i * 1.1, "land"))
            if named:
                n = len(report["arrived"])
                end = t + 1.6 + len(named) * 1.1 + 1.6
                lines = ["THE FIRST", "*OF THEM*"] if big else ["*1* SIGNAL" if n == 1 else f"*{n}* SIGNALS", "*ANSWERED*"]
                caps.append({"lines": lines, "t0": t, "t1": end})
                t = end
                extra = n - len(named)
                if extra > 0 and not big:
                    caps.append({"lines": [f"+{extra} MORE", "MOVED IN"], "t0": t, "t1": t + BEAT})
                    t += BEAT
            elif t == 0:
                caps.append({"lines": ["ANOTHER NIGHT", "ON *FARSIDE*"], "t0": t, "t1": t + 2.4})
                t += 2.4
        elif kind == "slot" and b["slot"] == "people":
            found = []
            for r in report["recruits"]:
                if r["by"] in people and r["friend"] in people:
                    found.append((r["by"], ["@" + people[r["by"]]["handle"], "BROUGHT", "*@" + people[r["friend"]]["handle"] + "*"]))
            for r in report["ranked_up"]:
                if r["who"] in people and r["rank"] != "newcomer":
                    found.append((r["who"], ["@" + people[r["who"]]["handle"], "IS NOW A", f"*{r['rank'].upper()}*"]))
            for j in report["jobs"]:
                if j["who"] in people:
                    found.append((j["who"], ["@" + people[j["who"]]["handle"], "IS NOW", JOB_LINE[j["job"]]]))
            for who, lines in found[:3]:
                spot(who)
                caps.append({"lines": lines, "t0": t, "t1": t + BEAT})
                tags[people[who]["handle"]] = (t, t + BEAT)
                sfx.append((t, "blip"))
                t += BEAT
        elif kind == "slot" and b["slot"] == "granted":
            spot_handles = {str(x.get("who", "")).lstrip("@").lower() for x in beats if x.get("type") in ("feature", "say")}
            keys = []
            for h in (ep or {}).get("settlers") or {}:
                k = _by_handle(s).get(h.lstrip("@").lower())
                if k and h.lstrip("@").lower() not in spot_handles and k not in named:
                    keys.append(k)
            if not keys:
                continue
            show = keys[:PARADE_MAX]
            dur = round(2.0 + 0.45 * len(show), 2)
            parades.append({"t0": t, "t1": t + dur,
                            "people": [{"name": people[k]["handle"], "look": look_for(s, k, ep)} for k in show]})
            for k in show:
                tags[people[k]["handle"]] = (t, t + dur)
                paraded.add(k)
            n = len(keys)
            caps.append({"lines": ["GRANTED TODAY", f"*{n}* WISHES" if n > 1 else "*1* WISH"], "t0": t, "t1": t + dur})
            sfx += [(t + 0.4 + i * 0.45, "blip") for i in range(len(show))]
            t += dur
        elif kind == "slot" and b["slot"] == "build":
            if len(report.get("unlocked") or []) >= 2:  # a jump in followers unlocks several at once
                n = len(report["unlocked"])
                caps.append({"lines": [f"*{n}* BUILDINGS", "*UNLOCKED*"], "t0": t, "t1": t + 2.6})
                sfx.append((t, "chime"))
                t += 2.6
            prog = report.get("progress")
            if not prog:
                continue
            bd = rules.BY_ID[prog["id"]]
            done = report.get("finished") == prog["id"]
            if prog["id"] in DRAWN:
                buildings = [x for x in buildings if x["kind"] != prog["id"]]
                buildings.append({"kind": prog["id"], "from": prog["from"], "to": 1.0 if done else prog["to"],
                                  "t0": t + 0.4, "t1": t + 4.4})
                cam_to(_cam_for(SITE_X[prog["id"]]))
            g = report["gained"]
            if done:
                lines = ["THE", hl(bd["name"]), "IS *DONE*"]
            elif g.get("shares"):
                lines = [f"*+{int(round((prog['to'] - prog['from']) * 100))}%* TODAY", f"*{g['shares']}* SHARES HELPED"]
            else:
                lines = ["WORK GOES ON", hl(bd["name"])]
            secs = 4.2 if big else 5.4
            caps.append({"lines": lines, "t0": t, "t1": t + secs - 0.4})
            progress.append({"label": bd["name"], "from": prog["from"], "to": 1.0 if done else prog["to"],
                             "right": "{pct}", "t0": t, "t1": t + secs, "fill_s": secs - 1.4})
            sfx.append((t, "chime"))
            t += secs
        elif kind == "slot" and b["slot"] == "next":
            nxt = report.get("next")
            if not nxt:
                continue
            caps.append({"lines": [f"*{nxt['more']}* MORE", "UNLOCK THE", hl(nxt["name"])], "t0": t, "t1": t + 3.6})
            progress.append({"label": "NEXT: " + nxt["name"], "from": s["followers"] / nxt["at"], "to": s["followers"] / nxt["at"],
                             "right": f"{s['followers']}/{nxt['at']}", "t0": t, "t1": t + 3.6})
            if nxt["id"] == "beacon":
                beacon_ghost = (t, t + 6.6)
                cam_to(_cam_for(scene.BEACON_X))
            t += 3.6
        elif kind == "slot" and b["slot"] == "ask":
            cam_to(0) if cam[-1][1] else None
            caps.append({"lines": ["COMMENT TO", "*MOVE IN*"], "t0": t, "t1": t + 3.0})
            sfx.append((t, "blip"))
            t += 3.0
        elif kind == "caption":
            caps.append({"lines": b["lines"], "t0": t, "t1": t + secs})
            t += secs
        elif kind == "event":
            events.append({"kind": b["event"], "t0": t, "t1": t + secs})
            if b.get("lines"):
                caps.append({"lines": b["lines"], "t0": t, "t1": t + secs})
            sfx.append((t, "chime" if b["event"] in ("signal", "aurora") else "land"))
            t += secs
        elif kind in ("say", "feature"):
            r = resolve(str(b.get("who", "")), s, report)
            if not r:
                continue
            name, k = r
            if cam[-1][1]:
                cam_to(0)
            if k:
                spot(k)
            handle = people[k]["handle"] if k else name
            if kind == "say":
                bubbles.append({"who": handle, "text": b["text"], "t0": t, "t1": t + secs})
                sfx.append((t, "blip"))
            else:
                caps.append({"lines": b["lines"], "t0": t, "t1": t + secs})
                sfx.append((t, "chime"))
            tags[handle] = (t, t + secs)
            t += secs
        elif kind == "decision":
            r = resolve(str(b.get("who", "")), s, report)
            decision = (b, r)
            break  # the decision is the end of the episode

    # who's drawn: the crew, settlers with a moment at their spots, everyone else wandering
    settlers = [dict(c, look=CREW_LOOKS[c["name"]]) for c in CREW]
    for k, x in spotted.items():
        settlers.append({"name": people[k]["handle"], "job": "sit", "x": x, "look": look_for(s, k, ep)})
    for k in rules.featured(s, report, limit=12) + list(people):
        if k in spotted or k in named or k in paraded or any(x["name"] == people[k]["handle"] for x in settlers):
            continue
        st = people[k]
        row = {"name": st["handle"], "look": look_for(s, k, ep)}
        if st.get("job") == "build":
            row.update(job="carry", phase=len(settlers) * 13)
        settlers.append(row)
    for i in range(max(0, min(s["followers"], 30) - len(settlers))):  # followers who've never commented
        settlers.append({"name": f"~{i}"})
    side = {
        "seed": seed, "count": max(0, s["followers"] - len(named)), "settlers": settlers[:40],
        "buildings": buildings, "heaters": [61], "camera": cam, "arrivals": arrivals, "tags": tags,
        "bubbles": bubbles, "progress": progress, "parades": parades, "beacon_ghost": beacon_ghost, "captions": caps, "events": events,
        "duration": round(t, 2), "building_now": (0, t),
    }
    shots = [{"view": "side", "spec": side, "dur": round(t, 2)}] if t > 0 else []
    if decision:
        b, r = decision
        shots.append({"view": "inside", "spec": inside_spec(s, report, ep, b, r), "dur": 6.0})
        sfx.append((t, "chime"))
        t += 6.0
    if big:  # open on the planet: every new settler's light coming on
        planet = surge_spec(s, report, seed)
        shots.insert(0, {"view": "planet", "spec": planet, "dur": SURGE_SECS})
        sfx = planet["sfx"] + [(a + SURGE_SECS, k) for a, k in sfx]
        t += SURGE_SECS
    return {"shots": shots, "duration": round(t, 2), "sfx": sfx,
            "caption": (ep or {}).get("caption") or default_caption(s, report, decision)}


SURGE_SECS = 7.0
MAX_LIGHTS = 4000  # past this, each light stands for several settlers


def surge_spec(s: dict, report: dict, seed: int = 7) -> dict:
    """The planet turning while the day's new followers come on as lights, in a random order."""
    after = s["followers"]
    before = max(0, after - report["joined"])
    scale = max(1.0, after / MAX_LIGHTS)
    lights, lights_from = int(after / scale), int(before / scale)
    n = report["joined"]
    sfx = [(0.6, "chime")] + [(1.0 + i * 0.32, "blip") for i in range(14)] + [(5.6, "chime")]
    return {"seed": seed, "count": after, "count_from": before, "lights": lights, "lights_from": lights_from,
            "surge": (0.9, 5.4), "lon0": -0.2, "spin": -0.03, "title": True, "scale": scale, "sfx": sfx,
            "captions": [{"lines": [f"*+{n:,}*", "NEW SETTLERS", "IN ONE DAY"], "t0": 1.2, "t1": SURGE_SECS}]}


def inside_spec(s: dict, report: dict, ep: dict | None, b: dict, r) -> dict:
    """A decision, inside a dome: who decides, with a crew member, and the question on screen."""
    people = []
    name, k = r if r else ("EVERYONE", None)
    if k:
        people.append({"name": s["settlers"][k]["handle"], "x": 30, "flip": True, "look": look_for(s, k, ep)})
    people.append({"name": "MAREN", "x": 64, "flip": True, "look": CREW_LOOKS["MAREN"]})
    choices = [tuple(c) for c in b["choices"]]
    lines = list(b["lines"])
    return {"people": people, "tags": [s["settlers"][k]["handle"]] if k else [],
            "question": {"t0": 0, "lines": lines, "choices": choices},
            "captions": [{"lines": ["COMMENT " + " OR ".join(c[0] for c in choices)], "t0": 3.0, "t1": 6.0}]}


def default_caption(s: dict, report: dict, decision=None) -> str:
    """The post's caption when no writer has written one: what happened, and how to join in."""
    parts = []
    n = len(report["arrived"])
    if n:
        names = ", ".join("@" + s["settlers"][k]["handle"] for k in report["arrived"][:3] if k in s["settlers"])
        parts.append(f"{n} new settler{'s' if n != 1 else ''} on Farside: {names}{' and more' if n > 3 else ''}.")
    if report.get("finished"):
        parts.append(f"The {rules.BY_ID[report['finished']]['name'].title()} is finished.")
    elif report.get("progress"):
        p = report["progress"]
        parts.append(f"The {rules.BY_ID[p['id']]['name'].title()} is {int(p['to'] * 100)}% built.")
    if report.get("next"):
        parts.append(f"{report['next']['more']} more followers unlock the {report['next']['name'].title()}.")
    if decision:
        b = decision[0]
        parts.append("Decide in the comments: " + " or ".join(f"{c[0]} ({c[1].title()})" for c in b["choices"]) + ".")
    parts.append("Follow and comment to move in. Comment FARM, BUILD, SCOUT, GUARD or TINKER to pick your job.")
    return " ".join(parts)
