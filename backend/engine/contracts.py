"""The frozen seams between engines (docs/ARCHITECTURE.md §2).

Phase 1 needs Thing + Extent + Relation -> Placement. Connector/DrawOp are stubbed
here so the contract is whole; route()/paint() arrive in Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# --------------------------------------------------------------------------- #
# Board: the canvas. Centered at the origin; Manim-ish 14 x 8 frame.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Board:
    w: float = 14.0
    h: float = 8.0

    @property
    def hw(self) -> float:
        return self.w / 2.0

    @property
    def hh(self) -> float:
        return self.h / 2.0


# 9-region anchor grid (board-relative centers). The model speaks these names,
# never coordinates (ARCHITECTURE §4.2 `at`).
REGIONS: dict[str, tuple[float, float]] = {
    "center": (0.0, 0.0),
    "left": (-4.5, 0.0),
    "right": (4.5, 0.0),
    "top": (0.0, 3.0),
    "bottom": (0.0, -3.0),
    "top_left": (-4.5, 3.0),
    "top_right": (4.5, 3.0),
    "bottom_left": (-4.5, -3.0),
    "bottom_right": (4.5, -3.0),
}

# Panel sub-rects (x0, y0, x1, y1), board units. Segments rotate across these.
PANELS: dict[str, tuple[float, float, float, float]] = {
    "full": (-7.0, -4.0, 7.0, 4.0),
    "left": (-7.0, -4.0, 0.0, 4.0),
    "right": (0.0, -4.0, 7.0, 4.0),
}


# --------------------------------------------------------------------------- #
# Extent: what Drawing.measure returns (ARCHITECTURE §2). layout_bbox is what
# Positioning consumes; ink_bbox is the true rendered ink (graded in Phase 2).
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Extent:
    w: float  # layout_bbox width
    h: float  # layout_bbox height
    anchor: str = "center"  # "center" | "baseline"


# --------------------------------------------------------------------------- #
# Relation: the spatial-intent vocabulary (the Story<->Positioning seam).
# A closed, validated set (ARCHITECTURE §2 / task V0). No coordinates ever.
# --------------------------------------------------------------------------- #
POSITIONAL_KINDS = frozenset(
    {"at", "near", "left_of", "right_of", "above", "below", "on", "between", "in_panel"}
)
# Relations checked as hard geometric predicates on the output (relation-fidelity).
HARD_KINDS = frozenset({"left_of", "right_of", "above", "below", "on", "in_panel"})


@dataclass(frozen=True)
class Relation:
    kind: str
    target: str | None = None  # B (the thing this relates to)
    target2: str | None = None  # C (for `between`)
    region: str | None = None  # for `at`
    side: str | None = None  # for `near`: left|right|above|below
    panel: str | None = None  # for `in_panel`


# Ergonomic constructors (the vocabulary, spelled out).
def at(region: str) -> Relation:
    return Relation("at", region=region)


def near(b: str, side: str = "right") -> Relation:
    return Relation("near", target=b, side=side)


def left_of(b: str) -> Relation:
    return Relation("left_of", target=b)


def right_of(b: str) -> Relation:
    return Relation("right_of", target=b)


def above(b: str) -> Relation:
    return Relation("above", target=b)


def below(b: str) -> Relation:
    return Relation("below", target=b)


def on(b: str) -> Relation:
    return Relation("on", target=b)


def between(b: str, c: str) -> Relation:
    return Relation("between", target=b, target2=c)


def in_panel(p: str) -> Relation:
    return Relation("in_panel", panel=p)


# --------------------------------------------------------------------------- #
# Thing: a nameable drawable. attrs are split: geometry_* are part of the cache
# key; paint_* (color/label) are applied at paint time (ARCHITECTURE §2).
# --------------------------------------------------------------------------- #
@dataclass
class Thing:
    id: str
    concept: str
    extent: Extent
    relations: tuple[Relation, ...] = ()
    priority: int = 0  # higher survives when drop-don't-repair fires
    geometry_attrs: dict = field(default_factory=dict)
    paint_attrs: dict = field(default_factory=dict)


# Beat.geometry mixes geometry (cache-key) + paint hints; these keys are PAINT
# concerns and must be split into paint_attrs so they never pollute the Drawing
# cache key (concept, geometry_attrs). One shared definition (used by stream +
# scene) so the two Beat->Thing paths can't drift (§2 geometry/paint split).
PAINT_ATTR_KEYS = frozenset({"color", "entrance", "ambient", "z"})


def split_paint_attrs(geometry: dict) -> tuple[dict, dict]:
    """Split a Beat.geometry dict into (geometry_attrs, paint_attrs)."""
    geom = {k: v for k, v in geometry.items() if k not in PAINT_ATTR_KEYS}
    paint = {k: v for k, v in geometry.items() if k in PAINT_ATTR_KEYS}
    return geom, paint


# Connector: an edge whose geometry only exists AFTER its endpoints are placed.
# Bypasses measure() and the VPSC box pass; drawn by route() in Phase 2 (§4.4/§B1).
@dataclass
class Connector:
    id: str
    src: str
    dst: str
    kind: str = "arrow"  # arrow | line | brace
    label: str | None = None


# --------------------------------------------------------------------------- #
# Placement: Positioning output, as DATA (never a live solver reference).
# Carries resolved geometry so route()/paint() needn't re-query the solver.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Placement:
    id: str
    x: float
    y: float
    w: float
    h: float
    scale: float = 1.0

    @property
    def left(self) -> float:
        return self.x - self.w / 2.0

    @property
    def right(self) -> float:
        return self.x + self.w / 2.0

    @property
    def bottom(self) -> float:
        return self.y - self.h / 2.0

    @property
    def top(self) -> float:
        return self.y + self.h / 2.0


# --------------------------------------------------------------------------- #
# Drawing-side contracts (ARCHITECTURE §2, §5). A Stroke is a board-unit
# polyline; a Drawable is measure()'s geometry-only artifact (cacheable, color
# applied at paint); a DrawOp is paint()/route()'s absolute-space output, the
# canonical "list of polylines + total length for a length-parameterized reveal".
# --------------------------------------------------------------------------- #
Point = tuple[float, float]


@dataclass(frozen=True)
class Stroke:
    points: tuple[Point, ...]
    closed: bool = False
    color: str | None = None  # line color (None = inherit the DrawOp's color)
    fill: str | None = None  # fill color for a closed shape (None = no fill / whiteboard)


@dataclass(frozen=True)
class Drawable:
    """measure() output — LOCAL space, centered at the origin. Color-independent
    (paint_attrs are applied at paint time), so it caches by (concept, geometry_attrs)."""

    strokes: tuple[Stroke, ...]
    extent: Extent
    rung: int  # which ladder rung resolved it (§5.3)
    source: str = "primitive"  # primitive | icon | character | catalog | sketch | generated | box
    fill: bool = False
    label: str | None = None  # text rendered inside/with the drawable


@dataclass(frozen=True)
class DrawOp:
    """paint()/route() output — absolute board space, ready for the board."""

    thing_id: str
    kind: str  # "draw" | "connector"
    strokes: tuple[Stroke, ...]
    length: float  # total arc length, for the length-fraction reveal
    color: str = "#e6edf3"
    fill: bool = False
    label: str | None = None
    label_pos: Point | None = None
    rung: int = 0  # which Drawing ladder rung drew it (6 = placeholder box; 0 = connector)
    source: str = (
        ""  # primitive | icon | character | catalog | sketch | generated | box | connector
    )
    z: int = 1  # paint order: background=0, things=1, connectors=2, presenter=3
    entrance: str = "draw"  # how it appears: draw (pen reveal) | pop | rise | fade
    ambient: str = ""  # idle motion once drawn: "" (none) | bob | float | sway


# --------------------------------------------------------------------------- #
# Beat: Story output (ARCHITECTURE §2, §3). Abstract intent — entities + spatial
# relation + narration. NO geometry, NO coordinates. Compiled to a Scene.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Beat:
    kind: str  # "show" | "connect" | "say" | "clear"
    entity: str | None = None  # the thing (show) or edge source (connect)
    concept: str | None = None  # what to draw (defaults to entity)
    target: str | None = None  # edge destination (connect)
    relation: Relation | None = None  # spatial intent vs already-shown entities
    text: str | None = None  # narration (say) or edge label (connect)
    connector_kind: str = "arrow"
    geometry: dict = field(default_factory=dict)  # geometry_attrs for Drawing


def show(entity: str, concept: str | None = None, relation: Relation | None = None, **geom) -> Beat:
    return Beat(
        "show", entity=entity, concept=concept or entity, relation=relation, geometry=dict(geom)
    )


def connect(src: str, dst: str, kind: str = "arrow", label: str | None = None) -> Beat:
    return Beat("connect", entity=src, target=dst, connector_kind=kind, text=label)


def say(text: str) -> Beat:
    return Beat("say", text=text)


def clear() -> Beat:
    return Beat("clear")
