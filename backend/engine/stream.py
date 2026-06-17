"""Streaming lesson runtime — the live cadence (ARCHITECTURE §1).

The Story emits a directed LessonPlan (scenes/shots/actions); `plan.compile_plan` turns
it into the renderer's timed event stream. This is now a THIN selector: a topic goes to
the Story engine (local Ollama / template), a bring-your-own story is sanitized + lifted
to a plan — then BOTH compile through the one pipeline to the one renderer.

Events: start / background / camera / draw / connector / say / action / hold / clear / done.
"""

from __future__ import annotations

from collections.abc import Iterator

from engine import director, plan, story
from engine.contracts import Board


def stream_lesson(
    topic: str,
    mode: str = "learn",
    board: Board | None = None,
    generate: bool = True,
    spec=None,
    beats=None,
) -> Iterator[dict]:
    board = board or Board()
    spec = spec if spec is not None else director.direct(topic, mode=mode)
    if beats is not None:
        # Bring-your-own beats: sanitize (author-trusted cap) -> lift to a plan -> compile.
        lifted = plan.lift_beats(
            story.sanitize_beats(beats, spec, max_concepts=8), topic, spec.style
        )
        prov = {"requested": "script", "used": "script", "fallback": False, "reason": None}
        yield from plan.compile_plan(lifted, spec, board, generate, provenance=prov)
        return
    r = story.plan_lesson(topic, spec)
    prov = {"requested": r.requested, "used": r.used, "fallback": r.fallback, "reason": r.reason}
    yield from plan.compile_plan(r.plan, spec, board, generate, provenance=prov)
