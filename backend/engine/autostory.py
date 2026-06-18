"""Autoregressive Story generation — EXPERIMENT (branch: autoregressive-story).

WHY: the one-shot approach (story._PROMPT + a single BEAT_SCHEMA call with a big minItems floor)
doesn't scale. A small local model can't emit a long, coherent lesson in one JSON object — it
truncates, repeats itself, or loses the thread, and we papered over it with arbitrary caps/floors.

So generate the lesson AUTOREGRESSIVELY: one SCENE at a time, each conditioned on the story-so-far
(its narration + the concepts already drawn), looping to the target length. Each call is small (a
few beats) — squarely in a 7B model's competence — and the running context keeps it coherent and
non-repetitive. Length is just "how many scenes", so 2/5/10-min lessons fall out naturally. (It also
pairs with streaming: play scene k while scene k+1 generates — the PAPER plan-ahead property; not
wired yet, but the per-scene seam is the hook.)

Same StoryProvider contract as story.OllamaStory (`tell(spec) -> list[Beat]`); the per-scene LLM
call is INJECTABLE so the orchestration is hermetically testable without a model.
"""

from __future__ import annotations

import copy
import json
import os
import urllib.request

from engine import story
from engine.contracts import Beat, clear
from engine.director import DirectorSpec

# One SCENE is a small, reliable generation: a few beats, not a whole lesson.
_SCENE_SCHEMA = copy.deepcopy(story.BEAT_SCHEMA)
_SCENE_SCHEMA["properties"]["beats"]["minItems"] = 3
_SCENE_SCHEMA["properties"]["beats"]["maxItems"] = 10
_CONTEXT_WINDOW = 8  # how many recent narration lines to feed forward (bounds the prompt)


def _arc_guidance(i: int, n: int) -> str:
    """The scene's job in the arc, by position — so an autoregressive story still has SHAPE
    (open → build → turn → resolve) instead of drifting scene to scene."""
    if i == 0:
        return "This is the OPENING scene — set the scene and introduce the subject."
    if i == n - 1:
        return "This is the FINAL scene — resolve the idea and end on a satisfying note."
    pos = i / (n - 1)
    if pos < 0.45:
        return "Build on what came before — develop the idea one step further."
    if pos < 0.75:
        return "This is a TURNING POINT — the key mechanism or the most important idea."
    return "Start bringing the threads together toward the conclusion."


class AutoregressiveStory:
    """Generate a lesson scene-by-scene, each scene conditioned on the story so far."""

    name = "ollama-ar"

    def __init__(self, model: str | None = None, complete=None) -> None:
        self.model = model or os.environ.get("OLLAMA_STORY_MODEL", "qwen2.5:7b")
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        self._complete_fn = complete  # injectable for tests; else the live Ollama call

    def tell(self, spec: DirectorSpec) -> list[Beat]:
        """Roll forward N scenes, each conditioned on the prior narration + drawn concepts.
        Drop-don't-repair: a repeated concept is dropped, and a scene with no NEW drawable is
        skipped (no clear), so the lesson never stalls on a barren or duplicate scene."""
        n = max(2, spec.scenes)
        beats: list[Beat] = []
        transcript: list[str] = []  # narration so far — the autoregressive context
        concepts: list[str] = []  # concepts already drawn (human-readable, fed to the next prompt)
        seen: set[str] = set()  # entity ids AND concept words already drawn — the dedup keys
        for i in range(n):
            scene: list[Beat] = []
            for b in self._scene(spec, i, n, transcript, concepts):
                if b.kind == "show":
                    keys = {(b.entity or "").lower(), (b.concept or "").strip().lower()} - {""}
                    if keys & seen:
                        continue  # the same thing again (by id OR concept) → drop, don't redraw
                    seen |= keys
                scene.append(b)
            if not any(b.kind == "show" for b in scene):
                continue  # no NEW drawable this scene → skip it (don't clear to an empty board)
            if beats:
                beats.append(clear())  # each scene is a fresh staged board
            beats.extend(scene)
            transcript.extend(b.text for b in scene if b.kind == "say" and b.text)
            concepts.extend(b.concept for b in scene if b.kind == "show" and b.concept)
        return beats

    def _scene(
        self, spec, i: int, n: int, transcript: list[str], concepts: list[str]
    ) -> list[Beat]:
        raw = self._complete(self._prompt(spec, i, n, transcript, concepts), _SCENE_SCHEMA)
        return story.parse_beats(json.loads(story._strip_json(raw or "{}")))

    def _prompt(self, spec, i: int, n: int, transcript: list[str], concepts: list[str]) -> str:
        from engine import icons

        vocab = ", ".join(icons.known())
        so_far = "\n".join(f"  - {t}" for t in transcript[-_CONTEXT_WINDOW:]) or (
            "  (this is the opening scene)"
        )
        drawn = ", ".join(concepts) or "(none yet)"
        return (
            f'Write ONE scene of an animated cartoon lesson on "{spec.topic}" for a {spec.audience} '
            f"audience, {spec.tone} tone. This is scene {i + 1} of {n}. {_arc_guidance(i, n)}\n\n"
            f"THE LESSON SO FAR (narration):\n{so_far}\nConcepts already drawn: {drawn}.\n\n"
            'Output ONLY a JSON object {"beats":[ ... ]}. Each beat is one of:\n'
            '  {"kind":"show","entity":"id","concept":"drawable noun","relation":{"<rel>":"<arg>"}}\n'
            '  {"kind":"connect","src":"id","dst":"id","label":"short verb"}\n'
            '  {"kind":"say","text":"one sentence of narration"}\n'
            f"{story._RELATION_PROMPT}\n"
            "RULES:\n"
            f'- STAY STRICTLY ON TOPIC: every concept must be a real, specific part of "{spec.topic}" '
            "— never an unrelated object. (For 'the water cycle': sun, cloud, rain, river, ocean — "
            "NOT a watermelon or any random item.)\n"
            "- Introduce 1-3 NEW drawable concepts THIS scene; reference already-drawn ones but do "
            "NOT re-show them.\n"
            f"- every concept is a CONCRETE, DRAWABLE noun; prefer ones with an icon here:\n  {vocab}\n"
            "- 2-4 say lines; in each, wrap a shown concept's word in [brackets] (its id/concept).\n"
            "- CONTINUE coherently from THE LESSON SO FAR — advance it, never restart or repeat.\n"
            "Output ONLY the JSON object."
        )

    def _complete(self, prompt: str, schema: dict) -> str | None:
        if self._complete_fn is not None:  # injected (tests)
            return self._complete_fn(prompt, schema)
        return self._ollama(prompt, schema)  # pragma: no cover - network

    def _ollama(self, prompt: str, schema: dict) -> str | None:  # pragma: no cover - network
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "format": schema,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        return story._http_json(req)["message"]["content"]
