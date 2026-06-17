"""Lesson engine v2 — a topic becomes a *stream of board actions*.

v1 generated one JSON blob per segment: the board waited ~(segment tokens /
tok rate) between drawings. v2 makes the model emit NDJSON — one action per
line — and dispatches every action the moment its line closes:

    per-action latency  =  line tokens / generation rate   (~30 tok ≈ 2s)
    perceived stall     =  max(0, gen time − playback time of previous action)

Playback (animation 0.6-2.5s + concurrent speech) roughly matches per-line
generation, so the pipeline stays saturated and the board never visibly idles.
See actions.py for the protocol, layout solver, and macros.

Latency ladder (everything is tokens):
  intro      deterministic actions, 0 LLM tokens, <1s first paint
  call 1     {"title"} {"plan"} lines then segment-1 actions — one round trip
  call 2+    one small action stream per remaining segment
  errors     a bad line is DROPPED (free); only a fully-empty stream falls
             back to a legacy whole-JSON parse, then to a narration card
  cache      system prompts are byte-identical across calls (board state in
             the user message) so Ollama re-evals only the new suffix
  model      prefers a small fast model for the live lane (gemma3:4b) —
             override with OLLAMA_LESSON_MODEL / OLLAMA_MODEL
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator

from actions import BoardLayout, LineAssembler, actions_from_dict, auto_reveal
from ir import SceneObject, Step
from modes import ModeSpec, get_mode
from planner import _strip_to_json, chat_stream, list_models, ollama_available

# The live lane wants tokens/sec above all; quality holds up because each
# call is one small teaching beat. Bigger models stay better for offline mp4.
LESSON_PREFERRED = ["gemma3:4b", "gemma3", "qwen2.5:7b", "qwen2.5", "llama3.1"]


def pick_lesson_model() -> str | None:
    env = os.environ.get("OLLAMA_LESSON_MODEL") or os.environ.get("OLLAMA_MODEL")
    if env:
        return env
    avail = list_models()
    if not avail:
        return None
    base = lambda n: n.split(":")[0]
    for p in LESSON_PREFERRED:
        for m in avail:
            if m == p or base(m) == base(p):
                return m
    return avail[0]


# --------------------------------------------------------------------------- #
# One LLM call -> stream of laid-out actions (with legacy-JSON fallback)
# --------------------------------------------------------------------------- #
def _stream_actions(
    model: str,
    messages: list[dict],
    layout: BoardLayout,
    seg_ids: set,
    meta: dict | None,
    num_predict: int,
):
    """Yield action dicts as lines close. Ends early on {"end":true} (the
    HTTP response is dropped, saving every remaining token)."""
    debug = bool(os.environ.get("LESSON_DEBUG"))
    asm = LineAssembler(layout, seg_ids, meta)
    buf, emitted = "", 0
    stream = chat_stream(model, messages, temperature=0.3, num_predict=num_predict, fmt=None)
    for chunk in stream:
        buf += chunk
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            acts = asm.feed(line)
            if debug and not acts and line.strip() and not asm.pending:
                print(f"  [drop] {line.strip()[:160]}", flush=True)
            for act in acts:
                if act["kind"] == "end":
                    stream.close()  # early stop: unneeded tokens never decode
                    return
                emitted += 1
                yield act
    for act in asm.flush(buf):
        if act["kind"] != "end":
            emitted += 1
            yield act
    if emitted == 0:
        # Legacy fallback: the model ignored NDJSON and produced one big
        # object (possibly pretty-printed). Mine it for whatever is usable.
        yield from _legacy_actions(buf, layout, seg_ids, meta)


def _legacy_actions(raw: str, layout: BoardLayout, seg_ids: set, meta: dict | None):
    try:
        d = json.loads(_strip_to_json(raw))
    except json.JSONDecodeError:
        return
    if not isinstance(d, dict):
        return
    if meta is not None:
        meta.update({k: d[k] for k in ("title", "plan") if k in d})
    if d.get("narration"):
        yield {"kind": "say", "text": str(d["narration"])}
    if d.get("clear"):
        yield from actions_from_dict({"clear": True}, layout, seg_ids)
    for o in d.get("objects") or []:
        yield from actions_from_dict({"add": o}, layout, seg_ids)
    for s in d.get("steps") or []:
        yield from actions_from_dict({"play": s}, layout, seg_ids)


# --------------------------------------------------------------------------- #
# Deterministic pieces (no LLM)
# --------------------------------------------------------------------------- #
def _title_actions(title: str, layout: BoardLayout, say: str | None = None) -> list[dict]:
    """Write the title into the reserved band (bypasses panel clamping)."""
    obj = SceneObject(
        id="intro_title",
        type="text",
        text=title.title()[:60],
        font_size=44,
        position=(0.0, 3.1, 0.0),
        color="#58A6FF",
    )
    layout.register(obj)
    out = [{"kind": "say", "text": say}] if say else []
    return out + [
        {"kind": "add", "object": obj.model_dump()},
        {
            "kind": "play",
            "step": Step(animation="write", target="intro_title", duration=1.4).model_dump(),
        },
    ]


def _intro_actions(topic: str, layout: BoardLayout, greeting: bool = True) -> list[dict]:
    title = (topic.strip().split("\n")[0] or "Lesson")[:60]
    say = f"Alright — let's look at {title}. Let me sketch this out." if greeting else None
    return _title_actions(title, layout, say=say)


def _panel_actions(
    layout: BoardLayout, seg_index: int, title: str, policy: str = "columns"
) -> list[dict]:
    """Board real estate between segments, by mode policy:
    columns — left column → right column → wipe + re-title → repeat;
    scenes  — a fresh full stage for every scene (wipe + re-title);
    full    — one canvas, no management (single-pass modes)."""
    out: list[dict] = []
    if policy == "scenes":
        if seg_index > 1:
            layout.clear()
            out.append({"kind": "clear"})
            out += _title_actions(title, layout)
        layout.set_panel("full")
        return out
    if policy == "columns":
        content_i = seg_index - 1  # 0-based among content segments
        if content_i > 0 and content_i % 2 == 0:
            layout.clear()
            out.append({"kind": "clear"})
            out += _title_actions(title, layout)
        layout.set_panel("left" if content_i % 2 == 0 else "right")
        return out
    layout.set_panel("full")
    return out


def _card_actions(title: str, goal: str, index: int, layout: BoardLayout) -> list[dict]:
    """Narration-only fallback card: a failed segment still teaches."""
    obj = SceneObject(
        id=f"fb_{index}",
        type="text",
        text=title,
        font_size=30,
        position=(0.0, 2.2 - index * 0.9, 0.0),
        color="#8B949E",
    )
    layout.place(obj)
    return [
        {"kind": "say", "text": goal or title},
        {"kind": "add", "object": obj.model_dump()},
        {"kind": "play", "step": Step(animation="write", target=obj.id, duration=1.0).model_dump()},
    ]


def _normalize_plan(meta: dict, topic: str, mode: ModeSpec) -> tuple[str, list[dict]]:
    title = str(meta.get("title") or topic[:60])
    plan = []
    for p in (meta.get("plan") or [])[:4]:
        if isinstance(p, dict):
            plan.append(
                {
                    "title": str(p.get("title") or p.get("name") or ""),
                    "goal": str(p.get("goal") or p.get("desc") or ""),
                }
            )
        elif p:
            plan.append({"title": str(p), "goal": ""})
    # Pad a short plan out to the mode's default arc (a 1-entry "plan" is a
    # common model slip; the arc must still end properly).
    while len(plan) < min(3, len(mode.default_plan)):
        plan.append(mode.default_plan[min(len(plan), len(mode.default_plan) - 1)])
    if not plan:
        plan = [{"title": mode.label, "goal": topic}]
    return title, plan


# --------------------------------------------------------------------------- #
# Mock lesson (no Ollama) — same action protocol, zero models.
# --------------------------------------------------------------------------- #
def mock_lesson(topic: str) -> Iterator[dict]:
    layout = BoardLayout()
    title = (topic.strip().split("\n")[0] or "Lesson")[:60]
    yield {
        "type": "lesson",
        "title": title,
        "model": None,
        "segments": [{"title": "Introduction"}, {"title": "The idea"}, {"title": "Recap"}],
    }
    yield {"type": "segment_start", "index": 0, "title": "Introduction"}
    for a in _intro_actions(topic, layout):
        yield {"type": "action", "seg": 0, **a}
    yield {"type": "segment_start", "index": 1, "title": "The idea"}
    layout.set_panel("left")
    seg_ids: set = set()
    demo = [
        {"say": "Here's a simple picture of the idea: one thing leads to another."},
        {
            "add": {
                "id": "m_a",
                "type": "circle",
                "radius": 0.9,
                "position": [-3.5, 0],
                "color": "#3FB950",
            }
        },
        {"play": {"animation": "create", "target": "m_a", "duration": 1.0}},
        {
            "add": {
                "id": "m_b",
                "type": "square",
                "width": 1.8,
                "position": [3.5, 0],
                "color": "#D29922",
            }
        },
        {"play": {"animation": "create", "target": "m_b", "duration": 1.0}},
        {"macro": "flow", "from": "m_a", "to": "m_b", "text": "leads to"},
        {"play": {"animation": "scale", "target": "m_b", "factor": 1.25, "duration": 0.6}},
    ]
    for d in demo:
        for a in actions_from_dict(d, layout, seg_ids):
            yield {"type": "action", "seg": 1, **a}
    yield {"type": "segment_start", "index": 2, "title": "Recap"}
    layout.set_panel("right")
    for d in [
        {"say": "And that's the heart of it. Start Ollama to get real lessons on any topic."},
        {
            "add": {
                "id": "m_note",
                "type": "text",
                "text": "(mock lesson — start Ollama for real teaching)",
                "font_size": 22,
                "position": [0, -3.2],
                "color": "#8B949E",
            }
        },
        {"play": {"animation": "fadein", "target": "m_note", "duration": 0.8}},
    ]:
        for a in actions_from_dict(d, layout, set()):
            yield {"type": "action", "seg": 2, **a}
    yield {"type": "done"}


# --------------------------------------------------------------------------- #
# Public generator — the websocket endpoint iterates this.
# --------------------------------------------------------------------------- #
def stream_lesson(topic: str, model: str | None = None, mode: str = "learn") -> Iterator[dict]:
    """Yield session events: segment_start / action (one per board action) /
    lesson (when the plan is known) / status / done.

    `mode` selects a ModeSpec (modes.py): same engine, different voice, arc,
    board policy, and budgets.
    """
    spec = get_mode(mode)
    t0 = time.time()
    elapsed = lambda: round(time.time() - t0, 1)
    model = model or (pick_lesson_model() if ollama_available() else None)
    if not model:
        yield from mock_lesson(topic)
        return

    layout = BoardLayout()

    # Segment 0: deterministic intro — first paint with zero LLM tokens.
    yield {"type": "segment_start", "index": 0, "title": "Introduction", "t": 0}
    for a in _intro_actions(topic, layout, greeting=spec.greeting):
        yield {"type": "action", "seg": 0, **a, "t": elapsed()}

    # Call 1: (title + plan if the mode has an arc) + first actions,
    # dispatched as lines close.
    yield {"type": "status", "status": f"{spec.label.lower()}: planning", "t": elapsed()}
    yield {"type": "segment_start", "index": 1, "title": "", "t": elapsed()}
    for a in _panel_actions(layout, 1, topic, spec.panel_policy):
        yield {"type": "action", "seg": 1, **a, "t": elapsed()}
    meta: dict = {}
    seg_ids: set = set()
    played: set = set()
    lesson_sent = False
    emitted = 0
    messages = [
        {"role": "system", "content": spec.start_system},
        {"role": "user", "content": f"Topic: {topic}\nAlready on the board: {layout.summary()}"},
    ]
    try:
        for a in _stream_actions(
            model,
            messages,
            layout,
            seg_ids,
            meta if spec.has_plan else None,
            num_predict=spec.num_predict_start,
        ):
            if a["kind"] == "play":
                played.add(a["step"].get("target"))
            emitted += 1
            yield {"type": "action", "seg": 1, **a, "t": elapsed()}
            if spec.has_plan and not lesson_sent and meta.get("plan"):
                title, plan = _normalize_plan(meta, topic, spec)
                lesson_sent = True
                yield {
                    "type": "lesson",
                    "title": title,
                    "model": model,
                    "t": elapsed(),
                    "segments": [{"title": "Introduction"}]
                    + [{"title": p.get("title", "")} for p in plan],
                }
    except Exception:
        pass
    title, plan = _normalize_plan(meta, topic, spec)
    if emitted == 0:
        first = plan[0] if plan else {"title": spec.label, "goal": topic}
        for a in _card_actions(first.get("title", spec.label), first.get("goal", ""), 1, layout):
            yield {"type": "action", "seg": 1, **a, "t": elapsed()}
    if not lesson_sent:
        segs = [{"title": "Introduction"}] + (
            [{"title": p.get("title", "")} for p in plan]
            if spec.has_plan
            else [{"title": spec.label}]
        )
        yield {"type": "lesson", "title": title, "model": model, "t": elapsed(), "segments": segs}
    for a in auto_reveal(seg_ids, played):
        yield {"type": "action", "seg": 1, **a, "t": elapsed()}

    # Remaining segments (multi-segment modes): one small stream each.
    if spec.segment_system:
        total = len(plan)
        plan_text = " / ".join(f"{i + 1}. {p.get('title', '')}" for i, p in enumerate(plan))
        for i, seg_plan in enumerate(plan[1:], start=2):
            yield {"type": "status", "status": f"planning part {i}/{total}", "t": elapsed()}
            yield {
                "type": "segment_start",
                "index": i,
                "title": seg_plan.get("title", ""),
                "t": elapsed(),
            }
            for a in _panel_actions(layout, i, title, spec.panel_policy):
                yield {"type": "action", "seg": i, **a, "t": elapsed()}
            seg_ids, played, emitted = set(), set(), 0
            messages = [
                {"role": "system", "content": spec.segment_system},
                {
                    "role": "user",
                    "content": f"Session: {title}\nTopic: {topic}\nPlan: {plan_text}\n"
                    f"Already on the board: {layout.summary()}\n"
                    f"Do NOW part {i} of {total}: {seg_plan.get('title', '')} "
                    f"— {seg_plan.get('goal', '')}",
                },
            ]
            try:
                for a in _stream_actions(
                    model, messages, layout, seg_ids, None, num_predict=spec.num_predict_segment
                ):
                    if a["kind"] == "play":
                        played.add(a["step"].get("target"))
                    emitted += 1
                    yield {"type": "action", "seg": i, **a, "t": elapsed()}
            except Exception:
                pass
            if emitted == 0:
                for a in _card_actions(
                    seg_plan.get("title", f"Part {i}"), seg_plan.get("goal", ""), i, layout
                ):
                    yield {"type": "action", "seg": i, **a, "t": elapsed()}
            for a in auto_reveal(seg_ids, played):
                yield {"type": "action", "seg": i, **a, "t": elapsed()}
    yield {"type": "done", "t": elapsed()}


# --------------------------------------------------------------------------- #
# CLI: event trace + the latency stats that matter (TTFA, inter-action gaps).
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys

    args = sys.argv[1:]
    mode_arg = "learn"
    if args and args[0] == "--mode" and len(args) > 1:
        mode_arg, args = args[1], args[2:]
    topic = " ".join(args) or "why the sky is blue"
    t0 = time.time()
    say = lambda *a: print(f"[{time.time() - t0:6.1f}s]", *a, flush=True)
    action_times: list[float] = []
    first_llm_action = None
    for event in stream_lesson(topic, mode=mode_arg):
        now = time.time() - t0
        if event["type"] == "action":
            k = event["kind"]
            if event.get("seg", 0) >= 1:  # LLM-generated content only
                action_times.append(now)
                if first_llm_action is None:
                    first_llm_action = now
            if k == "say":
                say(f"  SAY({event['seg']}): {event['text']}")
            elif k == "add":
                o = event["object"]
                say(
                    f"  ADD({event['seg']}): {o['id']} [{o['type']}] at "
                    f"[{o['position'][0]:.1f},{o['position'][1]:.1f}]"
                )
            elif k == "play":
                s = event["step"]
                say(f"  PLAY({event['seg']}): {s['animation']} {s['target']}")
            else:
                say(f"  {k.upper()}({event['seg']})")
        elif event["type"] == "lesson":
            say(f"LESSON: {event['title']} — {[s['title'] for s in event['segments']]}")
        else:
            say(event["type"].upper(), event.get("status", ""), event.get("title", ""))
    gaps = [b - a for a, b in zip(action_times, action_times[1:], strict=False)]
    if gaps:
        gaps.sort()
        p = lambda q: gaps[min(len(gaps) - 1, int(q * len(gaps)))]
        say(
            f"STATS: first LLM action {first_llm_action:.1f}s | "
            f"{len(action_times)} actions | gap p50 {p(0.5):.2f}s "
            f"p95 {p(0.95):.2f}s max {gaps[-1]:.2f}s"
        )
