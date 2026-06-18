"""Exact per-element diagnostic for a cartoon lesson — the DATA half of the visual feedback loop.

Compiles a lesson through the real engine and reports, for every drawable: concept, render SOURCE
(icon/primitive/family/catalog/box/character), dominant COLOR, bounding box, on-board/grounded/size
checks — and auto-flags issues (placeholder box, floating prop, tiny prop, off-board, off-palette).
Run alongside tools/grab_frames.js (the pixels) to pinpoint exactly what's wrong and verify fixes.

    .venv/bin/python tools/diagnose_lesson.py "how a volcano erupts" story
"""

import collections
import sys

sys.path.insert(0, "backend")

from engine import palette, story  # noqa: E402
from engine import plan as P  # noqa: E402
from engine.contracts import Board  # noqa: E402
from engine.director import direct  # noqa: E402

topic = sys.argv[1] if len(sys.argv) > 1 else "how a volcano erupts"
mode = sys.argv[2] if len(sys.argv) > 2 else "story"
spec = direct(topic, mode=mode, style="cartoon")
lp = story.tell_plan(spec)
board = Board()
grass_top = round(-board.hh + palette.HORIZON_FRAC * board.h, 2)  # props should SIT here

meta = {e.id: (e.concept, e.role, e.kind) for sc in lp.scenes for e in sc.entities}


def _bbox(op):
    pts = [p for s in op.get("strokes", []) for p in s.get("points", [])]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _color(op):
    c = collections.Counter()
    for s in op.get("strokes", []):
        key = s.get("fill") or s.get("color")
        if key:
            c[key] += 1
    return c.most_common(1)[0][0] if c else None


print(
    f"LESSON {topic!r}  mode={mode}  scenes={len(lp.scenes)}  board={board.w}x{board.h}  "
    f"grass_top_y={grass_top}"
)
issues_total = collections.Counter()
scene_i = 0
for ev in P.compile_plan(lp, spec, board):
    t = ev.get("type")
    if t == "clear":
        scene_i += 1
    elif t == "background":
        g = ev.get("ground", {})
        print(
            f"  ── scene {scene_i}: backdrop={ev.get('scene')} emotion={ev.get('emotion')} "
            f"ground_frac={g.get('frac')} sky={(ev.get('gradient') or {}).get('top')}"
        )
    elif t == "draw":
        op = ev["op"]
        concept, role, kind = meta.get(op["id"], ("?", "?", "?"))
        bb = _bbox(op)
        flags = []
        if op.get("source") == "box":
            flags.append("PLACEHOLDER-BOX")
        if bb:
            w, h, bottom = bb[2] - bb[0], bb[3] - bb[1], bb[1]
            if kind not in ("text", "character") and bottom > grass_top + 0.2:
                flags.append(f"FLOATS(+{bottom - grass_top:.2f})")
            if kind not in ("text", "character") and h < board.h * 0.22:
                flags.append(f"TINY(h={h:.1f})")
            if bb[0] < -board.hw - 0.05 or bb[2] > board.hw + 0.05:
                flags.append("OFF-BOARD")
            dims = f"{w:.1f}x{h:.1f} bottom={bottom:.2f}"
        else:
            dims = "(no strokes)"
        for f in flags:
            issues_total[f.split("(")[0]] += 1
        print(
            f"    {op['id']:7} {str(concept)[:14]:14} role={str(role):8} src={str(op.get('source')):9} "
            f"color={str(_color(op)):9} {dims:24} {'  '.join(flags) if flags else 'ok'}"
        )
print("\nISSUES:", dict(issues_total) or "none flagged")
