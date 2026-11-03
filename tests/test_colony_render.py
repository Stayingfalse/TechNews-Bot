"""The colony look test's renderer: frames are the right size, the same every time, and the
captions and title stay inside the area Instagram's overlays leave clear."""
import numpy as np

import render_colony
from app.render.colony import pixfont, scene
from app.render.colony.art import SAFE


def test_frames_are_1080x1920_and_repeatable():
    spec = render_colony.day_spec()
    a, b = scene.draw(spec, 7.0).frame(), scene.draw(spec, 7.0).frame()
    assert a.shape == (1920, 1080, 3) and np.array_equal(a, b)


def test_every_caption_fits_the_safe_area():
    for spec in (render_colony.day_spec(), render_colony.day0_spec()):
        for cap in spec["captions"]:
            scale = min(scene.fit_scale(l.replace("*", "")) for l in cap["lines"])
            for line in cap["lines"]:
                assert pixfont.width(line.replace("*", ""), scale) <= SAFE[2] - SAFE[0], line


def test_every_glyph_is_5x7():
    assert all(g.shape == (7, 5) for g in pixfont.GLYPHS.values())


def test_the_other_views_render_at_full_size():
    from app.render.colony import views

    vs = render_colony.view_specs()
    for name, (kind, t, spec) in vs.items():
        draw = {"topdown": views.draw_topdown, "inside": views.draw_inside, "planet": views.draw_planet}[kind]
        assert draw(spec, t).frame().shape == (1920, 1080, 3), name
