"""The colony look test (docs/COLONY_PLAN.md, M1): three stills and a 25 s video.

    python render_colony.py out/colony            # stills + video
    python render_colony.py out/colony --stills   # stills only
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from app.render.colony import scene, sound
from app.render.colony.art import SKINS, SUITS

FPS = 30
CREW = [  # the founding crew: our own characters, there before any viewer
    {"name": "MAREN", "suit": "e8e2d0", "skin": SKINS[1], "job": "sit", "x": 54},
    {"name": "TOLU", "suit": "f2a33a", "skin": SKINS[3], "job": "sit", "x": 68, "flip": True},
    {"name": "BASK", "suit": "4fb3a8", "skin": SKINS[0], "job": "carry", "phase": 0},
    {"name": "IKO", "suit": "d65a5a", "skin": SKINS[2]},
]
VIEWERS = ["nova.k", "pixelpip", "mossbyte", "astra_lou", "quietkettle", "remy.out", "dunebug", "hal9001fan",
           "orbit.olly", "saltwick", "teapot_tom", "lunaria", "kestrel88", "zed.makes", "fernhollow",
           "milo.spins", "ivy_and_ink", "copperjay", "gnomebody", "sol.rae", "bramblecat", "vexley", "ottoloop",
           "wrenfield", "skyemarr", "jupi.ter", "pebbleface", "nightowl.jo", "bytebaker", "lowtide_lu"]


def day_spec() -> dict:
    """A normal day: three newcomers land, the greenhouse goes up, the next goal is the beacon."""
    settlers = [dict(c) for c in CREW]
    for i, n in enumerate(VIEWERS):
        s = {"name": n}
        if i in (3, 9):
            s.update(job="carry", phase=i * 11)
        settlers.append(s)
    return {
        "seed": 7,
        "count": len(settlers),
        "settlers": settlers,
        "buildings": [{"kind": "dome"},
                      {"kind": "greenhouse", "from": 0.48, "to": 0.62, "t0": 10.0, "t1": 16.0}],
        "building_now": (9.5, 16.5),
        "heaters": [61],
        "camera": [(0, 0), (8.6, 0), (10.2, 50), (16.5, 50), (18.0, 80), (25, 80)],
        "arrivals": [
            {"name": "grimble.g", "x": 138, "land": 2.4, "walk": -14, "suit": SUITS[4], "skin": SKINS[0]},
            {"name": "oldbarrel", "x": 80, "land": 3.6, "walk": -6, "look": "barrel"},
            {"name": "juno.sails", "x": 122, "land": 4.8, "walk": 12, "suit": SUITS[5], "skin": SKINS[2]},
        ],
        "tags": {"MAREN": (6.4, 8.6), "TOLU": (6.4, 8.6), "BASK": (11.0, 16.0), "astra_lou": (11.0, 16.0)},
        "bubbles": [{"who": "oldbarrel", "text": "I'LL TAKE THE|DRAFTY CORNER.", "t0": 5.8, "t1": 8.8}],
        "progress": [{"label": "GREENHOUSE", "from": 0.48, "to": 0.62, "right": "{pct}", "t0": 9.6, "t1": 17.4, "fill_s": 6.0},
                     {"label": "NEXT: BEACON", "from": 37 / 50, "to": 37 / 50, "right": "37/50", "t0": 17.6, "t1": 25.0}],
        "beacon_ghost": (17.6, 25.0),
        "captions": [
            {"lines": ["3 SIGNALS", "*ANSWERED*"], "t0": 0.0, "t1": 5.6},
            {"lines": ["WELCOME TO", "*FARSIDE*"], "t0": 5.8, "t1": 9.2},
            {"lines": ["*14* SHARES", "= *14* PANES"], "t0": 9.6, "t1": 17.4},
            {"lines": ["*13* MORE", "LIGHT THE", "*BEACON*"], "t0": 17.6, "t1": 21.9},
            {"lines": ["ANSWER THE", "*SIGNAL*"], "t0": 22.0, "t1": 25.0},
        ],
        "duration": 25.0,
        "sfx": [(2.4, "land"), (3.6, "land"), (4.8, "land"), (5.8, "blip"), (9.6, "chime"), (17.6, "chime"),
                (22.0, "blip")],
    }


def day0_spec() -> dict:
    """Day 0: the pod has just landed, the crew's first night, nobody else yet."""
    crew = [dict(CREW[0]), dict(CREW[1]), {**CREW[2], "job": "sit", "x": 84}, {**CREW[3], "job": "sit", "x": 98, "flip": True}]
    return {"seed": 7, "count": 4, "settlers": crew, "buildings": [], "heaters": [61], "ambient": 0.5,
            "tags": {"MAREN": (0, 99), "TOLU": (0, 99), "BASK": (0, 99), "IKO": (0, 99)},
            "captions": [{"lines": ["FOUR OF US.", "*FOR NOW.*"], "t0": 0, "t1": 99}], "duration": 1}


def view_specs() -> dict:
    """The other three views, at the size the colony might reach in a few months."""
    return {
        "5-topdown": ("topdown", 4.0, {
            "seed": 7, "count": 1284, "walkers": 160, "named": ["astra_lou", "kestrel88"],
            "camera": [(0, (120, 70))], "site": (262, 222, 11), "labels": {"NEW DOME?": (262, 206)},
            "captions": [{"lines": ["WHERE'S THE", "*NEW* *DOME?*"], "t0": 0, "t1": 99}]}),
        "6-inside": ("inside", 3.0, {
            "people": [("mossbyte", 30, True, SUITS[2], SKINS[2]), ("MAREN", 64, True, "e8e2d0", SKINS[1])],
            "elder": "oldbarrel", "tags": ["mossbyte"],
            "bubbles": [{"who": "oldbarrel", "text": "DON'T.|TRUST ME.", "t0": 0, "t1": 99}],
            "question": {"t0": 0, "lines": ["*@MOSSBYTE*", "FOUND A", "SEALED DOOR"], "choices": [("A", "OPEN IT"), ("B", "LEAVE IT")]}}),
        "7-planet": ("planet", 6.0, {
            "seed": 7, "count": 1284, "lights": 1284, "spin": 0.12, "lon0": -0.4,
            "captions": [{"lines": ["EVERY LIGHT", "IS *SOMEONE*"], "t0": 0, "t1": 99}]}),
    }


def cuts_video(path: Path) -> None:
    """One episode cutting between the views: planet → top-down → side-on → inside, ~14 s."""
    from app.render.colony import views
    vs = view_specs()
    day = day_spec()
    shots = [(views.draw_planet, vs["7-planet"][2], 0.0, 3.5),
             (views.draw_topdown, {**vs["5-topdown"][2], "camera": [(0, (150, 20)), (3.5, (110, 80))]}, 0.0, 3.5),
             (scene.draw, day, 3.0, 3.5),
             (views.draw_inside, vs["6-inside"][2], 0.0, 3.5)]
    total = sum(d for *_, d in shots)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", str(path)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for draw, spec, t0, dur in shots:
        n = int(dur * FPS)
        for i in range(n):
            f = draw(spec, t0 + i / FPS).frame()
            edge = min(i, n - 1 - i) / (0.25 * FPS)  # a quick pixel iris at each cut
            if edge < 1:
                blk = int((1 - edge) * 40) * 6 + 6
                small = f[::blk, ::blk]
                f = small.repeat(blk, 0).repeat(blk, 1)[:1920, :1080]
            ff.stdin.write(np.ascontiguousarray(f).tobytes())
    ff.stdin.close()
    ff.wait()


def still(spec: dict, t: float, path: Path) -> None:
    Image.fromarray(scene.draw(spec, t).frame()).save(path)


def video(spec: dict, path: Path) -> None:
    from app.render.colony import video as vid
    vid.render({"shots": [{"view": "side", "spec": spec, "dur": spec["duration"]}], "duration": spec["duration"],
                "sfx": spec.get("sfx", [])}, path)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out/colony")
    out.mkdir(parents=True, exist_ok=True)
    day = day_spec()
    still(day0_spec(), 0.5, out / "1-day0.png")
    still(day, 7.0, out / "2-arrivals.png")
    still(day, 13.5, out / "3-building.png")
    still(day, 20.0, out / "4-next-goal.png")
    from app.render.colony import views
    for name, (kind, t, spec) in view_specs().items():
        draw = {"topdown": views.draw_topdown, "inside": views.draw_inside, "planet": views.draw_planet}[kind]
        Image.fromarray(draw(spec, t).frame()).save(out / f"{name}.png")
    if "--stills" not in sys.argv:
        cuts_video(out / "colony-views.mp4")
        video(day, out / "colony-look-test.mp4")
    print(json.dumps(sorted(p.name for p in out.iterdir())))


if __name__ == "__main__":
    main()
