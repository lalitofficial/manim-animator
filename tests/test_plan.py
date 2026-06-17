"""The cartoon DIRECTION pipeline (engine.plan): DirectorSpec -> LessonPlan -> Scene ->
Shot -> Action -> compile -> timed events. Hermetic — no model call (the plan IS the IR)."""

from __future__ import annotations

from collections import Counter

from engine.contracts import Beat, Board, at, connect, right_of, say, show
from engine.director import direct
from engine.plan import (
    VERBS,
    Action,
    Entity,
    LessonPlan,
    ScenePlan,
    Shot,
    _host_entity,
    compile_plan,
    lift_beats,
    parse_plan,
)

BOARD = Board()
SPEC = direct("the water cycle", style="cartoon")


def _directed() -> LessonPlan:
    return LessonPlan(
        "The Water Cycle",
        (
            ScenePlan(
                "sky",
                setting="the water cycle",
                cast=("guide",),
                entities=(
                    Entity("guide", "presenter", "character", appearance={"pose": "point"}),
                    Entity("sun", "sun"),
                    Entity("cloud", "cloud"),
                    Entity("rain", "rain"),
                ),
                shots=(
                    Shot(
                        framing="establishing",
                        enter=("guide", "sun"),
                        say="The sun shines.",
                        actions=(Action("point", "guide", "sun"), Action("pulse", "sun")),
                    ),
                    Shot(
                        framing="close",
                        focus="rain",
                        enter=("cloud", "rain"),
                        say="It rains.",
                        actions=(Action("fall", "rain"), Action("connect", "cloud", "rain")),
                    ),
                ),
            ),
        ),
    )


def test_compile_directed_plan_emits_shots_and_actions():
    evs = list(compile_plan(_directed(), SPEC, BOARD))
    t = Counter(e["type"] for e in evs)
    assert evs[0]["type"] == "start" and evs[-1]["type"] == "done"
    assert t["draw"] >= 4 and t["action"] >= 2 and t["camera"] >= 2  # framing per shot
    verbs = [e["verb"] for e in evs if e["type"] == "action"]
    assert "pulse" in verbs and "fall" in verbs
    # `point` makes the character ACT — it re-poses the rig (guide is re-drawn, not a tilt).
    guide_draws = sum(1 for e in evs if e["type"] == "draw" and e["op"]["id"] == "guide")
    assert guide_draws >= 2
    assert evs[-1]["summary"]["shots"] == 2  # the done summary reports the shot count


def test_actions_only_reference_drawn_actors():
    evs = list(compile_plan(_directed(), SPEC, BOARD))
    drawn = {e["op"]["id"] for e in evs if e["type"] == "draw"}
    for e in evs:
        if e["type"] == "action":
            assert e["id"] in drawn  # never animate something that isn't on the board


def test_lift_beats_runs_through_the_same_compiler():
    beats = [
        say("intro"),
        show("sun", "sun", at("top_left")),
        show("cloud", "cloud", right_of("sun")),
        connect("sun", "cloud", "arrow", "warms"),
        say("more"),
        show("tree", "tree"),
    ]
    lp = lift_beats(beats, "demo")
    assert len(lp.scenes) == 1 and len(lp.scenes[0].shots) == 2  # one shot per `say`
    assert {e.id for e in lp.scenes[0].entities} == {"sun", "cloud", "tree"}
    evs = list(compile_plan(lp, SPEC, BOARD))
    assert any(e["type"] == "draw" for e in evs) and any(e["type"] == "connector" for e in evs)


def test_lift_beats_infers_semantic_roles_in_cartoon():
    """Beat content (LLM/BYO) gets the SAME visual hierarchy a directed template gets:
    the title subject (or most-connected prop) becomes the hero, particle-lexicon concepts
    shrink, the rest are props. Whiteboard stays a uniform diagram (no roles)."""
    beats = [
        show("cloud", "cloud"),
        show("rain", "raindrop"),  # particle lexicon -> small
        show("ocean", "ocean"),
        connect("ocean", "cloud", "arrow", "evaporates"),
        connect("cloud", "rain", "arrow", "falls as"),  # cloud is most-connected -> hero
    ]
    roles = {e.id: e.role for e in lift_beats(beats, "the water cycle").scenes[0].entities}
    assert roles == {"cloud": "hero", "rain": "particle", "ocean": "prop"}
    # the hero towers over the particle once measured + staged (semantic scale)
    spec = direct("the water cycle", style="cartoon")
    evs = list(compile_plan(lift_beats(beats, "the water cycle"), spec, BOARD))
    h = {}
    for e in evs:
        if e["type"] == "draw" and e["op"]["id"] in roles:
            ys = [p[1] for s in e["op"]["strokes"] for p in s["points"]]
            h[e["op"]["id"]] = (max(ys) - min(ys)) if ys else 0
    assert h["cloud"] > h["rain"]  # hero drawn bigger than the particle
    # whiteboard keeps every node role-less (a diagram, not a staged scene)
    white = {e.id: e.role for e in lift_beats(beats, "x", style="whiteboard").scenes[0].entities}
    assert set(white.values()) == {None}


def test_scene_emotion_drives_face_warmth_and_pacing():
    """Emotion is first-class director intent: it sets the host's FACE, warms the BACKDROP,
    and PACES the beat (tension cuts quick, joy lingers) — the same staging FEELS different."""

    def scene(emotion):
        return ScenePlan(
            emotion,
            setting="a forest",
            emotion=emotion,
            entities=(Entity("tree", "tree", role="hero"),),
            shots=(Shot(enter=("tree",), say="A tree.", hold="med"),),
        )

    lp = LessonPlan("Moods", (scene("tense"), scene("joyful")))
    evs = list(compile_plan(lp, direct("a forest", style="cartoon"), BOARD))
    holds = [e["ms"] for e in evs if e["type"] == "hold"]
    assert holds[0] < holds[1]  # tense beat cuts quicker than the joyful one
    tops = [e["gradient"]["top"] for e in evs if e["type"] == "background"]
    assert tops[0] != tops[1]  # each mood warms the sky differently
    assert [e["emotion"] for e in evs if e["type"] == "background"] == ["tense", "joyful"]
    # the injected presenter's face follows the mood (rig EXPRESSIONS)
    assert _host_entity(direct("x"), "wonder").appearance["expression"] == "surprised"
    assert _host_entity(direct("x"), "tense").appearance["expression"] == "neutral"
    # purpose shapes the host's body language (pose)
    assert _host_entity(direct("x"), "", "contrast").appearance["pose"] == "point"


def test_joyful_host_carries_a_motion_clip():
    """The presenter ACTS its mood: a joyful scene attaches a (mined) gesture clip to the
    host draw — placed frames the board flips through. The frames genuinely move."""
    lp = LessonPlan(
        "Party",
        (
            ScenePlan(
                "s",
                setting="a party",
                emotion="joyful",
                entities=(Entity("cake", "cake", role="hero"),),
                shots=(Shot(enter=("cake",), say="Hooray!"),),
            ),
        ),
    )
    evs = list(compile_plan(lp, direct("a party", style="cartoon"), BOARD))
    host = next(e for e in evs if e["type"] == "draw" and e["op"]["id"] == "guide")
    frames = host["op"].get("frames")
    assert frames and len(frames) > 4 and host["op"]["fps"]
    assert any(
        f != frames[0] for f in frames
    )  # the rig moves (cheer returns to idle, so mid differs)
    # whiteboard host (none here) + calm/tense scenes don't animate
    calm = list(
        compile_plan(
            LessonPlan(
                "C",
                (
                    ScenePlan(
                        "s",
                        emotion="tense",
                        entities=(Entity("x", "rock"),),
                        shots=(Shot(enter=("x",)),),
                    ),
                ),
            ),
            direct("x", style="cartoon"),
            BOARD,
        )
    )
    chost = next(e for e in calm if e["type"] == "draw" and e["op"]["id"] == "guide")
    # tense holds no big gesture, but still BREATHES — a looping idle-life (sway + blink)
    assert chost["op"].get("loop") is True and chost["op"].get("frames")


def test_per_scene_casting_changes_the_host():
    """The host is recast PER SCENE from the scene's setting/content — a story that moves
    through settings changes who's on stage (lab→scientist, field→farmer)."""
    lp = LessonPlan(
        "Food",
        (
            ScenePlan("s0", setting="inside the science lab", shots=(Shot(say="study"),)),
            ScenePlan("s1", setting="out in the farm field", shots=(Shot(say="grow"),)),
        ),
    )
    evs = list(compile_plan(lp, direct("food", style="cartoon"), BOARD))
    hosts = [e for e in evs if e["type"] == "draw" and e["op"]["id"] == "guide"]
    assert len(hosts) == 2
    assert hosts[0]["op"]["strokes"] != hosts[1]["op"]["strokes"]  # scientist ≠ farmer costume
    # the injected host is a neutral presenter; the SCENE recasts it
    assert _host_entity(direct("food", style="cartoon")).concept == "presenter"


def test_lift_beats_gives_cartoon_an_emotional_arc():
    beats = [show("a", "sun"), say("one"), connect("a", "b", "arrow", "x"), show("b", "cloud")]
    # single cartoon scene -> an engaged, curious default (not a flat happy host)
    assert lift_beats(beats, "x").scenes[0].emotion == "curious"
    # a multi-scene lift LANDS on joy (a satisfying close); whiteboard stays mood-less
    multi = [show("a", "sun"), say("s1"), Beat("clear"), show("b", "cloud"), say("s2")]
    cartoon = lift_beats(multi, "x")
    assert cartoon.scenes[0].emotion == "curious" and cartoon.scenes[-1].emotion == "joyful"
    assert {s.emotion for s in lift_beats(multi, "x", style="whiteboard").scenes} == {""}


def test_parse_plan_from_json_and_rejects_beats():
    data = {
        "title": "T",
        "scenes": [
            {
                "id": "a",
                "setting": "space",
                "purpose": "introduce",
                "emotion": "wonder",
                "entities": [
                    {"id": "sun", "concept": "sun", "role": "hero"},
                    {"id": "p", "concept": "planet"},
                ],
                "shots": [
                    {
                        "enter": ["sun", "p"],
                        "say": "hi",
                        "actions": [{"verb": "pulse", "actor": "sun"}],
                    }
                ],
            }
        ],
    }
    lp = parse_plan(data)
    assert lp is not None and lp.scenes[0].setting == "space"
    assert lp.scenes[0].purpose == "introduce" and lp.scenes[0].emotion == "wonder"
    assert lp.scenes[0].entities[0].role == "hero"  # authored role round-trips
    assert lp.scenes[0].shots[0].actions[0].verb == "pulse"
    # a flat beats payload is NOT a plan -> None (caller falls back to parse_beats)
    assert parse_plan({"beats": [{"kind": "show", "entity": "x"}]}) is None


def test_parse_plan_drops_unknown_verbs():
    lp = parse_plan(
        {
            "scenes": [
                {
                    "shots": [
                        {
                            "actions": [
                                {"verb": "teleport", "actor": "x"},
                                {"verb": "pulse", "actor": "y"},
                            ]
                        }
                    ]
                }
            ]
        }
    )
    verbs = [a.verb for sh in lp.scenes[0].shots for a in sh.actions]
    assert verbs == ["pulse"]  # only the closed vocabulary survives


def test_verb_vocabulary_is_closed():
    assert {"rise", "fall", "pulse", "point", "transform", "connect"} <= VERBS
    assert "enter" not in VERBS  # entry is the draw reveal, not a motion verb


def test_authored_cast_members_do_not_collapse_to_one_role():
    """A scene can stage its OWN distinct cast — two authored characters must render as
    two different rigs (the per-scene recast applies to the injected host only)."""
    lp = LessonPlan(
        "T",
        (
            ScenePlan(
                "s",
                setting="a farm",
                entities=(
                    Entity("a", "farmer", "character", appearance={"size": 2.5}),
                    Entity("b", "scientist", "character", appearance={"size": 2.5}),
                ),
                shots=(Shot(enter=("a", "b"), say="hi"),),
            ),
        ),
    )
    evs = list(compile_plan(lp, direct("farm", style="cartoon"), BOARD))
    a = next(e for e in evs if e["type"] == "draw" and e["op"]["id"] == "a")["op"]["strokes"]
    b = next(e for e in evs if e["type"] == "draw" and e["op"]["id"] == "b")["op"]["strokes"]
    assert a != b  # farmer (straw hat) ≠ scientist (lab coat) — no collapse
