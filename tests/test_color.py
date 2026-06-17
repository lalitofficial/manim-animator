"""Color + fill foundation (cartoon branch): drawables can carry per-part fill and
line color; the renderer fills closed shapes. Whiteboard (no color) is unchanged.
"""

from __future__ import annotations

from engine import geometry as g
from engine import icons
from engine.contracts import Board, Stroke
from engine.serialize import stroke_to_dict
from engine.svg import _polyline


def test_recipe_applies_fill_and_line_color():
    strokes = icons.render_recipe(
        {"parts": [{"prim": "circle", "r": 0.5, "fill": "#ffd23f", "stroke": "#e09f00"}]}
    )
    assert strokes[0].fill == "#ffd23f" and strokes[0].color == "#e09f00"


def test_transform_preserves_color_and_fill():
    s = Stroke(((0, 0), (1, 0), (1, 1)), closed=True, color="#111", fill="#abc")
    t = g.transform([s], 1.0, 1.0, 2.0)[0]
    assert t.color == "#111" and t.fill == "#abc" and t.closed


def test_svg_fills_closed_shapes_only():
    filled = Stroke(((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)), True, "#000", "#ffd23f")
    out = _polyline(filled, "#fff", Board())
    assert "<polygon" in out and "#ffd23f" in out and "#000" in out
    outline = Stroke(((0, 0), (1, 1)), closed=False)
    assert 'fill="none"' in _polyline(outline, "#fff", Board())  # whiteboard unchanged


def test_serialize_only_emits_color_when_set():
    colored = stroke_to_dict(Stroke(((0, 0), (1, 1)), color="#111", fill="#abc"))
    assert colored["color"] == "#111" and colored["fill"] == "#abc"
    mono = stroke_to_dict(Stroke(((0, 0), (1, 1))))
    assert "color" not in mono and "fill" not in mono  # whiteboard: no color keys on the wire
