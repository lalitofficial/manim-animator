"""The cartoon STYLE layer (docs/CARTOON.md): paint-time color. Whiteboard stays
mono (byte-identical wire); cartoon fills closed shapes + lays a scene backdrop.
Style is a separate axis from mode and is decided by the Director.
"""

from __future__ import annotations

from engine import drawing, icons, palette, story
from engine.contracts import Board, Placement, Thing
from engine.director import direct
from engine.drawing import measure, paint
from engine.serialize import op_to_dict
from engine.stream import stream_lesson

BOARD = Board()
P = Placement("x", 0.0, 0.0, 2.0, 2.0)


def setup_function():
    drawing.reset()
    story.set_provider(None)


# --- palette ---------------------------------------------------------------- #
def test_concept_colors_known_and_default():
    assert palette.concept_colors("sun")[0] == "#ffd23f"
    assert palette.concept_colors("rain cloud")[0] == "#ffffff"  # substring bucket -> cloud
    fill, line = palette.concept_colors("nonexistent-thing")
    assert fill == palette.DEFAULT_FILL and line == palette.DEFAULT_LINE


def test_whiteboard_paint_is_mono_even_for_colored_recipe():
    """A recipe carries authored cartoon hex, but the whiteboard style strips it so
    the original mono board is unchanged."""
    from engine.contracts import Extent

    d = measure(Thing("s", "sun", Extent(1, 1)), generate=False)
    op = paint(Thing("s", "sun", Extent(1, 1)), P, d, style=palette.WHITEBOARD)
    assert all(s.color is None and s.fill is None for s in op.strokes)
    assert op.fill is False
    # And the wire carries no color keys (whiteboard contract).
    for sd in op_to_dict(op)["strokes"]:
        assert "color" not in sd and "fill" not in sd


def test_cartoon_paint_fills_closed_shapes():
    from engine.contracts import Extent

    d = measure(Thing("s", "sun", Extent(1, 1)), generate=False)
    op = paint(Thing("s", "sun", Extent(1, 1)), P, d, style=palette.CARTOON)
    assert op.fill is True
    filled = [s for s in op.strokes if s.closed and s.fill]
    assert filled and filled[0].fill == "#ffd23f"  # the sun's authored body color
    assert all(s.color for s in op.strokes)  # every stroke gets an outline color


def test_cartoon_default_fill_for_uncolored_closed_primitive():
    from engine.contracts import Extent

    d = measure(
        Thing("c", "circle", Extent(1, 1)), generate=False
    )  # bare primitive, no recipe color
    op = paint(Thing("c", "circle", Extent(1, 1)), P, d, style=palette.CARTOON)
    assert any(s.fill == palette.DEFAULT_FILL for s in op.strokes)


# --- backgrounds ------------------------------------------------------------ #
def test_background_none_for_whiteboard_gradient_for_cartoon():
    assert palette.background("space", "learn", palette.WHITEBOARD) is None
    bg = palette.background("a trip through space", "learn", palette.CARTOON)
    assert bg["scene"] == "space" and "top" in bg["gradient"] and "bottom" in bg["gradient"]


def test_scene_keyword_routing():
    assert palette.scene_for("life in the ocean") == "underwater"
    assert palette.scene_for("the water cycle") == "sky"
    assert palette.scene_for("a totally abstract idea") == "default"


def test_scene_routing_review_fixes():
    # night precedes space so moon/starry-night topics get the gentle navy stage
    assert palette.scene_for("the moon at night") == "night"
    assert palette.scene_for("a starry night") == "night"
    # but real astronomy still routes to space, incl. the "solar" near-miss
    assert palette.scene_for("the solar system") == "space"
    assert palette.scene_for("how rockets reach orbit") == "space"
    # new coverage: desert + body interior
    assert palette.scene_for("life in the desert") == "desert"
    assert palette.scene_for("the human heart") == "body"


def test_dark_scenes_get_light_label_ink():
    assert palette.op_color(palette.CARTOON, None, None, "space") == palette.LABEL_INK_DARK
    assert palette.op_color(palette.CARTOON, None, None, "night") == palette.LABEL_INK_DARK
    assert palette.op_color(palette.CARTOON, None, None, "sky") == palette.LABEL_INK  # light scene
    assert palette.op_color(palette.CARTOON, None, "#abc", "space") == "#abc"  # explicit wins


def test_apply_mood_warms_or_cools_the_backdrop():
    """A scene's emotion tints the sky toward warmth (joy) or cool (tension); calm and
    unknown moods leave the backdrop untouched, and the scene identity always survives."""
    base = palette.background("a forest", "learn", palette.CARTOON)
    assert base is not None
    joyful = palette.apply_mood(base, "joyful")
    tense = palette.apply_mood(base, "tense")

    def red(hexc: str) -> int:
        return int(hexc.lstrip("#")[0:2], 16)

    assert red(joyful["gradient"]["top"]) > red(base["gradient"]["top"])  # warmer = more red
    assert red(tense["gradient"]["top"]) < red(base["gradient"]["top"])  # cooler = less red
    assert joyful["scene"] == base["scene"]  # identity preserved, only the tint shifts
    assert palette.apply_mood(base, "calm") == base  # neutral mood is a no-op
    assert palette.apply_mood(base, "bogus") == base  # unknown mood is a no-op


def test_open_stroke_authored_fill_is_dropped():
    from engine.contracts import Stroke

    openstroke = Stroke(((0, 0), (1, 1)), closed=False, fill="#ff0000")
    out = palette.apply((openstroke,), palette.CARTOON, "x")[0]
    assert out.fill is None  # an open stroke is never flood-filled, even if authored


def test_cartoon_recipes_override_mono_with_color():
    # a concept authored in cartoon_recipes.json composes WITH fills (was mono before)
    strokes = icons.compose("rocket")
    assert strokes and any(s.fill for s in strokes)


# --- director --------------------------------------------------------------- #
def test_child_audience_defaults_to_cartoon():
    assert direct("x", audience="child").style == "cartoon"
    assert direct("x").style == "whiteboard"  # default stays whiteboard


def test_explicit_style_and_cues_win():
    assert direct("x", style="cartoon").style == "cartoon"
    assert direct("x", request="make it a colorful cartoon").style == "cartoon"
    assert direct("x", audience="child", style="whiteboard").style == "whiteboard"


# --- serialize -------------------------------------------------------------- #
def test_op_dict_carries_layer_and_motion_fields():
    from engine.contracts import Extent

    d = measure(Thing("s", "sun", Extent(1, 1)), generate=False)
    sd = op_to_dict(paint(Thing("s", "sun", Extent(1, 1)), P, d))
    assert sd["z"] == 1 and sd["entrance"] == "draw" and sd["ambient"] == ""


# --- motion ----------------------------------------------------------------- #
def test_ambient_and_entrance_defaults():
    # EXPLANATORY motion: the concept's nature drives how it moves.
    assert palette.ambient_for("sun") == "glow"
    assert palette.ambient_for("rain") == "fall"
    assert palette.ambient_for("river") == "flow"
    assert palette.ambient_for("vapor") == "rise"
    assert palette.ambient_for("cloud") == "float"
    assert palette.ambient_for("presenter") == "bob"
    assert palette.ambient_for("democracy") == ""  # abstract -> no motion
    assert palette.entrance_for("teacher") == "rise"
    assert palette.entrance_for("sun") == "draw"


def test_cartoon_paint_applies_motion_whiteboard_does_not():
    from engine.contracts import Extent

    d = measure(Thing("s", "sun", Extent(1, 1)), generate=False)
    cartoon = paint(Thing("s", "sun", Extent(1, 1)), P, d, style=palette.CARTOON)
    assert cartoon.ambient == "glow" and cartoon.entrance == "draw"  # the sun glows
    white = paint(Thing("s", "sun", Extent(1, 1)), P, d, style=palette.WHITEBOARD)
    assert white.ambient == "" and white.entrance == "draw"  # mono board stays still


def test_explicit_paint_attrs_override_concept_defaults():
    from engine.contracts import Extent

    t = Thing("s", "sun", Extent(1, 1), paint_attrs={"ambient": "sway", "entrance": "pop"})
    d = measure(t, generate=False)
    op = paint(t, P, d, style=palette.CARTOON)
    assert op.ambient == "sway" and op.entrance == "pop"


def test_cartoon_connector_uses_dark_ink():
    from engine.contracts import Connector
    from engine.route import CARTOON_COLOR, DEFAULT_COLOR, route

    pm = {"a": Placement("a", -2, 0, 1, 1), "b": Placement("b", 2, 0, 1, 1)}
    conn = Connector("a->b", "a", "b", "arrow")
    assert route(conn, pm, style="cartoon").color == CARTOON_COLOR
    assert route(conn, pm).color == DEFAULT_COLOR  # whiteboard unchanged


# --- camera ----------------------------------------------------------------- #
def test_director_cinematic_flag():
    assert direct("x", style="cartoon").cinematic is True  # cartoon + normal energy
    assert direct("x", style="cartoon", energy="calm").cinematic is False  # calm = static
    assert direct("x").cinematic is False  # whiteboard never


def test_cartoon_stream_emits_camera_within_board():
    spec = direct("the water cycle", style="cartoon")
    evs = list(stream_lesson("the water cycle", board=BOARD, spec=spec))
    cams = [e for e in evs if e["type"] == "camera"]
    assert cams  # the camera follows the lesson
    for c in cams:  # every focus rect stays fully on-board (sub-mm slack for rounding)
        assert c["x"] - c["w"] / 2 >= -BOARD.hw - 1e-3 and c["x"] + c["w"] / 2 <= BOARD.hw + 1e-3
        assert c["y"] - c["h"] / 2 >= -BOARD.hh - 1e-3 and c["y"] + c["h"] / 2 <= BOARD.hh + 1e-3
        assert c["w"] <= BOARD.w and c["h"] <= BOARD.h
    assert cams[-1]["w"] == BOARD.w and cams[-1]["h"] == BOARD.h  # ends on a full pull-back


def test_no_camera_in_whiteboard_or_calm():
    assert not any(e["type"] == "camera" for e in stream_lesson("x", board=BOARD))
    calm = direct("x", style="cartoon", energy="calm")
    assert not any(e["type"] == "camera" for e in stream_lesson("x", board=BOARD, spec=calm))


# --- stream ----------------------------------------------------------------- #
def test_stream_emits_background_only_in_cartoon():
    cartoon = list(
        stream_lesson(
            "the water cycle", board=BOARD, spec=direct("the water cycle", style="cartoon")
        )
    )
    assert cartoon[0]["style"] == "cartoon"
    bgs = [e for e in cartoon if e["type"] == "background"]
    assert bgs and bgs[0]["scene"] == "sky"

    drawing.reset()
    white = list(stream_lesson("the water cycle", board=BOARD))
    assert white[0]["style"] == "whiteboard"
    assert not any(e["type"] == "background" for e in white)  # mono board unchanged
