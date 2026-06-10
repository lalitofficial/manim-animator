"""Lesson planner — turns a topic into a *streamed* sequence of board segments.

This is the live-board planner. Where planner.py emits one Scene for an offline
mp4, this emits a lesson as it is planned, segment by segment, so the board
starts drawing while later segments are still being thought up.

Latency is the design driver (local 7B models generate ~10 tok/s):

  intro    deterministic, no LLM — the title is on the board and the teacher
           is talking in <1s while the model warms up on the real work
  call 1   topic -> {title, plan, narration, objects, steps}  — the lesson
           outline and the first real segment in ONE round trip
  call 2+  one small call per remaining segment
  voice    every call streams; the moment the "narration" field closes we
           emit it, so speech starts seconds in, not after full generation
  cache    the segment system prompt is byte-identical across calls (board
           state travels in the user message), so Ollama's KV prefix cache
           re-evals only ~100 new tokens per segment instead of the world

Same safety rules as planner.py: the model only ever emits IR (no code), and
every failure degrades — a bad segment becomes a narration-only card, a dead
Ollama becomes a deterministic mock lesson. A lesson never hard-fails.
"""

from __future__ import annotations

import json
import re
import time
from typing import Iterator, Optional

from pydantic import BaseModel, Field

from assets import catalog
from ir import SceneObject, Step
from planner import _coerce, _strip_to_json, chat_stream, ollama_available, pick_model

# Matches a completed `"narration": "..."` value in a *partial* JSON stream.
NARRATION_RE = re.compile(r'"narration"\s*:\s*"((?:\\.|[^"\\])*)"')


class SegmentIR(BaseModel):
    """One teaching beat: what the teacher says + what gets drawn."""
    narration: str = ""
    clear: bool = Field(False, description="Wipe the board before this segment.")
    objects: list[SceneObject] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)


class LessonStart(SegmentIR):
    """Call-1 payload: the plan and the first drawn segment together."""
    title: str = "Lesson"
    plan: list[dict] = Field(default_factory=list)  # [{title, goal}], plan[0] == this segment


# --------------------------------------------------------------------------- #
# Prompts (built with .replace — they contain literal {}).
# IMPORTANT: SEGMENT_SYSTEM must stay constant across calls within a lesson
# (and across lessons) so Ollama's prefix cache keeps it hot. Anything that
# varies (board state, plan, segment goal) goes in the *user* message.
# --------------------------------------------------------------------------- #
_SHARED_IR = """OBJECT shapes — EVERY object MUST start with a unique "id" string:
- {"id":str,"type":"asset","asset":"<name>","params":{"color":hex},"position":[x,y],"scale":num}
    use ONLY for real-world things: people, vehicles, nature, buildings, etc.
- {"id":str,"type":"text","text":str,"font_size":num,"position":[x,y],"color":hex}
- {"id":str,"type":"circle","radius":num,"position":[x,y],"color":hex}
- {"id":str,"type":"square","width":num,...} / {"id":str,"type":"rectangle","width":num,"height":num,...}
- {"id":str,"type":"triangle"|"polygon","points":[[x,y],...]}   (>=3 vertices)
- {"id":str,"type":"line"|"arrow","start":[x,y],"end":[x,y],"color":hex}
- {"id":str,"type":"dot","position":[x,y]}

ASSET names (use for real things; do NOT fake them with shapes):
__CATALOG__

STEP shapes (run in order while you talk):
{"animation":"write|create|fadein|fadeout|move|scale|transform|wait",
 "target":"object id", "to":[x,y] (move), "into":"id" (transform),
 "factor":num (scale), "duration":seconds}

RULES:
- BE BRIEF: narration is 1-3 short sentences; 1-4 new objects; 2-6 steps;
  each "write"/"create" 0.8-2.0s. Compact JSON, no extra whitespace.
- The user message lists what is ALREADY ON THE BOARD. Do not redefine those
  ids; you MAY reference them in steps (move, fadeout, scale...).
- Place new things in EMPTY space (origin center, +y up, x:[-6.5,6.5], y:[-3.5,3.5]).
- Set "clear": true ONLY if the board is full or the topic shifts completely.
- Labels: short text near the thing they label.
- EVERY step except "wait" MUST have a "target".
- A step "target" must be an id you defined in "objects" OR one already on the
  board — never an id you didn't define. Steps with unknown ids are DROPPED."""

START_SYSTEM = """You are a teacher starting a whiteboard lesson. In ONE JSON
object (no markdown), give the lesson plan AND the first thing you draw:
{
  "narration": "1-3 friendly sentences you say while drawing this first part",
  "title": "lesson title",
  "plan": [{"title": "short segment name", "goal": "<=10 words, what to draw"}],
  "clear": false,
  "objects": [ {object} ],
  "steps":   [ {step} ]
}
"narration" MUST be the FIRST field. "plan" MUST have EXACTLY 4 entries — the
whole lesson in teaching order, ending with a recap. plan[0] is the segment you
are drawing NOW (objects/steps here teach plan[0] only — later segments come in
later turns, so plan[1..3] are titles+goals only).

__SHARED__
Output JSON only."""

SEGMENT_SYSTEM = """You are a teacher mid-lesson, drawing on a whiteboard while
talking. The user message gives the lesson plan, what is already on the board,
and which segment to teach NOW. Output ONE JSON object (no markdown):
{
  "narration": "1-3 friendly sentences you say while drawing",
  "clear": false,
  "objects": [ {object} ],
  "steps":   [ {step} ]
}
"narration" MUST be the FIRST field.

__SHARED__
Output JSON only."""

START_SYSTEM = START_SYSTEM.replace("__SHARED__", _SHARED_IR)
SEGMENT_SYSTEM = SEGMENT_SYSTEM.replace("__SHARED__", _SHARED_IR)


# --------------------------------------------------------------------------- #
# Streaming plan call with early narration
# --------------------------------------------------------------------------- #
def _plan_events(model: str, messages: list[dict], validate, attempts: int = 3,
                 num_predict: int | None = None):
    """Yield ("narration", text) as soon as it appears in the token stream,
    then ("result", validated) — or raise after `attempts` repairs."""
    narrated = False
    last_err: Exception | None = None
    for _ in range(attempts):
        buf = ""
        for chunk in chat_stream(model, messages, temperature=0.3,
                                 num_predict=num_predict):
            buf += chunk
            if not narrated:
                m = NARRATION_RE.search(buf)
                if m:
                    try:
                        text = json.loads(f'"{m.group(1)}"')
                    except json.JSONDecodeError:
                        text = m.group(1)
                    if text.strip():
                        narrated = True
                        yield ("narration", text)
        try:
            data = _coerce(json.loads(_strip_to_json(buf)))
            yield ("result", validate(data))
            return
        # ValueError covers JSONDecodeError, pydantic's ValidationError, and
        # the semantic errors raised by _segment_validator.
        except ValueError as e:
            last_err = e
            messages.append({"role": "assistant", "content": buf})
            messages.append({"role": "user", "content":
                f"That JSON was invalid:\n{e}\n"
                "Fix ALL of these errors and return the full corrected JSON only."})
    raise last_err if last_err else RuntimeError("planner produced no output")


def _segment_validator(board: dict[str, list[float]], model_cls=SegmentIR):
    """Schema-validate, then enforce step/id integrity *cheaply*: dangling
    steps are pruned (a repair round trip costs ~40s locally; dropping a bad
    step costs nothing). Only an effectively-empty segment triggers repair."""
    def validate(data):
        seg = model_cls.model_validate(data)
        known = (set() if seg.clear else set(board)) | {o.id for o in seg.objects}
        kept = []
        for s in seg.steps:
            if s.animation == "wait":
                kept.append(s)
                continue
            if not s.target or s.target not in known:
                continue
            if s.animation == "transform" and (not s.into or s.into not in known):
                continue
            kept.append(s)
        dropped = len(seg.steps) - len(kept)
        # A declared object nothing animates would sit invisible forever
        # (objects only appear via steps). Prepend a reveal for each, so
        # "everything you declare gets drawn" holds even after pruning.
        targeted = {s.target for s in kept} | {s.into for s in kept}
        grouped = {m for o in seg.objects if o.type == "group" for m in (o.members or [])}
        auto = [Step(animation="write" if o.type in ("text", "mathtex") else "create",
                     target=o.id, duration=1.0)
                for o in seg.objects if o.id not in targeted and o.id not in grouped]
        seg.steps = auto + kept
        if not seg.objects and sum(1 for s in kept if s.animation != "wait") < 2:
            raise ValueError(
                f"{dropped} step(s) referenced ids that are neither defined in "
                '"objects" nor already on the board, leaving nothing to draw. '
                'Define every id you target in "objects", or target only ids '
                "from the board list.")
        return seg
    return validate


def _board_summary(board: dict[str, list[float]]) -> str:
    if not board:
        return "(the board is empty)"
    return "; ".join(f'"{oid}" at [{p[0]:g},{p[1]:g}]' for oid, p in board.items())


def _plan_text(plan: list[dict]) -> str:
    return " / ".join(f"{i + 1}. {p.get('title', '')}" for i, p in enumerate(plan))


# --------------------------------------------------------------------------- #
# Deterministic pieces (no LLM)
# --------------------------------------------------------------------------- #
def _intro_segment(topic: str) -> SegmentIR:
    """First paint in <1s: the title goes up while the model does real work."""
    title = (topic.strip().split("\n")[0] or "Lesson")[:60]
    return SegmentIR(
        narration=f"Alright — let's learn about {title}. Let me sketch this out.",
        objects=[SceneObject(id="intro_title", type="text", text=title.title(),
                             font_size=44, position=(0.0, 3.2, 0.0), color="#58A6FF")],
        steps=[Step(animation="write", target="intro_title", duration=1.4)],
    )


def _fallback_segment(title: str, goal: str, index: int) -> SegmentIR:
    """A narration-only card so a failed segment still teaches something."""
    return SegmentIR(
        narration=goal or title,
        objects=[SceneObject(id=f"fb_{index}", type="text", text=title,
                             font_size=30, position=(0.0, 2.2 - index * 0.9, 0.0),
                             color="#8B949E")],
        steps=[Step(animation="write", target=f"fb_{index}", duration=1.0)],
    )


def _track_board(board: dict[str, list[float]], seg: SegmentIR) -> None:
    """Maintain the ids+positions summary fed to the next segment prompt."""
    if seg.clear:
        board.clear()
    for o in seg.objects:
        if o.type != "group":
            board[o.id] = [o.position[0], o.position[1]]
    for s in seg.steps:
        if s.animation == "fadeout" and s.target:
            board.pop(s.target, None)
        elif s.animation == "move" and s.target and s.to and s.target in board:
            board[s.target] = [s.to[0], s.to[1]]


# --------------------------------------------------------------------------- #
# Mock lesson (no Ollama) — keeps the live board demoable offline.
# --------------------------------------------------------------------------- #
def mock_lesson(topic: str) -> Iterator[dict]:
    title = (topic.strip().split("\n")[0] or "Lesson")[:60]
    yield {"type": "lesson", "title": title, "model": None,
           "segments": [{"title": "Introduction"}, {"title": "The idea"}, {"title": "Recap"}]}
    segs = [
        _intro_segment(topic),
        SegmentIR(
            narration="Here's a simple picture of the idea: one thing leads to another.",
            objects=[
                SceneObject(id="m_a", type="circle", radius=0.9, position=(-3.5, 0.0, 0.0), color="#3FB950"),
                SceneObject(id="m_b", type="square", width=1.8, position=(3.5, 0.0, 0.0), color="#D29922"),
                SceneObject(id="m_arrow", type="arrow", start=(-2.4, 0.0, 0.0), end=(2.4, 0.0, 0.0), color="#E6EDF3"),
            ],
            steps=[Step(animation="create", target="m_a", duration=1.0),
                   Step(animation="create", target="m_b", duration=1.0),
                   Step(animation="create", target="m_arrow", duration=0.9),
                   Step(animation="scale", target="m_b", factor=1.25, duration=0.6)]),
        SegmentIR(
            narration="And that's the heart of it. Start Ollama to get real lessons on any topic.",
            objects=[SceneObject(id="m_note", type="text",
                                 text="(mock lesson — start Ollama for real teaching)",
                                 font_size=22, position=(0.0, -3.2, 0.0), color="#8B949E")],
            steps=[Step(animation="fadein", target="m_note", duration=0.8),
                   Step(animation="wait", duration=0.5)]),
    ]
    for i, s in enumerate(segs):
        yield {"type": "segment", "index": i, "title": ["Introduction", "The idea", "Recap"][i],
               **s.model_dump()}
    yield {"type": "done"}


# --------------------------------------------------------------------------- #
# Public generator — the websocket endpoint iterates this.
# --------------------------------------------------------------------------- #
def stream_lesson(topic: str, model: Optional[str] = None) -> Iterator[dict]:
    """Yield lesson events: intro segment immediately, then narration/segment
    events as the model produces them, then done.

    Synchronous generator (Ollama calls block); the caller runs it on a
    thread (asyncio.to_thread / run_in_executor) and forwards events.
    """
    t0 = time.time()
    elapsed = lambda: round(time.time() - t0, 1)
    model = model or (pick_model() if ollama_available() else None)
    if not model:
        yield from mock_lesson(topic)
        return

    # 0. Instant intro — the board is alive before the model says a word.
    intro = _intro_segment(topic)
    board: dict[str, list[float]] = {}
    _track_board(board, intro)
    yield {"type": "segment", "index": 0, "title": "Introduction", **intro.model_dump()}

    # 1. One round trip: lesson plan + first real segment, narration streamed.
    yield {"type": "status", "status": "planning the lesson", "t": elapsed()}
    start: LessonStart | None = None
    messages = [
        {"role": "system", "content": START_SYSTEM},
        {"role": "user", "content":
            f"Topic: {topic}\nAlready on the board: {_board_summary(board)}"},
    ]
    try:
        for kind, val in _plan_events(model, messages,
                                      _segment_validator(board, LessonStart),
                                      num_predict=900):
            if kind == "narration":
                yield {"type": "narration", "index": 1, "text": val, "t": elapsed()}
            else:
                start = val
    except Exception:
        start = None

    if start is None:
        plan = [{"title": "The idea", "goal": f"introduce {topic}"},
                {"title": "An example", "goal": "show a concrete example"},
                {"title": "Recap", "goal": "summarize the lesson"}]
        seg1 = _fallback_segment(plan[0]["title"], plan[0]["goal"], 1)
        title = topic[:60]
    else:
        plan = [p if isinstance(p, dict) else {"title": str(p), "goal": ""}
                for p in start.plan][:4]
        if not plan:
            plan = [{"title": "The idea", "goal": f"introduce {topic}"}]
        # Models sometimes return a 1-entry "plan" (just the current segment);
        # a lesson needs an arc, so pad it out and end on a recap.
        pads = [{"title": "An example", "goal": "show a concrete example of the idea"},
                {"title": "Recap", "goal": "summarize the lesson in one picture"}]
        while len(plan) < 3:
            plan.append(pads[len(plan) - 1])
        seg1, title = start, start.title

    yield {"type": "lesson", "title": title, "model": model, "t": elapsed(),
           "segments": [{"title": "Introduction"}] + [{"title": p.get("title", "")} for p in plan]}
    _track_board(board, seg1)
    yield {"type": "segment", "index": 1, "title": plan[0].get("title", ""),
           **SegmentIR(**{k: getattr(seg1, k) for k in SegmentIR.model_fields}).model_dump()}

    # 2. Remaining segments, one small cache-friendly call each.
    total = len(plan)
    for i, seg_plan in enumerate(plan[1:], start=2):
        yield {"type": "status", "status": f"planning segment {i}/{total}", "t": elapsed()}
        messages = [
            {"role": "system", "content": SEGMENT_SYSTEM},
            {"role": "user", "content":
                f"Lesson: {title}\nTopic: {topic}\nPlan: {_plan_text(plan)}\n"
                f"Already on the board: {_board_summary(board)}\n"
                f"Teach NOW segment {i} of {total}: {seg_plan.get('title', '')} "
                f"— {seg_plan.get('goal', '')}"},
        ]
        seg_ir: SegmentIR | None = None
        try:
            for kind, val in _plan_events(model, messages, _segment_validator(board),
                                          num_predict=700):
                if kind == "narration":
                    yield {"type": "narration", "index": i, "text": val, "t": elapsed()}
                else:
                    seg_ir = val
        except Exception:
            pass
        if seg_ir is None:
            seg_ir = _fallback_segment(seg_plan.get("title", f"Part {i}"),
                                       seg_plan.get("goal", ""), i)
        _track_board(board, seg_ir)
        yield {"type": "segment", "index": i, "title": seg_plan.get("title", ""),
               **seg_ir.model_dump()}
    yield {"type": "done", "t": elapsed()}


if __name__ == "__main__":
    import sys
    topic = " ".join(sys.argv[1:]) or "why the sky is blue"
    t0 = time.time()
    say = lambda *a: print(f"[{time.time() - t0:6.1f}s]", *a, flush=True)
    for event in stream_lesson(topic):
        if event["type"] == "segment":
            say(f"SEGMENT {event['index']} ({event['title']}): "
                f"objs={[o['id'] for o in event['objects']]} "
                f"steps={[(s['animation'], s['target']) for s in event['steps']]}")
            say(f"         say: {event['narration']}")
        elif event["type"] == "narration":
            say(f"VOICE  (seg {event['index']}): {event['text']}")
        elif event["type"] == "lesson":
            say(f"LESSON  {event['title']} — plan: "
                f"{[s['title'] for s in event['segments']]}")
        else:
            say(event["type"].upper(), event.get("status", ""), event.get("title", ""))
