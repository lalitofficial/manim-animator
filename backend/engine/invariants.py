"""The benchmark ruler (docs/ARCHITECTURE.md §7).

Every check is recomputed FROM THE OUTPUT (the Placements), sharing no code with
the placement path — an invariant you can't independently recompute is one a
broken-but-stable engine passes green (§K1). These predicates are deliberately a
second, independent implementation of positioning.py's filters.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.contracts import HARD_KINDS, Board, Placement, Thing

_TOL = 1e-6


def _boxes(placements: list[Placement]) -> dict[str, Placement]:
    return {p.id: p for p in placements}


# --------------------------------------------------------------------------- #
# Overlap — standalone AABB intersection over the OUTPUT boxes.
# --------------------------------------------------------------------------- #
def overlap_area(placements: list[Placement]) -> float:
    total = 0.0
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            ix = min(a.right, b.right) - max(a.left, b.left)
            iy = min(a.top, b.top) - max(a.bottom, b.bottom)
            if ix > _TOL and iy > _TOL:
                total += ix * iy
    return total


def overlap_pairs(placements: list[Placement]) -> list[tuple[str, str]]:
    out = []
    for i, a in enumerate(placements):
        for b in placements[i + 1 :]:
            ix = min(a.right, b.right) - max(a.left, b.left)
            iy = min(a.top, b.top) - max(a.bottom, b.bottom)
            if ix > _TOL and iy > _TOL:
                out.append((a.id, b.id))
    return out


# --------------------------------------------------------------------------- #
# On-board — every box inside the frame.
# --------------------------------------------------------------------------- #
def off_board(placements: list[Placement], board: Board) -> list[str]:
    bad = []
    for p in placements:
        if (
            p.left < -board.hw - _TOL
            or p.right > board.hw + _TOL
            or p.bottom < -board.hh - _TOL
            or p.top > board.hh + _TOL
        ):
            bad.append(p.id)
    return bad


# --------------------------------------------------------------------------- #
# Relation-fidelity — each HARD relation as a geometric predicate on the output.
# Soft relations (at/near/between/group_with) are best-effort, not gated.
# --------------------------------------------------------------------------- #
def relation_violations(things: list[Thing], placements: list[Placement]) -> list[str]:
    box = _boxes(placements)
    viol: list[str] = []
    for t in things:
        a = box.get(t.id)
        if a is None:  # dropped — coverage handles it, not fidelity
            continue
        for r in t.relations:
            if r.kind not in HARD_KINDS:
                continue
            b = box.get(r.target) if r.target else None
            if r.kind in ("right_of", "left_of", "above", "below", "on") and b is None:
                continue  # target dropped
            if r.kind == "right_of" and not (a.left >= b.right - _TOL):
                viol.append(f"{t.id} not right_of {r.target}")
            elif r.kind == "left_of" and not (a.right <= b.left + _TOL):
                viol.append(f"{t.id} not left_of {r.target}")
            elif r.kind == "above" and not (a.bottom >= b.top - _TOL):
                viol.append(f"{t.id} not above {r.target}")
            elif r.kind == "below" and not (a.top <= b.bottom + _TOL):
                viol.append(f"{t.id} not below {r.target}")
            elif r.kind == "on":
                sits = abs(a.bottom - b.top) <= 0.25
                aligned = abs(a.x - b.x) <= (a.w + b.w) / 2
                if not (sits and aligned):
                    viol.append(f"{t.id} not on {r.target}")
            elif r.kind == "in_panel":
                from engine.contracts import PANELS

                px0, py0, px1, py1 = PANELS[r.panel]
                if not (a.left >= px0 - _TOL and a.right <= px1 + _TOL) or not (
                    a.bottom >= py0 - _TOL and a.top <= py1 + _TOL
                ):
                    viol.append(f"{t.id} not in_panel {r.panel}")
    return viol


# --------------------------------------------------------------------------- #
# Coverage — every named Thing drawn (drops are by-design, but reported).
# --------------------------------------------------------------------------- #
def coverage(things: list[Thing], placements: list[Placement]) -> tuple[int, int]:
    drawn = len(_boxes(placements))
    return drawn, len(things)


# --------------------------------------------------------------------------- #
# Extent-honesty (§7, §A3) — the measured layout_bbox must match the ACTUAL
# painted ink. We recompute the rendered bbox from the DrawOp's board strokes
# (the true ink), divide out the placement scale, and compare to measure()'s
# Extent. A measure() that lies (so layout looks fine but ink overflows) fails here.
# For label-only drawables (text: no outline strokes) the metric IS the extent.
# --------------------------------------------------------------------------- #
def extent_error(extent_w: float, extent_h: float, strokes, scale: float = 1.0) -> float:
    if not strokes or not any(s.points for s in strokes):
        return 0.0  # label-only: rendered bbox is defined as the metric
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    rw = (max(xs) - min(xs)) / scale
    rh = (max(ys) - min(ys)) / scale
    ew = max(extent_w, 1e-9)
    eh = max(extent_h, 1e-9)
    return max(abs(rw - ew) / ew, abs(rh - eh) / eh)


# --------------------------------------------------------------------------- #
# Reading order — distinct rows, top->bottom / left->right (catches the
# "everything piles into a de-overlapped blob" flow failure, §K4).
# --------------------------------------------------------------------------- #
def reading_rows(placements: list[Placement], row_tol: float = 0.6) -> int:
    if not placements:
        return 0
    ys = sorted({round(p.y, 2) for p in placements}, reverse=True)
    rows = 1
    last = ys[0]
    for yv in ys[1:]:
        if last - yv > row_tol:
            rows += 1
            last = yv
    return rows


def in_reading_order(placements: list[Placement], row_tol: float = 0.6) -> bool:
    """True if placements are emitted top->bottom, then left->right within a row."""
    key = [(-round(p.y / row_tol), round(p.x, 3)) for p in placements]
    return key == sorted(key)


# --------------------------------------------------------------------------- #
# One-shot report for a scene.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Report:
    overlap: float
    off_board: list[str]
    relation_violations: list[str]
    drawn: int
    total: int
    rows: int

    @property
    def passes(self) -> bool:
        # Coverage floor: a scene that drew NOTHING is vacuously overlap-free /
        # on-board / relation-clean — that must never read as green (review A1/§K1).
        fully_dropped = self.total > 0 and self.drawn == 0
        return (
            self.overlap <= _TOL
            and not self.off_board
            and not self.relation_violations
            and not fully_dropped
        )


def evaluate(
    things: list[Thing], placements: list[Placement], board: Board | None = None
) -> Report:
    board = board or Board()
    drawn, total = coverage(things, placements)
    return Report(
        overlap=overlap_area(placements),
        off_board=off_board(placements, board),
        relation_violations=relation_violations(things, placements),
        drawn=drawn,
        total=total,
        rows=reading_rows(placements),
    )
