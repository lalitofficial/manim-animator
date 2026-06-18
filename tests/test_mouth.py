"""Phase 4a (docs/ROADMAP-story-voice.md §5): the mouth-slot viseme rig + its wiring.

The host's mouth becomes a swappable SLOT — viseme shapes the board flips through during speech
for lip-sync. Backend-testable: the shapes exist and the host draw op carries them.
"""

from __future__ import annotations

import pytest

from engine import character, director, drawing, story
from engine.contracts import Board
from engine.plan import compile_plan


@pytest.fixture(autouse=True)
def fresh():
    drawing.reset()
    story.set_provider(None)
    yield
    drawing.reset()
    story.set_provider(None)


def test_mouth_shapes_are_the_viseme_slot():
    shapes = character.mouth_shapes()
    assert set(shapes) == set(character.MOUTH_SHAPES)  # rest/closed/narrow/mid/wide/round
    assert all(strokes for strokes in shapes.values())  # every viseme has geometry
    assert any(s.fill for s in shapes["wide"])  # open visemes are filled (mouth interior)
    assert all(s.fill is None for s in shapes["rest"])  # rest/closed are ink lines (lips together)


def test_mouth_shapes_render_for_any_role_or_theme():
    for kw in ({}, {"character": "scientist"}, {"theme": "coral"}):
        shapes = character.mouth_shapes(**kw)
        assert set(shapes) == set(character.MOUTH_SHAPES)
        assert any(s.fill for s in shapes["round"])  # the rounded viseme is filled


def test_host_draw_op_carries_the_mouth_slot():
    spec = director.DirectorSpec("the water cycle", mode="learn", style="cartoon")  # cinematic host
    evs = list(compile_plan(story.tell_plan(spec), spec, Board(), generate=False))
    host = next((e for e in evs if e["type"] == "draw" and e["op"].get("mouths")), None)
    assert host is not None  # the host op carries swappable viseme mouths for lip-sync
    assert set(host["op"]["mouths"]) == set(character.MOUTH_SHAPES)
    assert all(host["op"]["mouths"].values())  # each viseme painted to board strokes


def test_whiteboard_has_no_mouth_slot():
    # whiteboard isn't cinematic and has no host -> no mouth slot anywhere (it's a diagram)
    spec = director.DirectorSpec("gravity", mode="learn", style="whiteboard")
    evs = list(compile_plan(story.tell_plan(spec), spec, Board(), generate=False))
    assert not any(e.get("op", {}).get("mouths") for e in evs if e["type"] == "draw")
