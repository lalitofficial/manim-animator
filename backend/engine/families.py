"""Parametric icon FAMILIES — how the composed visual language scales to thousands.

A hand-built recipe (icons.py) is one composition. A FAMILY is a *generator* of
compositions: `quadruped(body, ear, tail, …)` emits cat / dog / cow / lion / fox from
parameters, every one a fully composed, multi-color, FILLED cartoon (never a flat
flood-filled line-icon). Coverage then scales as a one-line DATA table — `"cat":
("quad", {...})` — not as fresh geometry per concept. This is the "a workflow can
mass-author them" promise made concrete: ~20 families × a concept table = thousands of
deterministic cartoon drawables, with the hand-built core (icons.ICON_RECIPES) still
overriding the concepts that deserve bespoke art.

Each family returns a recipe dict `{"parts": [...]}` the icons.py interpreter renders.
Parts are listed BACK-TO-FRONT (far legs → body → head → details) so z-order reads right.
Authored in the same ~2-unit origin box; drawing.py scales to the requested size.
"""

from __future__ import annotations

import math
from collections.abc import Callable

# A small, friendly cartoon palette so concepts that don't pin a color still look right.
_SKIN = "#f4c08a"
_DARK = "#3a3a3a"


def _eye(x: float, y: float, r: float = 0.04, line: str = _DARK) -> dict:
    return {"prim": "circle", "at": [x, y], "r": r, "fill": line, "stroke": line}


# --------------------------------------------------------------------------- #
# Animals
# --------------------------------------------------------------------------- #
def quadruped(
    body: str,
    line: str,
    ear: str = "round",
    tail: str = "up",
    belly: str | None = None,
    horns: bool = False,
    snout: str | None = None,
) -> dict:
    """A side-view four-legged animal: cat/dog/cow/horse/pig/lion/fox/bear…"""
    p: list[dict] = []
    # far legs (behind body) — drawn first, slightly darker reads as depth
    for x in (-0.3, 0.26):
        p.append(
            {"prim": "rect", "at": [x, -0.52], "w": 0.13, "h": 0.42, "fill": body, "stroke": line}
        )
    # tail (behind body)
    if tail == "up":
        p.append({"prim": "line", "at": [-0.52, 0.05], "to": [-0.28, 0.35], "stroke": line})
    elif tail == "down":
        p.append({"prim": "line", "at": [-0.52, -0.05], "to": [-0.32, -0.13], "stroke": line})
    elif tail == "puff":
        p.append(
            {
                "prim": "circle",
                "at": [-0.66, 0.12],
                "r": 0.16,
                "fill": belly or body,
                "stroke": line,
            }
        )
    # body
    p.append(
        {
            "prim": "ellipse",
            "at": [-0.05, -0.05],
            "rx": 0.52,
            "ry": 0.34,
            "fill": body,
            "stroke": line,
        }
    )
    # near legs
    for x in (-0.36, 0.2):
        p.append(
            {"prim": "rect", "at": [x, -0.52], "w": 0.13, "h": 0.42, "fill": body, "stroke": line}
        )
    # head
    p.append({"prim": "circle", "at": [0.56, 0.2], "r": 0.31, "fill": body, "stroke": line})
    # ears
    if ear == "round":
        p.append({"prim": "circle", "at": [0.4, 0.48], "r": 0.11, "fill": body, "stroke": line})
        p.append({"prim": "circle", "at": [0.72, 0.48], "r": 0.11, "fill": body, "stroke": line})
    elif ear == "point":
        p.append(
            {
                "prim": "triangle",
                "at": [0.4, 0.5],
                "w": 0.2,
                "h": 0.24,
                "fill": body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "triangle",
                "at": [0.72, 0.5],
                "w": 0.2,
                "h": 0.24,
                "fill": body,
                "stroke": line,
            }
        )
    elif ear == "long":
        p.append(
            {
                "prim": "ellipse",
                "at": [0.42, 0.56],
                "rx": 0.07,
                "ry": 0.2,
                "fill": body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "ellipse",
                "at": [0.7, 0.56],
                "rx": 0.07,
                "ry": 0.2,
                "fill": body,
                "stroke": line,
            }
        )
    if horns:
        p.append(
            {
                "prim": "triangle",
                "at": [0.42, 0.52],
                "w": 0.1,
                "h": 0.16,
                "fill": "#e8d8b0",
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "triangle",
                "at": [0.7, 0.52],
                "w": 0.1,
                "h": 0.16,
                "fill": "#e8d8b0",
                "stroke": line,
            }
        )
    # snout + eye
    p.append(
        {
            "prim": "circle",
            "at": [0.8, 0.12],
            "r": 0.13,
            "fill": snout or belly or body,
            "stroke": line,
        }
    )
    p.append(_eye(0.62, 0.28, 0.04, line))
    return {"parts": p}


def bird(
    body: str, line: str, belly: str | None = None, beak: str = "#f5a623", tall: bool = False
) -> dict:
    """A round little bird: robin/duck/chick/owl/penguin (tall)."""
    p: list[dict] = []
    if tall:
        p.append(
            {
                "prim": "ellipse",
                "at": [0.0, -0.1],
                "rx": 0.42,
                "ry": 0.55,
                "fill": body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "ellipse",
                "at": [0.0, -0.18],
                "rx": 0.27,
                "ry": 0.38,
                "fill": belly or "#fff",
                "stroke": line,
            }
        )
        hy = 0.5
    else:
        p.append(
            {
                "prim": "ellipse",
                "at": [0.0, -0.18],
                "rx": 0.5,
                "ry": 0.4,
                "fill": body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "ellipse",
                "at": [0.06, -0.22],
                "rx": 0.3,
                "ry": 0.27,
                "fill": belly or "#fff",
                "stroke": line,
            }
        )
        # wing
        p.append(
            {
                "prim": "ellipse",
                "at": [-0.18, -0.12],
                "rx": 0.22,
                "ry": 0.16,
                "fill": body,
                "stroke": line,
            }
        )
        hy = 0.32
    p.append({"prim": "circle", "at": [0.12, hy], "r": 0.28, "fill": body, "stroke": line})
    p.append(
        {
            "prim": "triangle",
            "at": [0.42, hy - 0.02],
            "w": 0.18,
            "h": 0.16,
            "rot": -90,
            "fill": beak,
            "stroke": line,
        }
    )
    p.append(_eye(0.18, hy + 0.06, 0.045, line))
    # feet
    p.append({"prim": "line", "at": [-0.1, -0.5], "to": [0.0, -0.12], "stroke": beak})
    p.append({"prim": "line", "at": [0.12, -0.5], "to": [0.0, -0.12], "stroke": beak})
    return {"parts": p}


def fish(body: str, line: str, belly: str | None = None, big: bool = False) -> dict:
    """A side-view fish/shark/whale (big)."""
    rx, ry = (0.62, 0.42) if big else (0.5, 0.32)
    p: list[dict] = [
        {
            "prim": "triangle",
            "at": [-0.55, 0.0],
            "w": 0.4,
            "h": 0.5,
            "rot": -90,
            "fill": body,
            "stroke": line,
        },
        {"prim": "ellipse", "at": [0.05, 0.0], "rx": rx, "ry": ry, "fill": body, "stroke": line},
    ]
    if belly:
        p.append(
            {
                "prim": "arc",
                "at": [0.05, -0.12],
                "r": rx * 0.8,
                "a0": 200,
                "a1": 340,
                "stroke": line,
            }
        )
    p.append(
        {"prim": "triangle", "at": [0.1, 0.42], "w": 0.22, "h": 0.16, "fill": body, "stroke": line}
    )
    p.append(_eye(0.42, 0.06, 0.05, line))
    return {"parts": p}


def bug(
    body: str, line: str, wings: bool = False, spots: str | None = None, legs: bool = True
) -> dict:
    """A round bug: ladybug/beetle/bee (spots), butterfly (wings)."""
    p: list[dict] = []
    if legs and not wings:  # winged bugs (butterfly/dragonfly/moth) don't show walking legs
        for x in (-0.2, 0.0, 0.2):
            p.append({"prim": "line", "at": [x, -0.32], "to": [-0.18, -0.18], "stroke": line})
            p.append({"prim": "line", "at": [x, -0.32], "to": [0.18, -0.18], "stroke": line})
    if wings:
        p.append(
            {
                "prim": "ellipse",
                "at": [-0.34, 0.1],
                "rx": 0.34,
                "ry": 0.42,
                "fill": body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "ellipse",
                "at": [0.34, 0.1],
                "rx": 0.34,
                "ry": 0.42,
                "fill": spots or body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "ellipse",
                "at": [0.0, -0.05],
                "rx": 0.1,
                "ry": 0.42,
                "fill": line,
                "stroke": line,
            }
        )
        return {"parts": p}
    p.append({"prim": "circle", "at": [0.0, 0.0], "r": 0.46, "fill": body, "stroke": line})
    if spots:
        p.append({"prim": "line", "at": [0.0, 0.46], "to": [0.0, -0.92], "stroke": line})
        for sx, sy in ((-0.2, 0.12), (0.2, 0.12), (-0.16, -0.2), (0.16, -0.2)):
            p.append({"prim": "circle", "at": [sx, sy], "r": 0.07, "fill": spots, "stroke": spots})
    p.append({"prim": "circle", "at": [0.0, 0.5], "r": 0.18, "fill": line, "stroke": line})
    return {"parts": p}


# --------------------------------------------------------------------------- #
# Plants & food
# --------------------------------------------------------------------------- #
def fruit(body: str, line: str, leaf: bool = True, shape: str = "round", stem: bool = True) -> dict:
    """Round/oval fruit: apple/orange/cherry/peach/pear (oval)."""
    p: list[dict] = []
    if stem:
        p.append({"prim": "line", "at": [0.0, 0.45], "to": [0.08, 0.27], "stroke": "#6e4a2b"})
    if leaf:
        p.append(
            {
                "prim": "ellipse",
                "at": [0.22, 0.62],
                "rx": 0.16,
                "ry": 0.08,
                "rot": 20,
                "fill": "#5bb86a",
                "stroke": "#3f9150",
            }
        )
    if shape == "pear":
        p.append({"prim": "circle", "at": [0.0, -0.2], "r": 0.42, "fill": body, "stroke": line})
        p.append(
            {
                "prim": "ellipse",
                "at": [0.0, 0.28],
                "rx": 0.26,
                "ry": 0.3,
                "fill": body,
                "stroke": line,
            }
        )
    else:
        p.append({"prim": "circle", "at": [0.0, 0.05], "r": 0.46, "fill": body, "stroke": line})
    return {"parts": p}


def tree_family(foliage: str, line: str, trunk: str = "#8a5a2b", kind: str = "round") -> dict:
    """Tree variants: round (oak), pine (triangles), palm (fronds)."""
    tl = "#5e3c1a"
    p: list[dict] = [
        {"prim": "rect", "at": [0.0, -0.55], "w": 0.18, "h": 0.7, "fill": trunk, "stroke": tl}
    ]
    if kind == "pine":
        for y, w in ((0.55, 0.7), (0.25, 0.9), (-0.05, 1.1)):
            p.insert(
                0,
                {
                    "prim": "triangle",
                    "at": [0.0, y],
                    "w": w,
                    "h": 0.55,
                    "fill": foliage,
                    "stroke": line,
                },
            )
    elif kind == "palm":
        for a in (-60, -25, 25, 60, 0):
            p.append(
                {
                    "prim": "ellipse",
                    "at": [0.22 * math.sin(math.radians(a)), 0.5],
                    "rx": 0.34,
                    "ry": 0.1,
                    "rot": a,
                    "fill": foliage,
                    "stroke": line,
                }
            )
    else:
        p.append(
            {
                "prim": "blob",
                "at": [0.0, 0.28],
                "r": 0.56,
                "bumps": 7,
                "jitter": 0.22,
                "fill": foliage,
                "stroke": line,
            }
        )
    return {"parts": p}


def round_food(body: str, line: str, leaf: bool = False, ridges: str | None = None) -> dict:
    """Tomato/pumpkin/ball/balloon — a colored sphere with optional detail."""
    p: list[dict] = [{"prim": "circle", "at": [0.0, 0.0], "r": 0.48, "fill": body, "stroke": line}]
    if ridges:
        for x in (-0.22, 0.0, 0.22):
            p.append(
                {"prim": "arc", "at": [x, 0.0], "r": 0.46, "a0": 250, "a1": 290, "stroke": ridges}
            )
    if leaf:
        p.append(
            {
                "prim": "triangle",
                "at": [0.0, 0.5],
                "w": 0.22,
                "h": 0.16,
                "fill": "#5bb86a",
                "stroke": "#3f9150",
            }
        )
    return {"parts": p}


# --------------------------------------------------------------------------- #
# Vehicles & buildings
# --------------------------------------------------------------------------- #
def vehicle(body: str, line: str, kind: str = "car", roof: str | None = None) -> dict:
    """Wheeled vehicle: car/bus/truck — body + cabin + wheels + windows."""
    wheel, wl = "#33373d", "#1d2024"
    p: list[dict] = []
    if kind == "bus":
        p.append(
            {"prim": "rect", "at": [0.0, 0.05], "w": 1.5, "h": 0.7, "fill": body, "stroke": line}
        )
        for x in (-0.5, -0.18, 0.14, 0.46):
            p.append(
                {
                    "prim": "rect",
                    "at": [x, 0.14],
                    "w": 0.2,
                    "h": 0.24,
                    "fill": "#bfe3ff",
                    "stroke": line,
                }
            )
        wheels = (-0.5, 0.5)
    elif kind == "truck":
        p.append(
            {"prim": "rect", "at": [-0.3, 0.1], "w": 0.9, "h": 0.6, "fill": body, "stroke": line}
        )
        p.append(
            {
                "prim": "rect",
                "at": [0.55, -0.02],
                "w": 0.55,
                "h": 0.42,
                "fill": roof or body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "rect",
                "at": [0.6, 0.08],
                "w": 0.28,
                "h": 0.2,
                "fill": "#bfe3ff",
                "stroke": line,
            }
        )
        wheels = (-0.45, 0.55)
    else:  # car
        p.append(
            {
                "prim": "rounded_rect",
                "at": [0.0, -0.05],
                "w": 1.3,
                "h": 0.5,
                "r": 0.18,
                "fill": body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "rounded_rect",
                "at": [0.0, 0.28],
                "w": 0.7,
                "h": 0.42,
                "r": 0.16,
                "fill": roof or body,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "rect",
                "at": [0.0, 0.3],
                "w": 0.5,
                "h": 0.26,
                "fill": "#bfe3ff",
                "stroke": line,
            }
        )
        wheels = (-0.4, 0.4)
    for x in wheels:
        p.append({"prim": "circle", "at": [x, -0.34], "r": 0.2, "fill": wheel, "stroke": wl})
        p.append({"prim": "circle", "at": [x, -0.34], "r": 0.07, "fill": "#9aa0a6", "stroke": wl})
    return {"parts": p}


def building(
    body: str, line: str, roof: str | None = None, kind: str = "house", door: str = "#8a5a2b"
) -> dict:
    """house/school/shop/tower — wall + roof + door + windows."""
    p: list[dict] = []
    if kind == "tower":
        p.append(
            {"prim": "rect", "at": [0.0, -0.05], "w": 0.7, "h": 1.3, "fill": body, "stroke": line}
        )
        p.append(
            {
                "prim": "triangle",
                "at": [0.0, 0.78],
                "w": 0.85,
                "h": 0.4,
                "fill": roof or "#e2614b",
                "stroke": line,
            }
        )
        for y in (0.3, -0.05, -0.4):
            p.append(
                {
                    "prim": "rect",
                    "at": [0.0, y],
                    "w": 0.22,
                    "h": 0.22,
                    "fill": "#bfe3ff",
                    "stroke": line,
                }
            )
        return {"parts": p}
    p.append({"prim": "rect", "at": [0.0, -0.2], "w": 1.2, "h": 0.85, "fill": body, "stroke": line})
    p.append(
        {
            "prim": "triangle",
            "at": [0.0, 0.42],
            "w": 1.45,
            "h": 0.5,
            "fill": roof or "#e2614b",
            "stroke": line,
        }
    )
    p.append({"prim": "rect", "at": [0.0, -0.36], "w": 0.3, "h": 0.5, "fill": door, "stroke": line})
    for x in (-0.36, 0.36):
        p.append(
            {
                "prim": "rect",
                "at": [x, -0.05],
                "w": 0.26,
                "h": 0.26,
                "fill": "#bfe3ff",
                "stroke": line,
            }
        )
    return {"parts": p}


# --------------------------------------------------------------------------- #
# Sky & nature
# --------------------------------------------------------------------------- #
def celestial(body: str, line: str, kind: str = "planet", ring: str | None = None) -> dict:
    """planet/moon/comet — a colored disc with optional ring/craters/tail."""
    p: list[dict] = []
    if kind == "comet":
        p.append(
            {
                "prim": "triangle",
                "at": [-0.4, -0.1],
                "w": 0.4,
                "h": 0.7,
                "rot": 60,
                "fill": "#ffd98a",
                "stroke": "#e0a800",
            }
        )
    p.append({"prim": "circle", "at": [0.1, 0.1], "r": 0.4, "fill": body, "stroke": line})
    if kind == "moon":
        for cx, cy, r in ((0.0, 0.2, 0.08), (0.2, 0.0, 0.06), (0.08, -0.08, 0.05)):
            p.append({"prim": "circle", "at": [cx, cy], "r": r, "fill": line, "stroke": line})
    if ring or kind == "ringed":
        p.append(
            {
                "prim": "ellipse",
                "at": [0.1, 0.1],
                "rx": 0.62,
                "ry": 0.18,
                "rot": -18,
                "stroke": ring or "#caa46a",
            }
        )
    return {"parts": p}


def blobby(body: str, line: str, eyes: bool = True) -> dict:
    """A generic friendly blob with a face — for soft/abstract concepts (germ, cell, slime)."""
    p: list[dict] = [
        {
            "prim": "blob",
            "at": [0.0, 0.0],
            "r": 0.5,
            "bumps": 8,
            "jitter": 0.16,
            "fill": body,
            "stroke": line,
        }
    ]
    if eyes:
        p.append(_eye(-0.14, 0.08, 0.06, line))
        p.append(_eye(0.14, 0.08, 0.06, line))
        p.append(
            {"prim": "arc", "at": [0.0, -0.12], "r": 0.14, "a0": 200, "a1": 340, "stroke": line}
        )
    return {"parts": p}


# --------------------------------------------------------------------------- #
# Registry + the concept → (family, params) DATA table.
# --------------------------------------------------------------------------- #
FAMILIES: dict[str, Callable[..., dict]] = {
    "quad": quadruped,
    "bird": bird,
    "fish": fish,
    "bug": bug,
    "fruit": fruit,
    "tree": tree_family,
    "round_food": round_food,
    "vehicle": vehicle,
    "building": building,
    "celestial": celestial,
    "blob": blobby,
}

# Data table — one compact line per concept. This is the part a workflow mass-authors;
# every entry is GUARANTEED a composed, colored, filled cartoon because the family makes it.
CONCEPT_FAMILIES: dict[str, tuple[str, dict]] = {}


def _add(family: str, table: dict[str, dict]) -> None:
    for concept, params in table.items():
        CONCEPT_FAMILIES[concept] = (family, params)


_add(
    "quad",
    {
        "cat": {
            "body": "#f4a23f",
            "line": "#b86a1a",
            "ear": "point",
            "tail": "up",
            "belly": "#ffe0b0",
        },
        "dog": {
            "body": "#c98a4d",
            "line": "#8a5a2b",
            "ear": "round",
            "tail": "down",
            "belly": "#e8cba0",
        },
        "cow": {
            "body": "#f0ead8",
            "line": "#7a6a52",
            "ear": "round",
            "horns": True,
            "belly": "#d8c0a0",
        },
        "horse": {"body": "#a9743f", "line": "#6e4a2b", "ear": "point", "tail": "down"},
        "pig": {
            "body": "#f3a9c0",
            "line": "#cf6f93",
            "ear": "point",
            "tail": "puff",
            "snout": "#e98aae",
        },
        "sheep": {
            "body": "#f2efe9",
            "line": "#8a8378",
            "ear": "long",
            "tail": "puff",
            "belly": "#fff",
        },
        "lion": {
            "body": "#e0a23f",
            "line": "#a86a1a",
            "ear": "round",
            "tail": "puff",
            "belly": "#c98a2b",
        },
        "fox": {
            "body": "#ef8b3c",
            "line": "#b85a1a",
            "ear": "point",
            "tail": "puff",
            "belly": "#fff",
        },
        "bear": {
            "body": "#8a5a3a",
            "line": "#5e3c22",
            "ear": "round",
            "tail": "puff",
            "belly": "#b08a64",
        },
        "rabbit": {
            "body": "#e8e2da",
            "line": "#9a8f80",
            "ear": "long",
            "tail": "puff",
            "belly": "#fff",
        },
        "mouse": {"body": "#b8b0a4", "line": "#7a7264", "ear": "round", "tail": "down"},
        "tiger": {
            "body": "#f0922f",
            "line": "#a85a1a",
            "ear": "round",
            "tail": "down",
            "belly": "#fff",
        },
        "elephant": {"body": "#9aa0a6", "line": "#666c72", "ear": "round", "tail": "down"},
        "goat": {"body": "#e8e0d2", "line": "#8a8074", "ear": "long", "horns": True},
        "wolf": {
            "body": "#8d949c",
            "line": "#5a6068",
            "ear": "point",
            "tail": "down",
            "belly": "#c8ccd0",
        },
        "deer": {
            "body": "#bf8a55",
            "line": "#84582f",
            "ear": "long",
            "horns": True,
            "belly": "#e0c4a0",
        },
    },
)
_add(
    "bird",
    {
        "bird": {"body": "#e85d4a", "line": "#b03a28", "belly": "#ffd9a8"},
        "robin": {"body": "#7a5a3a", "line": "#52402a", "belly": "#e8703a"},
        "duck": {"body": "#f4d03f", "line": "#c79a1a", "belly": "#fff7d0", "beak": "#f5871f"},
        "chick": {"body": "#ffe066", "line": "#e0a800", "belly": "#fff2a8"},
        "owl": {"body": "#9a7a52", "line": "#6e5436", "belly": "#d8c4a0"},
        "penguin": {
            "body": "#2c3038",
            "line": "#15181d",
            "belly": "#fff",
            "tall": True,
            "beak": "#f5871f",
        },
        "chicken": {"body": "#f2efe9", "line": "#b85a3a", "belly": "#fff", "beak": "#f5871f"},
        "parrot": {"body": "#3fa46a", "line": "#2b7a4b", "belly": "#ffd23f", "beak": "#e0991b"},
    },
)
_add(
    "fish",
    {
        "fish": {"body": "#f5912f", "line": "#c06a1a", "belly": "#ffd9a8"},
        "shark": {"body": "#8d949c", "line": "#5a6068", "belly": "#dfe3e6", "big": True},
        "whale": {"body": "#5b8def", "line": "#2f6fd0", "belly": "#bcd3ff", "big": True},
        "goldfish": {"body": "#f5a623", "line": "#cf7f17"},
        "dolphin": {"body": "#7aa5d6", "line": "#4f78a8", "belly": "#dfeaf6", "big": True},
    },
)
_add(
    "bug",
    {
        "bee": {"body": "#ffd23f", "line": "#3a3a3a", "spots": "#3a3a3a", "wings": False},
        "ladybug": {"body": "#e2473b", "line": "#3a3a3a", "spots": "#3a3a3a"},
        "beetle": {"body": "#5b7a3a", "line": "#3a4a22"},
        "butterfly": {"body": "#ef6fb0", "line": "#c23f86", "spots": "#7a4fd6", "wings": True},
        "ant": {"body": "#7a4a2b", "line": "#4e2f1a"},
        "spider": {"body": "#3a3a3a", "line": "#1a1a1a"},
    },
)
_add(
    "fruit",
    {
        "apple": {"body": "#e2473b", "line": "#b0302a"},
        "orange": {"body": "#f5912f", "line": "#c06a1a", "leaf": True},
        "cherry": {"body": "#d22f4a", "line": "#a01f38"},
        "peach": {"body": "#ffb27a", "line": "#e0824a"},
        "pear": {"body": "#bfd23f", "line": "#8aa01a", "shape": "pear"},
        "lemon": {"body": "#f5d423", "line": "#c0a217", "leaf": False},
        "lime": {"body": "#9fd23f", "line": "#6fa01a", "leaf": False},
        "plum": {"body": "#8a4fd6", "line": "#5f2fa0"},
    },
)
_add(
    "round_food",
    {
        "tomato": {"body": "#e2473b", "line": "#b0302a", "leaf": True},
        "pumpkin": {"body": "#f5871f", "line": "#c06a1a", "leaf": True, "ridges": "#c06a1a"},
        "ball": {"body": "#e2473b", "line": "#b0302a", "ridges": "#fff"},
        "balloon": {"body": "#e2473b", "line": "#b0302a"},
        "planet ball": {"body": "#5b8def", "line": "#2f6fd0"},
        "orange fruit": {"body": "#f5912f", "line": "#c06a1a"},
        "coconut": {"body": "#8a5a3a", "line": "#5e3c22"},
    },
)
_add(
    "tree",
    {
        "tree": {"foliage": "#3fa46a", "line": "#2b7a4b", "kind": "round"},
        "oak": {"foliage": "#4a9e5a", "line": "#2b7a4b", "kind": "round"},
        "pine": {"foliage": "#2f8a52", "line": "#1f6a3a", "kind": "pine"},
        "palm": {"foliage": "#3fa46a", "line": "#2b7a4b", "kind": "palm"},
        "bush": {"foliage": "#4aa05a", "line": "#2b7a4b", "kind": "round", "trunk": "#4aa05a"},
    },
)
_add(
    "vehicle",
    {
        "car": {"body": "#e2473b", "line": "#b0302a", "kind": "car", "roof": "#f06a5e"},
        "bus": {"body": "#f5b800", "line": "#c08e00", "kind": "bus"},
        "truck": {"body": "#3f7ad6", "line": "#2b56a0", "kind": "truck", "roof": "#5b8def"},
        "taxi": {"body": "#f5c518", "line": "#c09a00", "kind": "car", "roof": "#ffd84a"},
        "van": {"body": "#5bbf6a", "line": "#3f9150", "kind": "truck"},
    },
)
_add(
    "building",
    {
        "house": {"body": "#ffcaa8", "line": "#d68a5e", "kind": "house", "roof": "#e2614b"},
        "home": {"body": "#ffcaa8", "line": "#d68a5e", "kind": "house", "roof": "#e2614b"},
        "school": {"body": "#f5d49a", "line": "#c79a4a", "kind": "house", "roof": "#b03a28"},
        "shop": {"body": "#bfe3ff", "line": "#5f9fd0", "kind": "house", "roof": "#3f7ad6"},
        "tower": {"body": "#dfe3e6", "line": "#9aa0a6", "kind": "tower", "roof": "#e2614b"},
        "castle": {"body": "#cfd4d8", "line": "#8a9098", "kind": "tower", "roof": "#5b6def"},
    },
)
_add(
    "celestial",
    {
        "planet": {"body": "#5b8def", "line": "#2f6fd0", "kind": "ringed", "ring": "#caa46a"},
        "earth": {"body": "#4a9ed6", "line": "#2f6fa8", "kind": "planet"},
        "mars": {"body": "#d2603a", "line": "#a0401a", "kind": "planet"},
        "moon": {"body": "#dfe3e6", "line": "#9aa0a6", "kind": "moon"},
        "comet": {"body": "#bcd3ff", "line": "#7aa5d6", "kind": "comet"},
        "asteroid": {"body": "#9aa0a6", "line": "#666c72", "kind": "moon"},
        "saturn": {"body": "#e8d49a", "line": "#c0a460", "kind": "ringed", "ring": "#caa46a"},
    },
)
_add(
    "blob",
    {  # cell/virus/pathogen live in the dedicated science families below (richer art)
        "germ": {"body": "#8acb5a", "line": "#5a9a2b"},
        "bacteria": {"body": "#bf8acb", "line": "#8a5a9a"},
        "slime": {"body": "#5bd6a0", "line": "#2fa070"},
        "amoeba": {"body": "#c0d65b", "line": "#90a02b"},
    },
)


# --- second wave: densify the families (mostly color/param variants of the above) ----- #
_add(
    "quad",
    {
        "panda": {
            "body": "#f4f4f4",
            "line": "#3a3a3a",
            "ear": "round",
            "tail": "puff",
            "snout": "#3a3a3a",
        },
        "zebra": {"body": "#f4f4f4", "line": "#2a2a2a", "ear": "point", "tail": "down"},
        "giraffe": {
            "body": "#e8c15a",
            "line": "#b8902b",
            "ear": "point",
            "horns": True,
            "belly": "#f0d88a",
        },
        "monkey": {
            "body": "#9a6a3a",
            "line": "#6e4a22",
            "ear": "round",
            "tail": "down",
            "snout": "#d8b088",
        },
        "koala": {"body": "#a8b0b6", "line": "#6e767c", "ear": "round", "snout": "#7a8288"},
        "hippo": {"body": "#a98ab0", "line": "#7a5a82", "ear": "round", "tail": "down"},
        "rhino": {"body": "#9aa0a6", "line": "#666c72", "ear": "point", "horns": True},
        "camel": {"body": "#cf9a5a", "line": "#9a6a2b", "ear": "round", "tail": "down"},
        "kangaroo": {
            "body": "#c98a5a",
            "line": "#94582b",
            "ear": "long",
            "tail": "up",
            "belly": "#e8c4a0",
        },
        "squirrel": {
            "body": "#b08050",
            "line": "#7a5430",
            "ear": "point",
            "tail": "puff",
            "belly": "#e8d0b0",
        },
        "raccoon": {
            "body": "#8d949c",
            "line": "#3a3a3a",
            "ear": "point",
            "tail": "down",
            "snout": "#dfe3e6",
        },
        "llama": {"body": "#efe6d4", "line": "#9a8f74", "ear": "point", "tail": "puff"},
        "leopard": {
            "body": "#e8b24a",
            "line": "#8a5a1a",
            "ear": "round",
            "tail": "down",
            "belly": "#f0d488",
        },
        "donkey": {"body": "#b0b4b8", "line": "#74787c", "ear": "long", "tail": "down"},
        "goat kid": {"body": "#e8e0d2", "line": "#8a8074", "ear": "long", "horns": True},
        "puppy": {
            "body": "#d8a868",
            "line": "#9a6a2b",
            "ear": "long",
            "tail": "up",
            "belly": "#f0d4a8",
        },
        "kitten": {
            "body": "#a8a8a8",
            "line": "#6a6a6a",
            "ear": "point",
            "tail": "up",
            "belly": "#d8d8d8",
        },
        "hedgehog": {
            "body": "#8a6a4a",
            "line": "#5a4430",
            "ear": "round",
            "tail": "puff",
            "snout": "#d8b890",
        },
        "bull": {"body": "#7a5a3a", "line": "#4e3a22", "ear": "round", "horns": True},
        "ox": {"body": "#9a7a5a", "line": "#6a4e36", "ear": "round", "horns": True},
    },
)
_add(
    "bird",
    {
        "eagle": {"body": "#6e4a2b", "line": "#4a3018", "belly": "#e8d4a8", "beak": "#f5b800"},
        "crow": {"body": "#2c3038", "line": "#15181d", "belly": "#3a3f48"},
        "dove": {"body": "#f2f2f2", "line": "#b0b4b8", "belly": "#fff"},
        "swan": {
            "body": "#f7f7f7",
            "line": "#b8bcc0",
            "belly": "#fff",
            "tall": True,
            "beak": "#f5871f",
        },
        "flamingo": {"body": "#f48fb0", "line": "#cf6f93", "belly": "#ffd0e0", "tall": True},
        "peacock": {"body": "#1f8a8a", "line": "#14605f", "belly": "#3fb0c0"},
        "turkey": {"body": "#8a5a3a", "line": "#5e3c22", "belly": "#c08a5a", "beak": "#e2473b"},
        "sparrow": {"body": "#a98a5a", "line": "#74582f", "belly": "#e0d0b0"},
        "toucan": {"body": "#2c3038", "line": "#15181d", "belly": "#fff", "beak": "#f5871f"},
        "ostrich": {"body": "#6e5a44", "line": "#48382a", "belly": "#d8c4a0", "tall": True},
    },
)
_add(
    "fish",
    {
        "tuna": {"body": "#5b7a9a", "line": "#3a5470", "belly": "#bcd0e0", "big": True},
        "salmon": {"body": "#ef8b7a", "line": "#c05a48", "belly": "#ffd0c4"},
        "clownfish": {"body": "#f5871f", "line": "#c06a1a", "belly": "#fff"},
        "pufferfish": {"body": "#e8c15a", "line": "#b8902b"},
        "swordfish": {"body": "#6a8ab0", "line": "#456487", "big": True},
    },
)
_add(
    "bug",
    {
        "dragonfly": {"body": "#3fb0a0", "line": "#2b7a70", "wings": True, "spots": "#9ad0c8"},
        "moth": {"body": "#b0a080", "line": "#7a6e52", "wings": True, "spots": "#d8ccb0"},
        "grasshopper": {"body": "#7aae3a", "line": "#52801a"},
        "firefly": {"body": "#5b6a3a", "line": "#3a4422", "spots": "#ffe066"},
        "wasp": {"body": "#ffc23f", "line": "#3a3a3a", "spots": "#3a3a3a"},
        "caterpillar": {"body": "#8acb5a", "line": "#5a9a2b", "spots": "#5a9a2b"},
    },
)
_add(
    "fruit",
    {
        "strawberry": {"body": "#e2384a", "line": "#b01f30", "shape": "pear"},
        "apricot": {"body": "#f5b15a", "line": "#c0822b"},
        "fig": {"body": "#8a5fa0", "line": "#5f3a70", "shape": "pear"},
        "pomegranate": {"body": "#d2384a", "line": "#a01f30"},
        "mango": {"body": "#f5b32f", "line": "#c0801a"},
        "tangerine": {"body": "#f5871f", "line": "#c06a1a", "leaf": True},
    },
)
_add(
    "round_food",
    {
        "watermelon": {"body": "#3fa46a", "line": "#2b7a4b", "ridges": "#2b7a4b"},
        "melon": {"body": "#bfd28a", "line": "#8aa04a"},
        "potato": {"body": "#cf9a5a", "line": "#9a6a2b"},
        "onion": {"body": "#e8c4d0", "line": "#b8849a", "ridges": "#b8849a", "leaf": True},
        "soccer ball": {"body": "#f4f4f4", "line": "#2a2a2a", "ridges": "#2a2a2a"},
        "basketball": {"body": "#f5871f", "line": "#a85a1a", "ridges": "#a85a1a"},
        "globe": {"body": "#4a9ed6", "line": "#2f6fa8", "ridges": "#2f6fa8"},
        "cabbage": {"body": "#7abf6a", "line": "#4f9150", "ridges": "#4f9150"},
    },
)
_add(
    "vehicle",
    {
        "ambulance": {"body": "#f4f4f4", "line": "#c03030", "kind": "truck", "roof": "#fff"},
        "firetruck": {"body": "#e2473b", "line": "#a01f30", "kind": "truck", "roof": "#c0302a"},
        "tractor": {"body": "#5bbf6a", "line": "#3f9150", "kind": "truck", "roof": "#3f9150"},
        "jeep": {"body": "#7a8a4a", "line": "#54602f", "kind": "truck"},
        "police car": {"body": "#3a5fae", "line": "#27407a", "kind": "car", "roof": "#f4f4f4"},
    },
)
_add(
    "building",
    {
        "church": {"body": "#e8dcc0", "line": "#b09a6a", "kind": "tower", "roof": "#8a5a3a"},
        "barn": {"body": "#c0392b", "line": "#8a2418", "kind": "house", "roof": "#7a1f14"},
        "hospital": {"body": "#f4f4f4", "line": "#b03030", "kind": "house", "roof": "#e2473b"},
        "factory": {"body": "#9aa0a6", "line": "#666c72", "kind": "house", "roof": "#666c72"},
        "library": {"body": "#d8c49a", "line": "#a8884a", "kind": "house", "roof": "#8a5a3a"},
        "skyscraper": {"body": "#7aa5d6", "line": "#4f78a8", "kind": "tower", "roof": "#4f78a8"},
    },
)
_add(
    "celestial",
    {
        "jupiter": {"body": "#d8a86a", "line": "#a8783a", "kind": "ringed", "ring": "#caa46a"},
        "venus": {"body": "#e8c47a", "line": "#b8943a", "kind": "planet"},
        "mercury": {"body": "#b0a89a", "line": "#7a7264", "kind": "moon"},
        "neptune": {"body": "#3f6ad6", "line": "#2b46a0", "kind": "planet"},
        "uranus": {"body": "#7ad6d6", "line": "#3fa0a0", "kind": "planet"},
        "pluto": {"body": "#cf9a7a", "line": "#9a6a4a", "kind": "moon"},
        "sun star": {"body": "#ffd23f", "line": "#e0991b", "kind": "planet"},
    },
)
_add(
    "blob",
    {
        "microbe": {"body": "#7acb8a", "line": "#4a9a5a"},
        "fungus": {"body": "#d6a05b", "line": "#a0702b"},
        "mold": {"body": "#9abf5b", "line": "#6a902b"},
        "microorganism": {"body": "#8acbcf", "line": "#4a9a9f"},
    },
)

# Aliases — synonyms/spellings that should resolve to a family concept.
_FAMILY_ALIASES = {
    "kitty": "cat",
    "puppy dog": "dog",
    "doggy": "dog",
    "bunny": "rabbit",
    "piggy": "pig",
    "birdie": "bird",
    "honeybee": "bee",
    "lady bug": "ladybug",
    "auto": "car",
    "automobile": "car",
    "lorry": "truck",
    "planet earth": "earth",
    "the moon": "moon",
    "red planet": "mars",
    "apple fruit": "apple",
    "house home": "house",
}
for _a, _t in _FAMILY_ALIASES.items():
    if _t in CONCEPT_FAMILIES:
        CONCEPT_FAMILIES[_a] = CONCEPT_FAMILIES[_t]


# --------------------------------------------------------------------------- #
# Science — the education domain (BioIcons proved too messy to ingest cleanly:
# clip-paths + even-odd holes + specialized names; composed families are clean,
# consistent, and named with the COMMON nouns lessons actually use). NOTEBOOK §B10.
# --------------------------------------------------------------------------- #
def cell(membrane="#bcdfff", line="#5b8fd0", nucleus="#7a5fd0", organelle="#5bd6a0") -> dict:
    """A cell: wobbly membrane + nucleus (+ nucleolus) + a few organelles."""
    p = [
        {
            "prim": "blob",
            "at": [0, 0],
            "r": 0.56,
            "bumps": 9,
            "jitter": 0.07,
            "fill": membrane,
            "stroke": line,
        }
    ]
    if organelle:
        for ox, oy, rot in ((-0.28, 0.2, 30), (0.32, -0.2, -20), (-0.18, -0.3, 60)):
            p.append(
                {
                    "prim": "ellipse",
                    "at": [ox, oy],
                    "rx": 0.11,
                    "ry": 0.05,
                    "rot": rot,
                    "fill": organelle,
                    "stroke": line,
                }
            )
    p.append({"prim": "circle", "at": [0.06, 0.02], "r": 0.21, "fill": nucleus, "stroke": line})
    p.append({"prim": "circle", "at": [0.06, 0.02], "r": 0.08, "fill": line, "stroke": line})
    return {"parts": p}


def atom(core="#ff8a5b", line="#c85a2b", rings=3, electron="#3f7ad6") -> dict:
    """A nucleus + elliptical orbits with electrons (atom/molecule/ion)."""
    p = []
    for i in range(rings):
        p.append(
            {
                "prim": "ellipse",
                "at": [0, 0],
                "rx": 0.58,
                "ry": 0.2,
                "rot": i * 180 / rings,
                "stroke": "#9aa6b8",
            }
        )
    p.append({"prim": "circle", "at": [0, 0], "r": 0.17, "fill": core, "stroke": line})
    for i in range(rings):
        a = math.radians(i * 180 / rings)
        p.append(
            {
                "prim": "circle",
                "at": [0.58 * math.cos(a), 0.58 * math.sin(a)],
                "r": 0.07,
                "fill": electron,
                "stroke": line,
            }
        )
    return {"parts": p}


def virus(body="#ef6f6f", line="#c23f3f", spike="#c23f3f", n=11) -> dict:
    """A round capsid with radiating spike proteins (virus/pathogen)."""
    p = []
    for i in range(n):
        a = math.radians(i * 360 / n)
        x, y = 0.42 * math.cos(a), 0.42 * math.sin(a)
        kx, ky = 0.62 * math.cos(a), 0.62 * math.sin(a)
        p.append({"prim": "line", "at": [x, y], "to": [kx - x, ky - y], "stroke": spike})
        p.append({"prim": "circle", "at": [kx, ky], "r": 0.07, "fill": body, "stroke": line})
    p.append({"prim": "circle", "at": [0, 0], "r": 0.44, "fill": body, "stroke": line})
    p.append({"prim": "circle", "at": [0, 0], "r": 0.18, "fill": line, "stroke": line})
    return {"parts": p}


def dna(s1="#3f7ad6", s2="#ef6f6f", line="#2b4a7a") -> dict:
    """A double helix: two sine strands + base-pair rungs."""
    p = []
    a = [[0.32 * math.sin(i / 20 * math.pi * 3), (i / 20 - 0.5) * 1.7] for i in range(21)]
    b = [[-x, y] for x, y in a]
    p.append({"prim": "polyline", "points": a, "stroke": s1})
    p.append({"prim": "polyline", "points": b, "stroke": s2})
    for i in range(2, 19, 3):
        x, y = a[i]
        p.insert(0, {"prim": "line", "at": [-x, y], "to": [2 * x, 0], "stroke": line})
    for i in range(0, 21, 2):  # nucleotide nodes (filled bases) — color + a real fill
        x, y = a[i]
        p.append({"prim": "circle", "at": [x, y], "r": 0.06, "fill": s1, "stroke": s1})
        p.append({"prim": "circle", "at": [-x, y], "r": 0.06, "fill": s2, "stroke": s2})
    return {"parts": p}


def neuron(body="#f5c06a", line="#c8902b", nucleus="#c8902b") -> dict:
    """A nerve cell: soma + dendrites + a long axon to a terminal."""
    p = []
    for ang in (120, 150, 205, 240):
        ar = math.radians(ang)
        p.append(
            {
                "prim": "line",
                "at": [0, 0],
                "to": [0.62 * math.cos(ar), 0.62 * math.sin(ar)],
                "stroke": line,
            }
        )
    p.append({"prim": "line", "at": [0.28, 0], "to": [0.6, -0.06], "stroke": line})
    p.append({"prim": "circle", "at": [0.92, -0.08], "r": 0.07, "fill": body, "stroke": line})
    p.append(
        {
            "prim": "blob",
            "at": [0, 0],
            "r": 0.32,
            "bumps": 6,
            "jitter": 0.14,
            "fill": body,
            "stroke": line,
        }
    )
    p.append({"prim": "circle", "at": [0, 0], "r": 0.1, "fill": nucleus, "stroke": line})
    return {"parts": p}


def vessel(kind="beaker", glass="#d4ecf8", liquid="#5bbfe0", line="#6f9fbf") -> dict:
    """Lab glassware: beaker / flask / test_tube with liquid."""
    p = []
    if kind == "flask":
        p.append(
            {
                "prim": "polyline",
                "points": [
                    [-0.12, 0.6],
                    [-0.12, 0.2],
                    [-0.5, -0.5],
                    [0.5, -0.5],
                    [0.12, 0.2],
                    [0.12, 0.6],
                ],
                "closed": True,
                "fill": glass,
                "stroke": line,
            }
        )
        p.append(
            {
                "prim": "polyline",
                "points": [[-0.32, -0.2], [-0.5, -0.5], [0.5, -0.5], [0.32, -0.2]],
                "closed": True,
                "fill": liquid,
                "stroke": line,
            }
        )
    elif kind == "test_tube":
        p.append(
            {
                "prim": "rounded_rect",
                "at": [0, -0.02],
                "w": 0.42,
                "h": 1.2,
                "r": 0.2,
                "fill": glass,
                "stroke": line,
            }
        )
        p.append(
            {"prim": "rect", "at": [0, -0.32], "w": 0.38, "h": 0.5, "fill": liquid, "stroke": line}
        )
    else:  # beaker
        p.append({"prim": "rect", "at": [0, 0], "w": 0.85, "h": 1.0, "fill": glass, "stroke": line})
        p.append(
            {"prim": "rect", "at": [0, -0.22], "w": 0.83, "h": 0.55, "fill": liquid, "stroke": line}
        )
        p.append({"prim": "line", "at": [-0.42, 0.5], "to": [0.12, 0.06], "stroke": line})  # spout
    return {"parts": p}


def bulb(glass="#fff3b0", line="#d9a900", base="#9aa0a6") -> dict:
    """A light bulb (energy/idea/electricity)."""
    return {
        "parts": [
            {"prim": "circle", "at": [0, 0.12], "r": 0.42, "fill": glass, "stroke": line},
            {
                "prim": "rect",
                "at": [0, -0.42],
                "w": 0.34,
                "h": 0.3,
                "fill": base,
                "stroke": "#666c72",
            },
            {
                "prim": "polyline",
                "points": [[-0.12, 0.12], [0, 0.28], [0.12, 0.12]],
                "stroke": line,
            },
        ]
    }


def magnet(body="#e2473b", line="#a01f30", tip="#dfe3e6") -> dict:
    """A horseshoe magnet."""
    return {
        "parts": [
            {"prim": "arc", "at": [0, 0.05], "r": 0.45, "a0": 0, "a1": 180, "stroke": line},
            {"prim": "rect", "at": [-0.45, -0.3], "w": 0.18, "h": 0.5, "fill": tip, "stroke": line},
            {"prim": "rect", "at": [0.45, -0.3], "w": 0.18, "h": 0.5, "fill": body, "stroke": line},
            {
                "prim": "rect",
                "at": [-0.36, 0.05],
                "w": 0.72,
                "h": 0.16,
                "fill": body,
                "stroke": line,
            },
        ]
    }


def organ(kind="heart", body="#e2616f", line="#b03a4a") -> dict:
    """Soft anatomy: lungs / brain / bone (heart has a hand recipe)."""
    if kind == "lungs":
        p = [{"prim": "line", "at": [0, 0.5], "to": [0, -0.7], "stroke": "#b09a6a"}]
        for sx in (-1, 1):
            p.append(
                {
                    "prim": "blob",
                    "at": [sx * 0.28, -0.1],
                    "r": 0.34,
                    "bumps": 5,
                    "jitter": 0.12,
                    "fill": body,
                    "stroke": line,
                }
            )
        return {"parts": p}
    if kind == "brain":
        p = [
            {
                "prim": "blob",
                "at": [0, 0],
                "r": 0.52,
                "bumps": 11,
                "jitter": 0.22,
                "fill": body,
                "stroke": line,
            }
        ]
        for ox in (-0.2, 0.1):
            p.append(
                {"prim": "arc", "at": [ox, 0.05], "r": 0.18, "a0": 200, "a1": 360, "stroke": line}
            )
        return {"parts": p}
    # bone
    return {
        "parts": [
            {"prim": "polyline", "points": [[-0.5, 0], [0.5, 0]], "stroke": line},
            {"prim": "circle", "at": [-0.5, 0.12], "r": 0.13, "fill": body, "stroke": line},
            {"prim": "circle", "at": [-0.5, -0.12], "r": 0.13, "fill": body, "stroke": line},
            {"prim": "circle", "at": [0.5, 0.12], "r": 0.13, "fill": body, "stroke": line},
            {"prim": "circle", "at": [0.5, -0.12], "r": 0.13, "fill": body, "stroke": line},
            {"prim": "rect", "at": [0, 0], "w": 1.0, "h": 0.18, "fill": body, "stroke": body},
        ]
    }


FAMILIES.update(
    {
        "cell": cell,
        "atom": atom,
        "virus": virus,
        "dna": dna,
        "neuron": neuron,
        "vessel": vessel,
        "bulb": bulb,
        "magnet": magnet,
        "organ": organ,
    }
)
_add(
    "cell",
    {
        "cell": {},
        "animal cell": {},
        "plant cell": {"membrane": "#cfeeb0", "line": "#6fa03f", "nucleus": "#5b9a3f"},
        "stem cell": {"membrane": "#f5d0e0", "line": "#cf6f93", "nucleus": "#a04f76"},
        "red blood cell": {
            "membrane": "#e2616f",
            "line": "#b03a4a",
            "nucleus": "#c2485a",
            "organelle": None,
        },
        "white blood cell": {"membrane": "#eef2f6", "line": "#9aa6b8", "nucleus": "#a98acb"},
        "egg cell": {"membrane": "#ffe0a8", "line": "#d9a900", "nucleus": "#c8902b"},
    },
)
_add(
    "atom",
    {
        "atom": {},
        "molecule": {"rings": 2, "core": "#9ad0ff", "line": "#4a90d9"},
        "ion": {"rings": 1},
        "electron": {"rings": 1, "core": "#3f7ad6", "line": "#2b4a7a"},
        "proton": {"rings": 0, "core": "#ef6f6f", "line": "#c23f3f"},
        "nucleus": {"rings": 0, "core": "#ff8a5b", "line": "#c85a2b"},
    },
)
_add(
    "virus",
    {
        "virus": {},
        "coronavirus": {},
        "pathogen": {"body": "#bf8acb", "line": "#8a5a9a", "spike": "#8a5a9a"},
        "covid": {},
        "flu virus": {"body": "#8acb5a", "line": "#5a9a2b", "spike": "#5a9a2b"},
    },
)
_add(
    "dna",
    {
        "dna": {},
        "double helix": {},
        "gene": {},
        "genome": {},
        "chromosome": {"s1": "#7a5fd0", "s2": "#7a5fd0"},
    },
)
_add("neuron", {"neuron": {}, "nerve cell": {}, "brain cell": {}})
_add(
    "vessel",
    {
        "beaker": {},
        "flask": {"kind": "flask"},
        "test tube": {"kind": "test_tube"},
        "erlenmeyer flask": {"kind": "flask"},
        "chemical": {"kind": "flask", "liquid": "#9fd23f"},
        "potion": {"kind": "flask", "liquid": "#bf8acb"},
    },
)
_add("bulb", {"light bulb": {}, "lightbulb": {}, "bulb": {}, "idea": {}, "lamp": {}})
_add("magnet", {"magnet": {}, "horseshoe magnet": {}})
_add(
    "organ",
    {
        "lungs": {"kind": "lungs", "body": "#ef9aa6", "line": "#c25f6f"},
        "lung": {"kind": "lungs", "body": "#ef9aa6", "line": "#c25f6f"},
        "brain": {"kind": "brain", "body": "#f3b0c0", "line": "#c25f86"},
        "bone": {"kind": "bone", "body": "#f2efe2", "line": "#b0a884"},
    },
)


def compose_family(concept: str) -> dict | None:
    """Look up a concept's family recipe (exact key), or None. icons.compose() handles
    article/plural variants before calling, so this stays a plain dict lookup."""
    entry = CONCEPT_FAMILIES.get(concept)
    if entry is None:
        return None
    family, params = entry
    fn = FAMILIES.get(family)
    return fn(**params) if fn else None


def known() -> list[str]:
    return sorted(CONCEPT_FAMILIES)
