"""Drawing benchmark — renders the scenes end-to-end, checks invariants +
extent-honesty, and writes an inspectable SVG per scene (ARCHITECTURE §7, §9).

    make bench-draw      # writes build/engine/<scene>.svg, prints the gate
"""

from __future__ import annotations

from pathlib import Path

from engine import invariants, palette
from engine.contracts import Board
from engine.corpus import cartoon_scene, scenes
from engine.scene import render
from engine.svg import to_svg

EPS = 0.10  # extent-honesty tolerance (§7)


def main() -> int:
    board = Board()
    outdir = Path("build/engine")
    outdir.mkdir(parents=True, exist_ok=True)
    all_pass = True
    print(f"\nDrawing benchmark — {len(list(scenes()))} scenes  ->  {outdir}/\n" + "=" * 64)
    for sc in scenes():
        r = render(sc, board)
        rep = invariants.evaluate(sc.things, r.placements, board)
        pmap = r.placement_of()
        worst_ext = 0.0
        for op in r.ops:
            if op.kind != "draw":
                continue
            d = r.drawables.get(op.thing_id)
            p = pmap.get(op.thing_id)
            if d and p:
                worst_ext = max(
                    worst_ext, invariants.extent_error(d.extent.w, d.extent.h, op.strokes, p.scale)
                )
        n_conn = sum(1 for op in r.ops if op.kind == "connector")
        ok = rep.passes and worst_ext <= EPS
        all_pass &= ok
        (outdir / f"{sc.name}.svg").write_text(to_svg(r, board))
        mark = "PASS" if ok else "FAIL"
        print(
            f"[{mark}] {sc.name:<16} placed {rep.drawn}/{rep.total}  drops {len(r.drops)}  "
            f"connectors {n_conn}  overlap {rep.overlap:.3f}  extent-err {worst_ext:.3f}"
        )
        if rep.relation_violations:
            print(f"        violations: {rep.relation_violations}")
    # Cartoon style: render the nature scene in color over a sky backdrop, so the
    # full palette/fill/background path has an inspectable artifact.
    cs = cartoon_scene()
    cr = render(cs, board, style=palette.CARTOON)
    bg = palette.background("the sky", "draw")
    (outdir / "cartoon_demo.svg").write_text(to_svg(cr, board, background=bg))
    print(f"[cartoon] {cs.name:<16} placed {len(cr.ops)} ops over '{bg['scene']}' backdrop")

    print("=" * 64)
    print(f"DRAWING GATE: {'PASS' if all_pass else 'FAIL'}   (SVGs in {outdir}/)\n")
    return 0 if all_pass else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
