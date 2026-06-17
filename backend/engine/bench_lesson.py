"""Render a full lesson end-to-end (ARCHITECTURE §9 Phase 5).

    make lesson T="the water cycle"

Runs Story -> compile -> render, writes build/engine/lesson.svg, prints the
narration + the output-derived invariants. STORY_PROVIDER / ENGINE_SVG_PROVIDER
env vars swap in real models; the default is fully offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

from engine import invariants
from engine.contracts import Board
from engine.runtime import lesson
from engine.svg import to_svg


def main() -> int:
    topic = " ".join(sys.argv[1:]) or "the water cycle"
    board = Board()
    les = lesson(topic, board=board)
    rep = invariants.evaluate(les.scene.things, les.rendered.placements, board)

    outdir = Path("build/engine")
    outdir.mkdir(parents=True, exist_ok=True)
    # Paint the cartoon backdrop if the spec resolved to cartoon (else mono on dark).
    (outdir / "lesson.svg").write_text(to_svg(les.rendered, board, background=les.background))

    rungs: dict[int, int] = {}
    for d in les.rendered.drawables.values():
        rungs[d.rung] = rungs.get(d.rung, 0) + 1

    print(f'\nLesson: "{topic}"  ({len(les.beats)} beats)\n' + "=" * 60)
    print("Narration:")
    for line in les.narration:
        print(f"  • {line}")
    print(
        f"\nBoard: placed {rep.drawn}/{rep.total}  drops {len(les.rendered.drops)}  "
        f"connectors {sum(1 for o in les.rendered.ops if o.kind == 'connector')}  "
        f"rung-hits {dict(sorted(rungs.items()))}"
    )
    print(
        f"Invariants: overlap {rep.overlap:.3f}  off-board {len(rep.off_board)}  "
        f"relation-violations {len(rep.relation_violations)}  -> "
        f"{'PASS' if rep.passes else 'FAIL'}"
    )
    print(f"SVG: {outdir}/lesson.svg\n")
    return 0 if rep.passes else 1


if __name__ == "__main__":
    sys.exit(main())
