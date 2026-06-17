"""Positioning benchmark runner — the ruler as a CLI (docs/ARCHITECTURE.md §7, §9).

    python backend/engine/bench.py        # run the whole corpus, print the gate

Prints, per case, the output-derived invariants and an overall Phase-1 verdict
(overlap==0, on-board==100%, relation-fidelity==100% across the suite).
"""

from __future__ import annotations

from engine import invariants
from engine.contracts import Board
from engine.corpus import corpus
from engine.positioning import place


def main() -> int:
    board = Board()
    cases = corpus()
    all_pass = True
    print(f"\nPositioning benchmark — {len(cases)} cases\n" + "=" * 60)
    for case in cases:
        placed, drops = place(case.things, board)
        rep = invariants.evaluate(case.things, placed, board)
        ok = rep.passes and len(drops) >= case.expect_drops
        all_pass &= ok
        mark = "PASS" if ok else "FAIL"
        print(
            f"[{mark}] {case.level:>2} {case.name:<14} "
            f"placed {rep.drawn}/{rep.total}  drops {len(drops)}  "
            f"overlap {rep.overlap:.3f}  rows {rep.rows}  "
            f"offboard {len(rep.off_board)}  relviol {len(rep.relation_violations)}"
        )
        if rep.relation_violations:
            print(f"        violations: {rep.relation_violations}")
    print("=" * 60)
    print(f"PHASE-1 GATE: {'PASS' if all_pass else 'FAIL'}\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
