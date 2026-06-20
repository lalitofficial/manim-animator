"""The Story-Studio → animation BRIDGE (plan.from_story_package) — the two-stage workflow's join.

An APPROVED StoryPackage becomes a multi-scene animated LessonPlan: one scene per story scene,
`focus`→hero drawable, `beat`/`goal`/`turn`→narration, `direction`→process motion. This is how a
generated+approved story turns into a full-length cartoon.
"""

from __future__ import annotations

from engine import plan
from engine.contracts import Board
from engine.director import direct
from engine.plan import compile_plan


def _pkg(scenes):
    return {"title": "the water cycle", "scenes": scenes}


def test_one_animated_scene_per_story_scene_with_motion():
    pkg = _pkg(
        [
            {
                "focus": "sun",
                "beat": "The sun warms the ocean.",
                "direction": "the sun shines down",
                "purpose": "introduce",
                "emotion": "curious",
                "goal": "Show the energy source.",
            },
            {
                "focus": "vapor",
                "beat": "Water rises as invisible vapor.",
                "direction": "small dots rise upward",
                "purpose": "build",
                "emotion": "wonder",
                "turn": "It disappears into the sky.",
            },
            {
                "focus": "cloud",
                "beat": "The vapor forms a cloud.",
                "direction": "dots condense into a cloud",
                "purpose": "resolve",
                "emotion": "joyful",
            },
        ]
    )
    lp = plan.from_story_package(pkg)
    assert lp.title == "the water cycle" and len(lp.scenes) == 3  # one scene per story scene
    # focus -> the hero concept (a drawable subject), not a generic box
    assert [s.entities[0].concept for s in lp.scenes] == ["sun", "vapor", "cloud"]
    assert all(s.entities[0].role == "hero" for s in lp.scenes)
    # direction -> a PROCESS motion verb on the subject (the animation IS the explanation)
    verbs = {a.verb for s in lp.scenes for sh in s.shots for a in sh.actions}
    assert "rise" in verbs and "transform" in verbs  # vapor rises; the cloud forms (condenses)
    # purpose/emotion carried straight from the story
    assert lp.scenes[0].purpose == "introduce" and lp.scenes[-1].emotion == "joyful"
    # narration comes from the scene text (beat spine + a distinct goal/turn line)
    says = [sh.say for sh in lp.scenes[1].shots]
    assert "Water rises as invisible vapor." in says and "It disappears into the sky." in says


def test_bridge_animates_a_film_not_a_diagram():
    pkg = _pkg([{"focus": "sun", "beat": "The sun shines.", "direction": "it shines"}])
    lp = plan.from_story_package(pkg, "cartoon")
    spec = direct("the water cycle", mode="story", style="cartoon")
    evs = list(compile_plan(lp, spec, Board(), generate=False))
    assert not any(e["type"] == "connector" for e in evs)  # cartoon is film: NO arrows
    assert any(e["type"] == "say" for e in evs) and any(e["type"] == "draw" for e in evs)


def test_length_drives_video_length():
    short = plan.from_story_package(_pkg([{"focus": "sun", "beat": "a"}]))
    long = plan.from_story_package(
        _pkg([{"focus": f"c{i}", "beat": f"line {i}"} for i in range(8)])
    )
    assert len(short.scenes) == 1 and len(long.scenes) == 8  # #story scenes -> video length


def test_empty_or_malformed_package_is_safe():
    assert len(plan.from_story_package({"title": "x", "scenes": []}).scenes) == 1
    assert len(plan.from_story_package({}).scenes) == 1  # degenerate but valid, no crash
    # a non-dict scene is skipped, not fatal
    lp = plan.from_story_package({"title": "x", "scenes": ["junk", {"focus": "sun", "beat": "ok"}]})
    assert [s.entities[0].concept for s in lp.scenes] == ["sun"]
