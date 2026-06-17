"""SVG sanitize + geometric-normalize boundary (ARCHITECTURE §5.4, review B8/B9).

Turns arbitrary (LLM/VLM) SVG into a safe local Drawable:
  1. security: reject scripts / external refs / disallowed elements
  2. flatten the transform stack into leaf geometry (svgelements, reify=True)
  3. flatten paths/curves into polylines, split per M-subpath
  4. normalize to a board-unit box centered at the origin (y flipped to board-up)
  5. quality gate: non-degenerate, bounded point count

The model proposes WHAT to draw; this boundary makes it safe + measurable, and the
solver still decides WHERE. Returns None on any rejection (caller falls to backstop).
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from svgelements import SVG, Close, Line, Move, Path, Shape

from engine.contracts import Drawable, Extent, Stroke

_DISALLOWED = {
    "script",
    "foreignobject",
    "image",
    "use",
    "animate",
    "animatetransform",
    "set",
    "style",
}
_CURVE_SAMPLES = 12
_MAX_POINTS = 8000
_MIN_POINTS = 4


def sanitize_to_drawable(svg_text: str, target: float = 1.8) -> Drawable | None:
    try:
        _security_check(svg_text)
        polylines = _to_polylines(svg_text)
        return _normalize(polylines, target)
    except Exception:
        return None


def _security_check(svg_text: str) -> None:
    root = ET.fromstring(svg_text)  # raises on malformed XML -> rejected
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag in _DISALLOWED:
            raise ValueError(f"disallowed element <{tag}>")
        for k, v in el.attrib.items():
            key = k.rsplit("}", 1)[-1].lower()
            if key.startswith("on"):  # onload, onclick, ...
                raise ValueError("event handler attribute")
            if key in ("href", "xlink:href") and "://" in v:
                raise ValueError("external reference")


def _to_polylines(svg_text: str) -> list[tuple[list[tuple[float, float]], bool]]:
    # reify=True bakes the full transform stack into each shape's geometry.
    svg = SVG.parse(io.StringIO(svg_text), reify=True)
    polylines: list[tuple[list[tuple[float, float]], bool]] = []
    n_points = 0
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        try:
            path = Path(el)
        except Exception:
            continue
        if len(path) == 0:
            continue
        cur: list[tuple[float, float]] = []
        for seg in path:
            if isinstance(seg, Move):
                if len(cur) >= 2:
                    polylines.append((cur, False))
                cur = [(float(seg.end.x), float(seg.end.y))]
            elif isinstance(seg, Close):
                if len(cur) >= 2:
                    polylines.append((cur, True))
                cur = []
            elif isinstance(seg, Line):
                cur.append((float(seg.end.x), float(seg.end.y)))
            else:  # Cubic/Quadratic/Arc — sample along the curve
                for i in range(1, _CURVE_SAMPLES + 1):
                    p = seg.point(i / _CURVE_SAMPLES)
                    cur.append((float(p.x), float(p.y)))
            n_points += len(cur)
            if n_points > _MAX_POINTS:
                raise ValueError("too many points")
        if len(cur) >= 2:
            polylines.append((cur, False))
    return polylines


def _normalize(
    polylines: list[tuple[list[tuple[float, float]], bool]], target: float
) -> Drawable | None:
    pts = [p for poly, _ in polylines for p in poly]
    if len(pts) < _MIN_POINTS:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w0, h0 = maxx - minx, maxy - miny
    if w0 < 1e-6 or h0 < 1e-6:
        return None
    scale = target / max(w0, h0)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    strokes = tuple(
        Stroke(
            tuple(
                (round((x - cx) * scale, 4), round(-(y - cy) * scale, 4))  # flip y -> board up
                for x, y in poly
            ),
            closed=closed,
        )
        for poly, closed in polylines
    )
    return Drawable(
        strokes=strokes,
        extent=Extent(round(w0 * scale, 4), round(h0 * scale, 4)),
        rung=3,
    )
