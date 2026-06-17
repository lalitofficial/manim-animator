"""Deterministic stroke geometry for the Drawing engine (ARCHITECTURE §5).

Pure functions: shape generators (board-unit polylines centered at the origin),
plus length / bbox / transform helpers. No randomness — same input, same strokes.
"""

from __future__ import annotations

import math

from engine.contracts import Point, Stroke


def circle(r: float, n: int = 48) -> Stroke:
    pts = tuple(
        (r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)
    )
    return Stroke(pts, closed=True)


def rectangle(w: float, h: float) -> Stroke:
    hw, hh = w / 2, h / 2
    return Stroke(((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)), closed=True)


def rounded_rect(w: float, h: float, r: float = 0.2, n: int = 5) -> Stroke:
    """A rectangle with rounded corners (a friendly UI 'card' shape)."""
    hw, hh = w / 2, h / 2
    r = max(0.0, min(r, hw, hh))
    pts: list[Point] = []
    for cx, cy, a0, a1 in (
        (hw - r, -hh + r, -90, 0),  # bottom-right
        (hw - r, hh - r, 0, 90),  # top-right
        (-hw + r, hh - r, 90, 180),  # top-left
        (-hw + r, -hh + r, 180, 270),  # bottom-left
    ):
        for i in range(n + 1):
            a = math.radians(a0 + (a1 - a0) * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return Stroke(tuple(pts), closed=True)


def triangle(w: float, h: float) -> Stroke:
    hw, hh = w / 2, h / 2
    return Stroke(((-hw, -hh), (hw, -hh), (0.0, hh)), closed=True)


def segment(p0: Point, p1: Point) -> Stroke:
    return Stroke((p0, p1), closed=False)


def ellipse(rx: float, ry: float, n: int = 48) -> Stroke:
    pts = tuple(
        (rx * math.cos(2 * math.pi * i / n), ry * math.sin(2 * math.pi * i / n)) for i in range(n)
    )
    return Stroke(pts, closed=True)


def arc(r: float, a0: float, a1: float, n: int = 32) -> Stroke:
    """Open arc from angle a0 to a1 (degrees), radius r, centered at origin."""
    a0r, a1r = math.radians(a0), math.radians(a1)
    pts = tuple(
        (r * math.cos(a0r + (a1r - a0r) * i / n), r * math.sin(a0r + (a1r - a0r) * i / n))
        for i in range(n + 1)
    )
    return Stroke(pts, closed=False)


def blob(r: float, bumps: int = 6, jitter: float = 0.18, seed: float = 0.0, n: int = 56) -> Stroke:
    """A closed organic curve — radius wobbles sinusoidally (deterministic, seeded)."""
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        rr = r * (1 + jitter * math.sin(bumps * t + seed))
        pts.append((rr * math.cos(t), rr * math.sin(t)))
    return Stroke(tuple(pts), closed=True)


def wave(width: float, amp: float, cycles: float = 2.0, n: int = 48) -> Stroke:
    """Open sine wave along x, centered at origin."""
    pts = tuple(
        (-width / 2 + width * i / n, amp * math.sin(2 * math.pi * cycles * i / n))
        for i in range(n + 1)
    )
    return Stroke(pts, closed=False)


def polyline(points: list[Point] | tuple[Point, ...], closed: bool = False) -> Stroke:
    return Stroke(tuple((float(x), float(y)) for x, y in points), closed=closed)


def arrow(p0: Point, p1: Point, head: float = 0.35) -> list[Stroke]:
    """A shaft p0->p1 plus a two-line arrowhead at p1."""
    strokes = [segment(p0, p1)]
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for a in (ang + math.radians(150), ang - math.radians(150)):
        tip = (p1[0] + head * math.cos(a), p1[1] + head * math.sin(a))
        strokes.append(segment(p1, tip))
    return strokes


def stroke_length(s: Stroke) -> float:
    pts = list(s.points)
    if s.closed and pts:
        pts.append(pts[0])
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def total_length(strokes: list[Stroke] | tuple[Stroke, ...]) -> float:
    return sum(stroke_length(s) for s in strokes)


def strokes_bbox(strokes: list[Stroke] | tuple[Stroke, ...]) -> tuple[float, float, float, float]:
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    return (min(xs), min(ys), max(xs), max(ys))


def transform(
    strokes: list[Stroke] | tuple[Stroke, ...],
    dx: float,
    dy: float,
    scale: float = 1.0,
    rot: float = 0.0,
) -> tuple[Stroke, ...]:
    """Rotate (radians) + scale about the origin, then translate (local -> board space)."""
    c, s = math.cos(rot), math.sin(rot)

    def t(px: float, py: float) -> Point:
        x, y = px * scale, py * scale
        return (x * c - y * s + dx, x * s + y * c + dy)

    return tuple(
        Stroke(tuple(t(px, py) for px, py in st.points), st.closed, st.color, st.fill)
        for st in strokes
    )
