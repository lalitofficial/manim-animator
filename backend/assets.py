"""Asset library — named composite building blocks for scenes.

This is what lets a prompt say "a man on a road" and get a recognizable man and
road instead of a circle pretending to be one. Each asset is a factory that
returns a Manim mobject (usually a VGroup of primitives) with consistent
styling, built around its own local origin so the renderer can `move_to` it.

Three ways an asset name resolves (in order):
  1. a registered built-in factory (optionally via an alias),
  2. a drop-in SVG at backend/assets/svg/<name>.svg,
  3. a labeled fallback box — so an unknown name degrades, never crashes.

`catalog()` is the single source of truth fed to the planner prompt, so adding
a factory here (or dropping in an SVG) automatically extends what the model can
ask for — no prompt edits needed.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SVG_DIR = Path(__file__).resolve().parent / "assets" / "svg"


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
@dataclass
class AssetSpec:
    name: str
    factory: Callable
    aliases: list[str] = field(default_factory=list)
    params: str = ""
    desc: str = ""


ASSETS: dict[str, AssetSpec] = {}
ALIASES: dict[str, str] = {}


def register(name: str, aliases=(), params: str = "", desc: str = ""):
    def deco(fn: Callable) -> Callable:
        ASSETS[name] = AssetSpec(name, fn, list(aliases), params, desc)
        for a in aliases:
            ALIASES[a] = name
        return fn

    return deco


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def resolve(name: str) -> str:
    """Map an alias to its canonical asset name (identity if not an alias)."""
    n = _norm(name)
    return ALIASES.get(n, n)


def known_names() -> set[str]:
    """All names the planner may legitimately use (for repair coercion)."""
    names = set(ASSETS) | set(ALIASES)
    if SVG_DIR.exists():
        names |= {p.stem for p in SVG_DIR.glob("*.svg")}
    return names


def catalog() -> str:
    lines = []
    for spec in ASSETS.values():
        al = f" (aka {', '.join(spec.aliases)})" if spec.aliases else ""
        p = f" [params: {spec.params}]" if spec.params else ""
        lines.append(f"- {spec.name}{al}: {spec.desc}{p}")
    if SVG_DIR.exists():
        for p in sorted(SVG_DIR.glob("*.svg")):
            lines.append(f"- {p.stem}: custom SVG asset")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Built-in composites
#   Imports are local to each factory so this module is importable without
#   manim present (the planner imports `catalog()`/`known_names()` only).
# --------------------------------------------------------------------------- #
@register(
    "stick_figure",
    aliases=[
        "man",
        "person",
        "human",
        "boy",
        "girl",
        "woman",
        "people",
        "student",
        "teacher",
        "figure",
        "stickman",
        "stick_man",
        "walker",
    ],
    params="color, height",
    desc="a stick-figure person",
)
def stick_figure(color="#E6EDF3", height=2.0):
    from manim import DOWN, LEFT, RIGHT, UP, Circle, Line, VGroup

    sw = 4
    head = Circle(radius=0.3, color=color, stroke_width=sw).move_to(UP * 1.3)
    body = Line(UP * 1.0, DOWN * 0.2, color=color, stroke_width=sw)
    arms = Line(LEFT * 0.6 + UP * 0.6, RIGHT * 0.6 + UP * 0.6, color=color, stroke_width=sw)
    l_leg = Line(DOWN * 0.2, DOWN * 1.1 + LEFT * 0.45, color=color, stroke_width=sw)
    r_leg = Line(DOWN * 0.2, DOWN * 1.1 + RIGHT * 0.45, color=color, stroke_width=sw)
    fig = VGroup(head, body, arms, l_leg, r_leg)  # sub-parts kept for future articulation
    fig.set(height=height)
    return fig


@register(
    "road",
    aliases=["street", "path", "highway", "ground", "floor"],
    params="color, width",
    desc="a horizontal road with center dashes",
)
def road(color="#30363D", width=14.0, height=1.6):
    import numpy as np
    from manim import LEFT, RIGHT, Line, Rectangle, VGroup

    # A road is conceptually frame-wide; small models often shrink it to a box.
    # Clamp so it always reads as a road (callers wanting a short path use a line).
    width = max(float(width), 8.0)
    surface = Rectangle(
        width=width, height=height, fill_color=color, fill_opacity=1.0, stroke_width=0
    )
    dashes = VGroup()
    x = -width / 2 + 0.7
    while x < width / 2 - 0.5:
        dashes.add(
            Line(LEFT * 0.35, RIGHT * 0.35, color="#E3B341", stroke_width=6).move_to(
                np.array([x, 0, 0])
            )
        )
        x += 1.4
    return VGroup(surface, dashes)


@register("car", aliases=["vehicle", "automobile"], params="color", desc="a simple side-view car")
def car(color="#58A6FF"):
    from manim import DOWN, LEFT, RIGHT, UP, Circle, Rectangle, VGroup

    body = Rectangle(width=2.2, height=0.6, fill_color=color, fill_opacity=1, stroke_width=0)
    cabin = Rectangle(
        width=1.1, height=0.5, fill_color=color, fill_opacity=1, stroke_width=0
    ).move_to(UP * 0.5 + LEFT * 0.1)
    w1 = Circle(
        radius=0.28, fill_color="#0E1116", fill_opacity=1, stroke_color="#8B949E", stroke_width=3
    ).move_to(DOWN * 0.35 + LEFT * 0.6)
    w2 = Circle(
        radius=0.28, fill_color="#0E1116", fill_opacity=1, stroke_color="#8B949E", stroke_width=3
    ).move_to(DOWN * 0.35 + RIGHT * 0.6)
    return VGroup(body, cabin, w1, w2)


@register("tree", aliases=["plant"], params="color", desc="a tree (trunk + foliage)")
def tree(color="#3FB950"):
    from manim import DOWN, UP, Circle, Rectangle, VGroup

    trunk = Rectangle(
        width=0.35, height=1.0, fill_color="#8B5A2B", fill_opacity=1, stroke_width=0
    ).move_to(DOWN * 0.5)
    foliage = Circle(radius=0.8, fill_color=color, fill_opacity=1, stroke_width=0).move_to(UP * 0.5)
    return VGroup(trunk, foliage)


@register("house", aliases=["home"], params="color", desc="a house (square + roof)")
def house(color="#D29922"):
    import numpy as np
    from manim import DOWN, Polygon, Rectangle, Square, VGroup

    walls = Square(side_length=1.6, fill_color=color, fill_opacity=1, stroke_width=0).move_to(
        DOWN * 0.2
    )
    roof = Polygon(
        np.array([-1.0, 0.6, 0]),
        np.array([1.0, 0.6, 0]),
        np.array([0, 1.5, 0]),
        fill_color="#B62324",
        fill_opacity=1,
        stroke_width=0,
    )
    door = Rectangle(
        width=0.4, height=0.7, fill_color="#3A2410", fill_opacity=1, stroke_width=0
    ).move_to(DOWN * 0.6)
    return VGroup(walls, roof, door)


@register("sun", params="color", desc="a sun with rays")
def sun(color="#F2CC60"):
    import numpy as np
    from manim import Circle, Line, VGroup

    disc = Circle(radius=0.6, fill_color=color, fill_opacity=1, stroke_width=0)
    rays = VGroup()
    for i in range(8):
        a = i * np.pi / 4
        d = np.array([np.cos(a), np.sin(a), 0])
        rays.add(Line(d * 0.8, d * 1.2, color=color, stroke_width=5))
    return VGroup(disc, rays)


@register("cloud", params="color", desc="a fluffy cloud")
def cloud(color="#C9D1D9"):
    from manim import LEFT, RIGHT, Circle, VGroup

    parts = VGroup(
        Circle(radius=0.5, fill_color=color, fill_opacity=1, stroke_width=0).move_to(LEFT * 0.6),
        Circle(radius=0.65, fill_color=color, fill_opacity=1, stroke_width=0),
        Circle(radius=0.5, fill_color=color, fill_opacity=1, stroke_width=0).move_to(RIGHT * 0.6),
    )
    return parts


@register("mountain", aliases=["hill"], params="color", desc="a mountain peak")
def mountain(color="#6E7681"):
    import numpy as np
    from manim import Polygon

    return Polygon(
        np.array([-1.5, -0.8, 0]),
        np.array([1.5, -0.8, 0]),
        np.array([0, 1.2, 0]),
        fill_color=color,
        fill_opacity=1,
        stroke_width=0,
    )


@register(
    "building", aliases=["tower", "skyscraper"], params="color", desc="a tall building with windows"
)
def building(color="#484F58"):
    import numpy as np
    from manim import Rectangle, VGroup

    body = Rectangle(width=1.4, height=3.0, fill_color=color, fill_opacity=1, stroke_width=0)
    windows = VGroup()
    for row in range(5):
        for col in range(2):
            w = Rectangle(
                width=0.3, height=0.3, fill_color="#F2CC60", fill_opacity=1, stroke_width=0
            )
            w.move_to(np.array([-0.35 + col * 0.7, 1.0 - row * 0.5, 0]))
            windows.add(w)
    return VGroup(body, windows)


@register("book", params="color", desc="a closed book")
def book(color="#A371F7"):
    from manim import LEFT, Line, Rectangle, VGroup

    cover = Rectangle(width=1.4, height=1.8, fill_color=color, fill_opacity=1, stroke_width=0)
    spine = Line(
        cover.get_top() + LEFT * 0.6,
        cover.get_bottom() + LEFT * 0.6,
        color="#0E1116",
        stroke_width=4,
    )
    return VGroup(cover, spine)


@register("bulb", aliases=["lightbulb", "idea"], params="color", desc="a light bulb")
def bulb(color="#F2CC60"):
    from manim import DOWN, Circle, Rectangle, VGroup

    glass = Circle(radius=0.55, fill_color=color, fill_opacity=0.9, stroke_width=0)
    base = Rectangle(
        width=0.4, height=0.35, fill_color="#8B949E", fill_opacity=1, stroke_width=0
    ).move_to(DOWN * 0.7)
    return VGroup(glass, base)


@register("dot_label", aliases=["marker"], params="color", desc="a small labeled dot")
def dot_label(color="#58A6FF"):
    from manim import Dot

    return Dot(color=color, radius=0.12)


# --------------------------------------------------------------------------- #
# Resolution + build
# --------------------------------------------------------------------------- #
def _filter_kwargs(fn: Callable, params: dict) -> dict:
    """Pass only kwargs the factory actually accepts (drops junk from the LLM)."""
    sig = inspect.signature(fn)
    return {k: v for k, v in params.items() if k in sig.parameters}


def _svg_asset(name: str):
    path = SVG_DIR / f"{name}.svg"
    if path.exists():
        from manim import SVGMobject

        return SVGMobject(str(path))
    return None


def _fallback(name: str):
    """A labeled box so an unknown asset is visible, not fatal."""
    from manim import RoundedRectangle, Text, VGroup

    box = RoundedRectangle(
        width=2.6, height=1.2, corner_radius=0.15, color="#8B949E", stroke_width=3
    )
    label = Text(name, font_size=22, color="#8B949E")
    return VGroup(box, label)


def build_asset(name: str, **params):
    """Resolve `name` to a mobject: built-in -> SVG -> labeled fallback.

    Never raises: any failure (bad params, broken SVG, missing name) degrades to
    a labeled fallback box so a single bad object can't kill a whole render.
    """
    canonical = resolve(name or "")
    spec = ASSETS.get(canonical)
    try:
        if spec:
            return spec.factory(**_filter_kwargs(spec.factory, params))
        svg = _svg_asset(canonical)
        if svg is not None:
            return svg
    except Exception:
        pass
    return _fallback(name or "asset")
