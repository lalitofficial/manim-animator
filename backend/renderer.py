"""Manim renderer — turns a Scene IR into an mp4.

This is the *only* place that knows about Manim. The planner and IR stay
renderer-agnostic, so a future web/canvas renderer (for the realtime board)
plugs in here without touching anything upstream.

We build a manim.Scene subclass dynamically from the IR, then invoke manim
programmatically (no CLI, no scene file to import).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from ir import Scene as SceneIR
from ir import SceneObject


def _build_mobject(spec: SceneObject):
    """Map one IR object to a Manim mobject. Groups are built separately
    (they reference other objects) — see `_make_scene_class`."""
    import numpy as np
    from manim import (
        Arrow, Circle, Dot, Line, Polygon, Rectangle, Square, Text, Triangle,
    )

    color = spec.color
    pos = np.array(spec.position, dtype=float)
    # Objects defined by explicit coordinates carry their own position.
    self_positioned = spec.type in ("line", "arrow") or bool(spec.points and len(spec.points) >= 3)

    if spec.type == "text":
        m = Text(spec.text or "", font_size=spec.font_size, color=color)
    elif spec.type == "mathtex":
        from manim import MathTex  # needs LaTeX installed
        m = MathTex(spec.tex or "", color=color).scale(spec.font_size / 40)
    elif spec.type == "circle":
        m = Circle(radius=spec.radius, color=color)
    elif spec.type == "square":
        m = Square(side_length=spec.width, color=color)
    elif spec.type == "rectangle":
        m = Rectangle(width=spec.width, height=spec.height, color=color)
    elif spec.type == "triangle":
        if spec.points and len(spec.points) >= 3:
            m = Polygon(*[np.array(p, dtype=float) for p in spec.points], color=color)
        else:
            m = Triangle(color=color)
    elif spec.type == "polygon":
        pts = spec.points or []
        if len(pts) < 3:
            raise ValueError("polygon needs >= 3 points")
        m = Polygon(*[np.array(p, dtype=float) for p in pts], color=color)
    elif spec.type == "dot":
        m = Dot(color=color)
    elif spec.type == "line":
        m = Line(np.array(spec.start), np.array(spec.end), color=color)
    elif spec.type == "arrow":
        m = Arrow(np.array(spec.start), np.array(spec.end), color=color)
    elif spec.type == "asset":
        import assets
        # Asset colors come from `params` (each asset has a tasteful default);
        # the top-level `color` is for primitives only. build_asset never raises.
        m = assets.build_asset(spec.asset or "", **(spec.params or {}))
    else:
        raise ValueError(f"unknown object type: {spec.type}")

    if spec.scale != 1.0:
        m.scale(spec.scale)  # scales about the mobject's center, position preserved
    if self_positioned:
        return m
    return m.move_to(pos)


def _make_scene_class(ir: SceneIR):
    import numpy as np
    from manim import (
        Create, FadeIn, FadeOut, Scene as MScene, Transform, VGroup, Write,
    )

    class GeneratedScene(MScene):
        def construct(self):
            self.camera.background_color = ir.background

            # Two passes: build standalone objects first, then groups that
            # reference them by id. A group bundles already-placed members so
            # steps can animate them as a unit (it does not relocate them).
            mobjects = {}
            for o in ir.objects:
                if o.type != "group":
                    try:
                        mobjects[o.id] = _build_mobject(o)
                    except Exception:
                        continue  # skip a malformed object; its steps are tolerated
            for o in ir.objects:
                if o.type == "group":
                    members = [mobjects[m] for m in (o.members or []) if m in mobjects]
                    if not members:
                        continue
                    g = VGroup(*members)
                    if o.scale != 1.0:
                        g.scale(o.scale)
                    mobjects[o.id] = g

            for step in ir.steps:
                # Manim rejects run_time <= 0; models sometimes emit 0. Clamp.
                d = max(float(step.duration), 0.1)
                # A single malformed step must not kill the whole render.
                try:
                    if step.animation == "wait":
                        self.wait(d)
                        continue

                    mob = mobjects.get(step.target) if step.target else None
                    if mob is None:
                        continue  # tolerate a step that references a missing id

                    if step.animation == "write":
                        self.play(Write(mob), run_time=d)
                    elif step.animation == "create":
                        self.play(Create(mob), run_time=d)
                    elif step.animation == "fadein":
                        self.play(FadeIn(mob), run_time=d)
                    elif step.animation == "fadeout":
                        self.play(FadeOut(mob), run_time=d)
                    elif step.animation == "move" and step.to is not None:
                        self.play(mob.animate.move_to(np.array(step.to, dtype=float)),
                                  run_time=d)
                    elif step.animation == "scale":
                        self.play(mob.animate.scale(step.factor), run_time=d)
                    elif step.animation == "transform" and step.into:
                        target = mobjects.get(step.into)
                        if target is not None:
                            self.play(Transform(mob, target), run_time=d)
                except Exception:
                    continue  # skip the bad step, keep rendering the rest

            self.wait(0.5)

    return GeneratedScene


def render(ir: SceneIR, out_dir: Path, quality: str = "low") -> Path:
    """Render `ir` to an mp4 under `out_dir`. Returns the mp4 path."""
    from manim import config, tempconfig

    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"scene_{uuid.uuid4().hex[:8]}"

    # low: 480p15 (fast feedback). raise to "high" (1080p60) when needed.
    q = {"low": "low_quality", "medium": "medium_quality", "high": "production_quality"}
    settings = {
        "media_dir": str(out_dir),
        "output_file": name,
        "quality": q.get(quality, "low_quality"),
        "disable_caching": True,
        "verbosity": "ERROR",
    }

    with tempconfig(settings):
        SceneClass = _make_scene_class(ir)
        scene = SceneClass()
        scene.render()
        produced = Path(config.output_file)

    return produced


if __name__ == "__main__":
    # Smoke test with hand-written IR — no LLM. Exercises assets, a bogus asset
    # (must fall back, not crash), and motion.
    demo = SceneIR.model_validate(
        {
            "title": "asset demo",
            "objects": [
                {"id": "road", "type": "asset", "asset": "road", "position": [0, -2.5]},
                {"id": "man", "type": "asset", "asset": "man", "position": [-5, -1.4], "scale": 0.9},
                {"id": "tree", "type": "asset", "asset": "tree", "position": [4, -1.2]},
                {"id": "sun", "type": "asset", "asset": "sun", "position": [-4.5, 2.5]},
                {"id": "mystery", "type": "asset", "asset": "dragon", "position": [3, 2]},
            ],
            "steps": [
                {"animation": "fadein", "target": "road", "duration": 0.6},
                {"animation": "create", "target": "sun", "duration": 0.6},
                {"animation": "fadein", "target": "tree", "duration": 0.6},
                {"animation": "fadein", "target": "mystery", "duration": 0.6},
                {"animation": "fadein", "target": "man", "duration": 0.6},
                {"animation": "move", "target": "man", "to": [4, -1.4], "duration": 3.0},
            ],
        }
    )
    out = render(demo, Path("media"))
    print("rendered:", out)
