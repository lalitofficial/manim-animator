"""Phase 2 (docs/ROADMAP-story-voice.md §3): the Timeline IR + anti-rewrite adapter.

The gate is TOLERANCE-based, not pixel-identical: the degenerate timeline a lesson compiles
to must, when scheduled, reproduce the CURRENT board queue's order + blocking + timing. We
re-derive the old schedule INDEPENDENTLY from the raw events (the §K1 output-derived check),
sharing no code with timeline.py, and compare.
"""

from __future__ import annotations

import pytest

from engine import director, drawing, story, timeline
from engine.contracts import Board
from engine.plan import compile_plan

BOARD = Board()


@pytest.fixture(autouse=True)
def fresh():
    drawing.reset()
    story.set_provider(None)  # deterministic TemplateStory
    yield
    drawing.reset()
    story.set_provider(None)


def _events(topic="the water cycle", mode="learn", style="cartoon"):
    spec = director.DirectorSpec(topic, mode=mode, style=style)
    return list(compile_plan(story.tell_plan(spec), spec, BOARD, generate=False))


# --------------------------------------------------------------------------- #
# The adapter: every event becomes exactly one ordered entry; nothing is lost.
# --------------------------------------------------------------------------- #
def test_adapter_preserves_every_event_in_order():
    events = _events()
    tl = timeline.from_events(events)
    body = [e["type"] for e in events if e["type"] not in ("start", "done")]
    assert [e.kind for e in tl.entries] == body  # no add / drop / reorder
    assert tl.meta.get("topic") and "done" in tl.meta  # start -> meta, done captured


def test_blocking_flags_mirror_the_board_queue():
    tl = timeline.from_events(_events())
    for e in tl.entries:
        expected = e.kind in ("draw", "connector", "say", "hold", "clear")
        assert e.blocking is expected, f"{e.kind} blocking={e.blocking}"


def test_tracks_routed_sensibly():
    tl = timeline.from_events(_events())  # cartoon learn => host + camera + narration
    by_track: dict[str, set[str]] = {}
    for e in tl.entries:
        by_track.setdefault(e.track, set()).add(e.kind)
    assert "say" in by_track.get("speech", set())  # narration on the speech track
    assert "background" in by_track.get("stage", set())  # backdrop on the stage track
    assert any(e.track == "character" for e in tl.entries)  # the host has its own track
    assert by_track.get("camera", set()) <= {"camera"}  # only camera moves on the camera track


def test_markers_for_says_and_concepts():
    events = [
        {"type": "start", "topic": "t", "mode": "learn", "style": "cartoon"},
        {"type": "draw", "op": {"id": "sun", "source": "icon"}},
        {
            "type": "say",
            "text": "The sun is hot.",
            "marks": [{"concept": "sun", "word": "sun", "start": 4, "end": 7, "entity": "sun"}],
        },
        {"type": "say", "text": "No markers here."},
        {"type": "done", "summary": {}},
    ]
    tl = timeline.from_events(events)
    names = [m["name"] for m in tl.markers]
    assert "say:0" in names and "say:1" in names  # one marker per say
    assert "m:sun" in names  # one marker per resolved [concept]
    conc = next(m for m in tl.markers if m["name"] == "m:sun")
    assert conc["kind"] == "concept" and conc["entity"] == "sun"
    assert conc["char_start"] == 4 and conc["char_end"] == 7  # char offsets for word-timing
    assert conc["t"] is None  # §3 master-clock time slot — filled later by the voice layer
    assert all(m.get("t") is None for m in tl.markers)  # every marker has the time slot


def test_unresolved_marks_make_no_marker():
    tl = timeline.from_events(
        [
            {"type": "say", "text": "x", "marks": [{"word": "ghost", "entity": None}]},
        ]
    )
    assert all(m["kind"] != "concept" for m in tl.markers)  # entity-less mark -> no marker


# --------------------------------------------------------------------------- #
# The ANTI-REWRITE tolerance gate: the scheduled degenerate timeline reproduces
# the current queue's (kind, start_ms) sequence. _queue_schedule is an INDEPENDENT
# re-derivation straight from the raw events (no timeline.py), per §K1.
# --------------------------------------------------------------------------- #
def _dur(kind: str, payload: dict) -> int:
    """A deterministic duration model applied IDENTICALLY to both schedulers."""
    if kind in ("camera", "action", "hold"):
        return int(payload.get("ms") or 0)
    if kind == "clear":
        return 800
    if kind == "background":
        return 0
    if kind == "say":
        return 50 * len(payload.get("text", ""))  # stand-in for the runtime TTS estimate
    if kind in ("draw", "connector"):
        return 600  # stand-in for the runtime stroke-length reveal
    return 0


def _queue_schedule(events) -> list[tuple[str, int]]:
    """Re-derive the CURRENT board playback schedule directly from raw events (independent of
    timeline.py): blocking kinds advance the cursor, others fire at it without advancing."""
    block = {"draw", "connector", "say", "hold", "clear"}
    t = 0
    out: list[tuple[str, int]] = []
    for ev in events:
        et = ev["type"]
        if et in ("start", "done"):
            continue
        out.append((et, t))
        if et in block:
            t += _dur(et, {k: v for k, v in ev.items() if k != "type"})
    return out


@pytest.mark.parametrize("mode", ["learn", "story", "draw", "explain"])
@pytest.mark.parametrize("style", ["cartoon", "whiteboard"])
def test_degenerate_timeline_reproduces_the_queue(mode, style):
    events = _events(mode=mode, style=style)
    tl = timeline.from_events(events)
    sched = timeline.resolve_schedule(tl, lambda e: _dur(e.kind, e.payload))
    got = [(s["kind"], s["start_ms"]) for s in sched]
    # same events, order, blocking + cursor arithmetic. Durations here are STAND-INS (real
    # draw/say ms are DOM/TTS-derived) — real-ms fidelity is the Phase-2b scheduler's job.
    assert got == _queue_schedule(events)


def test_to_dict_round_trips_the_shape():
    tl = timeline.from_events(_events(mode="explain"))
    d = timeline.to_dict(tl)
    assert set(d) == {"version", "meta", "markers", "entries"} and d["version"] == 1
    assert len(d["entries"]) == len(tl.entries)
    assert all(
        {"id", "track", "kind", "blocking", "at", "dur_ms", "payload"} == set(e)
        for e in d["entries"]
    )


# --------------------------------------------------------------------------- #
# Robustness (drop-don't-repair) + base cases + track/marker coverage (review).
# --------------------------------------------------------------------------- #
def test_empty_and_meta_only_inputs_dont_crash():
    assert timeline.from_events([]).entries == ()
    assert timeline.from_events(None).entries == ()  # defensive on None
    only_meta = timeline.from_events(
        [{"type": "start", "topic": "t"}, {"type": "done", "summary": {}}]
    )
    assert only_meta.entries == () and only_meta.meta.get("topic") == "t"


def test_adapter_is_drop_dont_repair_on_garbage():
    """Never crash on malformed input (Phase-3 LLM-sourced events/marks will be messy)."""
    events = [
        None,  # not a dict
        {"no_type": 1},  # missing type
        {"type": 123},  # non-string type
        {"type": "draw"},  # op missing entirely
        {"type": "say", "text": "x", "marks": None},  # marks not a list
        {"type": "say", "text": "y", "marks": ["junk", {"word": "z"}, {"entity": "real"}]},
        {"type": "mystery"},  # unknown but valid type -> sane passthrough
    ]
    tl = timeline.from_events(events)  # must not raise
    assert [e.kind for e in tl.entries] == ["draw", "say", "say", "mystery"]
    concept = [m["entity"] for m in tl.markers if m["kind"] == "concept"]
    assert concept == ["real"]  # only the one well-formed mark mints a marker


def test_whiteboard_vs_cartoon_tracks_differ():
    c_tracks = {e.track for e in timeline.from_events(_events(style="cartoon")).entries}
    w_tracks = {e.track for e in timeline.from_events(_events(style="whiteboard")).entries}
    assert "character" in c_tracks  # cartoon stages a host on its own track
    assert (
        "character" not in w_tracks and "camera" not in w_tracks
    )  # whiteboard: no host, not cinematic


def test_say_markers_number_across_scene_clears():
    events = [
        {"type": "start", "topic": "t"},
        {"type": "say", "text": "one"},
        {"type": "clear", "scene": 1},
        {"type": "say", "text": "two"},
        {"type": "done", "summary": {}},
    ]
    assert [m["name"] for m in timeline.from_events(events).markers] == ["say:0", "say:1"]


def test_to_dict_payload_is_verbatim():
    op = {"id": "sun", "source": "icon", "z": 1, "strokes": [{"points": [[0, 0]]}]}
    tl = timeline.from_events([{"type": "draw", "op": op}])
    assert timeline.to_dict(tl)["entries"][0]["payload"]["op"] == op  # payload survives intact
