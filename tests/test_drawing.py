"""Phase-2 gate (docs/ARCHITECTURE.md §9): Drawing measure/paint + route, run
end-to-end through the scene pipeline. Invariants stay output-derived.
"""

from __future__ import annotations

import pytest

from engine import drawing, invariants
from engine.contracts import Board, Placement, Thing
from engine.corpus import scenes
from engine.scene import render

BOARD = Board()
SCENES = scenes()


# --------------------------------------------------------------------------- #
# measure() — the ladder resolves concepts to honest extents, and memoizes.
# --------------------------------------------------------------------------- #
def test_parametric_extent_matches_geometry():
    d = drawing.measure(Thing("x", "circle", _e(), geometry_attrs={"radius": 0.8}))
    assert d.extent.w == pytest.approx(1.6, abs=0.05)
    assert d.extent.h == pytest.approx(1.6, abs=0.05)
    assert d.rung == 1


def test_measure_is_memoized():
    a = drawing.measure(Thing("a", "square", _e(), geometry_attrs={"size": 1.4}))
    b = drawing.measure(Thing("b", "square", _e(), geometry_attrs={"size": 1.4}))
    assert a is b  # same concept+geometry_attrs -> cached drawable


def test_backstop_is_labeled_box():
    drawing.set_sketch_lookup(lambda name: None)  # ensure no QuickDraw match
    d = drawing.measure(Thing("c", "chloroplast", _e()))
    assert d.rung == 6
    assert d.label == "chloroplast"
    assert d.strokes  # a box outline
    drawing.set_sketch_lookup(None)


def test_backstop_label_is_kinetic():
    """An un-drawable concept lands as the labeled-box backstop, and its label is flagged
    `kinetic` so the live board reveals it word-by-word (P2 — attention-holding typography)."""
    from engine.serialize import op_to_dict

    drawing.set_sketch_lookup(lambda name: None)  # force the backstop (no QuickDraw match)
    box = drawing.paint(Thing("c", "chloroplast", _e()), Placement("c", 0, 0, 1, 1))
    drawing.set_sketch_lookup(None)
    assert box.source == "box" and box.text_anim == "kinetic"
    assert op_to_dict(box)["text_anim"] == "kinetic"
    # a real drawing (a primitive) is NOT kinetic — it draws normally
    circ = drawing.paint(Thing("o", "circle", _e()), Placement("o", 0, 0, 1, 1))
    assert circ.source != "box" and circ.text_anim == ""


def test_stem_diagram_recipes_compose():
    # math/physics line diagrams (recipe rung, incl. aliases) compose, not the box backstop
    for concept in ("axes", "number line", "sine wave", "coordinate plane", "waveform"):
        d = drawing.measure(Thing("x", concept, _e()))
        assert d.source == "icon" and d.rung != 6 and d.strokes, concept


def test_quickdraw_sketch_resolves_to_rung2():
    """Rung 2: a cached QuickDraw concept becomes a real stroke drawing (not a box).
    Uses a non-icon concept + disables icons to isolate the catalog rung."""
    fake = {"name": "widget", "strokes": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
    drawing.reset()
    drawing.set_compose(lambda concept: None)  # isolate from the icon language
    drawing.set_catalog_lookup(lambda concept: None)  # ...and the catalog
    drawing.set_sketch_lookup(lambda name: fake if name == "widget" else None)
    d = drawing.measure(Thing("k", "widget", _e()))
    assert d.rung == 2 and d.source == "sketch"
    assert d.strokes and sum(len(s.points) for s in d.strokes) >= 5
    drawing.set_sketch_lookup(None)
    drawing.set_compose(None)
    drawing.set_catalog_lookup(None)
    drawing.reset()


def test_concept_normalization_finds_sketches():
    """LLM-named variants (underscores, articles, plurals) resolve to the sketch."""
    widget = {"name": "widget", "strokes": [[[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]]]}
    drawing.set_compose(lambda concept: None)
    drawing.set_catalog_lookup(lambda concept: None)
    drawing.set_sketch_lookup(lambda name: widget if name == "widget" else None)
    for variant in ("the_widget", "widgets", "the widget", "Widget"):
        drawing.reset()
        assert drawing.measure(Thing("k", variant, _e())).rung == 2, variant
    drawing.set_sketch_lookup(None)
    drawing.set_compose(None)
    drawing.set_catalog_lookup(None)
    drawing.reset()


def test_color_is_paint_time_not_in_measure_key():
    red = Thing("r", "circle", _e(), geometry_attrs={"radius": 0.5}, paint_attrs={"color": "#f00"})
    blue = Thing("b", "circle", _e(), geometry_attrs={"radius": 0.5}, paint_attrs={"color": "#00f"})
    assert drawing.measure(red) is drawing.measure(blue)  # color doesn't fork geometry
    op_r = drawing.paint(red, Placement("r", 0, 0, 1, 1))
    op_b = drawing.paint(blue, Placement("b", 0, 0, 1, 1))
    assert op_r.color == "#f00" and op_b.color == "#00f"


# --------------------------------------------------------------------------- #
# paint() — places the local drawable into board space.
# --------------------------------------------------------------------------- #
def test_paint_translates_to_placement():
    t = Thing("s", "square", _e(), geometry_attrs={"size": 2.0})
    op = drawing.paint(t, Placement("s", 3.0, -1.0, 2.0, 2.0))
    xs = [p[0] for st in op.strokes for p in st.points]
    ys = [p[1] for st in op.strokes for p in st.points]
    assert sum(xs) / len(xs) == pytest.approx(3.0, abs=1e-6)
    assert sum(ys) / len(ys) == pytest.approx(-1.0, abs=1e-6)
    assert op.length > 0


# --------------------------------------------------------------------------- #
# Scene pipeline — measure -> position -> route -> paint, invariants hold.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scene", SCENES, ids=[s.name for s in SCENES])
def test_scene_invariants_and_extent_honesty(scene):
    r = render(scene, BOARD)
    rep = invariants.evaluate(scene.things, r.placements, BOARD)
    assert rep.overlap <= 1e-6, f"{scene.name}: overlap"
    assert not rep.off_board, f"{scene.name}: off-board {rep.off_board}"
    assert not rep.relation_violations, f"{scene.name}: {rep.relation_violations}"

    pmap = r.placement_of()
    for op in r.ops:
        if op.kind != "draw":
            continue
        d = r.drawables[op.thing_id]
        p = pmap[op.thing_id]
        err = invariants.extent_error(d.extent.w, d.extent.h, op.strokes, p.scale)
        assert err <= 0.10, f"{scene.name}: {op.thing_id} extent error {err}"


def test_connectors_attach_between_placed_boxes():
    scene = next(s for s in SCENES if s.name == "two_circles")
    r = render(scene, BOARD)
    pmap = r.placement_of()
    a, b = pmap["a"], pmap["b"]
    conn = next(op for op in r.ops if op.kind == "connector")
    shaft = conn.strokes[0].points
    p0, p1 = shaft[0], shaft[1]
    # Endpoints attach on the boundary side facing the other box (b is right of a).
    assert a.x < p0[0] <= a.right + 1e-6
    assert b.left - 1e-6 <= p1[0] < b.x


def test_dropped_endpoint_yields_no_edge():
    from engine.contracts import Connector
    from engine.scene import Scene

    # 'ghost' is never declared as a Thing -> the connector has no endpoint.
    scene = Scene("dangler", [_thing("a", "circle")], [Connector("e", "a", "ghost")])
    r = render(scene, BOARD)
    assert not any(op.kind == "connector" for op in r.ops)


def test_svg_export_is_wellformed():
    from engine.svg import to_svg

    r = render(SCENES[0], BOARD)
    out = to_svg(r, BOARD)
    assert out.startswith("<svg") and "</svg>" in out
    assert "<polyline" in out


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _e():
    from engine.contracts import Extent

    return Extent(1.0, 1.0)


def _thing(id_, concept, **geom):
    return Thing(id_, concept, _e(), geometry_attrs=dict(geom))
