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


def test_no_camera_chasing_animation_is_in_the_subjects():
    """The choreographer must NOT cut/pan the camera per concept — that reads as 'the animation is
    just the camera moving between objects' (the wrong principle). Motion lives in the SUBJECTS; the
    camera stays a calm wide frame. It also STRIPS compile_plan's per-shot 'cut to focus' (sub-full)
    cameras so the lens doesn't chase. The concept still REVEALS as its word is spoken."""
    events = [
        {"type": "start", "topic": "sky", "style": "cartoon", "board": {"w": 14.0, "h": 8.0}},
        {"type": "draw", "op": {"id": "guide", "source": "character", "z": 3}},
        {"type": "camera", "x": 0.5, "y": 0.0, "w": 8.4, "h": 4.8, "ms": 0},  # a per-shot focus cut
        {"type": "draw", "op": {"id": "sun", "source": "icon", "strokes": [{"points": [[0, 0]]}]}},
        {
            "type": "say",
            "text": "The sun.",
            "marks": [{"entity": "sun", "word": "sun", "start": 4, "end": 7}],
        },
    ]
    tl = choreograph.choreograph(_tl(events))
    cams = [e for e in tl.entries if e.kind == "camera"]
    assert all(e.payload.get("w", 14.0) >= 14.0 for e in cams)  # only full-frame; no sub-full chase
    assert any(e.kind == "draw" and e.at == "m:sun" for e in tl.entries)  # reveal-as-spoken stays


def test_calm_camera_keeps_establish_drops_per_shot_frames():
    """The choreographer keeps compile_plan's full-frame establish bookend but DROPS its per-shot
    'cut to focus' (sub-full) frames — so the lens doesn't chase concepts — and adds NO per-concept
    camera. The eye follows the subjects' motion in a steady wide shot, not the camera."""
    events = [
        {"type": "start", "topic": "sky", "style": "cartoon", "board": {"w": 14.0, "h": 8.0}},
        {"type": "camera", "x": 0.0, "y": 0.0, "w": 14.0, "h": 8.0, "ms": 0},  # establish — KEPT
        {"type": "draw", "op": {"id": "sun", "source": "icon", "strokes": [{"points": [[0, 0]]}]}},
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
            "text": "The sun.",
            "marks": [{"entity": "sun", "word": "sun", "start": 4, "end": 7}],
        },
    ]
    cams = [e for e in choreograph.choreograph(_tl(events)).entries if e.kind == "camera"]
    assert any(c.payload["w"] == 14.0 for c in cams)  # the full-frame establish stays
    assert all(c.payload.get("w", 14.0) >= 14.0 for c in cams)  # sub-full frames dropped; no chase


def test_host_points_only_when_a_host_is_present():
    tl = choreograph.choreograph(_tl(_events(host=False)))  # no character on stage
    assert not any(e.kind == "action" for e in tl.entries)  # nothing to point WITH
    # but concept draws are still anchored (draw-while-talking doesn't need a host)
    sun = next(e for e in tl.entries if e.kind == "draw" and e.payload["op"]["id"] == "sun")
    assert sun.at == "m:sun"
