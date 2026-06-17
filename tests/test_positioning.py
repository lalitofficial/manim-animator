"""Phase-1 gate (docs/ARCHITECTURE.md §9): Positioning + the invariant ruler.

Every assertion is recomputed from the OUTPUT Placements (invariants.py), never
from solver state. The whole corpus must satisfy: overlap==0, on-board==100%,
relation-fidelity==100% (for survivors), plus flow reading-order, drop-don't-repair,
and incremental==batch determinism.
"""

from __future__ import annotations

import random

import pytest

from engine import invariants
from engine.contracts import Board
from engine.corpus import corpus
from engine.positioning import place

CASES = corpus()
BOARD = Board()


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_invariants_hold(case):
    placed, drops = place(case.things, BOARD)
    rep = invariants.evaluate(case.things, placed, BOARD)

    # The output-derived gates — must hold for the survivors of every case.
    assert rep.overlap <= 1e-6, (
        f"{case.name}: overlap {rep.overlap}, pairs {invariants.overlap_pairs(placed)}"
    )
    assert not rep.off_board, f"{case.name}: off-board {rep.off_board}"
    assert not rep.relation_violations, f"{case.name}: {rep.relation_violations}"

    # Drops are by design but bounded. Cases that expect none must reach FULL
    # coverage — otherwise a silently-dropped Thing passes relation-fidelity
    # (which skips drops) unnoticed. The over-fill/conflict cases expect drops.
    if case.expect_drops == 0:
        assert not drops, f"{case.name}: unexpected drops {drops} (full coverage expected)"
    else:
        assert len(drops) >= case.expect_drops, (
            f"{case.name}: expected >= {case.expect_drops} drops, got {drops}"
        )
    assert len(placed) + len(drops) == len(case.things)
    for d in drops:
        assert "id" in d and "reason" in d


def test_flow_lands_in_reading_order():
    """6 untethered Things must spread into distinct rows in reading order, not a blob (§K4)."""
    case = next(c for c in CASES if c.name == "flow6")
    placed, drops = place(case.things, BOARD)
    assert not drops and len(placed) == 6
    assert invariants.overlap_area(placed) <= 1e-6
    assert invariants.reading_rows(placed) >= 2, "flow Things collapsed into one row/blob"
    assert invariants.in_reading_order(placed), "flow Things not emitted top->bottom, left->right"


def test_conflict_is_dropped_not_faked():
    case = next(c for c in CASES if c.name == "conflict")
    placed, drops = place(case.things, BOARD)
    assert {d["id"] for d in drops} == {"x"}, (
        "impossible relation should drop, not produce a bogus placement"
    )
    assert invariants.evaluate(case.things, placed, BOARD).passes


def test_overfill_drops_some_and_survivors_are_valid():
    case = next(c for c in CASES if c.name == "overfill")
    placed, drops = place(case.things, BOARD)
    assert drops, "an over-filled board must drop, never overlap"
    rep = invariants.evaluate(case.things, placed, BOARD)
    assert rep.overlap <= 1e-6 and not rep.off_board


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_deterministic_rerun(case):
    """Same input -> byte-identical Placements (§4.8 determinism contract)."""
    a, da = place(case.things, BOARD)
    b, db = place(case.things, BOARD)
    assert a == b and da == db


def test_incremental_equals_batch_for_independent_scene():
    """Independent Things: shuffling input order must not change the result set
    (each lands in its own slot); and re-running is identical (§4.5/§4.8)."""
    case = next(c for c in CASES if c.name == "flow6")
    placed1, _ = place(case.things, BOARD)
    shuffled = list(case.things)
    random.Random(0).shuffle(shuffled)
    placed2, _ = place(shuffled, BOARD)
    # Same set of (x,y,w,h) occupied, regardless of order (independent Things).
    slots1 = sorted((p.x, p.y, p.w, p.h) for p in placed1)
    slots2 = sorted((p.x, p.y, p.w, p.h) for p in placed2)
    assert slots1 == slots2


def test_difficulty_grading_is_computable():
    levels = {c.name: c.level for c in CASES}
    assert levels["single"] == "L1"
    assert levels["flow6"] == "L1"
    assert levels["conflict"] == "L3"
    # L3 must include at least one conflicting/over-constrained case (review B12).
    assert any(c.level == "L3" and c.expect_drops for c in CASES)
