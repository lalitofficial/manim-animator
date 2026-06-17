"""The parameterized presenter rig (docs/CARTOON.md §3): one reusable character,
pose + expression vary, consistency for free. Resolves through the Drawing ladder
as source=character; the Story injects it only for cartoon lessons.
"""

from __future__ import annotations

import pytest

from engine import character, drawing, palette, story
from engine.contracts import Board, Extent, Placement, Thing
from engine.director import DirectorSpec, direct
from engine.drawing import measure, paint

BOARD = Board()
P = Placement("g", 0.0, 0.0, 2.8, 2.8)


def setup_function():
    drawing.reset()
    story.set_provider(None)


@pytest.mark.parametrize("pose", character.POSES)
@pytest.mark.parametrize("expr", character.EXPRESSIONS)
def test_build_every_pose_expression(pose, expr):
    strokes = character.build(pose=pose, expression=expr)
    assert strokes and all(len(s.points) >= 2 for s in strokes)
    assert any(s.fill for s in strokes)  # the rig is colored (head/torso fills)


def test_poses_differ_geometrically():
    idle = character.build(pose="idle")
    point = character.build(pose="point")
    assert idle != point  # arms move -> distinct geometry


def test_cast_roles_are_distinct_characters_in_one_style():
    """The modular cast (§C2): role concepts resolve to the SAME rig with different
    outfits/accessories — distinct characters, one style, no foreign-art ingest."""
    assert {"teacher", "scientist", "doctor", "farmer", "astronaut", "king"} <= set(character.ROLES)
    assert character.is_character("scientist") and character.is_character("Teacher")
    rigs = {
        r: character.build(character=r)
        for r in ("presenter", "teacher", "scientist", "farmer", "king", "wizard")
    }
    assert len(set(rigs.values())) == 6  # each role looks different
    assert all(any(s.fill for s in r) for r in rigs.values())  # all colored


def test_cast_role_resolves_through_measure_and_keeps_costume_in_motion():
    drawing.reset()
    d = measure(
        Thing("s", "scientist", Extent(1, 1), geometry_attrs={"pose": "wave"}),
        generate=False,
        style="cartoon",
    )
    assert d.source == "character"
    # a role gestures while staying in costume (its clip frames differ from the presenter's)
    sci = character.clip_drawables("cheer", character="scientist")
    pres = character.clip_drawables("cheer", character="presenter")
    assert len(sci) > 4 and sci[len(sci) // 2] != pres[len(pres) // 2]


def test_new_clips_and_head_tilt():
    for clip in ("jump", "nod", "think", "walk", "cheer"):
        assert len(character.perform(clip)) >= 2  # every clip expands to motion frames
    # the head ARTICULATES: the nod's 'agree' pose tilts the head, so it differs from idle
    assert character.build("idle") != character.build("agree")
    assert character.interpolate("idle", "agree", 0.5).get("head", 0.0) < 0  # bowed mid-nod


def test_side_profile_is_a_distinct_silhouette():
    # a full side profile (facing ±1): profile head (one eye + nose wedge) + far arm hidden
    front = character.build("idle")
    assert character.build("side_left") != character.build("side_right")
    assert character.build("side_right") != character.build("turn_right")  # ≠ the 3/4 turn
    assert len(character.build("side_right")) < len(front)  # far arm + an eye dropped


def test_cast_concept_recasts_only_generic_hosts():
    assert character.cast_concept("presenter", "a day on the farm") == "farmer"
    assert character.cast_concept("guide", "the science lab") == "scientist"
    assert character.cast_concept("scientist", "the farm") == "scientist"  # a real role is kept
    assert character.cast_concept("sun", "the farm") == "sun"  # a thing is never recast


def test_head_direction_and_body_facing():
    # head TURN (look) shifts the face features — left ≠ right ≠ front
    assert character.build("look_left") != character.build("look_right")
    assert character.build("look_left") != character.build("idle")
    # body FACING turns the whole figure (3/4) — distinct from a head-only glance
    assert character.build("turn_left") != character.build("look_left")
    assert character.build("turn_left") != character.build("turn_right")
    # the look/turn/facing all interpolate (smooth head + body turns)
    mid = character.interpolate("idle", "turn_right", 0.5)
    assert mid.get("facing", 0) > 0 and mid.get("turn", 0) >= 0


def test_motion_easing_overshoots_and_jump_anticipates():
    # 'back' easing OVERSHOOTS the target then settles (follow-through)
    frames = character.perform("cheer", frames_per_key=6)  # ease=back
    target = character.POSE_LIBRARY["cheer"]["l_arm"][0]
    assert min(f["l_arm"][0] for f in frames) < target - 1  # goes past the cheer pose
    # the jump WINDS UP through a crouch (anticipation) before launching
    assert "crouch" in character.CLIPS["jump"]["keys"]
    jump = character.perform("jump")
    assert any(f.get("head", 0) < -1 for f in jump[: len(jump) // 2])  # head bows in the crouch


def test_new_gesture_clips_all_move():
    for clip in (
        "explain",
        "surprised",
        "shrug",
        "clap",
        "nod",
        "look_up",
        "turn_left",
        "celebrate",
    ):
        frames = character.perform(clip)
        assert len(frames) >= 2
        assert len({str(sorted(f.items())) for f in frames}) >= 2  # genuinely animates


def test_director_casts_topic_appropriate_host():
    assert character.cast_for("a day on the farm") == "farmer"
    assert character.cast_for("the solar system") == "astronaut"
    assert character.cast_for("the human cell") == "scientist"
    assert character.cast_for("baking bread") == "chef"  # word-boundary, NOT 'king' in 'baking'
    assert character.cast_for("the water cycle") == "presenter"  # unthemed → neutral host


def test_star_concept_is_the_sky_object_not_a_role():
    # role names must not shadow object concepts: a lesson about a star draws the star icon
    drawing.reset()
    d = measure(Thing("s", "star", Extent(1, 1)), generate=False, style="cartoon")
    assert d.source != "character"


def test_mined_poses_loaded_and_distinct():
    # the data-derived poses (Meta Amateur Drawings) are present alongside the hand ones
    assert {"cheer", "wave", "walk", "present"} <= set(character.POSES)
    rigs = {p: character.build(pose=p) for p in ("idle", "cheer", "wave", "walk")}
    assert len(set(rigs.values())) == 4  # each reads as a different body language


def test_interpolate_is_a_genuine_inbetween():
    a, b = character.build("idle"), character.build("cheer")
    mid = character.build(character.interpolate("idle", "cheer", 0.5))
    assert mid not in (a, b)  # a real tween, not a snap to either end


def test_perform_clip_produces_moving_frames():
    frames = character.perform("wave", frames_per_key=4)
    assert len(frames) > 6
    rigs = [character.build(f) for f in frames]
    assert len(set(rigs)) > 4  # the rig actually moves across the clip
    # consistent-scale placed frames for the board flipbook
    placed = character.clip_drawables("cheer", size=2.8)
    assert len(placed) > 4 and all(fr for fr in placed)


def test_theme_changes_shirt_color():
    teal = {s.fill for s in character.build(theme="teal") if s.fill}
    coral = {s.fill for s in character.build(theme="coral") if s.fill}
    assert teal != coral  # same rig, different consistent palette


def test_is_character_names():
    assert character.is_character("presenter") and character.is_character("Teacher")
    assert not character.is_character("sun")


def test_measure_resolves_presenter_to_character_rung():
    d = measure(
        Thing("g", "presenter", Extent(1, 1), geometry_attrs={"pose": "wave"}), generate=False
    )
    assert d.source == "character" and d.rung == 1
    assert d.extent.w > 0 and d.extent.h > 0


def test_pose_is_part_of_cache_key():
    a = measure(
        Thing("g", "presenter", Extent(1, 1), geometry_attrs={"pose": "idle"}), generate=False
    )
    b = measure(
        Thing("g", "presenter", Extent(1, 1), geometry_attrs={"pose": "point"}), generate=False
    )
    assert a.strokes != b.strokes  # distinct poses don't collide in the cache


def test_whiteboard_strips_cartoon_paint_keeps_in_cartoon():
    t = Thing("g", "presenter", Extent(1, 1), geometry_attrs={"pose": "present"})
    d = measure(t, generate=False)
    white = paint(t, P, d, style=palette.WHITEBOARD)
    assert all(s.fill is None for s in white.strokes)  # mono presenter still reads
    cartoon = paint(t, P, d, style=palette.CARTOON)
    assert any(s.fill for s in cartoon.strokes)


# --- story injection -------------------------------------------------------- #
def test_presenter_injected_only_in_cartoon():
    cartoon = story.tell("frogs", direct("frogs", style="cartoon"))
    assert any(b.kind == "show" and b.entity == "guide" for b in cartoon)
    white = story.tell("frogs", DirectorSpec("frogs"))  # whiteboard default
    assert not any(b.entity == "guide" for b in white)


def test_presenter_beat_carries_paint_hints_not_geometry_pollution():
    cartoon = story.tell("x", direct("x", style="cartoon"))
    guide = next(b for b in cartoon if b.entity == "guide")
    # entrance/ambient/z ride in the beat's geometry dict; stream/scene route them
    # to paint_attrs so they never become Drawing cache-key geometry.
    from engine.contracts import split_paint_attrs

    geom, paint_attrs = split_paint_attrs(guide.geometry)
    assert "pose" in geom and "ambient" in paint_attrs and "entrance" in paint_attrs
    assert "ambient" not in geom and "z" not in geom


def test_explain_show_count_unchanged_in_whiteboard():
    # The presenter must NOT leak into whiteboard explain (the 2-show contract).
    beats = story.tell("inflation", "explain")
    assert sum(1 for b in beats if b.kind == "show") == 2


def test_cartoon_character_paints_on_top_layer():
    # z=3 so the host renders above things(1)/connectors(2); a sun stays at z=1.
    t = Thing("g", "presenter", Extent(1, 1), geometry_attrs={"pose": "wave"})
    d = measure(t, generate=False)
    assert paint(t, P, d, style=palette.CARTOON).z == 3
    sun = Thing("s", "sun", Extent(1, 1))
    assert paint(sun, P, measure(sun, generate=False), style=palette.CARTOON).z == 1
