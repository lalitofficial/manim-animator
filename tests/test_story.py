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


def test_parse_beats_hardening_and_connector_kind():
    # valid-but-non-beats JSON must NOT KeyError (the public POST /api/engine/animate path)
    assert story.parse_beats({"title": "x"}) == []
    assert story.parse_beats({}) == []
    # a connect beat's connector_kind is 'arrow', not the literal beat kind 'connect'
    bs = story.parse_beats(
        {
            "beats": [
                {"kind": "show", "entity": "a"},
                {"kind": "show", "entity": "b"},
                {"kind": "connect", "src": "a", "dst": "b", "label": "x"},
            ]
        }
    )
    conn = next(b for b in bs if b.kind == "connect")
    assert conn.connector_kind == "arrow"


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


# --------------------------------------------------------------------------- #
# Script V0: inline [concept] markers bind narration to the visual (ROADMAP §1).
# --------------------------------------------------------------------------- #
def test_parse_marks_extracts_clean_text_and_offsets():
    clean, marks = story.parse_marks("Water turns to [vapor] and forms [clouds].")
    assert clean == "Water turns to vapor and forms clouds."  # brackets stripped for TTS
    assert [m.word for m in marks] == ["vapor", "clouds"]
    assert [m.concept for m in marks] == ["vapor", "clouds"]
    for m in marks:  # offsets index the surface word IN THE CLEAN text
        assert clean[m.start : m.end] == m.word
        assert m.entity is None  # unbound until compile-time resolution


def test_parse_marks_passthrough_without_brackets():
    assert story.parse_marks("Just plain narration.") == ("Just plain narration.", ())
    assert story.parse_marks("") == ("", ())


def test_parse_marks_drops_stray_and_empty_brackets():
    # drop-don't-repair: unbalanced / empty brackets are stripped, never spoken
    clean, marks = story.parse_marks("a [unclosed and [sun] ok] and []")
    assert "[" not in clean and "]" not in clean
    assert [m.word for m in marks] == ["sun"]  # the one balanced marker survives


def test_parse_beats_carries_marks_and_cleans_text():
    beats = story.parse_beats({"beats": [{"kind": "say", "text": "The [sun] shines."}]})
    assert beats[0].text == "The sun shines."  # clean text for display/TTS
    assert [m.word for m in beats[0].marks] == ["sun"]
    plain = story.parse_beats({"beats": [{"kind": "say", "text": "no markers here"}]})[0]
    assert plain.text == "no markers here" and plain.marks == ()  # backward compatible


def test_marks_resolve_to_staged_entity_on_say_event():
    """End-to-end: a [concept] matching a shown entity rides out on the say event with a
    resolved entity id; an unmatched marker is dropped (drop-don't-repair)."""
    from engine import plan
    from engine.director import DirectorSpec

    beats = story.parse_beats(
        {
            "beats": [
                {"kind": "show", "entity": "sun", "concept": "sun", "relation": {"at": "center"}},
                {"kind": "say", "text": "The [sun] is bright but the [moon] is hidden."},
            ]
        }
    )
    spec = DirectorSpec("the sky", mode="learn", style="cartoon")
    lp = plan.lift_beats(story.sanitize_beats(beats, spec), "the sky", "cartoon")
    evs = list(plan.compile_plan(lp, spec, BOARD, generate=False))
    say_ev = next(e for e in evs if e["type"] == "say" and "sun is bright" in e["text"])
    bound = {m["word"]: m["entity"] for m in say_ev.get("marks", [])}
    assert bound.get("sun") == "sun"  # matched a shown entity -> resolved id
    assert "moon" not in bound  # unmatched -> dropped (drop-don't-repair)


def test_say_event_has_no_marks_key_when_none():
    """Backward compat: an unmarked lesson streams plain say events (no `marks`)."""
    from engine import plan
    from engine.director import DirectorSpec

    spec = DirectorSpec("rain", mode="learn", style="cartoon")
    evs = list(plan.compile_plan(story.tell_plan(spec), spec, BOARD, generate=False))
    says = [e for e in evs if e["type"] == "say"]
    assert says and all("marks" not in e for e in says)


def test_parse_marks_strips_lone_close_bracket():
    """Review fix: a stray ']' with no '[' must be stripped too (the fast path used to leak
    it into the clean text, so TTS spoke a bracket)."""
    clean, marks = story.parse_marks("The sun sets] over the hills.")
    assert "]" not in clean and marks == ()  # drop-don't-repair, never spoken
    # and through parse_beats (the path that reaches TTS):
    b = story.parse_beats({"beats": [{"kind": "say", "text": "trailing bracket]"}]})[0]
    assert "]" not in b.text


def _compiled_say(beats, topic, *, mode="learn"):
    from engine import plan
    from engine.director import DirectorSpec

    spec = DirectorSpec(topic, mode=mode, style="cartoon")
    lp = plan.lift_beats(story.sanitize_beats(beats, spec), topic, "cartoon")
    return [e for e in plan.compile_plan(lp, spec, BOARD, generate=False) if e["type"] == "say"]


def test_marks_do_not_leak_across_shots():
    beats = story.parse_beats(
        {
            "beats": [
                {"kind": "show", "entity": "sun", "concept": "sun"},
                {"kind": "say", "text": "The [sun] is up."},
                {"kind": "say", "text": "It is a fine day."},  # unmarked -> a new shot
            ]
        }
    )
    says = _compiled_say(beats, "day")
    s1 = next(e for e in says if "is up" in e["text"])
    s2 = next(e for e in says if "fine day" in e["text"])
    assert s1.get("marks") and "marks" not in s2  # marks stay on their own shot, no leak


def test_marks_resolve_forward_reference():
    """Narration mentions [moon] BEFORE its show — still binds (resolution is against the
    whole staged scene, not beat order)."""
    beats = story.parse_beats(
        {
            "beats": [
                {"kind": "say", "text": "Soon the [moon] appears."},
                {"kind": "show", "entity": "moon", "concept": "moon"},
            ]
        }
    )
    say_ev = next(e for e in _compiled_say(beats, "night") if "appears" in e["text"])
    assert {m["word"]: m["entity"] for m in say_ev.get("marks", [])}.get("moon") == "moon"


def test_marker_to_capped_out_entity_is_dropped():
    """A marker referencing an entity the concept-cap dropped resolves to nothing
    (drop-don't-repair end to end)."""
    beats = story.parse_beats(
        {
            "beats": [
                {"kind": "show", "entity": e, "concept": e}
                for e in ("sun", "moon", "star", "cloud", "tree")  # learn cap is 4 -> 'tree' drops
            ]
            + [{"kind": "say", "text": "The [sun] shines on the [tree]."}]
        }
    )
    say_ev = next(e for e in _compiled_say(beats, "nature") if "shines" in e["text"])
    words = {m["word"] for m in say_ev.get("marks", [])}
    assert "tree" not in words  # the capped-out entity's marker is dropped


def test_marks_not_bound_to_title_or_host():
    """Scaffolding (the title 'text' entity, the host) is never a marker target — markers
    bind to content props only (review fix)."""
    beats = story.parse_beats(
        {
            "beats": [
                {"kind": "show", "entity": "title", "concept": "text"},  # a title (kind=text)
                {"kind": "show", "entity": "sun", "concept": "sun"},
                {"kind": "say", "text": "read the [text] and watch the [sun]"},
            ]
        }
    )
    say_ev = next(e for e in _compiled_say(beats, "sky") if "watch the sun" in e["text"])
    bound = {m["word"]: m["entity"] for m in say_ev.get("marks", [])}
    assert "text" not in bound and bound.get("sun") == "sun"  # title skipped, content binds


def test_prompt_format_has_no_brace_bug():
    """Regression guard: the [concept] example added doubled braces — _PROMPT.format must
    not raise (a stray single brace would KeyError)."""
    out = story._PROMPT.format(
        topic="photosynthesis",
        mode_hint="hint",
        audience="child",
        tone="playful",
        depth="normal",
        concept_count=4,
        style="cartoon",
    )
    assert "photosynthesis" in out and "[sun]" in out  # formats cleanly; marker rule present


def test_lesson_svg_renders():
    from engine.svg import to_svg

    les = lesson("the carbon cycle", board=BOARD)
    out = to_svg(les.rendered, BOARD)
    assert out.startswith("<svg") and "<polyline" in out
