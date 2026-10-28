"""Race commentary: lines of light-hearted text that call what's happening, shown during the race.

Built from the race itself (lead changes, spins, punctures, pit stops, tangles, breakdowns, the
last lap, close battles, runaway leaders, whoever's last), so every line is true. The moments are
ranked; the best ones get the screen for HOLD seconds each, and quiet stretches are filled with a
word about one of the cars. Wording is picked with the race's seed, so a re-render says the same.
"""
from __future__ import annotations

import random

import numpy as np

from .sim import CARS, FPS

HOLD = 2.6  # seconds a line stays up
GAP = 0.25  # between lines

LINES = {
    "start": ["And they're off! {a} gets the best start.", "Lights out! {a} is away like a rocket.",
              "Green flag! {a} leads them into the first corner."],
    "drag_start": ["{a} launches like it's late for work.", "{a} is off the line first. Rude, but effective."],
    "lead": ["{a} takes the lead! {b} did not read that in the brochure.", "{a} is past {b} for the lead. Cheeky!",
             "New leader: {a}! {b} is checking the mirrors in disbelief.", "{a} sneaks by {b}. The pit wall goes wild."],
    "spin": ["{a} spins! Somebody check the tyres. And the driver.", "{a} does a full 360. Ten out of ten for style.",
             "{a} has gone for a little twirl.", "Round and round goes {a}. Where it stops, nobody knows.",
             "{a} is facing the wrong way. Bold strategy.", "{a} spins! The marshals have seen this one before.",
             "{a} goes sideways. The crowd loves it. The team doesn't.", "Oops! {a} takes the long way round."],
    "puncture": ["{a} has a puncture. That's not a tyre, that's a pancake.",
                 "Bad news for {a}: one of those tyres has given up on life."],
    "pit": ["{a} pits. Four tyres and a quick sandwich.", "{a} dives into the pits. Crew, look busy!",
            "{a} is in for fresh rubber.", "{a} stops for tyres. And possibly a biscuit.",
            "Pit stop for {a}. Off come the old boots."],
    "slow_pit": ["{a}'s crew can't find the wheel gun. It was in the other pocket.",
                 "A slow stop for {a}. Someone's getting a stern talking-to."],
    "tangle": ["{a} meets the crossing at exactly the wrong moment.", "Traffic at the crossing! {a} comes off worst.",
               "{a} and the figure 8: a complicated relationship."],
    "blowup": ["Smoke from {a}! That engine has gone to the big garage in the sky.",
               "{a} is out! Something important just fell off.", "Engine failure for {a}. Oh dear, oh dear."],
    "jumpstart": ["{a} jumped the lights. Eager! Disqualified, but eager.",
                  "{a} went before green. The officials are not amused."],
    "last_lap": ["Last lap! {a} leads by {gap}.", "Bell lap! {a} is {gap} clear. Can anyone catch them?"],
    "battle": ["{b} is close enough to read {a}'s number plate.", "{a} and {b}: nose to tail, nobody blinking.",
               "{b} is all over the back of {a}!"],
    "runaway": ["{a} is so far ahead they've had time for a cuppa.", "{a} is in a different postcode.",
                "{a} is {gap} clear. The rest are racing for second."],
    "last": ["{a} is taking the scenic route.", "{a} brings up the rear. Steady does it.",
             "{a}: last, but looking very shiny."],
    "drag_mid": ["{a} and {b}, side by side down the strip!", "Quarter of a mile, about ten seconds. Blink and you miss it."],
}
FLAVOUR = {
    1: ["Red Rocket: all engine, very little patience.", "Red Rocket loves a straight. Corners, less so."],
    2: ["Mean Green treats corners like a personal hobby.", "Mean Green: grip for days."],
    3: ["Custard: smooth as... well, custard.", "Custard does everything nicely. Very nicely."],
    4: ["Blue Streak's acceleration is frankly suspicious.", "Blue Streak: zero to rude in no time."],
    5: ["Hot Pink: tyres that last longer than most marriages.", "Hot Pink will still be going at teatime."],
    6: ["Cyanara is nimble. Annoyingly nimble.", "Cyanara likes it twisty."],
}


def _name(no: int) -> str:
    return CARS[no - 1]["name"].title()


def _gap(s: float) -> str:
    return f"{s:.1f} seconds" if s < 60 else f"{int(s // 60)} min {int(s % 60)} s"


def moments(race: dict) -> list[tuple[float, int, str, dict]]:
    """(video time, priority, kind, values) for everything worth a line."""
    dist = np.array(race["dist"])
    nos = [c["no"] for c in CARS]
    laps = race["laps"]
    lap_time = race["winner_time"] / max(laps, 1)
    vfin = {int(k): v for k, v in race["vtimes"].items()}
    out_at = {e["car"]: e["t"] for e in race["events"] if e["kind"] in ("blowup", "jumpstart")}
    end = race["race_end"] - 1.6  # the finish has its own screen
    drag = race["format"]["launch"]
    found: list[tuple[float, int, str, dict]] = []

    def order(k: int) -> list[int]:
        t = k / FPS
        alive = [j for j in range(6) if not (nos[j] in out_at and out_at[nos[j]] <= t)]
        return sorted(alive, key=lambda j: (-(dist[k, j] if not (vfin.get(nos[j]) and vfin[nos[j]] <= t) else laps + 1
                                              - vfin[nos[j]] / 1000)))

    first = order(min(len(dist) - 1, int(1.2 * FPS)))
    found.append((0.3, 3, "drag_start" if drag else "start", {"a": nos[first[0]]}))
    for e in race["events"]:
        kind = e["kind"]
        if kind == "pit" and e.get("dur", 0) > 27:
            kind = "slow_pit"
        pr = {"blowup": 6, "jumpstart": 6, "tangle": 5, "puncture": 5, "spin": 5, "slow_pit": 5, "pit": 2}[kind]
        found.append((max(0.3, e["t"]), pr, kind, {"a": e["car"]}))
    leader, held = None, 0
    for k in range(0, len(dist), 6):
        t = k / FPS
        o = order(k)
        if leader is not None and o[0] != leader:
            held += 1
            if held >= 3 and t > 3.0 and not drag:  # the new leader has stayed in front for a moment
                found.append((t - 0.4, 4, "lead", {"a": nos[o[0]], "b": nos[leader]}))
                leader, held = o[0], 0
        else:
            held = 0
            leader = o[0] if leader is None else leader
        if not drag and k % (2 * FPS) == 0 and t > 2 and len(o) > 1:
            gap = (dist[k, o[0]] - dist[k, o[1]]) * lap_time
            if gap < 0.5:
                found.append((t, 2, "battle", {"a": nos[o[0]], "b": nos[o[1]]}))
            elif gap > 6:
                found.append((t, 1, "runaway", {"a": nos[o[0]], "gap": _gap(gap)}))
    if laps > 1:
        lead_d = dist.max(axis=1)
        k = int(np.argmax(lead_d >= laps - 1))
        if lead_d[k] >= laps - 1:
            o = order(k)
            gap = (dist[k, o[0]] - dist[k, o[1]]) * lap_time if len(o) > 1 else 0
            found.append((k / FPS, 4, "last_lap", {"a": nos[o[0]], "gap": _gap(gap)}))
    if drag:
        found.append((race["race_end"] * 0.45, 3, "drag_mid", {"a": nos[first[0]], "b": nos[first[1]]}))
    else:
        mid = int(len(dist) * 0.55)
        found.append((mid / FPS, 1, "last", {"a": nos[order(mid)[-1]]}))
    return [m for m in found if m[0] < end]


def lines(race: dict, seed: int) -> list[dict]:
    """The commentary: [{t, until, text, car}] in video seconds, never overlapping."""
    rng = random.Random(seed)
    used: set[str] = set()
    placed: list[dict] = []

    def say(kind_or_text: str, values: dict, t: float, car: int | None, flavour: bool = False) -> bool:
        for shift in (0.0, 0.4, 0.8, 1.2):
            start = t + shift
            if start + HOLD > race["race_end"] - 0.2:
                return False
            if all(start + HOLD + GAP <= p["t"] or start >= p["until"] + GAP for p in placed):
                if flavour:
                    text = kind_or_text
                else:
                    opts = [x for x in LINES[kind_or_text] if x not in used] or LINES[kind_or_text]
                    pick = rng.choice(opts)
                    used.add(pick)
                    text = pick.format(**{k: (_name(v) if k in "ab" else v) for k, v in values.items()})
                placed.append({"t": round(start, 2), "until": round(start + HOLD, 2), "text": text, "car": car})
                return True
        return False

    end = race["race_end"] - 1.6
    for t, _, kind, values in sorted(moments(race), key=lambda m: (-m[1], m[0])):
        say(kind, values, t, values.get("a"))
    t = 1.0
    cars = list(FLAVOUR)
    rng.shuffle(cars)
    while t < end - HOLD and cars:  # quiet stretches: a word about one of the cars
        if say(rng.choice(FLAVOUR[cars[-1]]), {}, t, cars[-1], flavour=True):
            cars.pop()
            t += HOLD + GAP
        else:
            t += 0.5
    return sorted(placed, key=lambda p: p["t"])

