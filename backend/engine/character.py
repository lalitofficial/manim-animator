"""A parameterized cartoon presenter — the reusable rig (docs/CARTOON.md §3).

ONE rigged asset, drawn from primitives, with a fixed palette: head, hair, face,
torso, two arms, two legs. POSE moves the arms (idle/point/wave/think/present);
EXPRESSION changes the face (neutral/happy/surprised/curious). Consistency is free
because it is always the SAME character — only pose + expression vary (the Animaker
model). The rig returns colored Strokes in a ~2-unit box centered at the origin,
exactly like an icon recipe, so drawing.measure() scales + caches it (pose/expression
live in geometry_attrs → each variant caches separately) and paint() styles it
(cartoon keeps the colors; whiteboard strips them to mono — the rig still reads).
"""

from __future__ import annotations

import json
import math
import pathlib
from dataclasses import replace

from engine import geometry as g
from engine.contracts import Stroke

# The concept names that resolve to the rig (vs the simple `person` icon).
NAMES = frozenset(
    {"presenter", "teacher", "narrator", "guide", "host", "character", "avatar", "buddy"}
)

EXPRESSIONS = ("neutral", "happy", "surprised", "curious")

# --------------------------------------------------------------------------- #
# Poses are DATA — a 2-segment limb spec per limb: [angle1, len1, angle2, len2]
# (shoulder→elbow→hand, hip→knee→foot), matching the AnimatedDrawings skeleton so
# mined angles drop straight in. `pose_library.json` + `character_proportions.json`
# are DERIVED from Meta's Amateur Drawings (MIT) — see tools/ad_mine.py + NOTICE.md.
# Falls back to a hand-authored idle if the mined files are absent (kept hermetic).
# --------------------------------------------------------------------------- #
_DIR = pathlib.Path(__file__).parent


def _load_json(name: str) -> dict:
    try:
        return json.loads((_DIR / name).read_text())
    except Exception:
        return {}


_PROPS = _load_json("character_proportions.json")
# Childlike limb lengths in rig-local units (mined ratios × the rig's torso span 0.40).
_UP, _FORE = _PROPS.get("upper_arm", 0.40) * 0.40, _PROPS.get("forearm", 0.42) * 0.40
_THIGH, _SHIN = _PROPS.get("thigh", 0.48) * 0.40, _PROPS.get("shin", 0.52) * 0.40

# Hand-authored poses the dataset can't give cleanly (a chin-resting think) — merged UNDER
# the mined library so real data wins where it has it.
_HAND_POSES: dict[str, dict] = {
    "idle": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
    },
    "think": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [80, _UP, 150, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "head": -9,
    },
    # jump — arms up, knees tucked (reads as mid-air)
    "jump": {
        "l_arm": [128, _UP, 140, _FORE],
        "r_arm": [52, _UP, 40, _FORE],
        "l_leg": [250, _THIGH, 226, _SHIN],
        "r_leg": [290, _THIGH, 314, _SHIN],
    },
    # agree — neutral stance, head bowed (the down-beat of a nod)
    "agree": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "head": -17,
    },
    # head-DIRECTION poses (the multi-angle look) — arms/legs idle, head turns/tilts
    "look_left": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "turn": -0.7,
    },
    "look_right": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "turn": 0.7,
    },
    "look_up": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "head": 16,
    },
    # explain — one open hand gesturing out, head turned to the audience
    "explain": {
        "l_arm": [248, _UP, 250, _FORE],
        "r_arm": [342, _UP, 8, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "turn": 0.18,
    },
    # surprised — both hands flung up, head back a touch
    "surprised": {
        "l_arm": [150, _UP, 166, _FORE],
        "r_arm": [30, _UP, 14, _FORE],
        "l_leg": [262, _THIGH, 262, _SHIN],
        "r_leg": [278, _THIGH, 278, _SHIN],
        "head": -4,
    },
    # hold_object — both hands forward/cupped, looking down at it
    "hold": {
        "l_arm": [318, _UP, 350, _FORE],
        "r_arm": [222, _UP, 190, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "head": -8,
    },
    # shrug — elbows out, palms up ("who knows?")
    "shrug": {
        "l_arm": [206, _UP, 150, _FORE],
        "r_arm": [334, _UP, 30, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "head": 4,
    },
    # clap — hands meeting in front of the chest
    "clap": {
        "l_arm": [322, _UP, 350, _FORE],
        "r_arm": [218, _UP, 190, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
    },
    # body 3/4 TURNS (the whole figure faces left/right, not just the head)
    "turn_left": {
        "l_arm": [248, _UP, 248, _FORE],
        "r_arm": [292, _UP, 292, _FORE],
        "l_leg": [266, _THIGH, 266, _SHIN],
        "r_leg": [274, _THIGH, 274, _SHIN],
        "facing": -0.7,
    },
    "turn_right": {
        "l_arm": [248, _UP, 248, _FORE],
        "r_arm": [292, _UP, 292, _FORE],
        "l_leg": [266, _THIGH, 266, _SHIN],
        "r_leg": [274, _THIGH, 274, _SHIN],
        "facing": 0.7,
    },
    # full side PROFILE (|facing|=1 → profile head + far arm hidden)
    "side_left": {
        "l_arm": [255, _UP, 250, _FORE],
        "r_arm": [285, _UP, 285, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "facing": -1.0,
    },
    "side_right": {
        "l_arm": [255, _UP, 255, _FORE],
        "r_arm": [285, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "facing": 1.0,
    },
    # walking in profile (a stride, side-on) — for crossing a scene
    "walk_side": {
        "l_arm": [250, _UP, 235, _FORE],
        "r_arm": [290, _UP, 305, _FORE],
        "l_leg": [248, _THIGH, 250, _SHIN],
        "r_leg": [300, _THIGH, 298, _SHIN],
        "facing": 0.92,
    },
    # crouch — the wind-up (ANTICIPATION) before a jump: knees bent, arms swung back/down
    "crouch": {
        "l_arm": [248, _UP, 232, _FORE],
        "r_arm": [292, _UP, 308, _FORE],
        "l_leg": [256, _THIGH, 232, _SHIN],
        "r_leg": [284, _THIGH, 308, _SHIN],
        "head": -5,
    },
    # idle LIFE — eyes shut (blink) + a gentle weight shift so a held pose isn't frozen
    "blink": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "blink": True,
    },
    "sway_l": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "turn": -0.14,
    },
    "sway_r": {
        "l_arm": [250, _UP, 250, _FORE],
        "r_arm": [290, _UP, 290, _FORE],
        "l_leg": [268, _THIGH, 268, _SHIN],
        "r_leg": [272, _THIGH, 272, _SHIN],
        "turn": 0.14,
    },
}
POSE_LIBRARY: dict[str, dict] = {
    **_HAND_POSES,
    **{k: v for k, v in _load_json("pose_library.json").items() if not k.startswith("_")},
}
POSES = tuple(POSE_LIBRARY)

# The default presenter look — friendly, saturated flats with darker outlines.
DEFAULT_PALETTE: dict[str, str] = {
    "skin": "#f6c79a",
    "skin_line": "#cf9a63",
    "hair": "#4a2f1a",
    "shirt": "#37b3a4",
    "shirt_line": "#268377",
    "pants": "#3b5a8a",
    "pants_line": "#27406a",
    "shoe": "#363b45",
    "ink": "#26354d",  # eyes / mouth / outlines
    "mouth": "#b5485a",  # open-mouth (surprised) interior
    "cheek": "#ff9aa6",  # rosy cheeks
}

# A couple of alternate skins so a lesson can have a small, consistent cast.
THEMES: dict[str, dict[str, str]] = {
    "teal": DEFAULT_PALETTE,
    "coral": {**DEFAULT_PALETTE, "shirt": "#ef7d6a", "shirt_line": "#c9543f", "hair": "#2b2b2b"},
    "violet": {**DEFAULT_PALETTE, "shirt": "#9b7ede", "shirt_line": "#6f4fc0", "hair": "#1f1f1f"},
}

# Anchors in the local ~2-unit box (y up).
_HEAD_C = (0.0, 0.56)
_HEAD_R = 0.30
_SHOULDER_Y = 0.10
_SHOULDER_X = 0.26
_HIP_Y = -0.30
_HIP_X = 0.13


def palette_for(name: str | None) -> dict[str, str]:
    return THEMES.get((name or "").strip().lower(), DEFAULT_PALETTE)


def _fill(strokes: list[Stroke], fill: str, line: str) -> list[Stroke]:
    from dataclasses import replace

    return [replace(s, fill=fill, color=line) for s in strokes]


def _translate(s: Stroke, to) -> Stroke:
    return g.transform([s], to[0], to[1], 1.0)[0]


def _seg2(root, spec, line_color: str):
    """A 2-segment limb root→elbow→end from a [a1, l1, a2, l2] spec (angles 0°=right, 90°=up).
    Returns (strokes, end_point) so the caller can place a hand/foot at the end."""
    a1, l1, a2, l2 = spec
    r1, r2 = math.radians(a1), math.radians(a2)
    elbow = (root[0] + l1 * math.cos(r1), root[1] + l1 * math.sin(r1))
    end = (elbow[0] + l2 * math.cos(r2), elbow[1] + l2 * math.sin(r2))
    return [Stroke((root, elbow, end), closed=False, color=line_color)], end


def _limbs(pose: dict, pal: dict[str, str], facing: float = 0.0) -> list[Stroke]:
    """Both legs then both arms (back-to-front) from a pose dict — the rig's whole body
    language. A pose is 4 limb specs; angles do all the acting. In a strict PROFILE
    (|facing|~1) the far arm is hidden, so the figure reads as a true side view."""
    profile = abs(facing) > 0.82
    near = 1.0 if facing >= 0 else -1.0  # the screen side facing the viewer
    out: list[Stroke] = []
    for hip_x, key in ((-_HIP_X, "l_leg"), (_HIP_X, "r_leg")):  # legs behind
        seg, end = _seg2((hip_x, _HIP_Y), pose[key], pal["pants_line"])
        out += seg
        out += [_translate(s, end) for s in _fill([g.ellipse(0.1, 0.06)], pal["shoe"], pal["ink"])]
    for sh_x, key in ((-_SHOULDER_X, "l_arm"), (_SHOULDER_X, "r_arm")):
        if profile and sh_x * near < 0:  # the FAR arm is behind the body — drop it (profile)
            continue
        seg, end = _seg2((sh_x, _SHOULDER_Y), pose[key], pal["shirt_line"])
        out += seg
        out += [_translate(s, end) for s in _fill([g.circle(0.07)], pal["skin"], pal["skin_line"])]
    return out


def _resolve_pose(pose) -> dict:
    """A pose NAME → its library spec, or a pose DICT (an interpolated frame) → itself."""
    if isinstance(pose, dict):
        return pose
    return POSE_LIBRARY.get(pose if pose in POSE_LIBRARY else "idle", POSE_LIBRARY["idle"])


def posed(name: str, **overrides: float) -> dict:
    """A library pose with head `turn`/`facing`/`head` overridden — e.g. to make the rig
    LOOK toward a target (`posed("point", turn=0.6)` turns the head to the right)."""
    return {**_resolve_pose(name), **{k: float(v) for k, v in overrides.items()}}


# --------------------------------------------------------------------------- #
# Expressions — eyes, brows, mouth.
# --------------------------------------------------------------------------- #
def _arc_at(r: float, a0: float, a1: float, cx: float, cy: float, color: str) -> Stroke:
    a = g.arc(r, a0, a1)
    return Stroke(tuple((x + cx, y + cy) for x, y in a.points), closed=False, color=color)


def _face(expr: str, pal: dict[str, str], turn: float = 0.0, blink: bool = False) -> list[Stroke]:
    """The face, optionally TURNED horizontally (turn∈[-1,1]: −left, +right). A turn slides
    every feature toward the facing side and pushes the nose to the head's edge, so the round
    head reads as 3/4 / looking sideways (the multi-angle cue). `blink` closes the eyes."""
    ink = pal["ink"]
    hx, hy = _HEAD_C
    eye_y = hy + 0.05
    eye_x = 0.13
    mouth_y = hy - 0.15
    # PROFILE — a true side view: ONE eye + a nose poking off the head's silhouette edge.
    if abs(turn) > 0.82:
        side = 1.0 if turn > 0 else -1.0
        ex = hx + side * 0.09
        prof: list[Stroke] = []
        if blink:
            prof.append(_arc_at(0.055, 200, 340, ex, eye_y, ink))
        else:
            prof += [_translate(s, (ex, eye_y)) for s in _fill([g.circle(0.05)], ink, ink)]
        prof.append(_arc_at(0.06, 200, 340, ex, eye_y + 0.12, ink))  # brow
        nx = hx + side * (_HEAD_R - 0.01)  # nose: a small wedge off the facing edge
        prof.append(
            Stroke(
                ((nx, eye_y + 0.0), (nx + side * 0.1, eye_y - 0.07), (nx, eye_y - 0.14)),
                closed=True,
                color=pal["skin_line"],
                fill=pal["skin"],
            )
        )
        if expr in ("happy", "curious"):
            prof.append(_arc_at(0.08, 250, 320, hx + side * 0.08, mouth_y + 0.04, ink))
        elif expr == "surprised":
            prof += [
                _translate(s, (hx + side * 0.12, mouth_y))
                for s in _fill([g.ellipse(0.045, 0.06)], pal["mouth"], ink)
            ]
        else:
            prof.append(
                Stroke(
                    ((hx + side * 0.04, mouth_y), (hx + side * 0.2, mouth_y)),
                    closed=False,
                    color=ink,
                )
            )
        return prof
    dx = turn * 0.11  # features slide toward the facing side
    out: list[Stroke] = []
    er = 0.045 if expr != "surprised" else 0.06
    for side in (-1, 1):  # the eye OPPOSITE the turn is "far" → it shrinks (foreshortening)
        ex = hx + side * eye_x + dx
        far = (side < 0) if turn > 0 else (side > 0)
        if blink:
            out.append(_arc_at(0.06, 200, 340, ex, eye_y, ink))
        else:
            r = er * (0.55 if (far and abs(turn) > 0.5) else 1.0)
            out += [_translate(s, (ex, eye_y)) for s in _fill([g.circle(r)], ink, ink)]
    brow_y = eye_y + 0.13
    if expr == "surprised":
        out += [
            _arc_at(0.07, 200, 340, hx - eye_x + dx, brow_y, ink),
            _arc_at(0.07, 200, 340, hx + eye_x + dx, brow_y, ink),
        ]
    elif expr == "curious":
        out.append(
            Stroke(
                ((hx + 0.05 + dx, brow_y), (hx + 0.21 + dx, brow_y + 0.05)), closed=False, color=ink
            )
        )
        out.append(
            Stroke(
                ((hx - 0.21 + dx, brow_y - 0.01), (hx - 0.05 + dx, brow_y - 0.01)),
                closed=False,
                color=ink,
            )
        )
    # Nose — pushed toward the facing edge (a profile cue when turned).
    nx = hx + dx + turn * 0.13
    out.append(
        Stroke(
            ((nx - 0.015 + turn * 0.02, eye_y - 0.07), (nx + 0.03 + turn * 0.05, hy - 0.06)),
            closed=False,
            color=pal["skin_line"],
        )
    )
    mouth_y = hy - 0.15
    mx = hx + dx
    if expr == "happy":
        out.append(_arc_at(0.15, 205, 335, mx, mouth_y + 0.06, ink))
    elif expr == "surprised":
        out += [
            _translate(s, (mx, mouth_y)) for s in _fill([g.ellipse(0.05, 0.07)], pal["mouth"], ink)
        ]
    elif expr == "curious":
        out.append(_arc_at(0.1, 210, 330, mx, mouth_y + 0.04, ink))
    else:
        out.append(Stroke(((mx - 0.09, mouth_y), (mx + 0.09, mouth_y)), closed=False, color=ink))
    if expr in ("happy", "curious"):
        for cx in (hx - 0.21 + dx, hx + 0.21 + dx):
            out += [
                _translate(s, (cx, mouth_y + 0.05))
                for s in _fill([g.circle(0.05)], pal["cheek"], pal["cheek"])
            ]
    return out


def _hair(pal: dict[str, str]) -> list[Stroke]:
    hx, hy = _HEAD_C
    # A rounded cap sitting on the top half of the head.
    cap = g.arc(_HEAD_R + 0.02, 15, 165)
    pts = tuple((x + hx, y + hy) for x, y in cap.points)
    return [Stroke(pts + (pts[0],), closed=True, color=pal["hair"], fill=pal["hair"])]


def _body(pal: dict[str, str]) -> list[Stroke]:
    # Torso as a slight trapezoid (shoulders wider than waist) → a friendly shirt.
    torso = Stroke(
        (
            (-_SHOULDER_X - 0.03, _SHOULDER_Y + 0.04),
            (_SHOULDER_X + 0.03, _SHOULDER_Y + 0.04),
            (_HIP_X + 0.07, _HIP_Y),
            (-_HIP_X - 0.07, _HIP_Y),
        ),
        closed=True,
        color=pal["shirt_line"],
        fill=pal["shirt"],
    )
    return [torso]


# --------------------------------------------------------------------------- #
# The CAST — a modular character grammar (NOTEBOOK §C2). The SAME rig + the SAME
# pose/emotion/motion engine, varied by skin + hair color + outfit (shirt) +
# ACCESSORIES (hat/glasses/coat/…) → many consistent characters in ONE style. We
# learn the modular grammar of Open Peeps / Humaaans; we do NOT ingest their art
# (each is a different style — the §B10 "composed beats ingested" rule for characters).
# --------------------------------------------------------------------------- #
SKINS = ("#f6c79a", "#e3ab78", "#c98a5a", "#9c6b43")
HAIR_COLORS = {
    "brown": "#4a2f1a",
    "black": "#1f1f1f",
    "blonde": "#e6b34a",
    "red": "#b5532b",
    "gray": "#9a9a9a",
    "white": "#ededed",
}
_HTOP = _HEAD_C[1] + _HEAD_R  # crown of the head (y)


def _ring(r: float, color: str, at=(0.0, 0.0)) -> Stroke:
    return _translate(replace(g.circle(r), color=color, fill=None), at)


def _disc(r: float, fill: str, line: str, at=(0.0, 0.0)) -> Stroke:
    return _translate(replace(g.circle(r), color=line, fill=fill), at)


def _poly(points, fill: str | None, line: str, closed: bool = True) -> Stroke:
    return Stroke(tuple(points), closed=closed, color=line, fill=fill if closed else None)


# Accessories — each returns Strokes in the rig's local box. `pal` carries the palette.
def _acc_glasses(pal):
    ink, ey = "#2b2b2b", _HEAD_C[1] + 0.05
    return [
        _ring(0.085, ink, (-0.13, ey)),
        _ring(0.085, ink, (0.13, ey)),
        Stroke(((-0.045, ey), (0.045, ey)), closed=False, color=ink),
    ]


def _acc_goggles(pal):
    ink, ey = "#3a4a5a", _HEAD_C[1] + 0.04
    return [
        _disc(0.12, "#bfe3ff", ink, (-0.13, ey)),
        _disc(0.12, "#bfe3ff", ink, (0.13, ey)),
        Stroke(((-0.25, ey + 0.05), (0.25, ey + 0.05)), closed=False, color=ink),
    ]


def _acc_straw_hat(pal):
    tan, line = "#e8c878", "#b89a48"
    return [
        _translate(replace(g.ellipse(0.5, 0.1), color=line, fill=tan), (0, _HTOP - 0.02)),
        _translate(replace(g.arc(0.28, 10, 170), color=line), (0, _HTOP - 0.02)),
    ]


def _acc_chef_hat(pal):
    w, line = "#fdfdfd", "#cfd4d8"
    out = [_poly([(-0.2, _HTOP), (0.2, _HTOP), (0.2, _HTOP + 0.12), (-0.2, _HTOP + 0.12)], w, line)]
    for cx in (-0.16, 0.0, 0.16):
        out.append(_disc(0.14, w, line, (cx, _HTOP + 0.2)))
    return out


def _acc_crown(pal):
    gold, line = "#ffd23f", "#e0a800"
    out = [
        _poly(
            [
                (-0.22, _HTOP - 0.02),
                (0.22, _HTOP - 0.02),
                (0.22, _HTOP + 0.08),
                (-0.22, _HTOP + 0.08),
            ],
            gold,
            line,
        )
    ]
    for x in (-0.17, 0.0, 0.17):
        out.append(
            _poly(
                [(x - 0.08, _HTOP + 0.08), (x, _HTOP + 0.24), (x + 0.08, _HTOP + 0.08)], gold, line
            )
        )
    return out


def _acc_wizard_hat(pal):
    blue, line = "#4a4fae", "#2f348a"
    return [
        _translate(replace(g.ellipse(0.4, 0.09), color=line, fill=blue), (0, _HTOP)),
        _poly([(-0.26, _HTOP), (0.04, _HTOP + 0.66), (0.26, _HTOP)], blue, line),
        _disc(0.04, "#ffe066", "#e0a800", (0.07, _HTOP + 0.34)),
    ]


def _acc_grad_cap(pal):
    ink = "#2b2b3a"
    return [
        _poly(
            [(-0.26, _HTOP + 0.05), (0.0, _HTOP + 0.16), (0.26, _HTOP + 0.05), (0.0, _HTOP - 0.06)],
            ink,
            ink,
        ),
        Stroke(((0.0, _HTOP + 0.05), (0.22, _HTOP - 0.04)), closed=False, color="#e0a800"),
        _disc(0.03, "#ffd23f", "#e0a800", (0.22, _HTOP - 0.08)),
    ]


def _acc_cap(pal):
    col, line = pal.get("hat", "#3a5fae"), "#26406a"
    return [
        _translate(replace(g.arc(_HEAD_R + 0.02, 12, 168), color=line, fill=col), (0, _HEAD_C[1])),
        _poly([(0.0, _HTOP - 0.16), (0.0, _HTOP - 0.02), (0.42, _HTOP - 0.08)], col, line),
    ]


def _acc_helmet(pal):  # astronaut bubble
    return [_ring(0.4, "#aaccee", _HEAD_C), _ring(0.43, "#8fb6da", _HEAD_C)]


def _acc_coat(pal):  # a white lab/medical coat: collar V on the torso
    w, line = "#fbfbfb", "#cfd4d8"
    return [
        _poly([(-0.12, 0.13), (0.0, -0.05), (0.12, 0.13)], w, line),
        Stroke(((0.0, -0.05), (0.0, -0.28)), closed=False, color=line),
    ]


def _acc_stethoscope(pal):
    ink = "#36506a"
    return [
        Stroke(((-0.12, 0.16), (-0.18, -0.05), (-0.02, -0.18)), closed=False, color=ink),
        Stroke(((0.12, 0.16), (0.18, -0.05), (0.04, -0.16)), closed=False, color=ink),
        _disc(0.05, "#c0d0e0", ink, (0.01, -0.2)),
    ]


def _acc_beard(pal):
    line = pal["hair"]
    hy = _HEAD_C[1]
    return [
        _poly(
            [
                (-0.2, hy - 0.05),
                (-0.16, hy - 0.34),
                (0.0, hy - 0.42),
                (0.16, hy - 0.34),
                (0.2, hy - 0.05),
                (0.12, hy - 0.16),
                (0.0, hy - 0.12),
                (-0.12, hy - 0.16),
            ],
            line,
            line,
        )
    ]


def _acc_cape(pal):  # drawn BEHIND the body
    col = pal.get("cape", "#e23b2b")
    line = pal.get("cape_line", "#a01f14")
    return [_poly([(-0.24, 0.16), (0.24, 0.16), (0.46, -0.56), (-0.46, -0.56)], col, line)]


def _acc_cowboy_hat(pal):
    tan, line = "#b78a4a", "#8a6432"
    return [
        _translate(replace(g.ellipse(0.47, 0.09), color=line, fill=tan), (0, _HTOP - 0.03)),
        _poly(
            [(-0.24, _HTOP - 0.04), (-0.2, _HTOP + 0.2), (0.2, _HTOP + 0.2), (0.24, _HTOP - 0.04)],
            tan,
            line,
        ),
    ]


def _acc_pirate_hat(pal):
    dk, line = "#2b2b34", "#15151c"
    return [
        _poly(
            [
                (-0.42, _HTOP - 0.02),
                (0.42, _HTOP - 0.02),
                (0.3, _HTOP + 0.2),
                (0.0, _HTOP + 0.12),
                (-0.3, _HTOP + 0.2),
            ],
            dk,
            line,
        ),
        _disc(0.06, "#f2f2f2", "#cfcfcf", (0.0, _HTOP + 0.06)),
    ]


def _acc_eyepatch(pal):
    dk, ey = "#1f1f24", _HEAD_C[1] + 0.05
    return [
        _translate(replace(g.ellipse(0.1, 0.08), color=dk, fill=dk), (0.13, ey)),
        Stroke(((-0.05, ey + 0.12), (0.28, ey - 0.04)), closed=False, color=dk),
    ]


def _acc_party_hat(pal):
    col, line = pal.get("hat", "#e2473b"), "#a01f14"
    return [
        _poly([(-0.17, _HTOP), (0.0, _HTOP + 0.5), (0.17, _HTOP)], col, line),
        _disc(0.06, "#ffe066", "#e0a800", (0.0, _HTOP + 0.52)),
    ]


def _acc_witch_hat(pal):
    dk, line = "#2f2740", "#1b1630"
    return [
        _translate(replace(g.ellipse(0.42, 0.09), color=line, fill=dk), (0, _HTOP)),
        _poly([(-0.26, _HTOP), (0.18, _HTOP + 0.62), (0.26, _HTOP)], dk, line),
        _poly(
            [
                (-0.16, _HTOP + 0.04),
                (0.16, _HTOP + 0.04),
                (0.16, _HTOP + 0.12),
                (-0.16, _HTOP + 0.12),
            ],
            "#8a5fd0",
            "#5f3a90",
        ),
    ]


def _acc_sunglasses(pal):
    dk, ey = "#1f2430", _HEAD_C[1] + 0.05
    return [
        _disc(0.09, dk, dk, (-0.13, ey)),
        _disc(0.09, dk, dk, (0.13, ey)),
        Stroke(((-0.045, ey), (0.045, ey)), closed=False, color=dk),
    ]


def _acc_headphones(pal):
    dk = "#33373d"
    return [
        _translate(replace(g.arc(_HEAD_R + 0.05, 20, 160), color=dk), _HEAD_C),
        _disc(0.08, dk, "#1d2024", (-_HEAD_R - 0.02, _HEAD_C[1])),
        _disc(0.08, dk, "#1d2024", (_HEAD_R + 0.02, _HEAD_C[1])),
    ]


def _acc_red_nose(pal):
    return [_disc(0.06, "#e2473b", "#a01f14", (0.0, _HEAD_C[1] - 0.06))]


def _acc_mustache(pal):
    ink = "#3a2a1a"
    y = _HEAD_C[1] - 0.06
    return [
        _poly(
            [
                (-0.13, y),
                (-0.04, y - 0.06),
                (0.0, y - 0.02),
                (0.04, y - 0.06),
                (0.13, y),
                (0.0, y - 0.1),
            ],
            ink,
            ink,
        )
    ]


def _acc_tie(pal):  # torso
    col = pal.get("tie", "#c0392b")
    return [
        _poly([(-0.05, 0.13), (0.05, 0.13), (0.0, 0.04)], col, col),
        _poly([(-0.06, 0.04), (0.06, 0.04), (0.08, -0.22), (-0.08, -0.22)], col, col),
    ]


# Layer: "back" (behind body) · "torso" (on the shirt) · "head" (rides the head, tilts with it).
_ACCESSORIES = {
    "glasses": ("head", _acc_glasses),
    "goggles": ("head", _acc_goggles),
    "straw_hat": ("head", _acc_straw_hat),
    "chef_hat": ("head", _acc_chef_hat),
    "crown": ("head", _acc_crown),
    "wizard_hat": ("head", _acc_wizard_hat),
    "grad_cap": ("head", _acc_grad_cap),
    "cap": ("head", _acc_cap),
    "helmet": ("head", _acc_helmet),
    "beard": ("head", _acc_beard),
    "cowboy_hat": ("head", _acc_cowboy_hat),
    "pirate_hat": ("head", _acc_pirate_hat),
    "eyepatch": ("head", _acc_eyepatch),
    "party_hat": ("head", _acc_party_hat),
    "witch_hat": ("head", _acc_witch_hat),
    "sunglasses": ("head", _acc_sunglasses),
    "headphones": ("head", _acc_headphones),
    "red_nose": ("head", _acc_red_nose),
    "mustache": ("head", _acc_mustache),
    "coat": ("torso", _acc_coat),
    "stethoscope": ("torso", _acc_stethoscope),
    "tie": ("torso", _acc_tie),
    "cape": ("back", _acc_cape),
}

# Roles — a concept → a consistent character spec. Skin/hair/outfit + accessories.
_DEF = {"skin": 0, "hair": "brown", "shirt": "#37b3a4", "shirt_line": "#268377", "acc": ()}
ROLES: dict[str, dict] = {
    "teacher": {**_DEF, "shirt": "#7b5ea8", "shirt_line": "#5b4488", "acc": ("glasses",)},
    "student": {
        **_DEF,
        "hair": "black",
        "shirt": "#e2724a",
        "shirt_line": "#b84f2b",
        "acc": ("cap",),
        "hat": "#e2473b",
    },
    "scientist": {
        **_DEF,
        "hair": "gray",
        "shirt": "#fbfbfb",
        "shirt_line": "#cfd4d8",
        "acc": ("coat", "goggles"),
    },
    "doctor": {
        **_DEF,
        "hair": "black",
        "shirt": "#fbfbfb",
        "shirt_line": "#cfd4d8",
        "acc": ("coat", "stethoscope"),
    },
    "nurse": {
        **_DEF,
        "hair": "brown",
        "shirt": "#eaf6ff",
        "shirt_line": "#b8d0e0",
        "acc": ("coat",),
    },
    "farmer": {
        **_DEF,
        "skin": 1,
        "shirt": "#5b9a4a",
        "shirt_line": "#3f7332",
        "acc": ("straw_hat",),
    },
    "chef": {
        **_DEF,
        "hair": "black",
        "shirt": "#fbfbfb",
        "shirt_line": "#cfd4d8",
        "acc": ("chef_hat",),
    },
    "astronaut": {**_DEF, "shirt": "#eef2f6", "shirt_line": "#c0c8d0", "acc": ("helmet",)},
    "artist": {
        **_DEF,
        "hair": "red",
        "shirt": "#5bbf9a",
        "shirt_line": "#3f9173",
        "acc": ("grad_cap",),
    },
    "graduate": {
        **_DEF,
        "hair": "black",
        "shirt": "#3a3a4a",
        "shirt_line": "#26263a",
        "acc": ("grad_cap",),
    },
    "king": {**_DEF, "shirt": "#9a3fae", "shirt_line": "#6f2f80", "acc": ("crown",)},
    "queen": {
        **_DEF,
        "hair": "blonde",
        "shirt": "#cf4f93",
        "shirt_line": "#a03570",
        "acc": ("crown",),
    },
    "wizard": {
        **_DEF,
        "hair": "white",
        "shirt": "#3f4fae",
        "shirt_line": "#2f348a",
        "acc": ("wizard_hat", "beard"),
    },
    "superhero": {
        **_DEF,
        "hair": "black",
        "shirt": "#2f6fd0",
        "shirt_line": "#1f4f9a",
        "acc": ("cape",),
        "cape": "#e23b2b",
        "cape_line": "#a01f14",
    },
    "police": {
        **_DEF,
        "shirt": "#3a5fae",
        "shirt_line": "#26406a",
        "acc": ("cap",),
        "hat": "#26406a",
    },
    "explorer": {
        **_DEF,
        "skin": 1,
        "hair": "brown",
        "shirt": "#9a8a4a",
        "shirt_line": "#6e6232",
        "acc": ("straw_hat",),
    },
    "cowboy": {
        **_DEF,
        "skin": 1,
        "shirt": "#9a6a3a",
        "shirt_line": "#6e4a22",
        "acc": ("cowboy_hat",),
    },
    "pirate": {
        **_DEF,
        "hair": "black",
        "shirt": "#7a3a3a",
        "shirt_line": "#522424",
        "acc": ("pirate_hat", "eyepatch"),
    },
    "businessman": {
        **_DEF,
        "shirt": "#2f3540",
        "shirt_line": "#1d222a",
        "acc": ("tie", "glasses"),
        "tie": "#c0392b",
    },
    "dj": {
        **_DEF,
        "hair": "black",
        "shirt": "#2b2b34",
        "shirt_line": "#16161c",
        "acc": ("headphones", "sunglasses"),
    },
    "witch": {
        **_DEF,
        "hair": "black",
        "shirt": "#3f2f5a",
        "shirt_line": "#281d3c",
        "acc": ("witch_hat",),
    },
    "clown": {
        **_DEF,
        "hair": "red",
        "shirt": "#e2473b",
        "shirt_line": "#a01f30",
        "acc": ("party_hat", "red_nose"),
        "hat": "#3fa46a",
    },
    "princess": {
        **_DEF,
        "hair": "blonde",
        "shirt": "#d98ac0",
        "shirt_line": "#a85a90",
        "acc": ("crown",),
    },
    "celebrity": {
        **_DEF,
        "hair": "blonde",
        "shirt": "#9b59b6",
        "shirt_line": "#7a3f93",
        "acc": ("sunglasses",),
    },
    "knight": {**_DEF, "shirt": "#9aa6b8", "shirt_line": "#6a7686", "acc": ("helmet",)},
    "grandpa": {
        **_DEF,
        "skin": 2,
        "hair": "white",
        "shirt": "#7a8a6a",
        "shirt_line": "#566248",
        "acc": ("glasses", "mustache"),
    },
}
NAMES = NAMES | frozenset(ROLES)  # roles resolve to the rig too

# Casting — the Director picks a topic-appropriate host instead of the generic presenter:
# a farm lesson gets a farmer, a space lesson an astronaut, a science lesson a scientist.
# First keyword match wins; an unthemed topic stays the neutral presenter.
_CASTING: tuple[tuple[tuple[str, ...], str], ...] = (
    (("farm", "crop", "harvest", "tractor", "barn", "cattle", "plow", "garden"), "farmer"),
    (
        ("space", "planet", "rocket", "astronaut", "orbit", "galaxy", "mars", "solar", "cosmos"),
        "astronaut",
    ),
    (
        (
            "cell",
            "atom",
            "molecul",
            "dna",
            "experiment",
            "chemist",
            "laborator",
            "science",
            "scientif",
            "physics",
            "biolog",
            "virus",
            "element",
            "gene",
        ),
        "scientist",
    ),
    (
        (
            "hospital",
            "doctor",
            "health",
            "medicine",
            "disease",
            "illness",
            "organ",
            "blood",
            "heart",
            "lung",
            "anatomy",
            "nurse",
        ),
        "doctor",
    ),
    (("cook", "recipe", "kitchen", "bak", "chef", "cuisine", "meal"), "chef"),
    (("paint", "drawing", "sketch", "artist", "canvas", "museum"), "artist"),
    (
        ("king", "queen", "castle", "kingdom", "crown", "royal", "throne", "palace", "knight"),
        "king",
    ),
    (("magic", "wizard", "spell", "potion", "witch", "sorcer", "enchant", "dragon"), "wizard"),
    (("ocean", "pirate", "ship", "sail", "treasure"), "pirate"),
    (("police", "crime", "detective"), "police"),
    (("music", "song", "band", "instrument", "concert", "melody"), "dj"),
    (("school", "classroom", "teach", "student", "educat"), "teacher"),
)


def cast_for(topic: str | None, mode: str = "learn") -> str:
    """A topic → the host ROLE that best fits it (else the neutral presenter). Matches on WORD
    boundaries (a keyword is a whole word or a word stem) so 'baking' isn't cast as a 'king'."""
    import re

    t = (topic or "").lower()
    words = set(re.findall(r"[a-z]+", t))
    for keywords, role in _CASTING:
        for k in keywords:
            hit = (k in t) if " " in k else any(w == k or w.startswith(k) for w in words)
            if hit:
                return role
    return "presenter"


# Generic host/narrator concepts that a scene may RECAST to a fitting role; a concept that's
# already a specific role (scientist) or a thing (sun) is left untouched.
NEUTRAL_HOST = frozenset({"presenter", "guide", "host", "narrator", "character", "avatar", "buddy"})


def cast_concept(concept: str | None, scene_topic: str | None, mode: str = "learn") -> str:
    """Per-SCENE casting: a generic host concept becomes the role that fits THIS scene's
    setting/content; anything specific passes through unchanged."""
    c = (concept or "").strip().lower()
    return cast_for(scene_topic, mode) if c in NEUTRAL_HOST else (concept or "")


def _role_palette(role: str | None, theme: str | None) -> dict[str, str]:
    spec = ROLES.get((role or "").strip().lower())
    pal = dict(palette_for(theme))
    if spec:
        pal = {
            **pal,
            "skin": SKINS[spec["skin"]],
            "hair": HAIR_COLORS[spec["hair"]],
            "shirt": spec["shirt"],
            "shirt_line": spec["shirt_line"],
        }
        for k in ("hat", "cape", "cape_line"):
            if k in spec:
                pal[k] = spec[k]
        if theme in THEMES:  # an explicit theme still overrides the outfit color
            pal["shirt"], pal["shirt_line"] = THEMES[theme]["shirt"], THEMES[theme]["shirt_line"]
    return pal


def _accessories(role: str | None, layer: str, pal: dict[str, str]) -> list[Stroke]:
    spec = ROLES.get((role or "").strip().lower())
    out: list[Stroke] = []
    for name in (spec or {}).get("acc", ()):
        entry = _ACCESSORIES.get(name)
        if entry and entry[0] == layer:
            out += entry[1](pal)
    return out


_NECK = (0.0, _HEAD_C[1] - _HEAD_R * 0.75)  # head pivots here when it tilts (nod/look)


def _turn_body(strokes: list[Stroke], facing: float) -> list[Stroke]:
    """Foreshorten the torso+limbs for a body turn: squash x toward the facing side + shift,
    so a front-on rig reads as 3/4 (gentle) → side profile (|facing|~1, strong squash + lean)."""
    sx = 1.0 - 0.46 * abs(facing)  # narrows with the turn; ~0.54 at a full side profile
    shift = facing * 0.12  # the body leans toward the facing direction
    return [
        replace(st, points=tuple((round(x * sx + shift, 5), y) for x, y in st.points))
        for st in strokes
    ]


def _rotate_about(strokes: list[Stroke], pivot, deg: float) -> list[Stroke]:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    px, py = pivot

    def rp(x, y):
        dx, dy = x - px, y - py
        return (round(px + dx * c - dy * s, 5), round(py + dx * s + dy * c, 5))

    return [replace(st, points=tuple(rp(x, y) for x, y in st.points)) for st in strokes]


def build(
    pose: str | dict = "idle",
    expression: str = "happy",
    theme: str | None = None,
    character: str | None = None,
) -> tuple[Stroke, ...]:
    """Compose a cast character as colored Strokes (local ~2-unit box). `pose` is a library
    NAME or a pose DICT (limb angles + an optional `head` tilt); `character` selects a ROLE
    (teacher/scientist/…) — same rig + motion, different outfit. Unknown role → the presenter."""
    pal = _role_palette(character, theme)
    expression = expression if expression in EXPRESSIONS else "happy"
    resolved = _resolve_pose(pose)
    # FACING — a body turn (front/3-4/side). The torso+limbs narrow toward the facing side
    # (foreshortening) and the head turns to match, so the character isn't flatly front-on.
    facing = max(-1.0, min(1.0, float(resolved.get("facing", 0.0))))
    body: list[Stroke] = []
    body += _accessories(character, "back", pal)  # cape behind everything
    body += _limbs(resolved, pal, facing)  # legs + arms (far arm hidden in profile)
    body += _body(pal)
    body += _accessories(character, "torso", pal)  # coat, stethoscope
    if facing:
        body = _turn_body(body, facing)
    strokes: list[Stroke] = list(body)
    # The HEAD is a group (skull + hair + face + head accessories) so it can nod/tilt as one.
    # facing drives the head turn FULLY (a full body turn → a profile head).
    turn = max(-1.0, min(1.0, float(resolved.get("turn", 0.0)) + facing))
    head = [
        _translate(s, _HEAD_C) for s in _fill([g.circle(_HEAD_R)], pal["skin"], pal["skin_line"])
    ]
    head += _hair(pal)
    head += _face(expression, pal, turn=turn, blink=bool(resolved.get("blink")))
    acc = _accessories(character, "head", pal)  # glasses, hat, beard …
    if turn:  # head accessories follow the turn (glasses track the eyes; hats shift a touch)
        acc = [_translate(s, (turn * 0.07, 0.0)) for s in acc]
    head += acc
    tilt = float(resolved.get("head", 0.0))
    if tilt:
        head = _rotate_about(head, _NECK, tilt)
    strokes += head
    return tuple(s for s in strokes if len(s.points) >= 2)


# --------------------------------------------------------------------------- #
# Motion — interpolate between poses (shortest angular path) and synthesize clips.
# This is what makes the rig ACT instead of holding one frame.
# --------------------------------------------------------------------------- #
def _lerp_ang(a: float, b: float, t: float) -> float:
    d = ((b - a + 180) % 360) - 180  # shortest signed delta
    return (a + d * t) % 360.0


def interpolate(a, b, t: float) -> dict:
    """Blend two poses at t∈[0,1] — angles take the shortest arc, lengths lerp linearly."""
    pa, pb = _resolve_pose(a), _resolve_pose(b)
    out = {}
    for limb in ("l_arm", "r_arm", "l_leg", "r_leg"):
        s0, s1 = pa[limb], pb[limb]
        out[limb] = [
            _lerp_ang(s0[0], s1[0], t),
            s0[1] + (s1[1] - s0[1]) * t,
            _lerp_ang(s0[2], s1[2], t),
            s0[3] + (s1[3] - s0[3]) * t,
        ]
    for k in ("head", "turn", "facing"):  # head tilt + look-turn + body-facing all interpolate
        v0, v1 = pa.get(k, 0.0), pb.get(k, 0.0)
        out[k] = v0 + (v1 - v0) * t
    # blink is discrete — the eyes stay closed only in a short window AT a blink keyframe,
    # so a blink reads as a quick flick rather than a slow fade.
    if (pa.get("blink") and t < 0.3) or (pb.get("blink") and t > 0.7):
        out["blink"] = True
    return out


# Gesture clips — a keyframe path through the library. The renderer tweens between frames;
# the Director picks the clip from emotion/action (A5). Clips loop unless one-shot.
CLIPS: dict[str, dict] = {
    "wave": {"keys": ["idle", "wave", "idle", "wave", "idle"], "loop": False, "ease": "back"},
    "cheer": {"keys": ["idle", "cheer", "cheer", "idle"], "loop": False, "ease": "back"},
    "point": {"keys": ["idle", "point"], "loop": False, "hold": True, "ease": "back"},
    "present": {"keys": ["idle", "present"], "loop": False, "hold": True},
    "walk": {"keys": ["walk", "stand", "walk"], "loop": True},
    # jump: idle → CROUCH (anticipation) → jump → land, with an overshoot pop
    "jump": {"keys": ["idle", "crouch", "jump", "idle"], "loop": False, "ease": "back"},
    "nod": {"keys": ["idle", "agree", "idle", "agree", "idle"], "loop": False},
    "think": {"keys": ["idle", "think"], "loop": False, "hold": True},
    "explain": {
        "keys": ["idle", "explain", "idle", "explain", "idle"],
        "loop": False,
        "ease": "back",
    },
    "surprised": {"keys": ["idle", "surprised"], "loop": False, "hold": True, "ease": "back"},
    "celebrate": {"keys": ["idle", "cheer", "cheer", "idle"], "loop": False, "ease": "back"},
    "shrug": {"keys": ["idle", "shrug", "idle"], "loop": False},
    "clap": {"keys": ["idle", "clap", "shrug", "clap", "idle"], "loop": False, "ease": "back"},
    "hold": {"keys": ["idle", "hold"], "loop": False, "hold": True},
    "look_left": {"keys": ["idle", "look_left"], "loop": False, "hold": True},
    "look_right": {"keys": ["idle", "look_right"], "loop": False, "hold": True},
    "look_up": {"keys": ["idle", "look_up"], "loop": False, "hold": True},
    "turn_left": {"keys": ["idle", "turn_left"], "loop": False, "hold": True},
    "turn_right": {"keys": ["idle", "turn_right"], "loop": False, "hold": True},
    "side_left": {"keys": ["idle", "side_left"], "loop": False, "hold": True},
    "side_right": {"keys": ["idle", "side_right"], "loop": False, "hold": True},
    "walk_side": {"keys": ["side_right", "walk_side", "side_right"], "loop": True},
    # idle LIFE — a slow loop: rest, sway, blink, rest — so a held character breathes
    "alive": {
        "keys": ["idle", "sway_l", "idle", "idle", "blink", "idle", "sway_r", "idle"],
        "loop": True,
    },
    "idle": {"keys": ["idle"], "loop": True},
}


# Easing — timing is what makes simple art look good. We bake the curve into the FRAME
# SPACING (eased t between keyframes), so the board can flip at a constant rate and still
# read as accelerate/decelerate. `back` overshoots past the target then settles = the
# follow-through of a real gesture; anticipation is authored as a wind-up keyframe (crouch).
def _ease_smooth(t: float) -> float:  # ease-in-out (smoothstep)
    return t * t * (3 - 2 * t)


def _ease_back(t: float) -> float:  # ease-out with overshoot (follow-through)
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


_EASINGS = {"smooth": _ease_smooth, "back": _ease_back, "linear": lambda t: t}


def perform(clip: str, frames_per_key: int = 6) -> list[dict]:
    """Expand a gesture CLIP into EASED pose frames (a server-rendered flipbook). The clip's
    `ease` curve shapes the timing — punchy gestures overshoot + settle. Unknown clip → idle."""
    spec = CLIPS.get(clip, CLIPS["idle"])
    keys = [k for k in spec["keys"] if k in POSE_LIBRARY] or ["idle"]
    if len(keys) == 1:
        return [_resolve_pose(keys[0])]
    ease = _EASINGS.get(spec.get("ease", "smooth"), _ease_smooth)
    frames: list[dict] = []
    for i in range(len(keys) - 1):
        for f in range(frames_per_key):
            frames.append(interpolate(keys[i], keys[i + 1], ease(f / frames_per_key)))
    frames.append(_resolve_pose(keys[-1]))
    return frames


def loops(clip: str) -> bool:
    return bool(CLIPS.get(clip, CLIPS["idle"]).get("loop"))


def clip_drawables(
    clip: str,
    expression: str = "happy",
    theme: str | None = None,
    size: float = 2.8,
    frames_per_key: int = 6,
    character: str | None = None,
) -> list[tuple[Stroke, ...]]:
    """A gesture clip → per-frame rig strokes at a CONSISTENT scale (the body stays put,
    only the limbs move — the scale is fixed from idle so a raised-arm frame doesn't shrink
    the whole figure). `character` keeps the same ROLE (outfit/accessories) across the clip."""
    ref = build("idle", expression, theme, character)
    x0, y0, x1, y1 = g.strokes_bbox(ref)
    scale = size / max(x1 - x0, y1 - y0, 1e-6)
    return [
        g.transform(build(fp, expression, theme, character), 0.0, 0.0, scale)
        for fp in perform(clip, frames_per_key)
    ]


def is_character(concept: str) -> bool:
    return concept.strip().lower() in NAMES
