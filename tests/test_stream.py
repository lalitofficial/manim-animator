"""Phase-6 gate: the streaming runtime + serialization (the live board's input).

Hermetic — template Story + parametric/fixture Drawing. The event stream must be
ordered, well-formed, and renderable (stroke-only polylines in board units).
"""

from __future__ import annotations

from engine import drawing, story
from engine.contracts import Board
from engine.stream import stream_lesson

BOARD = Board()


def setup_function():
    drawing.reset()
    story.set_provider(None)


def test_stream_emits_ordered_events():
    events = list(stream_lesson("the water cycle", board=BOARD))
    assert events[0]["type"] == "start"
    assert events[-1]["type"] == "done"
    types = {e["type"] for e in events}
    assert {"say", "draw"} <= types
    # start carries the board dims the client needs to map coordinates.
    assert events[0]["board"] == {"w": BOARD.w, "h": BOARD.h}


def test_draw_ops_are_wellformed_stroke_polylines():
    events = list(stream_lesson("binary search", board=BOARD))
    draws = [e for e in events if e["type"] in ("draw", "connector")]
    assert draws
    for e in draws:
        op = e["op"]
        assert op["kind"] in ("draw", "connector")
        assert isinstance(op["length"], (int, float))
        for s in op["strokes"]:
            assert len(s["points"]) >= 1
            assert all(len(p) == 2 for p in s["points"])  # [x, y] board units


def test_stream_is_deterministic():
    a = list(stream_lesson("mitosis", board=BOARD))
    drawing.reset()
    b = list(stream_lesson("mitosis", board=BOARD))
    assert a == b


def test_stream_reports_story_provenance_and_summary():
    events = list(stream_lesson("the water cycle", board=BOARD))
    start = events[0]
    assert start["story"]["used"] == "template" and start["story"]["fallback"] is False
    done = events[-1]
    assert done["type"] == "done"
    s = done["summary"]
    assert {"story", "real_drawings", "placeholders", "dropped"} <= s.keys()


def test_draw_ops_carry_rung_and_placeholder_flag():
    events = list(stream_lesson("the water cycle", board=BOARD))
    draws = [e for e in events if e["type"] == "draw"]
    assert draws
    for e in draws:
        assert "rung" in e["op"] and "placeholder" in e["op"]
        assert e["op"]["placeholder"] == (e["op"]["rung"] == 6)


def test_start_event_carries_director_pacing():
    from engine.director import direct

    start = list(stream_lesson("x", board=BOARD))[0]
    assert "pacing" in start and "draw_speed" in start["pacing"]
    lively = list(stream_lesson("x", board=BOARD, spec=direct("x", energy="lively")))[0]
    calm = list(stream_lesson("x", board=BOARD, spec=direct("x", energy="calm")))[0]
    assert lively["pacing"]["draw_speed"] > calm["pacing"]["draw_speed"]


def test_story_mode_streams_scene_clears():
    events = list(stream_lesson("the water cycle", mode="story", board=BOARD))
    clears = [e for e in events if e["type"] == "clear"]
    assert len(clears) == 2  # 3 scenes -> 2 clears
    assert [c["scene"] for c in clears] == [1, 2]
    assert events[-1]["type"] == "done"
    # Each scene places fresh (placer reset) -> draws appear after clears too.
    assert any(e["type"] == "draw" for e in events)


def test_connectors_follow_their_endpoints():
    events = list(stream_lesson("the water cycle", board=BOARD))
    drawn_ids = {e["op"]["id"] for e in events if e["type"] == "draw"}
    for e in events:
        if e["type"] == "connector":
            src, dst = e["op"]["id"].split("->")
            assert src in drawn_ids and dst in drawn_ids
