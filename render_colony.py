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


def still(spec: dict, t: float, path: Path) -> None:
    Image.fromarray(scene.draw(spec, t).frame()).save(path)


def video(spec: dict, path: Path) -> None:
    n = int(spec["duration"] * FPS)
    first = scene.draw(spec, 0.0).frame().astype(np.float32)
    wav = path.with_suffix(".wav")
    sound.write(spec, wav)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
           "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(path)]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    blend = int(0.5 * FPS)  # the last half second fades into the first frame, so a replay loops
    for i in range(n):
        f = scene.draw(spec, i / FPS).frame()
        if i >= n - blend:
            k = (i - (n - blend) + 1) / blend
            f = (f * (1 - k) + first * k).astype(np.uint8)
        ff.stdin.write(f.tobytes())
    ff.stdin.close()
    if ff.wait():
        raise RuntimeError("ffmpeg failed")
    wav.unlink(missing_ok=True)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "out/colony")
    out.mkdir(parents=True, exist_ok=True)
    day = day_spec()
    still(day0_spec(), 0.5, out / "1-day0.png")
    still(day, 7.0, out / "2-arrivals.png")
    still(day, 13.5, out / "3-building.png")
    still(day, 20.0, out / "4-next-goal.png")
    if "--stills" not in sys.argv:
        video(day, out / "colony-look-test.mp4")
    print(json.dumps(sorted(p.name for p in out.iterdir())))


if __name__ == "__main__":
    main()
