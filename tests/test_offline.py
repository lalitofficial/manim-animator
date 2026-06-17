"""The offline fallback lanes must always produce valid output, even with no
Ollama running. These are the paths the app degrades to in CI and on a fresh
machine, so they are the safety net worth guarding hardest."""

from __future__ import annotations

from ir import Scene
from lesson import mock_lesson
from planner import plan_mock


def test_plan_mock_returns_valid_scene():
    scene = plan_mock("the Pythagorean theorem")
    assert isinstance(scene, Scene)
    # A scene the renderer can act on: it round-trips through pydantic.
    dumped = scene.model_dump()
    assert isinstance(dumped, dict)
    assert scene.steps, "fallback scene should contain at least one step"


def test_mock_lesson_streams_events():
    events = list(mock_lesson("the water cycle"))
    assert events, "mock lesson should emit at least one event"
    assert all(isinstance(e, dict) for e in events)
    assert all("type" in e for e in events), "every lesson event needs a 'type'"
