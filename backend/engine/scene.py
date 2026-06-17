"""The full runtime pipeline: measure -> position -> route -> paint (ARCHITECTURE §1).

A Scene is the unit the engines render together. Extents come from measure() (the
Thing's hand-set extent, if any, is ignored — Drawing owns sizing), Positioning
places, route() draws connectors, paint() draws things. Story (Beats -> Scene) lands
in Phase 5; for now scenes are authored directly (the corpus).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from engine.contracts import (
    Beat,
    Board,
    Connector,
    Drawable,
    DrawOp,
    Extent,
    Placement,
    Thing,
    split_paint_attrs,
)
from engine.drawing import measure, paint
from engine.positioning import place
from engine.route import route


@dataclass
class Scene:
    name: str
    things: list[Thing]
    connectors: list[Connector] = field(default_factory=list)


def compile_beats(beats: list[Beat], name: str = "lesson") -> tuple[Scene, list[str]]:
    """Compile Story Beats into a Scene + narration (ARCHITECTURE §3).

    `show` -> a Thing (with its spatial relation); `connect` -> a Connector;
    `say` -> narration; `clear` -> a segment boundary (single-board render ignores it).
    """
    things: list[Thing] = []
    connectors: list[Connector] = []
    narration: list[str] = []
    for b in beats:
        if b.kind == "show" and b.entity:
            geom, paint_attrs = split_paint_attrs(b.geometry)
            things.append(
                Thing(
                    id=b.entity,
                    concept=b.concept or b.entity,
                    extent=Extent(1.0, 1.0),  # render() derives the real extent
                    relations=(b.relation,) if b.relation else (),
                    geometry_attrs=geom,
                    paint_attrs=paint_attrs,
                )
            )
        elif b.kind == "connect" and b.entity and b.target:
            connectors.append(
                Connector(f"{b.entity}->{b.target}", b.entity, b.target, b.connector_kind, b.text)
            )
        elif b.kind == "say" and b.text:
            narration.append(b.text)
    return Scene(name, things, connectors), narration


@dataclass
class Rendered:
    placements: list[Placement]
    drops: list[dict]
    ops: list[DrawOp]
    drawables: dict[str, Drawable]  # id -> the measured drawable (for invariants)

    def placement_of(self) -> dict[str, Placement]:
        return {p.id: p for p in self.placements}


def render(
    scene: Scene,
    board: Board | None = None,
    generate: bool = True,
    style: str = "whiteboard",
    scene_name: str | None = None,
) -> Rendered:
    """`scene_name` is the cartoon backdrop name (palette.scene_for) — threaded so
    labels/connectors pick a contrasting ink on a dark stage (space/night/underwater)."""
    board = board or Board()
    from engine import palette

    edge_ink = palette.LABEL_INK_DARK if scene_name in palette.DARK_SCENES else None

    # 1. measure -> derive each Thing's real extent (Drawing owns sizing).
    #    generate=False is the live placeholder path (§6.1): long-tail concepts
    #    resolve to the backstop instantly instead of blocking on a provider.
    drawables: dict[str, Drawable] = {}
    measured_things: list[Thing] = []
    for t in scene.things:
        d = measure(t, generate=generate, style=style)
        drawables[t.id] = d
        measured_things.append(replace(t, extent=d.extent))

    # 2. position. Cartoon uses an intentional composed frame (layout.py); whiteboard
    #    keeps the free-space positioner (the Phase-1 gate). Both are drop-don't-repair.
    if style == "cartoon":
        from engine.layout import compose_cartoon

        placements, drops = compose_cartoon(measured_things, board)
    else:
        placements, drops = place(measured_things, board)
    pmap = {p.id: p for p in placements}

    # 3. paint placed things, 4. route connectors between placed endpoints.
    ops: list[DrawOp] = []
    for t in measured_things:
        p = pmap.get(t.id)
        if p is not None:
            ops.append(paint(t, p, drawables[t.id], style=style, scene=scene_name))
    for c in scene.connectors:
        op = route(c, pmap, style=style, color=edge_ink)
        if op is not None:
            ops.append(op)

    return Rendered(placements=placements, drops=drops, ops=ops, drawables=drawables)
