"""Parts the routine draws when the kit hasn't got something (app/render/colony/custom.py)."""
from datetime import date, timedelta

import numpy as np

from app.colony import inbox, plan, replay, today
from app.render.colony import custom, kit

DRAGON = replay.DRAWS["dragon"][0]
GHOST = replay.DRAWS["ghost"][0]
TRICORN = replay.DRAWS["pirate"][0]


def test_a_good_part_passes_and_bad_ones_say_why():
    assert custom.check(DRAGON, kit.KIT) == []
    too_big = {**DRAGON, "rows": ["g" * 20] * 3}
    assert any("at most 10 wide" in p for p in custom.check(too_big, kit.KIT))
    no_colour = {**DRAGON, "rows": ["zzzz"]}
    assert any("no colour for 'z'" in p for p in custom.check(no_colour, kit.KIT))
    taken = {**DRAGON, "id": "cat"}
    assert any("already a pet called 'cat'" in p for p in custom.check(taken, kit.KIT))
    empty = {**DRAGON, "rows": ["...", ".g."]}
    assert any("draw something" in p for p in custom.check(empty, kit.KIT))
    assert any("slot must be" in p for p in custom.check({**DRAGON, "slot": "wings"}, kit.KIT))


def test_colours_snap_to_the_house_palette():
    near = custom.snap("#61f4e1")  # nearly crys0
    assert np.allclose(near, custom.snap("crys0")) and custom.snap("not a colour") is None


def test_drawn_parts_join_the_kit_and_draw_in_every_slot():
    for part in (DRAGON, GHOST, TRICORN,
                 {"slot": "held", "id": "balloon", "colors": {"r": "#f05a8a", "s": "metal1"}, "rows": [".rr", "rrr", ".rr", ".s.", ".s."]},
                 {"slot": "back", "id": "wings", "colors": {"w": "ui"}, "rows": ["w..", "ww.", "www", "ww."]},
                 {"slot": "carrier", "id": "rocket", "colors": {"m": "metal0", "f": "coil", "k": "ink"},
                  "rows": ["...mmm...", "..mmmmm..", "kmmmmmmmk", "kmmmmmmmk", "..f.f.f.."]}):
        custom.save(part, "@someone", "2026-11-10")
        look = {part["slot"]: part["id"]}
        assert kit.validate(look) == [] and part["id"] in kit.ids(part["slot"])
        spr = kit.compose(look, 1)
        assert spr.w == kit.GW and spr.h == kit.GH
    assert kit.pet_sprite("dragon", 1) is not None
    ghost = kit.compose({"costume": "ghost"})
    assert "S" not in ghost.layers  # a costume replaces the settler entirely


def test_a_blocked_part_is_never_drawn_again():
    custom.save(DRAGON, "@x", "2026-11-10")
    assert custom.block("pet", "dragon")
    assert "dragon" not in kit.ids("pet") and kit.full({"pet": "dragon"})["pet"] == "none"


def test_the_daily_episode_can_bring_new_parts_and_they_land_in_the_kit():
    inbox.add([{"id": "r1", "user": "nova.k", "uid": "1", "text": "can I have a pet dragon",
                "at": "2026-11-09T12:00:00+00:00", "platform": "instagram"}])
    day = date(2026, 11, 9)
    early = today.deadline(day) - timedelta(hours=2)
    ctx = today.context(day, now=early)
    assert ctx["draw"]["boxes"]["pet"] == {"max_width": 10, "max_height": 8} and "crys0" in ctx["draw"]["palette"]
    ep = {"beats": [{"type": "slot", "slot": "arrivals"}], "caption": "x",
          "settlers": {"@nova.k": {"look": {"pet": "dragon"}}}, "parts": [DRAGON]}
    assert today.accept(day, ep, now=early) == []
    assert "dragon" in kit.ids("pet") and custom.get("pet", "dragon")["requested_by"] == "@nova.k"
    assert (today._dir("kit-previews") / "pet-dragon.png").exists()
    # the next day it's just part of the kit
    assert "dragon" in today.context(day + timedelta(days=1), now=early + timedelta(days=1))["kit"]["pet"]


def test_too_many_new_parts_in_a_day_is_refused():
    parts = [{**DRAGON, "id": f"dragon{i}"} for i in range(custom.MAX_NEW_A_DAY + 1)]
    probs = plan.check_episode({"beats": [{"type": "slot", "slot": "ask"}], "caption": "x", "parts": parts}, set(), adapted=True)
    assert any("at most 5 new parts" in p for p in probs)
