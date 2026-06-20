"""Deterministic math-equation rendering: mathtext -> filled board strokes -> the math rung.

Hermetic: matplotlib renders locally + reproducibly (no network, bundled fonts).
"""

from __future__ import annotations

from engine import drawing, mathtext
from engine.contracts import Extent, Thing


def test_as_expression_detects_math_not_nouns():
    assert mathtext.as_expression("E = mc^2") == "$E = mc^2$"
    assert mathtext.as_expression("a^2 + b^2 = c^2")
    assert mathtext.as_expression("$x_i$") == "$x_i$"
    # plain nouns must NOT be treated as equations
    assert mathtext.as_expression("photosynthesis") is None
    assert mathtext.as_expression("cat") is None


def test_render_equation_to_filled_strokes():
    strokes = mathtext.render("E = mc^2")
    assert strokes, "equation produced no strokes"
    assert any(s.closed and s.fill for s in strokes)  # SOLID glyphs, not hollow outlines
    assert mathtext.render("just a plain noun") == ()  # non-expression -> nothing


def test_equation_resolves_through_measure_as_generated():
    # the deterministic math rung is always on — even generate=False (the live placeholder path)
    drawing._cache.clear()
    d = drawing.measure(Thing("e", "a^2 + b^2 = c^2", Extent(2, 1)), generate=False)
    assert d.source == "generated" and d.rung == 3 and d.strokes
