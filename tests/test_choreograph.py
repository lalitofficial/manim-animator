"""Phase 3 (docs/ROADMAP-story-voice.md): the deterministic choreographer.

Given a timeline whose narration carries [concept] markers, each named concept's draw (and a
host point at it) is re-anchored to the marker for its word, so it reveals AS spoken. A no-op
without markers / when not cinematic (anti-rewrite preserved).
"""

from __future__ import annotations

from engine import choreograph, timeline


def _tl(events):
    return timeline.from_events(events)


def _events(host=True):
    evs = []
    if host:
        evs.append({"type": "draw", "op": {"id": "guide", "source": "character", "z": 3}})
    evs += [
        {"type": "draw", "op": {"id": "sun", "source": "icon"}},
        {"type": "draw", "op": {"id": "cloud", "source": "icon"}},
        {
            "type": "say",
            "text": "The sun warms the cloud.",
            "marks": [
                {"concept": "sun", "word": "sun", "start": 4, "end": 7, "entity": "sun"},
                {"concept": "cloud", "word": "cloud", "start": 18, "end": 23, "entity": "cloud"},
            ],
        },
    ]
    return evs


def test_anchors_concept_draws_to_their_markers_and_overlaps():
    tl = choreograph.choreograph(_tl(_events()))
    sun = next(e for e in tl.entries if e.kind == "draw" and e.payload["op"]["id"] == "sun")
    cloud = next(e for e in tl.entries if e.kind == "draw" and e.payload["op"]["id"] == "cloud")
    assert sun.at == "m:sun" and sun.blocking is False  # reveals AS spoken, overlaps narration
    assert cloud.at == "m:cloud" and cloud.blocking is False
    # the host doesn't get anchored (it's not a narrated concept) and still draws normally
    guide = next(e for e in tl.entries if e.kind == "draw" and e.payload["op"]["id"] == "guide")
    assert guide.at == "" and guide.blocking is True


def test_adds_a_host_point_per_concept_anchored_to_its_marker():
    tl = choreograph.choreograph(_tl(_events()))
    pts = [e for e in tl.entries if e.kind == "action" and e.payload.get("verb") == "point"]
    assert {(p.payload["target"], p.at) for p in pts} == {("sun", "m:sun"), ("cloud", "m:cloud")}
    assert all(p.track == "character" and p.blocking is False for p in pts)


def test_noop_without_markers_is_anti_rewrite():
    tl = _tl([{"type": "draw", "op": {"id": "sun"}}, {"type": "say", "text": "no markers"}])
    assert choreograph.choreograph(tl) == tl  # unchanged -> plays exactly like today


def test_noop_when_not_cinematic():
    tl = _tl(_events())
    assert choreograph.choreograph(tl, cinematic=False) == tl  # whiteboard/calm stays a diagram


def test_skips_concepts_with_no_draw():
    evs = [
        {"type": "draw", "op": {"id": "guide", "source": "character", "z": 3}},
        {"type": "draw", "op": {"id": "sun", "source": "icon"}},
        {
            "type": "say",
            "text": "sun and ghost",
            "marks": [
                {"entity": "sun", "word": "sun", "start": 0, "end": 3},
                {"entity": "ghost", "word": "ghost", "start": 8, "end": 13},
            ],
        },
    ]
    tl = choreograph.choreograph(_tl(evs))
    pts = [e for e in tl.entries if e.kind == "action" and e.payload.get("verb") == "point"]
    assert {p.payload["target"] for p in pts} == {"sun"}  # ghost isn't drawn -> no point, no anchor


def test_camera_follows_each_narrated_concept():
    events = [
        {"type": "start", "topic": "sky", "style": "cartoon", "board": {"w": 14.0, "h": 8.0}},
        {"type": "draw", "op": {"id": "guide", "source": "character", "z": 3}},
        {
            "type": "draw",
            "op": {"id": "sun", "source": "icon", "strokes": [{"points": [[0, 0], [1, 0]]}]},
        },
        {
            "type": "say",
            "text": "The sun shines.",
            "marks": [{"entity": "sun", "word": "sun", "start": 4, "end": 7}],
        },
    ]
    tl = choreograph.choreograph(_tl(events))
    cams = [e for e in tl.entries if e.kind == "camera"]
    assert cams and cams[0].at == "m:sun"  # camera anchored to the concept's word
    p = cams[0].payload
    assert abs(p["x"] - 0.5) < 0.1 and abs(p["y"]) < 0.1  # centered on the sun's bbox
    assert 0 < p["w"] <= 14.0 and 0 < p["h"] <= 8.0  # window stays on-board


def test_no_follow_camera_when_not_cinematic():
    events = [
        {"type": "start", "board": {"w": 14.0, "h": 8.0}},
        {"type": "draw", "op": {"id": "sun", "strokes": [{"points": [[0, 0]]}]}},
        {
            "type": "say",
            "text": "sun",
            "marks": [{"entity": "sun", "word": "sun", "start": 0, "end": 3}],
        },
    ]
    tl = choreograph.choreograph(_tl(events), cinematic=False)
    assert not any(e.kind == "camera" for e in tl.entries)  # a diagram stays a static wide frame


def test_choreographer_owns_concept_cameras_dropping_sequential_frames():
    """#1b: on the timeline path the choreographer is the SOLE camera authority. It DROPS
    compile_plan's sequential per-shot concept frames (sub-full) so they don't fight, keeps the
    full-frame bookends, and re-emits one camera per narrated concept anchored to its word + CUT."""
    events = [
        {"type": "start", "topic": "sky", "style": "cartoon", "board": {"w": 14.0, "h": 8.0}},
        {"type": "camera", "x": 0.0, "y": 0.0, "w": 14.0, "h": 8.0, "ms": 0},  # establish — KEPT
        {
            "type": "draw",
            "op": {"id": "sun", "source": "icon", "strokes": [{"points": [[0, 0], [1, 0]]}]},
        },
        {
            "type": "camera",
            "x": 0.5,
            "y": 0.0,
            "w": 8.4,
            "h": 4.8,
            "ms": 0,
        },  # per-shot frame — DROPPED
        {
            "type": "say",
            "text": "The sun shines.",
            "marks": [{"entity": "sun", "word": "sun", "start": 4, "end": 7}],
        },
    ]
    cams = [e for e in choreograph.choreograph(_tl(events)).entries if e.kind == "camera"]
    assert any(c.payload["w"] == 14.0 for c in cams)  # the full-frame establish bookend stays
    # no SEQUENTIAL sub-full camera survives — every sub-full frame is now anchored to a word
    assert all(c.at != "" for c in cams if c.payload["w"] < 14.0)
    follow = [c for c in cams if c.at == "m:sun"]
    assert len(follow) == 1 and follow[0].payload["ms"] == 0  # one concept, anchored + CUT
    assert follow[0].payload["w"] < 14.0  # framed as a medium, not the whole stage


def test_host_points_only_when_a_host_is_present():
    tl = choreograph.choreograph(_tl(_events(host=False)))  # no character on stage
    assert not any(e.kind == "action" for e in tl.entries)  # nothing to point WITH
    # but concept draws are still anchored (draw-while-talking doesn't need a host)
    sun = next(e for e in tl.entries if e.kind == "draw" and e.payload["op"]["id"] == "sun")
    assert sun.at == "m:sun"
