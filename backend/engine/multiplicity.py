"""Quantity / multiplicity — a concept can mean MANY of something.

"rain" is not one drop; "stars" is not one star; "forest" is many trees. This module
expands such a concept into N copies of a base glyph arranged as ONE group (so the
positioner still places a single box). Two triggers:

1. an intrinsic COUNT_PROFILE for inherently-plural concepts (rain → a field of drops),
2. an explicit ``count`` (+ optional ``arrangement``) in a Thing's geometry_attrs, so the
   Story can ask for "3 servers in a row".

Tiling is pure geometry: it normalizes the base strokes to a unit, then places scaled
copies at deterministic positions. No randomness (positions are index-derived) so renders
are reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine import geometry as g

DEFAULT_BOX = 2.8  # board-units a multiple group spans by default
MAX_COUNT = 24


@dataclass(frozen=True)
class Multiple:
    base: str  # the concept to repeat (must itself be a single glyph)
    count: int
    arrangement: str  # row | grid | scatter | rainfall


# Inherently-plural concepts → (base glyph, how many, how arranged). The base must be a
# concept that resolves to a SINGLE drawable (no profile of its own → no recursion).
COUNT_PROFILE: dict[str, Multiple] = {
    "rain": Multiple("water", 9, "rainfall"),
    "rainfall": Multiple("water", 10, "rainfall"),
    "raindrops": Multiple("water", 10, "rainfall"),
    "drizzle": Multiple("water", 7, "rainfall"),
    "snow": Multiple("snowflake", 9, "rainfall"),
    "snowfall": Multiple("snowflake", 10, "rainfall"),
    "snowflakes": Multiple("snowflake", 9, "scatter"),
    "stars": Multiple("star", 7, "scatter"),
    "starfield": Multiple("star", 9, "scatter"),
    "clouds": Multiple("cloud", 3, "row"),
    "forest": Multiple("tree", 5, "row"),
    "trees": Multiple("tree", 5, "row"),
    "flowers": Multiple("flower", 5, "row"),
    "crowd": Multiple("person", 5, "row"),
    "people": Multiple("person", 5, "row"),
    "flock": Multiple("bird", 6, "scatter"),
    "birds": Multiple("bird", 5, "scatter"),
    "school of fish": Multiple("fish", 6, "scatter"),
    "bubbles": Multiple("bubble", 8, "scatter"),
    "coins": Multiple("coin", 5, "grid"),
    "books": Multiple("book", 4, "row"),
    "mountains": Multiple("mountain", 3, "row"),
}


def _norm(concept: str) -> str:
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def profile(concept: str, geometry_attrs: dict | None = None) -> Multiple | None:
    """The multiplicity for a concept, or None (single glyph). An explicit ``count`` in
    geometry_attrs wins and repeats the concept itself; otherwise the intrinsic profile."""
    geom = geometry_attrs or {}
    try:
        count = int(geom.get("count", 0))
    except (TypeError, ValueError):
        count = 0
    if count > 1:
        base = str(geom.get("base") or concept)
        arr = str(geom.get("arrangement") or "row")
        return Multiple(base, min(count, MAX_COUNT), arr)
    return COUNT_PROFILE.get(_norm(concept))


# --------------------------------------------------------------------------- #
# Deterministic placement of N scaled copies inside a box.
# --------------------------------------------------------------------------- #
def _hash01(i: int) -> float:
    """A reproducible pseudo-random in [0, 1) — no global RNG (renders stay stable)."""
    return ((i * 1103515245 + 12345) % 1000) / 1000.0


def _positions(n: int, arrangement: str, box: float) -> list[tuple[float, float, float]]:
    """(x, y, scale) for each copy — scale is the copy's box-unit size."""
    n = max(1, min(n, MAX_COUNT))
    half = box / 2.0

    def spread(k: int, s: float) -> list[float]:
        if k <= 1:
            return [0.0]
        return [(-half + s / 2) + (box - s) * (i / (k - 1)) for i in range(k)]

    if arrangement == "row":
        s = min(box * 0.95 / n, box * 0.5)
        return [(x, 0.0, s) for x in spread(n, s)]

    if arrangement == "grid":
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)
        s = min(box * 0.92 / cols, box * 0.92 / rows)
        xs, ys = spread(cols, s), spread(rows, s)
        return [(xs[i % cols], ys[i // cols], s) for i in range(n)]

    # scatter / rainfall — deterministic jitter in the box; rainfall biases to a falling
    # column layout with slightly taller drops.
    s = min(box * 0.85 / math.sqrt(n), box * 0.42)
    out = []
    for i in range(n):
        if arrangement == "rainfall":
            cols = max(2, round(math.sqrt(n * 1.4)))
            col = i % cols
            x = (-half + s / 2) + (box - s) * (col / (cols - 1) if cols > 1 else 0.5)
            x += (box - s) * 0.12 * (_hash01(i * 5 + 1) - 0.5)
            y = (half - s / 2) - (box - s) * _hash01(i * 7 + 3)
        else:
            x = (-half + s / 2) + (box - s) * _hash01(i * 2 + 1)
            y = (-half + s / 2) + (box - s) * _hash01(i * 2 + 7)
        out.append((x, y, s * (0.85 + 0.3 * _hash01(i * 3 + 2))))
    return out


def tile(base_strokes, count: int, arrangement: str, box: float = DEFAULT_BOX):
    """Repeat a base drawable's strokes into a `count`-instance group within `box`.
    The base is normalized to a unit first, so any source size works."""
    base_strokes = tuple(base_strokes)
    if not base_strokes or count <= 1:
        return base_strokes
    x0, y0, x1, y1 = g.strokes_bbox(base_strokes)
    span = max(x1 - x0, y1 - y0, 1e-6)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    unit = g.transform(base_strokes, -cx / span, -cy / span, 1.0 / span)  # centered, span 1
    out: list = []
    for x, y, s in _positions(count, arrangement, box):
        out.extend(g.transform(unit, x, y, s))
    return tuple(out)
