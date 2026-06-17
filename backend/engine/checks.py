"""Testing/checking integration layer — the backend behind the dashboard.

Every report is computed IN-PROCESS from the engine + the output-derived
invariants (the same ruler the test suite uses), so the dashboard reflects real
status, never a stale or self-certified one (§K1/§K2). `run_suite()` shells out to
pytest for the full unit-test view.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from engine import drawing, invariants
from engine.contracts import Board, Extent, Thing
from engine.corpus import corpus, scenes
from engine.positioning import place
from engine.runtime import lesson
from engine.scene import render
from engine.stream import stream_lesson
from engine.svg import to_svg

_ROOT = Path(__file__).resolve().parents[2]  # repo root
EXTENT_EPS = 0.10


def health() -> dict:
    from engine import models

    cfg = models.describe()
    return {
        "python": sys.version.split()[0],
        "story_provider": cfg["story"]["provider"],  # resolved (local-first), not raw env
        "story_model": cfg["story"]["model"],
        "svg_provider": cfg["svg"]["provider"],
        "corpus_cases": len(corpus()),
        "drawing_scenes": len(scenes()),
        "board": {"w": Board().w, "h": Board().h},
    }


def positioning_report() -> dict:
    board = Board()
    cases = []
    ok_all = True
    for c in corpus():
        placed, drops = place(c.things, board)
        rep = invariants.evaluate(c.things, placed, board)
        # Cases expecting no drops must reach FULL coverage; over-subscription
        # cases drop at least the expected count (mirrors the unit gate, review A1).
        coverage_ok = len(drops) == 0 if c.expect_drops == 0 else len(drops) >= c.expect_drops
        ok = rep.passes and coverage_ok
        ok_all = ok_all and ok
        cases.append(
            {
                "name": c.name,
                "level": c.level,
                "pass": ok,
                "placed": rep.drawn,
                "total": rep.total,
                "drops": len(drops),
                "overlap": round(rep.overlap, 4),
                "off_board": len(rep.off_board),
                "relation_violations": rep.relation_violations,
                "rows": rep.rows,
            }
        )
    return {"pass": ok_all, "cases": cases}


def drawing_report(include_svg: bool = False) -> dict:
    board = Board()
    out = []
    ok_all = True
    for sc in scenes():
        r = render(sc, board)
        rep = invariants.evaluate(sc.things, r.placements, board)
        pmap = r.placement_of()
        worst = 0.0
        for op in r.ops:
            if op.kind != "draw":
                continue
            d = r.drawables.get(op.thing_id)
            p = pmap.get(op.thing_id)
            if d and p:
                worst = max(
                    worst, invariants.extent_error(d.extent.w, d.extent.h, op.strokes, p.scale)
                )
        # Drawing scenes are authored to fully place; any drop is a failure.
        ok = rep.passes and worst <= EXTENT_EPS and len(r.drops) == 0
        ok_all = ok_all and ok
        item = {
            "name": sc.name,
            "pass": ok,
            "placed": rep.drawn,
            "total": rep.total,
            "drops": len(r.drops),
            "connectors": sum(1 for o in r.ops if o.kind == "connector"),
            "overlap": round(rep.overlap, 4),
            "extent_error": round(worst, 4),
            "relation_violations": rep.relation_violations,
        }
        if include_svg:
            item["svg"] = to_svg(r, board)
        out.append(item)
    return {"pass": ok_all, "scenes": out}


def speed_report() -> dict:
    topics = ["the water cycle", "binary search", "supply and demand", "photosynthesis"] * 5
    for tp in sorted(set(topics)):  # warm the MEASURED topics, not a throwaway (review B6)
        list(stream_lesson(tp))
    t0 = time.perf_counter()
    for tp in topics:
        list(stream_lesson(tp))
    per_ms = (time.perf_counter() - t0) / len(topics) * 1000

    scaling = []
    board = Board()
    for n in (10, 25, 50):
        things = [Thing(f"t{i}", "box", Extent(1.4, 0.9)) for i in range(n)]
        t0 = time.perf_counter()
        placed, drops = place(things, board)
        scaling.append(
            {
                "n": n,
                "ms": round((time.perf_counter() - t0) * 1000, 1),
                "placed": len(placed),
                "dropped": len(drops),
            }
        )
    return {
        "ms_per_lesson": round(per_ms, 2),
        "lessons_measured": len(topics),
        "positioning_scaling": scaling,
    }


def lesson_report(topic: str, mode: str = "learn") -> dict:
    board = Board()
    drawing.reset()  # deterministic render for the explorer
    les = lesson(topic, board=board)
    rep = invariants.evaluate(les.scene.things, les.rendered.placements, board)
    rungs: dict[int, int] = {}
    for d in les.rendered.drawables.values():
        rungs[d.rung] = rungs.get(d.rung, 0) + 1

    # Extent-honesty parity with the Drawing gate (review B2).
    pmap = les.rendered.placement_of()
    worst = 0.0
    for op in les.rendered.ops:
        if op.kind != "draw":
            continue
        d = les.rendered.drawables.get(op.thing_id)
        p = pmap.get(op.thing_id)
        if d and p:
            worst = max(worst, invariants.extent_error(d.extent.w, d.extent.h, op.strokes, p.scale))

    ok = rep.passes and worst <= EXTENT_EPS and rep.drawn == rep.total
    return {
        "topic": topic,
        "pass": ok,
        "beats": len(les.beats),
        "narration": les.narration,
        "placed": rep.drawn,
        "total": rep.total,
        "drops": len(les.rendered.drops),
        "overlap": round(rep.overlap, 4),
        "off_board": rep.off_board,
        "extent_error": round(worst, 4),
        "relation_violations": rep.relation_violations,
        "rung_hits": {str(k): v for k, v in sorted(rungs.items())},
        "svg": to_svg(les.rendered, board),
    }


def run_suite() -> dict:
    """Shell out to the pytest suite (the full unit-test view)."""
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--no-header"],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except Exception as e:  # noqa: BLE001 - surface any failure to the dashboard
        return {
            "ok": False,
            "error": str(e),
            "duration_ms": round((time.perf_counter() - t0) * 1000),
        }
    out = (proc.stdout or "") + (proc.stderr or "")
    lines = out.splitlines()
    # Prefer pytest's real summary banner (e.g. "=== 87 passed in 1.2s ===").
    summary = next(
        (ln for ln in reversed(lines) if ("passed" in ln or "failed" in ln or "error" in ln)),
        "(no summary)",
    )
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "summary": summary.strip(),
        "duration_ms": round((time.perf_counter() - t0) * 1000),
        "tail": "\n".join(lines[-40:]),  # line-boundary, not mid-line char slice (review C1)
    }


def full_report() -> dict:
    pos = positioning_report()
    draw = drawing_report()
    # Server-authoritative rollup so the client can't miss a sub-gate (review A2).
    return {
        "pass": pos["pass"] and draw["pass"],
        "health": health(),
        "positioning": pos,
        "drawing": draw,
        "speed": speed_report(),
    }
