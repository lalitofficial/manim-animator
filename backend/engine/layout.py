"""Cartoon composition — a staged SCENE, not free-space packing (docs/CARTOON.md).

Cartoon is film: a story, well presented. So we don't pack concepts into reading-order
free space (that's a diagram). We STAGE them: the title across the top, the host standing
on the ground to one side, and the props placed in semantic BANDS — sky things up (sun,
cloud, bird), ground things down (tree, house, river), everything else in a mid row. A
topic with real settings (most kid lessons) reads as a scene; a purely abstract topic
degrades gracefully to a centered row. Deterministic, never overlaps by construction, so
it satisfies the same output invariants. Whiteboard keeps the free-space positioner.
"""

from __future__ import annotations

import math

from engine import character, palette
from engine.contracts import Board, Placement, Thing

_MARGIN = 0.6

# Semantic vertical bands — what lives in the sky vs on the ground (the rest is mid).
_SKY = frozenset(
    {
        "sun",
        "moon",
        "star",
        "cloud",
        "rainbow",
        "sky",
        "bird",
        "kite",
        "balloon",
        "plane",
        "airplane",
        "rocket",
        "planet",
        "comet",
        "satellite",
        "snow",
        "snowflake",
        "lightning",
        "ufo",
        "butterfly",
        "bee",
        "sunrise",
        "sunset",
        "galaxy",
        "meteor",
        "helicopter",
    }
)
_GROUND = frozenset(
    {
        "tree",
        "house",
        "home",
        "mountain",
        "hill",
        "river",
        "lake",
        "ocean",
        "sea",
        "water",
        "waterfall",
        "grass",
        "flower",
        "plant",
        "rock",
        "stone",
        "person",
        "people",
        "car",
        "bus",
        "truck",
        "train",
        "road",
        "soil",
        "ground",
        "volcano",
        "bridge",
        "mushroom",
        "bush",
        "cactus",
        "dog",
        "cat",
        "rabbit",
        "fox",
        "frog",
        "turtle",
        "snake",
        "snail",
        "boat",
        "ship",
        "anchor",
        "island",
        "log",
        "fence",
        "field",
        "forest",
        "seed",
        "root",
    }
)


# MID — abstract / diagrammatic / body / TECH concepts that float between sky and ground
# (atom, gear, heart, server). Checked FIRST so a *technical* cloud (an imported
# "azure …" icon) floats in the diagram middle instead of drifting up into the weather sky.
_MID = frozenset(
    {
        "atom",
        "molecule",
        "electron",
        "proton",
        "neutron",
        "dna",
        "gene",
        "cell",
        "neuron",
        "virus",
        "bacteria",
        "germ",
        "microbe",
        "gear",
        "gears",
        "cog",
        "magnet",
        "battery",
        "circuit",
        "wave",
        "energy",
        "force",
        "gravity",
        "equation",
        "formula",
        "graph",
        "chart",
        "diagram",
        "orbit",
        "cycle",
        "heart",
        "brain",
        "lung",
        "lungs",
        "kidney",
        "liver",
        "stomach",
        "bone",
        "nerve",
        "muscle",
        "blood",
        "server",
        "database",
        "network",
        "gateway",
        "kubernetes",
        "docker",
        "container",
        "api",
        "function",
        "queue",
        "storage",
        "firewall",
        "router",
        "datacenter",
        "microservice",
        "internet",
    }
)
# Tokens that mark a multi-word IMPORTED tech id as a diagram icon (→ mid band).
_MID_SUBSTR = (
    "server",
    "database",
    "network",
    "gateway",
    "kubernetes",
    "storage",
    "azure",
    "aws",
    "gcp",
    "container",
    "compute",
    "firewall",
    "datacenter",
    "internet",
    "vpc",
    "subnet",
    "lambda",
    "microservice",
    "load balancer",
)


# Precipitation / vapor are IN TRANSIT between sky and ground (rising vapor, falling rain).
# Staging them in the MID band fills the dead middle and lets a vertical process read
# top→bottom (sun in sky · vapor/rain in transit · land on the ground), not crammed up top.
_TRANSIT = frozenset(
    {"rain", "raindrop", "droplet", "drop", "vapor", "mist", "snow", "snowflake", "steam", "dew"}
)


def _band(concept: str) -> str:
    c = concept.strip().lower().replace("_", " ").replace("-", " ")
    words = set(c.split())
    if words & _MID or any(s in c for s in _MID_SUBSTR):
        return "mid"  # abstract / tech / body — floats in the diagram middle
    if words & _TRANSIT or any(s in c for s in ("rain", "droplet", "vapor", "snow")):
        return "mid"  # precipitation / vapor — staged mid-air, in transit
    if c in _SKY or words & _SKY or any(s in c for s in ("cloud", "star")):
        return "sky"
    if c in _GROUND or words & _GROUND or any(s in c for s in ("tree", "mountain", "river")):
        return "ground"
    return "ground"  # default: a prop SITS on the ground, not floating in mid-air (looks amateur)


def _cols(n: int) -> int:
    return 1 if n <= 1 else 2 if n <= 4 else 3 if n <= 9 else 4


def _place_row(
    items: list[Thing],
    cy: float,
    board: Board,
    x0: float,
    x1: float,
    f: float,
    base_y: float | None = None,
) -> list[Placement]:
    """Evenly space a band's props across [x0, x1] at the SCENE scale `f` (passed in, not
    computed per-band). A scene-wide scale is what preserves semantic role-scale GLOBALLY:
    a particle alone in the mid band stays tiny next to a hero two bands away, instead of
    inflating to fill its own band. `base_y` sets the ground line — props STAND on it."""
    out: list[Placement] = []
    n = len(items)
    slot = (x1 - x0) / n
    for i, t in enumerate(items):
        cx = x0 + slot * (i + 0.5)
        h = t.extent.h * f
        y = base_y + h / 2 if base_y is not None else cy
        out.append(
            Placement(
                t.id, round(cx, 4), round(y, 4), round(t.extent.w * f, 4), round(h, 4), round(f, 4)
            )
        )
    return out


def _grid(concepts: list[Thing], board: Board, x0: float, has_title: bool) -> list[Placement]:
    """Abstract fallback — a centered grid (no sky/ground to stage by)."""
    out: list[Placement] = []
    n = len(concepts)
    cols = _cols(n)
    rows = math.ceil(n / cols)
    x1 = board.hw - _MARGIN
    y_top = board.hh - (1.3 if has_title else _MARGIN)
    y_bot = -board.hh + _MARGIN
    cw = (x1 - x0) / cols
    ch = (y_top - y_bot) / rows
    cxr = (x0 + x1) / 2
    # common scale -> relative role-sizes preserved across the grid
    mw = max((t.extent.w for t in concepts), default=1.0)
    mh = max((t.extent.h for t in concepts), default=1.0)
    f = min(cw * 0.8 / max(mw, 1e-6), ch * 0.78 / max(mh, 1e-6), 1.6)
    idx = 0
    for r in range(rows):
        in_row = min(cols, n - idx)
        x_start = cxr - (in_row - 1) * cw / 2
        cy = y_top - ch * (r + 0.5)
        for c in range(in_row):
            t = concepts[idx]
            idx += 1
            out.append(
                Placement(
                    t.id,
                    round(x_start + c * cw, 4),
                    round(cy, 4),
                    round(t.extent.w * f, 4),
                    round(t.extent.h * f, 4),
                    round(f, 4),
                )
            )
    return out


def compose_cartoon(
    things: list[Thing], board: Board | None = None
) -> tuple[list[Placement], list[dict]]:
    """Stage a cartoon scene: title (top) · host (left, on the ground) · props in bands."""
    board = board or Board()
    title = [t for t in things if (t.concept or "") == "text"]
    hosts = [t for t in things if character.is_character(t.concept)]
    concepts = [t for t in things if t not in title and t not in hosts]

    placements: list[Placement] = []
    horizon = -board.hh + palette.HORIZON_FRAC * board.h  # the ground line
    host_w = max((h.extent.w for h in hosts), default=0.0)
    for h in hosts:  # host STANDS ON the ground, far left — a presenter beside the stage
        placements.append(
            Placement(
                h.id,
                round(-board.hw + h.extent.w / 2 + 0.75, 4),  # clear the left edge (was clipping)
                round(horizon + h.extent.h / 2, 4),
                h.extent.w,
                h.extent.h,
            )
        )
    for t in title:  # title across the very top
        placements.append(
            Placement(t.id, 0.0, round(board.hh - t.extent.h / 2 - 0.35, 4), t.extent.w, t.extent.h)
        )

    if not concepts:
        return placements, []

    # Stage by band. The props' left edge clears the host; sky spans the full width.
    cx_left = -board.hw + (host_w + 1.2 if hosts else _MARGIN)
    cx_right = board.hw - _MARGIN
    bands = {"sky": [], "mid": [], "ground": []}
    for t in concepts:
        bands[_band(t.concept)].append(t)

    if not bands["sky"] and not bands["ground"]:  # purely abstract -> centered grid
        return placements + _grid(concepts, board, cx_left, bool(title)), []

    band_h = board.h * 0.4  # taller bands → bigger props + less empty middle (less dead space)
    sky_cy = board.hh - (1.3 if title else _MARGIN) - band_h / 2
    mid_cy = (horizon + sky_cy) / 2

    # ONE scale for the whole scene, from the tightest band + the largest item — so
    # semantic role-scale survives ACROSS bands (a hero towers over a particle even when
    # they never share a band). Per-band scaling would let a lone particle inflate to fill
    # its band and erase the hierarchy; a scene-wide scale is what makes it read as a film.
    smax_w = max((t.extent.w for t in concepts), default=1.0)
    smax_h = max((t.extent.h for t in concepts), default=1.0)
    band_x = {
        "sky": (-board.hw + _MARGIN, cx_right),
        "mid": (cx_left, cx_right),
        "ground": (cx_left, cx_right),
    }
    min_slot = min(
        (band_x[b][1] - band_x[b][0]) / len(items) for b, items in bands.items() if items
    )
    # When the scene is ONLY ground props (the common cartoon case: a hero on a stage), let them
    # use the whole height from the grass up to the title — a PROMINENT subject, not a token
    # stranded in a 32%-tall band. Multi-band scenes keep the banded height (so bands don't overlap).
    only_ground = bool(bands["ground"]) and not bands["sky"] and not bands["mid"]
    scale_h = (board.hh - (1.7 if title else _MARGIN) - horizon) if only_ground else band_h
    f = min(min_slot * 0.9 / max(smax_w, 1e-6), scale_h * 0.9 / max(smax_h, 1e-6), 4.2)

    for band, items in bands.items():
        if not items:
            continue
        x0, x1 = band_x[band]
        if band == "ground":  # props STAND on the horizon, clearing the host
            placements += _place_row(items, 0.0, board, x0, x1, f, base_y=horizon)
        elif band == "sky":  # full width, above the host
            placements += _place_row(items, sky_cy, board, x0, x1, f)
        else:  # mid — between the ground and the sky, clearing the host
            placements += _place_row(items, mid_cy, board, x0, x1, f)
    return placements, []
