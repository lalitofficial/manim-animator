"""Autoregressive story orchestration — hermetic (the per-scene LLM call is faked).

Proves the assembly logic (N scenes, clears between, running context fed forward, drop-don't-
repair) WITHOUT a model; the real Ollama generation is exercised by the manual smoke test.
"""

from __future__ import annotations

import json

from engine.autostory import AutoregressiveStory
from engine.director import DirectorSpec


def test_autoregressive_assembles_scenes_and_carries_context_forward():
    prompts: list[str] = []
    state = {"i": 0}

    def fake_complete(prompt, schema=None):
        prompts.append(prompt)
        state["i"] += 1
        i = state["i"]
        return json.dumps(
            {
                "beats": [
                    {"kind": "show", "entity": f"c{i}", "concept": f"thing{i}"},
                    {"kind": "say", "text": f"Scene {i} introduces [c{i}]."},
                ]
            }
        )

    prov = AutoregressiveStory(complete=fake_complete)
    beats = prov.tell(DirectorSpec("the water cycle", mode="story", length="5min"))  # 8 scenes

    assert len(prompts) == 8  # one LLM call per scene (autoregressive, not one-shot)
    assert sum(1 for b in beats if b.kind == "clear") == 7  # 8 scenes -> 7 board clears
    assert [b.entity for b in beats if b.kind == "show"] == [f"c{i}" for i in range(1, 9)]
    # AUTOREGRESSIVE: a later scene's prompt carries the EARLIER narration forward as context
    assert "Scene 1 introduces c1." in prompts[-1]
    assert "scene 8 of 8" in prompts[-1].lower()  # the model is told where it is in the arc


def test_autoregressive_drops_repeats_and_skips_barren_scenes():
    def repeat_complete(prompt, schema=None):
        return json.dumps(  # every scene tries to (re)introduce the same concept
            {
                "beats": [
                    {"kind": "show", "entity": "sun", "concept": "sun"},
                    {"kind": "say", "text": "The [sun]."},
                ]
            }
        )

    beats = AutoregressiveStory(complete=repeat_complete).tell(
        DirectorSpec("x", mode="story", length="2min")  # 3 scenes
    )
    # only the FIRST 'sun' survives; the repeat scenes have no NEW drawable -> skipped, no clears
    assert sum(1 for b in beats if b.kind == "show" and b.entity == "sun") == 1
    assert not any(b.kind == "clear" for b in beats)


def test_scene_count_follows_the_length_knob():
    def counting(length):
        calls = []

        def c(prompt, schema=None):
            calls.append(1)
            i = len(calls)
            return json.dumps({"beats": [{"kind": "show", "entity": f"c{i}", "concept": f"k{i}"}]})

        AutoregressiveStory(complete=c).tell(DirectorSpec("x", mode="story", length=length))
        return len(calls)

    assert counting("5min") == 8 and counting("10min") == 16  # length -> scenes -> LLM calls
