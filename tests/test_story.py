"""Phase-5 gate (docs/ARCHITECTURE.md §3, §9): Story -> Beats -> end-to-end.

Hermetic — the deterministic TemplateStory drives the pipeline; parse_beats is
tested directly for the LLM JSON path. The whole topic->board loop must satisfy
the same output-derived invariants as everything below it.
"""

from __future__ import annotations

import pytest

from engine import drawing, invariants, story
from engine.contracts import Board
from engine.runtime import lesson
from engine.scene import compile_beats

BOARD = Board()


@pytest.fixture(autouse=True)
def fresh():
    drawing.reset()
    story.set_provider(None)  # default = TemplateStory (deterministic, offline)
    yield
    drawing.reset()
    story.set_provider(None)


# --------------------------------------------------------------------------- #
# Story emits Beats; compile turns them into a Scene + narration.
# --------------------------------------------------------------------------- #
def test_template_story_emits_beats():
    beats = story.tell("photosynthesis")
    kinds = {b.kind for b in beats}
    assert "show" in kinds and "say" in kinds and "connect" in kinds
    assert any(b.kind == "show" and b.concept == "text" for b in beats)  # the title


def test_compile_beats_builds_scene_and_narration():
    beats = story.tell("the water cycle")
    scene, narration = compile_beats(beats, "wc")
    assert scene.things and scene.connectors
    assert narration and all(isinstance(s, str) for s in narration)
    # Every connector references real things.
    ids = {t.id for t in scene.things}
    assert all(c.src in ids and c.dst in ids for c in scene.connectors)


def test_modes_produce_distinct_structures():
    learn = story.tell("x", "learn")
    draw = story.tell("x", "draw")
    tale = story.tell("x", "story")
    assert any(b.kind == "show" and b.entity == "main" for b in draw)  # one central illustration
    assert sum(1 for b in tale if b.kind == "clear") == 2  # 3 scenes -> 2 scene breaks
    assert sum(1 for b in learn if b.kind == "show") >= 3  # a multi-concept board
    assert any(b.kind == "connect" for b in learn)


def test_explain_mode_is_terse_with_a_connection():
    beats = story.tell("inflation", "explain")
    assert any(b.kind == "connect" for b in beats)
    assert sum(1 for b in beats if b.kind == "show") == 2


def test_director_spec_drives_content_density():
    from engine.director import DirectorSpec

    sparse = story.tell("x", DirectorSpec("x", density="sparse"))
    dense = story.tell("x", DirectorSpec("x", density="dense"))
    n_sparse = sum(1 for b in sparse if b.kind == "show" and b.entity != "title")
    n_dense = sum(1 for b in dense if b.kind == "show" and b.entity != "title")
    assert n_dense > n_sparse


def test_director_spec_drives_scene_count():
    from engine.director import DirectorSpec

    two = story.tell("x", DirectorSpec("x", mode="story", scene_count=2))
    assert sum(1 for b in two if b.kind == "clear") == 1  # 2 scenes -> 1 break


def test_subject_extracts_a_drawable_hero_not_the_raw_phrase():
    """The story/draw hero is a DRAWABLE subject noun, not the whole topic string (which
    would box). Drawability is style-aware — cartoon skips the catalog, so it picks a word
    that actually renders as a recipe/primitive in cartoon."""
    from engine.director import direct
    from engine.plan import compile_plan

    drawing.reset()
    assert story._subject("how a volcano erupts", "cartoon") == "volcano"  # recipe-drawable
    assert story._subject("the human heart", "cartoon") == "heart"
    # cartoon skips the catalog: 'wrench' is catalog-only so it boxes in cartoon, and the
    # style-aware probe falls back to the family-drawable 'fox' instead — but whiteboard,
    # which HAS the catalog, keeps the trailing 'wrench'.
    assert story._subject("a fox holding a wrench", "cartoon") == "fox"
    assert story._subject("a fox holding a wrench", "whiteboard") == "wrench"
    # a recipe-subject topic compiles with NO placeholder box for the hero
    spec = direct("how a volcano erupts", mode="draw", style="cartoon")
    done = next(
        e for e in compile_plan(story.tell_plan(spec), spec, Board()) if e["type"] == "done"
    )
    assert done["summary"]["placeholders"] == 0  # the volcano draws, it isn't a labeled box


def test_story_template_plan_is_an_emotional_arc():
    """Story mode is a real arc, not N flat scenes: curiosity builds to tension, then
    releases into joy — and each scene carries a director's purpose."""
    from engine.director import DirectorSpec

    lp = story.tell_plan(DirectorSpec("a daring rescue", mode="story", scene_count=3))
    arc = [(s.purpose, s.emotion) for s in lp.scenes]
    assert arc == [("introduce", "curious"), ("build", "tense"), ("resolve", "joyful")]
    # single-scene modes still carry a fitting mood (not blank)
    assert story.tell_plan(DirectorSpec("rain", mode="draw")).scenes[0].emotion == "wonder"
    assert story.tell_plan(DirectorSpec("gravity", mode="explain")).scenes[0].emotion == "calm"


def test_plan_reports_template_when_no_model():
    r = story.plan("x", "learn")
    assert r.used == "template" and r.requested == "template" and r.fallback is False


def test_plan_reports_fallback_on_provider_failure():
    class Boom:
        name = "ollama"

        def tell(self, spec):
            raise RuntimeError("connection refused")

    story.set_provider(Boom())
    r = story.plan("x", "learn")
    assert r.requested == "ollama" and r.used == "template" and r.fallback is True
    assert "ollama" in (r.reason or "")
    assert r.beats  # still produced a (template) lesson — degraded, not broken


def test_plan_reports_empty_beats_as_fallback():
    class Empty:
        name = "ollama"

        def tell(self, spec):
            return []

    story.set_provider(Empty())
    r = story.plan("x", "learn")
    assert r.fallback is True and "no usable beats" in (r.reason or "")


def test_plan_uses_provider_when_it_succeeds():
    from engine.contracts import show

    class Fake:
        name = "ollama"

        def tell(self, spec):
            return [show("a", "cat")]

    story.set_provider(Fake())
    r = story.plan("x", "learn")
    assert r.used == "ollama" and r.fallback is False


def test_audience_changes_narration():
    from engine.director import DirectorSpec

    kid = story.tell("frogs", DirectorSpec("frogs", audience="child"))
    expert = story.tell("frogs", DirectorSpec("frogs", audience="expert"))
    first_kid = next(b.text for b in kid if b.kind == "say")
    first_expert = next(b.text for b in expert if b.kind == "say")
    assert first_kid != first_expert


def test_sanitize_beats_drops_what_breaks_the_board():
    """Drop-don't-repair for Story output: stray clears (learn), over-long concept
    lists, dangling connects, and relations to unshown ids."""
    from engine.contracts import clear, connect, right_of, show
    from engine.director import DirectorSpec
    from engine.story import sanitize_beats

    raw = [
        show("cloud", "cloud"),
        clear(),  # illegal in learn — should be dropped
        show("rain", "rain", right_of("cloud")),  # valid anchor
        show("x", "x", right_of("ghost")),  # anchor to an unshown id -> relation nulled
        connect("cloud", "rain"),  # both shown -> kept
        connect("cloud", "ghost"),  # dangling dst -> dropped
    ]
    out = sanitize_beats(raw, DirectorSpec("t", mode="learn"))
    assert not any(b.kind == "clear" for b in out)  # no wipes in learn
    conns = [b for b in out if b.kind == "connect"]
    assert len(conns) == 1 and conns[0].target == "rain"  # dangling edge dropped
    x = next(b for b in out if b.entity == "x")
    assert x.relation is None  # dangling anchor nulled (the thing just flows)


def test_sanitize_caps_concepts_in_learn():
    from engine.contracts import show
    from engine.director import DirectorSpec
    from engine.story import sanitize_beats

    raw = [show(f"c{i}", "cloud") for i in range(12)]
    out = sanitize_beats(raw, DirectorSpec("t", mode="learn", density="dense"))
    assert sum(1 for b in out if b.kind == "show") <= 6  # learn cap keeps the board readable


def test_plan_from_beats_animates_supplied_story():
    """Bring-your-own-story: sanitize + inject the cartoon host, no provider call."""
    from engine.contracts import say, show
    from engine.director import direct

    raw = [say("hi"), show("sun", "sun"), show("cloud", "cloud", text="")]
    r = story.plan_from_beats(raw, direct("x", style="cartoon"))
    assert r.used == "script" and r.fallback is False
    ids = {b.entity for b in r.beats if b.kind == "show"}
    assert {"sun", "cloud"} <= ids and "guide" in ids  # author's concepts + injected host


def test_plan_from_beats_trusts_author_count():
    """The author's concept count is respected up to the board cap (not the tight
    model-path cap of 4)."""
    from engine.contracts import show
    from engine.director import direct

    raw = [show(f"c{i}", "cloud") for i in range(7)]
    r = story.plan_from_beats(raw, direct("x", mode="learn"))
    assert sum(1 for b in r.beats if b.kind == "show") >= 7  # whiteboard: no host added


def test_sanitize_keeps_clears_in_story_mode():
    from engine.contracts import clear, show
    from engine.director import DirectorSpec
    from engine.story import sanitize_beats

    raw = [show("a", "sun"), clear(), show("b", "moon")]
    out = sanitize_beats(raw, DirectorSpec("t", mode="story"))
    assert any(b.kind == "clear" for b in out)  # story scenes legitimately wipe


def test_parse_beats_handles_clear():
    beats = story.parse_beats({"beats": [{"kind": "clear"}, {"kind": "say", "text": "hi"}]})
    assert [b.kind for b in beats] == ["clear", "say"]


def test_parse_beats_salvages_malformed_array():
    """A real qwen failure: array elements arrive as string fragments. Salvage the
    valid beats instead of crashing (observed reliability fix, not Outlines-yet)."""
    data = {
        "beats": [
            {"kind": "show", "entity": "1", "concept": "sun", "relation": {"at": "top"}},
            "{",
            'kind\\":\\"connect',  # garbage fragment
            {"kind": "say", "text": "ok"},
        ]
    }
    beats = story.parse_beats(data)
    assert [b.kind for b in beats] == ["show", "say"]  # valid ones survive, junk skipped


def test_parse_beats_from_json():
    data = {
        "beats": [
            {"kind": "show", "entity": "sun", "concept": "sun", "relation": {"at": "top"}},
            {
                "kind": "show",
                "entity": "earth",
                "concept": "earth",
                "relation": {"right_of": "sun"},
            },
            {"kind": "connect", "src": "sun", "dst": "earth", "label": "light"},
            {"kind": "say", "text": "The sun lights the earth."},
        ]
    }
    beats = story.parse_beats(data)
    assert [b.kind for b in beats] == ["show", "show", "connect", "say"]
    earth = next(b for b in beats if b.entity == "earth")
    assert earth.relation.kind == "right_of" and earth.relation.target == "sun"


# --------------------------------------------------------------------------- #
# End-to-end: topic -> a valid, painted board.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("topic", ["the water cycle", "supply and demand", "binary search"])
def test_lesson_end_to_end_holds_invariants(topic):
    les = lesson(topic, board=BOARD)
    rep = invariants.evaluate(les.scene.things, les.rendered.placements, BOARD)
    assert rep.passes, f"{topic}: {rep.off_board} {rep.relation_violations} overlap={rep.overlap}"
    assert les.narration, "a lesson should narrate"
    assert les.rendered.ops, "a lesson should paint something"
    # The title is rendered as text (rung 1); the topic appears as its label.
    titles = [o for o in les.rendered.ops if o.label == topic]
    assert titles, "the topic title should be on the board"


def test_lesson_is_deterministic():
    a = lesson("mitosis", board=BOARD)
    drawing.reset()
    b = lesson("mitosis", board=BOARD)
    assert a.rendered.placements == b.rendered.placements


def test_lesson_svg_renders():
    from engine.svg import to_svg

    les = lesson("the carbon cycle", board=BOARD)
    out = to_svg(les.rendered, BOARD)
    assert out.startswith("<svg") and "<polyline" in out
