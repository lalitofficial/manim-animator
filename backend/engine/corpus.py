"""The Positioning benchmark corpus (docs/ARCHITECTURE.md §7).

Inputs are structured Beats (decided G1) expressed as Things + Relations — this
also serves as task V0: exercising the relation vocabulary on representative
scenes. Difficulty is computable (n_things / n_relations / has_conflict), not a
hand label. Every case here is a scene the Positioning engine must satisfy.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.contracts import (
    Connector,
    Extent,
    Thing,
    at,
    below,
    between,
    in_panel,
    left_of,
    on,
    right_of,
)
from engine.scene import Scene


@dataclass(frozen=True)
class Case:
    name: str
    things: list[Thing]
    expect_drops: int = 0  # minimum drops expected (over-subscription cases)
    note: str = ""

    @property
    def level(self) -> str:
        # Computable difficulty (review B12): driven by COMPOSITIONAL relations
        # (those referencing another Thing). Absolute anchors (at/in_panel) are
        # trivial placement, not difficulty.
        n = len(self.things)
        n_comp = sum(1 for t in self.things for r in t.relations if r.target or r.target2)
        conflict = any(_conflicting(t) for t in self.things)
        if conflict:
            return "L3"
        if n_comp == 0:
            return "L1"
        if n_comp <= 2 and n <= 3:
            return "L2"
        return "L3"


def _conflicting(t: Thing) -> bool:
    kinds = [r.kind for r in t.relations]
    return ("right_of" in kinds and "left_of" in kinds) or ("above" in kinds and "below" in kinds)


def _box(id_: str, w: float = 1.6, h: float = 1.0, rels=(), priority: int = 0) -> Thing:
    return Thing(id=id_, concept=id_, extent=Extent(w, h), relations=tuple(rels), priority=priority)


def corpus() -> list[Case]:
    cases: list[Case] = []

    # L1 — primitives
    cases.append(Case("single", [_box("c", rels=[at("center")])]))
    cases.append(
        Case(
            "flow6",
            [_box(f"t{i}", w=3.0, h=1.2) for i in range(6)],
            note="6 untethered Things must land in distinct reading-order rows, not a blob",
        )
    )

    # L2 — compositions
    cases.append(Case("pair", [_box("a", rels=[at("left")]), _box("b", rels=[right_of("a")])]))
    cases.append(
        Case(
            "titled",
            [
                _box("title", w=4.0, h=0.8, rels=[at("top")]),
                _box("x", rels=[below("title")]),
                _box("y", rels=[right_of("x")]),
            ],
        )
    )

    # L3 — spatial intent
    cases.append(
        Case(
            "cause_effect",
            [
                _box("cause", rels=[at("left")]),
                _box("effect", rels=[right_of("cause")]),
                _box("link", w=1.2, h=0.7, rels=[between("cause", "effect")]),
            ],
        )
    )
    cases.append(
        Case(
            "stack_on",
            [
                _box("base", w=3.0, h=1.0, rels=[at("center")]),
                _box("top", w=1.4, h=1.0, rels=[on("base")]),
            ],
        )
    )
    cases.append(
        Case(
            "panels",
            [
                _box("l1", rels=[in_panel("left")]),
                _box("l2", rels=[in_panel("left"), below("l1")]),
                _box("r1", rels=[in_panel("right")]),
            ],
        )
    )

    # L3 — over-constrained: `x` both right_of and left_of `a` is impossible -> drop.
    cases.append(
        Case(
            "conflict",
            [
                _box("a", rels=[at("center")]),
                _box("x", rels=[right_of("a"), left_of("a")]),
            ],
            expect_drops=1,
            note="impossible relation -> drop-don't-repair",
        )
    )

    # Over-fill: ten 4x3 boxes can't all fit a 14x8 board -> some drops, survivors valid.
    cases.append(
        Case(
            "overfill",
            [_box(f"big{i}", w=4.0, h=3.0, priority=i) for i in range(10)],
            expect_drops=1,
            note="forces the VPSC cap / drop fallback; survivors stay overlap-free + on-board",
        )
    )

    return cases


# --------------------------------------------------------------------------- #
# Drawing scenes (Phase 2): real concepts + connectors, rendered end-to-end
# (measure -> position -> route -> paint). Extents come from measure().
# --------------------------------------------------------------------------- #
def _t(id_: str, concept: str, rels=(), **geom) -> Thing:
    return Thing(
        id=id_,
        concept=concept,
        extent=Extent(1.0, 1.0),  # placeholder; render() derives it from measure()
        relations=tuple(rels),
        geometry_attrs=dict(geom),
    )


def scenes() -> list[Scene]:
    return [
        Scene(
            "two_circles",
            [
                _t("a", "circle", [at("left")], radius=0.8),
                _t("b", "circle", [right_of("a")], radius=0.8),
            ],
            [Connector("e", "a", "b", "arrow", label="leads to")],
        ),
        Scene(
            "labeled_square",
            [
                _t("sq", "square", [at("center")], size=1.6),
                _t("lab", "text", [below("sq")], text="Energy", font=0.5),
            ],
        ),
        Scene(
            "flow_column",
            [
                _t("s1", "rect", [at("top")], w=2.4, h=0.9),
                _t("s2", "rect", [below("s1")], w=2.4, h=0.9),
                _t("s3", "rect", [below("s2")], w=2.4, h=0.9),
            ],
            [
                Connector("e1", "s1", "s2", "arrow"),
                Connector("e2", "s2", "s3", "arrow"),
            ],
        ),
        Scene(
            "backstop",
            [_t("c", "chloroplast", [at("center")])],
        ),
        # Rung 3: 'star' and 'leaf' resolve via the (fixture) SVG generator,
        # are sanitized/normalized, then placed like any other drawable.
        Scene(
            "generated",
            [
                _t("star", "star", [at("left")]),
                _t("leaf", "leaf", [right_of("star")]),
            ],
        ),
    ]


def cartoon_scene() -> Scene:
    """A colorful nature scene exercising the composed-icon palette end-to-end —
    rendered in the cartoon style (filled shapes + a sky backdrop) by the bench."""
    return Scene(
        "cartoon_demo",
        [
            _t("sun", "sun", [at("top_left")], size=2.2),
            _t("cloud", "cloud", [at("top_right")], size=2.4),
            _t("tree", "tree", [at("left")], size=2.6),
            _t("house", "house", [at("center")], size=2.6),
            _t("flower", "flower", [at("bottom_left")], size=1.6),
            _t("person", "person", [right_of("house")], size=2.4),
            _t("mountain", "mountain", [at("right")], size=2.8),
        ],
    )
