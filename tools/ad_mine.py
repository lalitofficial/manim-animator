"""Mine Meta's Amateur Drawings annotations → rig proportion priors + a pose library.

INPUT  (gitignored, MIT, ~288MB, download per docs/ROADMAP-assets.md):
    backend/engine/assets/animateddrawings/amateur_drawings_annotations.json
OUTPUT (committed — DERIVED measurements, not the images):
    backend/engine/character_proportions.json   limb-length ratios (median over clean figures)
    backend/engine/pose_library.json             named poses as rig limb-angles

COCO keypoints (17): 0 nose · 1/2 eyes · 3/4 ears · 5/6 shoulders · 7/8 elbows · 9/10 wrists ·
11/12 hips · 13/14 knees · 15/16 ankles. We map shoulder→elbow→wrist onto our rig's arm
(shoulder→elbow→hand) and hip→knee→ankle onto its leg. Each figure is converted to our rig frame
(y-up, origin at hip-mid), upright-canonicalized (torso rotated vertical so a leaning drawing
doesn't pollute angles), and reduced to 8 limb angles + length ratios. Run: `python tools/ad_mine.py`.
"""

from __future__ import annotations

import json
import math
import pathlib

import numpy as np

NOSE, LSH, RSH, LEL, REL, LWR, RWR, LHIP, RHIP, LKN, RKN, LAN, RAN = (
    0,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
)
_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SRC = _ROOT / "backend/engine/assets/animateddrawings/amateur_drawings_annotations.json"
_OUT = _ROOT / "backend/engine"
_RIG_TORSO = 0.40  # our rig's shoulder→hip span (character._SHOULDER_Y - _HIP_Y)


def _pts(kp: list[float]) -> np.ndarray:
    """51 flat COCO values → (17,3) array of (x, y_up, visibility)."""
    a = np.array(kp, float).reshape(17, 3)
    a[:, 1] = -a[:, 1]  # image y-down → rig y-up
    return a


def _ang(frm: np.ndarray, to: np.ndarray) -> float:
    """Angle of the vector frm→to in our rig convention (0°=right, 90°=up), degrees [0,360)."""
    return math.degrees(math.atan2(to[1] - frm[1], to[0] - frm[0])) % 360.0


def _clean(p: np.ndarray) -> np.ndarray | None:
    """Keep only figures with every limb joint labeled; rotate upright about hip-mid, scale so
    torso length = 1. Returns the canonical (17,2) positions, or None if unusable."""
    need = (LSH, RSH, LEL, REL, LWR, RWR, LHIP, RHIP, LKN, RKN, LAN, RAN)
    if any(p[j, 2] < 1 for j in need):
        return None
    xy = p[:, :2].copy()
    sh_mid = (xy[LSH] + xy[RSH]) / 2
    hip_mid = (xy[LHIP] + xy[RHIP]) / 2
    torso = float(np.linalg.norm(sh_mid - hip_mid))
    if torso < 1e-3:
        return None
    # rotate so the torso (hip_mid→sh_mid) points straight up (90°), about hip_mid
    theta = math.atan2(sh_mid[1] - hip_mid[1], sh_mid[0] - hip_mid[0])
    rot = math.radians(90) - theta
    c, s = math.cos(rot), math.sin(rot)
    xy = (xy - hip_mid) @ np.array([[c, -s], [s, c]]).T / torso
    return xy


def _circmean(degs: list[float]) -> float:
    r = np.deg2rad(degs)
    return round(math.degrees(math.atan2(np.sin(r).mean(), np.cos(r).mean())) % 360.0, 1)


def main() -> None:
    if not _SRC.exists():
        raise SystemExit(f"missing {_SRC} — download per docs/ROADMAP-assets.md (A0)")
    print(f"loading {_SRC.name} (~288MB)…")
    data = json.loads(_SRC.read_text())
    anns = data["annotations"]
    print(f"{len(anns)} annotations")

    ratios: dict[str, list[float]] = {
        k: []
        for k in (
            "upper_arm",
            "forearm",
            "thigh",
            "shin",
            "shoulder_w",
            "hip_w",
            "head",
            "leg",
            "arm",
        )
    }
    recs = []  # per clean figure: canonical positions + the 8 limb angles
    for a in anns:
        p = _pts(a["keypoints"])
        xy = _clean(p)
        if xy is None:
            continue
        d = lambda i, j, _xy=xy: float(np.linalg.norm(_xy[i] - _xy[j]))  # noqa: E731
        ratios["upper_arm"] += [d(LSH, LEL), d(RSH, REL)]
        ratios["forearm"] += [d(LEL, LWR), d(REL, RWR)]
        ratios["thigh"] += [d(LHIP, LKN), d(RHIP, RKN)]
        ratios["shin"] += [d(LKN, LAN), d(RKN, RAN)]
        ratios["shoulder_w"].append(d(LSH, RSH))
        ratios["hip_w"].append(d(LHIP, RHIP))
        ratios["head"].append(d(NOSE, LSH) if p[NOSE, 2] >= 1 else float("nan"))
        ratios["arm"] += [d(LSH, LEL) + d(LEL, LWR), d(RSH, REL) + d(REL, RWR)]
        ratios["leg"] += [d(LHIP, LKN) + d(LKN, LAN), d(RHIP, RKN) + d(RKN, RAN)]
        # screen-left limb = smaller x; canonicalize arm/leg by screen side
        lft, rgt = (
            (LSH, LEL, LWR) if xy[LSH, 0] < xy[RSH, 0] else (RSH, REL, RWR),
            (RSH, REL, RWR) if xy[LSH, 0] < xy[RSH, 0] else (LSH, LEL, LWR),
        )
        lfl, rfl = (
            (LHIP, LKN, LAN) if xy[LHIP, 0] < xy[RHIP, 0] else (RHIP, RKN, RAN),
            (RHIP, RKN, RAN) if xy[LHIP, 0] < xy[RHIP, 0] else (LHIP, LKN, LAN),
        )
        recs.append(
            {
                "xy": xy,
                "la_sh": _ang(xy[lft[0]], xy[lft[1]]),
                "la_el": _ang(xy[lft[1]], xy[lft[2]]),
                "ra_sh": _ang(xy[rgt[0]], xy[rgt[1]]),
                "ra_el": _ang(xy[rgt[1]], xy[rgt[2]]),
                "ll_hip": _ang(xy[lfl[0]], xy[lfl[1]]),
                "ll_kn": _ang(xy[lfl[1]], xy[lfl[2]]),
                "rl_hip": _ang(xy[rfl[0]], xy[rfl[1]]),
                "rl_kn": _ang(xy[rfl[1]], xy[rfl[2]]),
                "lwr": xy[lft[2]],
                "rwr": xy[rgt[2]],
                "lsh": xy[lft[0]],
                "rsh": xy[rgt[0]],
                "lan": xy[lfl[2]],
                "ran": xy[rfl[2]],
            }
        )
    n = len(recs)
    print(f"{n} clean figures ({100 * n / len(anns):.0f}% kept)")

    med = {k: round(float(np.nanmedian(v)), 3) for k, v in ratios.items()}
    proportions = {
        "_source": "Meta Amateur Drawings (MIT), median over clean figures",
        "_n_clean": n,
        "_unit": "ratio of standing torso length",
        **{k: med[k] for k in ("upper_arm", "forearm", "thigh", "shin", "shoulder_w", "hip_w")},
        "head": med["head"],
    }
    (_OUT / "character_proportions.json").write_text(json.dumps(proportions, indent=2))
    print("proportions:", {k: med[k] for k in ("upper_arm", "forearm", "thigh", "shin")})

    # ---- pose library: named poses by semantic filter, median angles over matches ---------- #
    up = _RIG_TORSO  # rig-local lengths from the mined ratios
    L = {
        "upper": med["upper_arm"] * up,
        "fore": med["forearm"] * up,
        "thigh": med["thigh"] * up,
        "shin": med["shin"] * up,
    }

    def _mirror(r: dict) -> dict:
        """Reflect a figure left↔right: angle a → (180−a), swap the l/r limb roles. Used to
        fold asymmetric gestures (a left-handed wave) onto one canonical side before averaging."""
        m = lambda a: (180.0 - a) % 360.0  # noqa: E731
        return {
            "la_sh": m(r["ra_sh"]),
            "la_el": m(r["ra_el"]),
            "ra_sh": m(r["la_sh"]),
            "ra_el": m(r["la_el"]),
            "ll_hip": m(r["rl_hip"]),
            "ll_kn": m(r["rl_kn"]),
            "rl_hip": m(r["ll_hip"]),
            "rl_kn": m(r["ll_kn"]),
        }

    def pose_from(sel, active=None) -> dict | None:
        """Median pose over figures matching `sel`. If `active` is given it returns 'l'/'r' for
        the gesturing arm, and we mirror so that arm is always screen-right before averaging."""
        ms = []
        for r in recs:
            if not sel(r):
                continue
            ms.append(_mirror(r) if (active and active(r) == "l") else r)
        if len(ms) < 200:
            return None
        a = {
            k: _circmean([r[k] for r in ms])
            for k in ("la_sh", "la_el", "ra_sh", "ra_el", "ll_hip", "ll_kn", "rl_hip", "rl_kn")
        }
        return {
            "_n": len(ms),
            "l_arm": [a["la_sh"], L["upper"], a["la_el"], L["fore"]],
            "r_arm": [a["ra_sh"], L["upper"], a["ra_el"], L["fore"]],
            "l_leg": [a["ll_hip"], L["thigh"], a["ll_kn"], L["shin"]],
            "r_leg": [a["rl_hip"], L["thigh"], a["rl_kn"], L["shin"]],
        }

    def above(r, w, s):  # wrist above its shoulder (y)
        return r[w][1] > r[s][1]

    def _active_up(r):  # which arm is raised
        return "r" if above(r, "rwr", "rsh") else "l"

    def _active_out(r):  # which arm reaches farther horizontally
        return "r" if abs(r["rwr"][0]) > abs(r["lwr"][0]) else "l"

    filters = {
        # both hands up
        "cheer": lambda r: above(r, "lwr", "lsh") and above(r, "rwr", "rsh"),
        # arms down, hands near the body center
        "idle": lambda r: (
            not above(r, "lwr", "lsh")
            and not above(r, "rwr", "rsh")
            and abs(r["lwr"][0]) < 0.6
            and abs(r["rwr"][0]) < 0.6
        ),
        # arms down-and-out (welcoming)
        "present": lambda r: (
            not above(r, "lwr", "lsh")
            and not above(r, "rwr", "rsh")
            and r["lwr"][0] < r["lsh"][0] - 0.15
            and r["rwr"][0] > r["rsh"][0] + 0.15
        ),
        # legs apart with a knee bend (a stride)
        "walk": lambda r: abs(r["lan"][0] - r["ran"][0]) > 0.7,
        # legs together, straight — a clean stand
        "stand": lambda r: abs(r["lan"][0] - r["ran"][0]) < 0.35,
    }
    # asymmetric gestures — mirror the active arm to screen-right before averaging
    asym = {
        # exactly one hand raised (a wave)
        "wave": (lambda r: above(r, "rwr", "rsh") != above(r, "lwr", "lsh"), _active_up),
        # one hand reaching far out sideways near shoulder height, the other low (a point)
        "point": (
            lambda r: (
                max(abs(r["lwr"][0]), abs(r["rwr"][0])) > 0.9
                and not (above(r, "lwr", "lsh") and above(r, "rwr", "rsh"))
            ),
            _active_out,
        ),
    }
    poses = {}
    for name, sel in filters.items():
        pose = pose_from(sel)
        if pose:
            poses[name] = pose
            print(f"  pose {name:9} from {pose.pop('_n')} figures")
    for name, (sel, active) in asym.items():
        pose = pose_from(sel, active)
        if pose:
            poses[name] = pose
            print(f"  pose {name:9} from {pose.pop('_n')} figures (mirrored)")
    poses["_source"] = "Meta Amateur Drawings (MIT) — median limb angles per named filter"
    poses["_n_clean"] = n
    (_OUT / "pose_library.json").write_text(json.dumps(poses, indent=2))
    print(f"wrote {len([k for k in poses if not k.startswith('_')])} poses → pose_library.json")


if __name__ == "__main__":
    main()
