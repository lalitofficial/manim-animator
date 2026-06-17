"""The Director layer: request + controls -> a typed DirectorSpec (hermetic,
deterministic). Every field maps to a Story-prompt modifier or an engine knob.
"""

from __future__ import annotations

from engine.director import DirectorSpec, direct, to_dict


def test_defaults_are_sane():
    s = direct("photosynthesis")
    assert s.mode == "learn" and s.depth == "normal" and s.audience == "general"
    assert s.concept_count == 3 and s.draw_speed == 1.0


def test_natural_language_cues_are_read():
    s = direct("photosynthesis", request="explain photosynthesis like I'm 5 and keep it fun")
    assert s.audience == "child" and s.tone == "playful" and s.energy == "lively"
    assert s.draw_speed > 1.0  # lively -> faster reveal

    deep = direct("x", request="a deep, technical, rigorous treatment")
    assert deep.depth == "deep" and deep.audience == "expert" and deep.tone == "formal"


def test_topic_words_do_not_reclassify_the_lesson():
    # cues are read from an explicit REQUEST only — never the topic itself
    assert direct("deep sea creatures").depth == "normal"  # not 'deep'
    assert direct("a simple machine").audience == "general"  # not 'child'
    assert direct("a brief history of time").depth == "normal"  # not 'brief'
    # the child cue implies the cartoon style, matching the audience=child dropdown
    s = direct("photosynthesis", request="explain like i'm 5")
    assert s.audience == "child" and s.style == "cartoon"
    assert direct("x", audience="child").style == "cartoon"  # the two paths agree


def test_explicit_controls_win_over_cues():
    s = direct("x", mode="story", request="quick and simple", audience="expert")
    assert s.mode == "story"  # explicit mode beats inference
    assert s.audience == "expert"  # explicit override beats "simple" -> child
    assert s.depth == "brief"  # cue still applied where not overridden


def test_derived_knobs():
    assert DirectorSpec("x", density="sparse").concept_count == 2
    assert DirectorSpec("x", density="dense").concept_count == 5
    assert DirectorSpec("x", depth="deep").concept_count == 4
    assert DirectorSpec("x", energy="calm").draw_speed < 1.0
    assert DirectorSpec("x", energy="lively").say_dwell < 1.0


def test_to_dict_includes_derived():
    d = to_dict(direct("x"))
    assert {"mode", "audience", "concept_count", "draw_speed", "say_dwell"} <= d.keys()
