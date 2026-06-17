"""DrawOp/Placement -> plain JSON dicts for the wire (the live board consumes these).

Coordinates stay in board units; the client maps to pixels. Stroke-only by design,
so each polyline animates with a length-fraction reveal (stroke-dasharray).
"""

from __future__ import annotations

from engine.contracts import DrawOp, Placement, Stroke


def stroke_to_dict(s: Stroke) -> dict:
    d = {"points": [[round(x, 3), round(y, 3)] for x, y in s.points], "closed": s.closed}
    if s.color:
        d["color"] = s.color
    if s.fill:
        d["fill"] = s.fill
    return d


def op_to_dict(op: DrawOp) -> dict:
    return {
        "id": op.thing_id,
        "kind": op.kind,
        "color": op.color,
        "fill": op.fill,
        "label": op.label,
        "label_pos": [round(op.label_pos[0], 3), round(op.label_pos[1], 3)]
        if op.label_pos
        else None,
        "length": op.length,
        "rung": op.rung,
        "source": op.source,  # primitive | icon | sketch | generated | box
        "placeholder": op.source == "box",  # a labeled box, not a real drawing
        "z": op.z,  # paint order (background 0 < things 1 < connectors 2 < presenter 3)
        "entrance": op.entrance,  # draw | pop | rise | fade
        "ambient": op.ambient,  # "" | bob | float | sway
        "strokes": [stroke_to_dict(s) for s in op.strokes],
    }


def placement_to_dict(p: Placement) -> dict:
    return {"id": p.id, "x": p.x, "y": p.y, "w": p.w, "h": p.h, "scale": p.scale}
