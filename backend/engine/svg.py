"""DrawOps -> SVG, for visual verification of the engine (stroke-only, matching
the board aesthetic). Not the live renderer — a debugging/inspection artifact.
"""

from __future__ import annotations

from engine.contracts import Board, Stroke
from engine.scene import Rendered

PX = 44.0  # pixels per board unit
BG = "#0d1117"


def _pt(x: float, y: float, board: Board) -> tuple[float, float]:
    # Board space (origin centered, y up) -> SVG (y down).
    return (round((x + board.hw) * PX, 1), round((board.hh - y) * PX, 1))


def _polyline(s: Stroke, color: str, board: Board) -> str:
    pts = list(s.points) + ([s.points[0]] if s.closed and s.points else [])
    coords = " ".join(f"{px},{py}" for px, py in (_pt(x, y, board) for x, y in pts))
    line = s.color or color  # per-stroke line color overrides the op default
    fill = s.fill or "none"  # filled closed shape (cartoon) vs outline (whiteboard)
    tag = "polygon" if (s.fill and s.closed) else "polyline"
    return (
        f'<{tag} points="{coords}" fill="{fill}" stroke="{line}" stroke-width="2.2" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )


def to_svg(rendered: Rendered, board: Board | None = None, background: dict | None = None) -> str:
    """Render to SVG. `background` (cartoon scene backdrop, from palette.background)
    paints a vertical-gradient stage behind the ops instead of the dark page."""
    board = board or Board()
    w, h = board.w * PX, board.h * PX
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="0 0 {w:.0f} {h:.0f}">',
    ]
    if background and background.get("gradient"):
        g = background["gradient"]
        parts.append(
            '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{g["top"]}"/>'
            f'<stop offset="100%" stop-color="{g["bottom"]}"/></linearGradient></defs>'
        )
        parts.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="url(#bg)"/>')
    elif background:
        parts.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="{background["fill"]}"/>')
    else:
        parts.append(f'<rect width="{w:.0f}" height="{h:.0f}" fill="{BG}"/>')
    if background and background.get("ground"):  # the horizon band props stand on
        gr = background["ground"]
        gh = h * gr["frac"]
        parts.append(
            f'<rect y="{h - gh:.0f}" width="{w:.0f}" height="{gh:.0f}" fill="{gr["fill"]}"/>'
        )
    for op in rendered.ops:
        for s in op.strokes:
            parts.append(_polyline(s, op.color, board))
        if op.label and op.label_pos:
            lx, ly = _pt(op.label_pos[0], op.label_pos[1], board)
            parts.append(
                f'<text x="{lx}" y="{ly + 4}" fill="{op.color}" font-family="sans-serif" '
                f'font-size="15" text-anchor="middle">{_esc(op.label)}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def _esc(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
