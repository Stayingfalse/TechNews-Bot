"""The sprite kit: every settler is a look made of parts, and the writer can only pick parts that
are here (docs/COLONY_PLAN.md §5a). A request the kit can't draw uses the nearest parts and is
logged as "wanted"; new parts are added to this file.

A look is a dict, slot → part id, e.g.
    {"body": "old", "suit": "orange", "skin": "s1", "helmet": "bowl", "hair": "none",
     "beard": "white", "hat": "none", "held": "none", "carrier": "barrel", "back": "none", "pet": "none"}
Missing slots take the default. `compose(look, frame)` gives the Sprite; `pet_sprite` the pet."""
from __future__ import annotations

from .art import P, Sprite, hexc

SUITS = {"white": "e8e2d0", "orange": "f2a33a", "teal": "4fb3a8", "red": "d65a5a", "blue": "7aa0e8",
         "yellow": "e6d34a", "purple": "b07ad6", "green": "9be07a", "black": "3a3448", "pink": "f29ac2"}
SKINS = {"s1": "f1c9a5", "s2": "d9a47a", "s3": "a86b48", "s4": "6e4430", "green": "8fd18a", "blue": "8fb6e6"}
HAIRS = {"none": None, "short": "5a3a22", "long": "3a2418", "white": "f0ece4", "ginger": "d0702e",
         "pink": "f07ac8", "mohawk": "62f5e2", "bun": "2a1a12"}

KIT: dict[str, list[str]] = {
    "body": ["adult", "kid", "tall", "old"],
    "suit": list(SUITS),
    "skin": list(SKINS),
    "helmet": ["bowl", "visor", "mask"],
    "hair": list(HAIRS),
    "beard": ["none", "white", "brown", "moustache"],
    "hat": ["none", "beanie", "cap", "antenna", "flower", "crown", "chef", "wizard", "bow", "horns", "tophat"],
    "held": ["none", "wrench", "mug", "lantern", "plant", "book", "flag", "rod", "umbrella", "toysword"],
    "carrier": ["none", "barrel", "crate", "hoverchair"],
    "back": ["pack", "none", "cape", "scarf", "jetpack"],
    "pet": ["none", "cat", "drone", "slug", "bird", "dog"],
    "costume": ["none"],  # a whole-body drawing (a ghost, a dragon) that replaces the settler; drawn ones only
}
DEFAULT = {slot: ids[0] for slot, ids in KIT.items()}
DEFAULT.update(suit="white", skin="s2", hair="short")

GW, GH = 17, 20  # the grid a settler is drawn on; the body's feet are on the bottom row
OX = 5  # body's left column (the body is 7 wide, centred, so flipping keeps it in place)


def ids(slot: str) -> list[str]:
    """The parts a slot has: the built-in ones and any drawn by the routine (custom.py)."""
    from . import custom
    return KIT[slot] + [i for i in custom.ids(slot) if i not in KIT[slot]]


def current() -> dict[str, list[str]]:
    return {slot: ids(slot) for slot in KIT}


def validate(look: dict) -> list[str]:
    """What's wrong with a look: unknown slots or part ids."""
    probs = []
    for slot, part in (look or {}).items():
        if slot not in KIT:
            probs.append(f"unknown slot {slot!r} (slots: {', '.join(KIT)})")
        elif part not in ids(slot):
            probs.append(f"{slot}: unknown part {part!r} (one of: {', '.join(ids(slot))}; or draw it in `parts`)")
    return probs


def full(look: dict | None) -> dict:
    return {**DEFAULT, **{k: v for k, v in (look or {}).items() if k in KIT and v in ids(k)}}


class _Grid:
    def __init__(self):
        self.g = [["."] * GW for _ in range(GH)]
        self.cols: dict[str, object] = {}

    def put(self, rows: list[str], x: int, y: int, cols: dict | None = None):
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch != "." and 0 <= y + dy < GH and 0 <= x + dx < GW:
                    self.g[y + dy][x + dx] = ch
        self.cols.update(cols or {})

    def sprite(self) -> Sprite:
        return Sprite(["".join(r) for r in self.g], self.cols)


def _custom(slot: str, pid: str):
    if pid in KIT.get(slot, []):
        return None
    from . import custom
    return custom.get(slot, pid)


def compose(look: dict | None, frame: int = 0) -> Sprite:
    lk = full(look)
    costume = _custom("costume", lk["costume"])
    if costume:  # a whole-body drawing, feet on the ground, centred where the body would be
        from . import custom
        spr = custom.sprite(costume, frame)
        g = _Grid()
        x = OX + 3 - spr.w // 2
        rows = [costume["rows"], *(costume.get("frames") or [])][frame % (1 + len((costume.get("frames") or [])[:1]))]
        g.put(rows, x, GH - len(rows), {k: custom.snap(str(v)) for k, v in costume["colors"].items()})
        return g.sprite()
    suit, skin = hexc(SUITS[lk["suit"]]), hexc(SKINS[lk["skin"]])
    hair = HAIRS[lk["hair"]]
    g = _Grid()
    g.cols.update({"G": P["rim"], "g": P["glass"], "h": P["hi"], "s": skin, "E": P["eye"], "S": suit,
                   "A": suit * 0.8, "L": suit * 0.7, "B": P["metal3"], "P": P["metal2"]})
    body = lk["body"]
    torso = {"adult": 4, "kid": 2, "tall": 5, "old": 4}[body]
    legs = {"adult": 3, "kid": 2, "tall": 4, "old": 3}[body]
    head_h = 5
    ride = _custom("carrier", lk["carrier"])
    if ride:  # riding a drawn mount: no legs, sitting two rows into it
        legs = 0
        top = GH - len(ride["rows"]) + 2 - (head_h + torso)
    else:
        top = GH - (head_h + torso + legs)
    hx = OX + (1 if body == "old" else 0)
    hy = top + (1 if body == "old" else 0)

    # head and helmet
    if lk["helmet"] == "mask":
        g.put(["..HHH..", ".sssss.", ".sssEs.", ".sMMMs.", "..sss.."], hx, hy,
              {"H": hexc(hair) if hair else skin, "M": P["metal2"]})
    elif lk["helmet"] == "visor":
        g.put(["..GGG..", ".GVVVG.", ".GVvVG.", ".GVVVG.", "..GGG.."], hx, hy, {"V": P["metal3"], "v": P["crys0"]})
    else:
        g.put(["..GGG..", ".GhggG.", ".GgsEG.", ".GgssG.", "..GGG.."], hx, hy)
        if hair and lk["hair"] != "none":
            hc = {"H": hexc(hair)}
            pattern = {"short": [".", "..HH"], "long": [".", "..HH", "..H", "..H"], "white": [".", "..HH", "..H"],
                       "ginger": [".", "..HH", "..H"], "pink": [".", "..HHH"], "mohawk": [".", "...H"],
                       "bun": [".", "..HH"]}[lk["hair"]]
            g.put(pattern, hx, hy, hc)
            if lk["hair"] == "bun":
                g.put(["..H"], hx, hy - 1, hc)

    # hats sit on the helmet
    hat = lk["hat"]
    hats = {
        "beanie": (["...k...", "..KKK.."], {"K": hexc("d65a5a"), "k": P["ui"]}),
        "cap": (["..CCCCc"], {"C": hexc("3f7fd6"), "c": hexc("2a5aa0")}),
        "antenna": (["...a...", "...l...", "...l..."], {"a": P["crys1"], "l": P["metal1"]}),
        "flower": (["...f...", "..fyf.."], {"f": hexc("f56ad0"), "y": P["gold"]}),
        "crown": ([".y.y.y.", ".yyyyy."], {"y": P["gold"]}),
        "chef": (["..www..", ".wwwww.", ".wwwww.", "..www.."], {"w": P["ui"]}),
        "wizard": (["....p..", "...pp..", "..pyp..", "..ppp..", ".ppppp."], {"p": hexc("5a3ab0"), "y": P["gold"]}),
        "bow": (["..rRr.."], {"r": hexc("f05a8a"), "R": hexc("c03a6a")}),
        "horns": ([".h...h.", ".h...h."], {"h": P["ui"]}),
        "tophat": (["..ttt..", "..ttt..", "..TTT..", ".ttttt."], {"t": hexc("2a2238"), "T": hexc("b03a3a")}),
    }
    drawn = _custom("hat", hat)
    if drawn:  # centred on the head, its bottom row on the helmet's top
        from . import custom
        g.put(drawn["rows"], hx + 3 - max(len(r) for r in drawn["rows"]) // 2, hy + 1 - len(drawn["rows"]),
              {k: custom.snap(str(v)) for k, v in drawn["colors"].items()})
    elif hat in hats:
        rows, cols = hats[hat]
        g.put(rows, hx, hy - len(rows) + 1 if hat in ("horns",) else hy - len(rows), cols)

    # torso (or a carrier in its place)
    ty = top + head_h
    carrier = lk["carrier"]
    if carrier in ("barrel", "crate"):
        n = torso + legs
        if carrier == "barrel":
            rows = ["RRRRRRR"] + ["rrrrrrr" if i % 3 != 1 else "IIIIIII" for i in range(n - 2)] + [".rrrrr."]
            g.put(rows, OX, ty, {"R": P["wood1"], "r": P["wood0"], "I": P["iron"]})
        else:
            rows = ["#######"] + ["#x#x#x#" if i % 2 else "##x#x##" for i in range(n - 2)] + ["#######"]
            g.put(rows, OX, ty, {"#": P["wood0"], "x": P["wood1"]})
    else:
        trows = [".PSSSA."] * min(2, torso) + [".PSSS.."] * (torso - min(2, torso))
        g.put(trows, OX, ty)
        ly = ty + torso
        if ride:
            pass
        elif carrier == "hoverchair":
            g.put(["TTTTTTT", ".ttttt.", "..~.~.." if frame % 2 else ".~.~.~."][:legs] + [], OX, ly,
                  {"T": P["metal1"], "t": P["metal2"], "~": P["crys0"]})
        else:
            stance = [["..L.L.."] * (legs - 1) + [".BB.BB."],
                      ["...L..."] + ["..L.L.."] * (legs - 2) + [".B...B."]][frame % 2]
            g.put(stance[:legs], OX, ly)

    if ride:  # the mount, under them
        from . import custom
        rr = [ride["rows"], *(ride.get("frames") or [])][frame % (1 + len((ride.get("frames") or [])[:1]))]
        g.put(rr, OX + 3 - max(len(r) for r in rr) // 2, GH - len(rr), {k: custom.snap(str(v)) for k, v in ride["colors"].items()})

    # beards go over the body (and the barrel)
    beard = lk["beard"]
    if lk["helmet"] == "bowl" and beard in ("white", "brown"):
        g.put(["...", "...", "...", "..WWW", "..WWW", "...W"], hx, hy, {"W": P["beard"] if beard == "white" else hexc("6a4428")})
    elif lk["helmet"] == "bowl" and beard == "moustache":
        g.put(["...", "...", "...", "...WW"], hx, hy, {"W": hexc("4a3020")})

    # what's on their back
    back = lk["back"]
    if back == "none" or carrier in ("barrel", "crate"):
        for r in g.g:
            if r[OX + 1] == "P":
                r[OX + 1] = "S" if carrier not in ("barrel", "crate") else r[OX + 1]
    if back == "cape":
        g.put(["C", "C", "CC", "CC"][:torso + 1], OX, ty, {"C": hexc("b03a3a")})
    elif back == "scarf":
        g.put([".ffff", "f"], OX, ty, {"f": hexc("e6d34a")})
    elif back == "jetpack":
        g.put(["jj", "jj", "jj"][:torso], OX - 1, ty, {"j": P["metal1"]})
        g.put(["o"], OX - 1, ty + min(3, torso), {"o": P["warm1"] if frame % 2 else P["coil"]})

    # held in the front hand
    held = lk["held"]
    hy0 = ty + 1
    items = {
        "wrench": ([".n", "n.", "n."], {"n": P["metal0"]}),
        "mug": (["mm", "mM"], {"m": P["ui"], "M": hexc("8a5a32")}),
        "lantern": (["l.", "LL", "LL"], {"l": P["metal2"], "L": P["warm0"]}),
        "plant": (["c.", "cc", "pp"], {"c": P["crys2"], "p": hexc("8a5a32")}),
        "book": (["bb", "bb"], {"b": hexc("b03a3a")}),
        "flag": (["|FF", "|FF", "|..", "|..", "|.."], {"|": P["metal1"], "F": P["gold"]}),
        "rod": (["...r", "..r.", ".r..", "r..."], {"r": P["wood0"]}),
        "umbrella": (["uuuuu", "..|..", "..|..", "..|.."], {"u": hexc("f05a8a"), "|": P["metal2"]}),
        "toysword": (["w", "w", "w", "Y"], {"w": P["metal0"], "Y": P["gold"]}),
    }
    drawn_held = _custom("held", held)
    drawn_back = _custom("back", back)
    if drawn_back:
        from . import custom
        rows = drawn_back["rows"]
        g.put(rows, OX + 1 - max(len(r) for r in rows) + 1, ty - 1, {k: custom.snap(str(v)) for k, v in drawn_back["colors"].items()})
    if drawn_held:  # in the front hand: its bottom row at the hand
        from . import custom
        rows = drawn_held["rows"]
        g.put(rows, OX + 6, ty + 3 - len(rows) + 1, {k: custom.snap(str(v)) for k, v in drawn_held["colors"].items()})
    elif held in items:
        rows, cols = items[held]
        off = {"flag": -4, "umbrella": -6, "rod": -3, "toysword": -3}.get(held, 0)
        xo = OX + 6 - (2 if held == "umbrella" else 0)
        g.put(rows, xo, hy0 + off, cols)
    return g.sprite()


def pet_sprite(pet: str, frame: int = 0) -> Sprite | None:
    drawn = _custom("pet", pet)
    if drawn:
        from . import custom
        return custom.sprite(drawn, frame)
    pets = {
        "cat": ([".k.k", "kkkk", "k..k"] if frame % 2 else [".k.k", "kkkk", ".kk."], {"k": hexc("e6a060")}),
        "drone": (["=-=", ".o."], {"=": P["metal1"], "-": P["metal3"], "o": P["crys1"] if frame % 2 else P["crys0"]}),
        "slug": (["..e.", ".ss.", "ssss"], {"s": P["crys2"], "e": P["eye"]}),
        "bird": ([".bb.", "bbb>", ".l.."], {"b": hexc("7aa0e8"), ">": P["gold"], "l": P["gold"]}),
        "dog": (["d..", "dddd", "d..d"] if frame % 2 else ["d..", "dddd", ".dd."], {"d": hexc("c08a50")}),
    }
    if pet not in pets:
        return None
    rows, cols = pets[pet]
    return Sprite(rows, cols)


def count() -> int:
    """How many built-in parts the kit has (every id but the 'none's)."""
    return sum(len([i for i in v if i != "none"]) for v in KIT.values())
