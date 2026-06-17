"""End-to-end: topic -> Lesson (ARCHITECTURE §1, §3).

Ties the engines together: Story.tell -> compile_beats -> render
(measure -> position -> route -> paint). This is the "product loop" — a topic in,
a placed/painted board out — now that all three engines exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine import director, palette, story
from engine.contracts import Beat, Board
from engine.scene import Rendered, Scene, compile_beats, render


@dataclass
class Lesson:
    topic: str
    mode: str
    beats: list[Beat]
    scene: Scene
    narration: list[str]
    rendered: Rendered
    style: str = "whiteboard"
    background: dict | None = None  # the cartoon scene backdrop (None for whiteboard)


def lesson(
    topic: str,
    mode: str = "learn",
    board: Board | None = None,
    generate: bool = True,
    spec=None,
) -> Lesson:
    board = board or Board()
    spec = spec if spec is not None else director.direct(topic, mode=mode)
    beats = story.tell(topic, spec)
    scene, narration = compile_beats(beats, name=topic[:24])
    # Thread the resolved style so the offline/SVG path matches the live stream —
    # a cartoon spec renders filled, over its scene backdrop (not silently mono).
    background = palette.background(topic, spec.mode, spec.style)
    scene_name = background["scene"] if background else None
    rendered = render(scene, board, generate=generate, style=spec.style, scene_name=scene_name)
    return Lesson(topic, spec.mode, beats, scene, narration, rendered, spec.style, background)
