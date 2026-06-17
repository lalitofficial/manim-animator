"""The route stage (ARCHITECTURE §1, §B1).

A Connector's geometry only exists AFTER its endpoints are placed — it has no
Extent and is never boxed by Positioning. route() computes the edge between two
Placements (attaching to each box's boundary toward the other) as a DrawOp.
"""

from __future__ import annotations

from engine import geometry as g
from engine.contracts import Connector, DrawOp, Placement, Point

DEFAULT_COLOR = "#8b949e"


def _attach(box: Placement, toward: Point) -> Point:
    """The point on `box`'s boundary on the ray from its center toward `toward`."""
    dx, dy = toward[0] - box.x, toward[1] - box.y
    if dx == 0 and dy == 0:
        return (box.x, box.y)
    tx = (box.w / 2) / abs(dx) if dx else float("inf")
    ty = (box.h / 2) / abs(dy) if dy else float("inf")
    t = min(tx, ty)
    return (box.x + dx * t, box.y + dy * t)


CARTOON_COLOR = "#3a4a63"  # darker edge ink that reads on a light cartoon scene


def route(
    conn: Connector,
    placements: dict[str, Placement],
    style: str = "whiteboard",
    color: str | None = None,
) -> DrawOp | None:
    """`color` overrides the edge ink — the stream passes a light ink so connectors
    stay visible on a dark cartoon scene (space/night/underwater)."""
    src = placements.get(conn.src)
    dst = placements.get(conn.dst)
    if src is None or dst is None:  # an endpoint was dropped — no edge
        return None
    p0 = _attach(src, (dst.x, dst.y))
    p1 = _attach(dst, (src.x, src.y))
    strokes = g.arrow(p0, p1) if conn.kind == "arrow" else [g.segment(p0, p1)]
    return DrawOp(
        thing_id=conn.id,
        kind="connector",
        strokes=tuple(strokes),
        length=round(g.total_length(strokes), 4),
        color=color or (CARTOON_COLOR if style == "cartoon" else DEFAULT_COLOR),
        label=conn.label,
        label_pos=((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2) if conn.label else None,
        z=2,
    )
