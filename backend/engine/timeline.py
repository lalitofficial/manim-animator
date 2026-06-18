"""The Timeline IR + the events->timeline adapter (docs/ROADMAP-story-voice.md §3, Phase 2).

Today's `compile_plan` emits a linear event QUEUE that the board plays with blocking awaits
(`say` blocks all drawing, each `draw` blocks the next). The Timeline IR is the richer target:
parallel TRACKS (stage / draw / speech / character / camera / control) whose entries anchor to
MARKERS (the narration `[concept]` words, §O6). A master-clock scheduler plays it.

`from_events` is the ANTI-REWRITE adapter: it compiles the existing event stream into a
*degenerate* timeline — sequential, one marker per `say` — that the scheduler plays IDENTICALLY
to the current queue. It encodes the queue's exact await semantics as per-entry `blocking` flags
(mirroring `board/engine.js play()`), so `resolve_schedule` reproduces the board cursor. The
choreographer (Phase 3) will emit real parallelism + marker `at`-anchors directly into this same
IR; the renderer (Phase 2b) is the only place that changes to play tracks against a clock.

This module is backend-only and fully Python-testable: the contract, the adapter, and the
tolerance gate (does the degenerate timeline reproduce the queue?) all live here.
"""

from __future__ import annotations

from dataclasses import dataclass

TRACKS = ("stage", "draw", "speech", "character", "camera", "control")

# Which event kinds BLOCK the play cursor (sequential) vs fire-and-continue. This EXACTLY
# mirrors board/engine.js play(): say/draw/connector/hold/clear await; camera/action/background
# do not. Encoding it as data is what lets the scheduler reproduce the queue, then generalize.
_BLOCKING = {
    "draw": True,
    "connector": True,
    "say": True,
    "hold": True,
    "clear": True,
    "camera": False,
    "action": False,
    "background": False,
}
_CLEAR_DWELL_MS = 800  # the board's transition dwell before a scene clear
TIMELINE_VERSION = 1  # wire-format version (bump on a breaking IR change)
# The board adds a fixed dwell AFTER a say finishes (board/engine.js: ~180ms cartoon / 90ms else) on
# top of the TTS time. resolve_schedule leaves say duration to the scheduler (dur_ms=None), so the
# Phase-2b scheduler MUST add this dwell to a say's runtime duration or narration pacing drifts fast.
POST_SAY_DWELL_MS = {"cartoon": 180, "default": 90}


@dataclass(frozen=True)
class TLEntry:
    """One timeline entry. `blocking` reproduces the queue's await; `at` is the anchor the
    choreographer will set ("" = sequential after the cursor); `dur_ms` is a known duration
    or None when it's runtime-derived (a draw's stroke length / a say's TTS time)."""

    id: str  # stable id, for `at` references from other entries / markers
    track: str  # one of TRACKS
    kind: str  # the original event type
    blocking: bool
    payload: dict  # the original event minus its "type"
    at: str = ""  # anchor expression; "" = sequential (the choreographer overrides this)
    dur_ms: int | None = None


@dataclass(frozen=True)
class Timeline:
    meta: dict  # from the `start` event (+ `done` summary), the playback header
    entries: tuple[TLEntry, ...]
    markers: tuple[dict, ...] = ()  # {name, entry, kind: say|concept, entity?, word?, start?, end?}


def _track_for(kind: str, payload: dict) -> str:
    if kind in ("background", "clear"):
        return "stage"
    if kind == "camera":
        return "camera"
    if kind == "say":
        return "speech"
    if kind == "hold":
        return "control"
    if kind == "draw":  # the host is its own track so it can act WHILE props are drawn
        op = payload.get("op", {})
        return "character" if op.get("source") == "character" or op.get("z") == 3 else "draw"
    if kind == "action":
        return "character" if payload.get("verb") in ("point", "look") else "draw"
    return "draw"


def _dur_ms_for(kind: str, payload: dict) -> int | None:
    if kind in ("camera", "action", "hold"):
        return int(payload.get("ms") or 0)
    if kind == "clear":
        return _CLEAR_DWELL_MS
    if kind == "background":
        return 0
    return None  # draw / connector / say are runtime-derived


def from_events(events) -> Timeline:
    """Compile a compile_plan event stream into a degenerate Timeline (anti-rewrite): every
    non-start/done event becomes exactly one ordered entry; each `say` mints a marker plus one
    per resolved `[concept]`. Order, blocking, and durations are preserved, so the scheduled
    result equals the current queue (see resolve_schedule + the tolerance gate test)."""
    meta: dict = {}
    entries: list[TLEntry] = []
    markers: list[dict] = []
    say_i = 0
    for n, ev in enumerate(events or ()):
        if not isinstance(ev, dict):
            continue  # drop-don't-repair: a malformed event is skipped, never crashes the adapter
        et = ev.get("type")
        if et == "start":
            meta = {k: v for k, v in ev.items() if k != "type"}
            continue
        if et == "done":
            meta["done"] = ev.get("summary", {})
            continue
        if not isinstance(et, str):
            continue  # no / non-string type -> not a real event
        payload = {k: v for k, v in ev.items() if k != "type"}
        eid = f"e{n}"
        entries.append(
            TLEntry(
                id=eid,
                track=_track_for(et, payload),
                kind=et,
                blocking=_BLOCKING.get(et, False),
                payload=payload,
                dur_ms=_dur_ms_for(et, payload),
            )
        )
        if et == "say":
            # Markers are §3 master-clock points: `name` is the handle an `at` anchor references,
            # `t` is the resolved time in SECONDS (None until the voice layer fills it from a word
            # boundary / audio timestamp). `char_start`/`char_end` index the say text (word-timing).
            markers.append({"name": f"say:{say_i}", "t": None, "entry": eid, "kind": "say"})
            say_i += 1
            marks = payload.get("marks")
            for m in marks if isinstance(marks, list) else ():
                if not isinstance(m, dict) or not m.get("entity"):
                    continue  # drop-don't-repair: malformed / unresolved marks mint no marker
                markers.append(
                    {
                        "name": f"m:{m['entity']}",
                        "t": None,
                        "entry": eid,
                        "kind": "concept",
                        "entity": m["entity"],
                        "word": m.get("word"),
                        "char_start": m.get("start"),
                        "char_end": m.get("end"),
                    }
                )
    return Timeline(meta=meta, entries=tuple(entries), markers=tuple(markers))


def resolve_schedule(tl: Timeline, dur_ms) -> list[dict]:
    """Absolute start_ms per entry, mirroring the board cursor: a blocking entry advances the
    cursor by its duration; a non-blocking one fires at the cursor without advancing. `dur_ms`
    is a callable (entry -> int) supplying durations for the runtime-derived (draw/say) entries.

    This is what the scheduler does for a degenerate (sequential, at="") timeline; once entries
    carry marker `at`-anchors, the scheduler resolves those against the live/audio clock instead.

    LIMITATION (by design, Phase 2a): a non-blocking entry fires at the cursor and does NOT bound the
    timeline — a long camera/action overlaps whatever follows (fire-and-forget, exactly today's queue).
    BOUNDED overlap ("overlap but finish before the next marker") is not expressible yet; it's the
    Phase-3 `at`-grammar extension (a future end/until anchor), deferred until the choreographer needs it."""
    t = 0
    out: list[dict] = []
    for e in tl.entries:
        d = e.dur_ms if e.dur_ms is not None else int(dur_ms(e))
        out.append({"id": e.id, "kind": e.kind, "track": e.track, "start_ms": t, "dur_ms": d})
        if e.blocking:
            t += d
    return out


def to_dict(tl: Timeline) -> dict:
    """Serialize for the wire (the scheduler consumes this)."""
    return {
        "version": TIMELINE_VERSION,
        "meta": tl.meta,
        "markers": list(tl.markers),
        "entries": [
            {
                "id": e.id,
                "track": e.track,
                "kind": e.kind,
                "blocking": e.blocking,
                "at": e.at,
                "dur_ms": e.dur_ms,
                "payload": e.payload,
            }
            for e in tl.entries
        ],
    }
