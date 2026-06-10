"""Run the verification prompt set through the planner (and render the first).

Reports, per prompt: validity, #objects, which assets were used, #steps.
Renders the first prompt to an mp4 for visual inspection.
"""
import sys
import time
from pathlib import Path

from planner import plan, pick_model
from renderer import render

PROMPTS = [
    "a man walking on a road",
    "a car driving past a tree",
    "explain the Pythagorean theorem",
    "a circle moving across the board",
    "the water cycle",
]

print(f"model: {pick_model()}\n")
for i, p in enumerate(PROMPTS):
    t0 = time.time()
    try:
        scene = plan(p)
        assets = sorted({o.asset for o in scene.objects if o.type == "asset" and o.asset})
        is_mock = any("mock planner" in (o.text or "") for o in scene.objects)
        tag = "MOCK-FALLBACK" if is_mock else "ok"
        print(f"[{tag}] {p!r}  ({time.time()-t0:.0f}s)")
        print(f"        objects={len(scene.objects)} steps={len(scene.steps)} assets={assets}")
        if i == 0:
            out = render(scene, Path("media"))
            print(f"        rendered -> {out}")
    except Exception as e:
        print(f"[FAIL] {p!r}: {type(e).__name__}: {e}")
    sys.stdout.flush()
