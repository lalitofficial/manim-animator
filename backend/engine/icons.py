"""Composable icons — the generative visual LANGUAGE (not a catalog).

A concept is drawn by COMPOSING primitives via a declarative recipe (data, not
code — safe + scalable + a workflow can mass-author them). Most teaching concepts
decompose this way, so generation/catalog become the rare fallback, not the norm:

    sun     = circle + rays
    cloud   = overlapping blobs
    tree    = trunk + foliage blob
    person  = head + body + limbs
    molecule = atoms (radial circles) + bonds

A recipe is authored in a ~2x2 box centered at the origin; drawing.py normalizes
it to the requested size. `compose(concept)` returns composed Strokes or None.
"""

from __future__ import annotations

import math
from dataclasses import replace

from engine import geometry as g
from engine.contracts import Stroke


# --------------------------------------------------------------------------- #
# Recipe interpreter: a recipe is {"parts": [part, ...]}; each part is a
# primitive draw with an `at`/`scale`/`rot` transform, or a composite (radial/rays).
# --------------------------------------------------------------------------- #
def _prim(part: dict) -> list[Stroke]:
    p = part.get("prim")
    if p == "circle":
        base = [g.circle(part.get("r", 0.5))]
    elif p == "ellipse":
        base = [g.ellipse(part.get("rx", 0.5), part.get("ry", 0.3))]
    elif p == "rect":
        base = [g.rectangle(part.get("w", 1.0), part.get("h", 1.0))]
    elif p == "rounded_rect":
        base = [g.rounded_rect(part.get("w", 1.0), part.get("h", 1.0), part.get("r", 0.2))]
    elif p == "triangle":
        base = [g.triangle(part.get("w", 1.0), part.get("h", 1.0))]
    elif p == "line":
        base = [g.segment((0.0, 0.0), tuple(part.get("to", [1.0, 0.0])))]  # type: ignore[arg-type]
    elif p == "arc":
        base = [g.arc(part.get("r", 0.5), part.get("a0", 0.0), part.get("a1", 180.0))]
    elif p == "blob":
        base = [
            g.blob(
                part.get("r", 0.5),
                part.get("bumps", 6),
                part.get("jitter", 0.18),
                part.get("seed", 0.0),
            )
        ]
    elif p == "wave":
        base = [g.wave(part.get("w", 1.0), part.get("amp", 0.2), part.get("cycles", 2.0))]
    elif p == "polyline":
        base = [g.polyline(part["points"], part.get("closed", False))]
    elif p == "rays":
        return _rays(part)
    elif p == "radial":
        return _radial(part)
    else:
        return []
    # Optional cartoon styling: per-part fill + stroke (line) color.
    fill, line = part.get("fill"), part.get("stroke")
    if fill or line:
        base = [replace(s, fill=fill or s.fill, color=line or s.color) for s in base]
    at = part.get("at", [0.0, 0.0])
    return list(
        g.transform(base, at[0], at[1], part.get("scale", 1.0), math.radians(part.get("rot", 0.0)))
    )


def _rays(part: dict) -> list[Stroke]:
    """n line segments radiating from `at`, between radius r and r+length."""
    at = part.get("at", [0.0, 0.0])
    r, length, n = part.get("r", 0.5), part.get("length", 0.3), part.get("n", 8)
    phase = math.radians(part.get("phase", 0.0))
    out = []
    for i in range(n):
        a = phase + 2 * math.pi * i / n
        c, s = math.cos(a), math.sin(a)
        out.append(
            g.segment(
                (at[0] + r * c, at[1] + r * s), (at[0] + (r + length) * c, at[1] + (r + length) * s)
            )
        )
    return out


def _radial(part: dict) -> list[Stroke]:
    """Repeat a sub-part `of` n times around `at` at radius r."""
    at = part.get("at", [0.0, 0.0])
    r, n = part.get("r", 0.5), part.get("n", 6)
    phase = math.radians(part.get("phase", 0.0))
    out = []
    for i in range(n):
        a = phase + 2 * math.pi * i / n
        sub = dict(part["of"])
        sub["at"] = [at[0] + r * math.cos(a), at[1] + r * math.sin(a)]
        out += _prim(sub)
    return out


def render_recipe(recipe: dict) -> tuple[Stroke, ...]:
    strokes: list[Stroke] = []
    for part in recipe.get("parts", []):
        strokes += _prim(part)
    return tuple(s for s in strokes if len(s.points) >= 2)


# --------------------------------------------------------------------------- #
# The icon library (declarative data). Authored in a ~2-unit box.
# --------------------------------------------------------------------------- #
# Core recipes carry authored cartoon colors (fill = body, stroke = outline). The
# whiteboard style strips them (palette.apply); cartoon honors them. Multi-part
# recipes (tree, house, person…) need PER-PART color a single concept tint can't give.
ICON_RECIPES: dict[str, dict] = {
    "sun": {
        "parts": [
            {"prim": "circle", "r": 0.45, "fill": "#ffd23f", "stroke": "#e0991b"},
            {"prim": "rays", "r": 0.55, "length": 0.32, "n": 12, "stroke": "#e0991b"},
        ]
    },
    "cloud": {
        "parts": [
            {
                "prim": "circle",
                "at": [-0.45, 0.0],
                "r": 0.38,
                "fill": "#ffffff",
                "stroke": "#bcc9d6",
            },
            {"prim": "circle", "at": [0.0, 0.18], "r": 0.5, "fill": "#ffffff", "stroke": "#bcc9d6"},
            {
                "prim": "circle",
                "at": [0.48, 0.0],
                "r": 0.36,
                "fill": "#ffffff",
                "stroke": "#bcc9d6",
            },
            {
                "prim": "ellipse",
                "at": [0.0, -0.25],
                "rx": 0.85,
                "ry": 0.3,
                "fill": "#ffffff",
                "stroke": "#bcc9d6",
            },
        ]
    },
    "tree": {
        "parts": [
            {
                "prim": "rect",
                "at": [0.0, -0.55],
                "w": 0.18,
                "h": 0.7,
                "fill": "#8a5a2b",
                "stroke": "#5e3c1a",
            },
            {
                "prim": "blob",
                "at": [0.0, 0.25],
                "r": 0.55,
                "bumps": 7,
                "jitter": 0.22,
                "fill": "#3fa46a",
                "stroke": "#2b7a4b",
            },
        ]
    },
    "person": {
        "parts": [
            {
                "prim": "circle",
                "at": [0.0, 0.62],
                "r": 0.18,
                "fill": "#f4c08a",
                "stroke": "#c98b4d",
            },
            {"prim": "line", "at": [0.0, 0.44], "to": [0.0, -0.54], "stroke": "#3b6ea5"},
            {"prim": "line", "at": [0.0, 0.28], "to": [-0.32, -0.23], "stroke": "#3b6ea5"},
            {"prim": "line", "at": [0.0, 0.28], "to": [0.32, -0.23], "stroke": "#3b6ea5"},
            {"prim": "line", "at": [0.0, -0.1], "to": [-0.26, -0.52], "stroke": "#26354d"},
            {"prim": "line", "at": [0.0, -0.1], "to": [0.26, -0.52], "stroke": "#26354d"},
        ]
    },
    "mountain": {
        "parts": [
            {
                "prim": "polyline",
                "points": [[-0.9, -0.5], [-0.2, 0.55], [0.15, 0.1], [0.5, 0.7], [0.95, -0.5]],
                "closed": True,
                "fill": "#8a93a6",
                "stroke": "#5b6478",
            },
        ]
    },
    "house": {
        "parts": [
            {
                "prim": "rect",
                "at": [0.0, -0.25],
                "w": 1.0,
                "h": 0.7,
                "fill": "#ffcaa8",
                "stroke": "#d68a5e",
            },
            {
                "prim": "triangle",
                "at": [0.0, 0.32],
                "w": 1.2,
                "h": 0.45,
                "fill": "#e2614b",
                "stroke": "#b03a28",
            },
            {
                "prim": "rect",
                "at": [0.0, -0.4],
                "w": 0.26,
                "h": 0.4,
                "fill": "#8a5a2b",
                "stroke": "#5e3c1a",
            },
        ]
    },
    "flower": {
        "parts": [
            {
                "prim": "radial",
                "at": [0.0, 0.0],
                "r": 0.42,
                "n": 6,
                "of": {
                    "prim": "ellipse",
                    "rx": 0.18,
                    "ry": 0.3,
                    "fill": "#ff8fb0",
                    "stroke": "#d65f86",
                },
            },
            {"prim": "circle", "r": 0.2, "fill": "#ffd23f", "stroke": "#e0a800"},
        ]
    },
    "water": {
        "parts": [
            {
                "prim": "polyline",
                "points": [[0.0, 0.7], [0.4, -0.1], [0.0, -0.55], [-0.4, -0.1]],
                "closed": True,
                "fill": "#5b8def",
                "stroke": "#2f6fd0",
            },
        ]
    },
    "molecule": {
        "parts": [
            {
                "prim": "radial",
                "at": [0.0, 0.0],
                "r": 0.5,
                "n": 3,
                "of": {"prim": "line", "to": [0.0, 0.0], "stroke": "#4a90d9"},
            },
            {"prim": "circle", "r": 0.16, "fill": "#9ad0ff", "stroke": "#4a90d9"},
            {
                "prim": "radial",
                "at": [0.0, 0.0],
                "r": 0.5,
                "n": 3,
                "of": {"prim": "circle", "r": 0.16, "fill": "#9ad0ff", "stroke": "#4a90d9"},
            },
        ]
    },
}


def _star_points(spikes: int = 5, outer: float = 0.6, inner: float = 0.26) -> list[list[float]]:
    pts = []
    for i in range(spikes * 2):
        r = outer if i % 2 == 0 else inner
        a = math.pi / 2 + math.pi * i / spikes
        pts.append([round(r * math.cos(a), 3), round(r * math.sin(a), 3)])
    return pts


ICON_RECIPES["star"] = {
    "parts": [
        {
            "prim": "polyline",
            "points": _star_points(),
            "closed": True,
            "fill": "#ffe066",
            "stroke": "#e0a800",
        }
    ]
}

ALIASES = {
    "sunshine": "sun",
    "sunlight": "sun",
    "human": "person",
    "people": "person",
    "man": "person",
    "woman": "person",
    "child": "person",
    "rain cloud": "cloud",
    "raindrop": "water",
    "water drop": "water",
    "drop": "water",
    "droplet": "water",
    "vapor": "cloud",
    "water vapor": "cloud",
    "evaporation": "water",
    "condensation": "cloud",
    "precipitation": "rain",
    "flower blossom": "flower",
    "plant": "tree",
}


# Recipe precedence (highest -> lowest) — COLOR before coverage:
#   1. the hand-built CORE above (sun/cloud/tree/… — already colored)
#   2. cartoon_recipes.json — colored cartoon recipes that OVERRIDE the mono ones
#   3. the parametric FAMILIES (engine.families) — the colored-cartoon corpus  [in compose()]
#   4. icon_recipes.json — the mass-authored MONO fallback (uncolored long tail)
# Mono is kept SEPARATE (not merged into ICON_RECIPES) so a colored family beats an
# uncolored mono recipe for the same concept (cat/dog/ladybug were rendering mono-gray).
import json as _json  # noqa: E402
import pathlib as _pathlib  # noqa: E402

_HAND_BUILT = set(ICON_RECIPES)  # snapshot the core before merging data files
_DIR = _pathlib.Path(__file__).parent
_MONO_RECIPES: dict[str, dict] = {}  # the uncolored fallback, lowest precedence


def _merge(filename: str, *, override: bool) -> None:
    path = _DIR / filename
    if not path.exists():
        return
    try:
        for _concept, _recipe in _json.loads(path.read_text()).items():
            if _concept in _HAND_BUILT:
                continue  # never override the hand-built core
            if override or _concept not in ICON_RECIPES:
                ICON_RECIPES[_concept] = _recipe
    except Exception:
        pass


def _load_mono(filename: str) -> None:
    path = _DIR / filename
    if not path.exists():
        return
    try:
        for _concept, _recipe in _json.loads(path.read_text()).items():
            if _concept not in _HAND_BUILT:
                _MONO_RECIPES[_concept] = _recipe
    except Exception:
        pass


_merge("cartoon_recipes.json", override=True)  # colored — wins over everything but the core
_load_mono("icon_recipes.json")  # mono — only when nothing colored matches


def _norm(concept: str) -> str:
    c = concept.strip().lower().replace("_", " ").replace("-", " ")
    return ALIASES.get(c, c)


def _variants(concept: str) -> list[str]:
    """Normalized lookup candidates: lowercased, article-stripped, and de-pluralized,
    so LLM-named 'the clouds'/'raindrops'/'berries' resolve to cloud/raindrop/berry."""
    c = concept.strip().lower().replace("_", " ").replace("-", " ")
    out = [c]
    for art in ("the ", "a ", "an "):
        if c.startswith(art):
            out.append(c[len(art) :])
    base = out[-1]
    # English plurals are ambiguous (trees->tree, boxes->box), so offer ALL forms
    # and let the first that matches a recipe win.
    if base.endswith("ies") and len(base) > 4:
        out.append(base[:-3] + "y")
    if base.endswith("es") and len(base) > 4:
        out.append(base[:-2])
    if base.endswith("s") and len(base) > 3:
        out.append(base[:-1])
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def compose(concept: str) -> tuple[Stroke, ...] | None:
    """Compose an icon from primitives, or None if there's no recipe. Precedence: the
    hand-built/JSON ICON_RECIPES first (bespoke art wins), then the parametric FAMILIES
    (the scalable colored-cartoon corpus). Both try article/plural variants so common LLM
    phrasings ('the clouds', 'raindrops') still hit the visual language."""
    from engine import families

    variants = _variants(concept)
    for v in variants:  # 1-2. hand core + cartoon_recipes.json (colored, bespoke)
        recipe = ICON_RECIPES.get(ALIASES.get(v, v))
        if recipe is not None:
            return render_recipe(recipe) or None
    for v in variants:  # 3. the colored family corpus (beats uncolored mono)
        recipe = families.compose_family(v)
        if recipe is not None:
            return render_recipe(recipe) or None
    for v in variants:  # 4. the mono long-tail fallback
        recipe = _MONO_RECIPES.get(v)
        if recipe is not None:
            return render_recipe(recipe) or None
    return None


def known() -> list[str]:
    from engine import families

    return sorted(set(ICON_RECIPES) | set(families.CONCEPT_FAMILIES) | set(_MONO_RECIPES))
