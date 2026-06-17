"""Engine 2 — Positioning (docs/ARCHITECTURE.md §4).

Deterministic. kiwisolver (Cassowary) computes the soft ANCHOR target from the
relation vocabulary; a deterministic free-space search settles the NON-CONVEX part
(overlap / on-board) that Cassowary can't express, and drop-don't-repair handles
infeasibility. Already-placed Things are frozen (the teacher never reshuffles what's
drawn), so the incremental result equals a batch solve in the same order (§4.5).

Geometry is the engine's job; the model never emits coordinates (§4.6).
"""

from __future__ import annotations

from kiwisolver import Solver, Variable

from engine.contracts import (
    PANELS,
    POSITIONAL_KINDS,
    REGIONS,
    Board,
    Placement,
    Thing,
)

GAP = 0.3  # min visual gap enforced during placement (checker sees raw overlap)
STEP = 0.5  # free-space scan resolution, board units
_EPS = 1e-6


class Placer:
    """Incremental placement (§4.5). Each added Thing is solved against the frozen
    set of already-placed Things, so streaming a lesson one beat at a time yields
    the same result as a batch solve in the same order."""

    def __init__(self, board: Board | None = None) -> None:
        self.board = board or Board()
        self.placed: list[Placement] = []

    def add(self, thing: Thing) -> Placement | None:
        p = _place_one(thing, self.placed, self.board)
        if p is not None:
            self.placed.append(p)
        return p

    def pmap(self) -> dict[str, Placement]:
        return {p.id: p for p in self.placed}


def place(things: list[Thing], board: Board | None = None) -> tuple[list[Placement], list[dict]]:
    """Place Things one at a time, freezing each (§4.5). Returns (placements, drops).

    A drop is `{"id", "reason"}` — coverage may be < 100% by design under
    over-subscription, and every drop is logged so a miss is distinguishable
    from a bug (§4.3).
    """
    placer = Placer(board)
    drops: list[dict] = []
    for t in things:  # input order is canonical; never iterate a set (§4.8)
        if placer.add(t) is None:
            drops.append({"id": t.id, "reason": "no_fit"})
    return placer.placed, drops


# --------------------------------------------------------------------------- #
# Place one Thing: anchor target (kiwisolver) -> deterministic valid slot.
# --------------------------------------------------------------------------- #
def _place_one(t: Thing, placed: list[Placement], board: Board) -> Placement | None:
    w, h = t.extent.w, t.extent.h
    by_id = {p.id: p for p in placed}
    preferred = _anchor_target(t, by_id, board, w, h)
    # A Thing may TOUCH the things it sits `on` (contact is the point); the gap
    # is enforced against everything else.
    contact = frozenset(r.target for r in t.relations if r.kind == "on" and r.target)
    for cx, cy in _candidates(t, by_id, board, w, h, preferred):
        if (
            _on_board(cx, cy, w, h, board)
            and _satisfies_hard(t, cx, cy, w, h, by_id)
            and not _overlaps(cx, cy, w, h, placed, contact)
        ):
            return Placement(t.id, round(cx, 4), round(cy, 4), w, h)
    return None  # drop-don't-repair: no valid slot


# --------------------------------------------------------------------------- #
# kiwisolver: the soft anchor target from the relation vocabulary (§4.2).
# Cassowary solves the linear anchors; it does NOT do non-overlap (§4.4).
# --------------------------------------------------------------------------- #
def _anchor_target(
    t: Thing, by_id: dict[str, Placement], board: Board, w: float, h: float
) -> tuple[float, float] | None:
    if not any(r.kind in POSITIONAL_KINDS for r in t.relations):
        return None
    try:
        s = Solver()
        x, y = Variable("x"), Variable("y")
        hw, hh = board.hw, board.hh
        for c in (x >= -hw + w / 2, x <= hw - w / 2, y >= -hh + h / 2, y <= hh - h / 2):
            s.addConstraint(c | "required")
        # Weak pull to the origin so under-constrained axes settle deterministically.
        s.addConstraint((x == 0) | "weak")
        s.addConstraint((y == 0) | "weak")
        for r in t.relations:
            b = by_id.get(r.target) if r.target else None
            c = by_id.get(r.target2) if r.target2 else None
            if r.kind == "at" and r.region in REGIONS:
                rx, ry = REGIONS[r.region]
                s.addConstraint((x == rx) | "strong")
                s.addConstraint((y == ry) | "strong")
            elif r.kind == "right_of" and b:
                s.addConstraint((x - w / 2 >= b.right + GAP) | "strong")
                s.addConstraint((y == b.y) | "medium")
            elif r.kind == "left_of" and b:
                s.addConstraint((x + w / 2 <= b.left - GAP) | "strong")
                s.addConstraint((y == b.y) | "medium")
            elif r.kind == "above" and b:
                s.addConstraint((y - h / 2 >= b.top + GAP) | "strong")
                s.addConstraint((x == b.x) | "medium")
            elif r.kind == "below" and b:
                s.addConstraint((y + h / 2 <= b.bottom - GAP) | "strong")
                s.addConstraint((x == b.x) | "medium")
            elif r.kind == "on" and b:
                s.addConstraint((y == b.top + h / 2) | "strong")
                s.addConstraint((x == b.x) | "medium")
            elif r.kind == "between" and b and c:
                s.addConstraint((x == (b.x + c.x) / 2) | "strong")
                s.addConstraint((y == (b.y + c.y) / 2) | "strong")
            elif r.kind == "near" and b:
                _near_constraints(s, x, y, w, h, b, r.side or "right")
            elif r.kind == "in_panel" and r.panel in PANELS:
                px0, py0, px1, py1 = PANELS[r.panel]
                s.addConstraint((x - w / 2 >= px0) | "strong")
                s.addConstraint((x + w / 2 <= px1) | "strong")
                s.addConstraint((y - h / 2 >= py0) | "strong")
                s.addConstraint((y + h / 2 <= py1) | "strong")
        s.updateVariables()
        return (x.value(), y.value())
    except Exception:
        # Over-constrained (e.g. right_of A AND left_of A): no anchor. The grid
        # scan + hard filter will find a slot or drop.
        return None


def _near_constraints(s: Solver, x, y, w: float, h: float, b: Placement, side: str) -> None:
    if side == "right":
        s.addConstraint((x - w / 2 >= b.right) | "strong")
    elif side == "left":
        s.addConstraint((x + w / 2 <= b.left) | "strong")
    elif side == "above":
        s.addConstraint((y - h / 2 >= b.top) | "strong")
    elif side == "below":
        s.addConstraint((y + h / 2 <= b.bottom) | "strong")
    s.addConstraint((x == b.x) | "weak")
    s.addConstraint((y == b.y) | "weak")


# --------------------------------------------------------------------------- #
# Candidate positions: a deterministic, reading-order free-space scan. Flow
# placement lives HERE, outside the solver (§4.3) — Cassowary has no model of
# free space, so "minimize y then x" must be a real scan, not a soft objective.
# --------------------------------------------------------------------------- #
def _candidates(
    t: Thing,
    by_id: dict[str, Placement],
    board: Board,
    w: float,
    h: float,
    preferred: tuple[float, float] | None,
) -> list[tuple[float, float]]:
    cands: list[tuple[float, float]] = []
    # Exact "on top of B" position first, if any.
    for r in t.relations:
        if r.kind == "on" and r.target in by_id:
            b = by_id[r.target]
            cands.append((round(b.x, 4), round(b.top + h / 2, 4)))
    if preferred is not None:
        cands.append((round(preferred[0], 4), round(preferred[1], 4)))

    # Reading-order grid: top -> bottom, left -> right (row-major).
    grid: list[tuple[float, float]] = []
    y = board.hh - h / 2
    while y >= -board.hh + h / 2 - _EPS:
        x = -board.hw + w / 2
        while x <= board.hw - w / 2 + _EPS:
            grid.append((round(x, 4), round(y, 4)))
            x += STEP
        y -= STEP
    if preferred is not None:
        px, py = preferred
        grid.sort(key=lambda p: (round(abs(p[0] - px) + abs(p[1] - py), 4), -p[1], p[0]))
    cands.extend(grid)

    seen: set[tuple[float, float]] = set()
    out: list[tuple[float, float]] = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


# --------------------------------------------------------------------------- #
# Predicates used to FILTER candidates (the engine side). The benchmark
# re-checks the same facts independently from the output (invariants.py) — these
# two implementations share no code, so a bug in one is caught by the other (§K1).
# --------------------------------------------------------------------------- #
def _on_board(x: float, y: float, w: float, h: float, board: Board) -> bool:
    return (
        x - w / 2 >= -board.hw - _EPS
        and x + w / 2 <= board.hw + _EPS
        and y - h / 2 >= -board.hh - _EPS
        and y + h / 2 <= board.hh + _EPS
    )


def _overlaps(
    x: float, y: float, w: float, h: float, placed: list[Placement], contact=frozenset()
) -> bool:
    # Enforce a visual gap by inflating the new box — except against `contact`
    # boxes (the things it sits `on`), which it may touch but not truly overlap.
    for p in placed:
        g = 0.0 if p.id in contact else GAP / 2
        ix = min(x + w / 2 + g, p.right) - max(x - w / 2 - g, p.left)
        iy = min(y + h / 2 + g, p.top) - max(y - h / 2 - g, p.bottom)
        if ix > _EPS and iy > _EPS:
            return True
    return False


def _satisfies_hard(
    t: Thing, x: float, y: float, w: float, h: float, by_id: dict[str, Placement]
) -> bool:
    for r in t.relations:
        b = by_id.get(r.target) if r.target else None
        if r.kind == "right_of" and b and not (x - w / 2 >= b.right - _EPS):
            return False
        if r.kind == "left_of" and b and not (x + w / 2 <= b.left + _EPS):
            return False
        if r.kind == "above" and b and not (y - h / 2 >= b.top - _EPS):
            return False
        if r.kind == "below" and b and not (y + h / 2 <= b.bottom + _EPS):
            return False
        if r.kind == "on" and b:
            sits = abs((y - h / 2) - b.top) <= 0.25
            aligned = abs(x - b.x) <= (w + b.w) / 2
            if not (sits and aligned):
                return False
        if r.kind == "in_panel" and r.panel in PANELS:
            px0, py0, px1, py1 = PANELS[r.panel]
            if not (x - w / 2 >= px0 - _EPS and x + w / 2 <= px1 + _EPS):
                return False
            if not (y - h / 2 >= py0 - _EPS and y + h / 2 <= py1 + _EPS):
                return False
    return True
