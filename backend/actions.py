"""Action protocol for the v2 live-board engine: streamed lines, not scenes.

The model emits ONE action per line (NDJSON) and the server validates,
lays out, and forwards each action the moment its line closes — so the gap
between board actions is the cost of ~30 tokens, not a whole segment.

Action lines the model may emit:
  {"say":  "a sentence spoken while drawing"}
  {"add":  {SceneObject IR}}
  {"play": {Step IR}}
  {"macro":"label","of":id,"text":str}            label an existing object
  {"macro":"flow","from":id,"to":id,"text":str?}  arrow between two objects
  {"clear": true}
  {"end":  true}                                  stream finished (early stop)

Validation is per line and *destructive, never blocking*: a malformed line
is dropped (costs nothing) instead of triggering a repair regeneration
(costs a full LLM pass). Geometry is not trusted from the model at all —
every `add` runs through the layout solver below, which clamps to frame and
resolves collisions deterministically.
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from ir import SceneObject, Step

FRAME_X, FRAME_Y = 6.6, 3.6  # usable half-extents (frame is 14.2 x 8)
MIN_DUR, MAX_DUR = 0.6, 2.5  # pacing clamp: keep playback ~ generation rate

_LINE_JSON = re.compile(r"\{.*\}")


# --------------------------------------------------------------------------- #
# Approximate extents — the solver's model of every object as a centered box.
# Coarse on purpose: it only has to prevent gross overlap, not kern text.
# --------------------------------------------------------------------------- #
_ASSET_BOXES = {
    "stick_figure": (1.4, 2.2),
    "road": (14.0, 1.6),
    "car": (2.4, 1.4),
    "tree": (1.7, 2.2),
    "house": (2.2, 2.6),
    "sun": (2.5, 2.5),
    "cloud": (2.4, 1.4),
    "mountain": (3.0, 2.0),
    "building": (1.6, 3.2),
    "book": (1.5, 1.9),
    "bulb": (1.2, 1.5),
    "dot_label": (0.3, 0.3),
}


def approx_extent(o: SceneObject) -> tuple[float, float]:
    """(width, height) of the object's bounding box, scale applied."""
    t = o.type
    if t in ("text", "mathtex"):
        n = len(o.text or o.tex or "")
        h = (o.font_size or 40) / 48
        # 0.62 em/char: sans glyphs run wider than the classic 0.5 guess, and
        # underestimating text width is exactly how labels end up overprinting.
        w, hh = max(0.6, 0.62 * h * n), h
    elif t == "circle":
        w = hh = 2 * (o.radius or 1)
    elif t == "square":
        w = hh = o.width or 2
    elif t == "rectangle":
        w, hh = o.width or 2, o.height or 1
    elif t in ("triangle", "polygon") and o.points:
        xs = [p[0] for p in o.points]
        ys = [p[1] for p in o.points]
        w, hh = max(xs) - min(xs), max(ys) - min(ys)
    elif t in ("line", "arrow"):
        s, e = o.start or (0, 0, 0), o.end or (1, 0, 0)
        w, hh = abs(e[0] - s[0]), abs(e[1] - s[1])
    elif t == "asset":
        from assets import resolve

        w, hh = _ASSET_BOXES.get(resolve(o.asset or ""), (2.0, 2.0))
    else:  # dot, group, unknown
        w, hh = 0.5, 0.5
    return w * (o.scale or 1), hh * (o.scale or 1)


def _center(o: SceneObject) -> tuple[float, float]:
    if o.type in ("line", "arrow") and o.start and o.end:
        return ((o.start[0] + o.end[0]) / 2, (o.start[1] + o.end[1]) / 2)
    if o.points:
        xs = [p[0] for p in o.points]
        ys = [p[1] for p in o.points]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    return (o.position[0], o.position[1])


# --------------------------------------------------------------------------- #
# Layout solver
# --------------------------------------------------------------------------- #
TITLE_Y = 2.5  # content lives below this line; the title band is reserved
PAD = 0.18  # breathing room added around every registered box

# Content panels: a teacher fills one column, then the next, then wipes.
PANELS = {
    "full": (-FRAME_X, -FRAME_Y, FRAME_X, TITLE_Y),
    "left": (-FRAME_X, -FRAME_Y, -0.3, TITLE_Y),
    "right": (0.3, -FRAME_Y, FRAME_X, TITLE_Y),
}


class BoardLayout:
    """Tracks every placed box; compiles anchors to geometry.

    The model speaks teacher-spatial-language — regions ("top-left"),
    relations ("near X", "on X", "between X and Y") — and this class turns
    it into coordinates: anchor resolution, then clamping into the active
    panel, then minimum-penetration collision separation (existing boxes
    never move — the teacher doesn't shuffle what's already drawn).
    """

    def __init__(self):
        self.boxes: dict[str, tuple[float, float, float, float]] = {}  # id -> cx,cy,w,h
        self.panel = PANELS["full"]

    def summary(self) -> str:
        if not self.boxes:
            return "(the board is empty)"
        return "; ".join(f'"{i}" at [{b[0]:g},{b[1]:g}]' for i, b in self.boxes.items())

    def ids(self) -> set[str]:
        return set(self.boxes)

    def clear(self):
        self.boxes.clear()

    def remove(self, oid: str):
        self.boxes.pop(oid, None)

    def set_panel(self, name: str):
        self.panel = PANELS.get(name, PANELS["full"])

    def register(self, o: SceneObject):
        """Track a box verbatim (no clamping) — for the title band."""
        w, h = approx_extent(o)
        self.boxes[o.id] = (o.position[0], o.position[1], w, h)

    def move(self, oid: str, to) -> tuple[float, float]:
        """Update a box's position, de-colliding the destination.
        Returns the (possibly adjusted) destination for the step to use."""
        if oid not in self.boxes:
            return (to[0], to[1])
        _, _, w, h = self.boxes.pop(oid)  # don't collide with our own old box
        cx, cy = self._clamp(to[0], to[1], w, h)
        for _ in range(10):
            pen = self._worst_overlap(cx, cy, w, h)
            if pen is None:
                break
            cx, cy = self._clamp(cx + pen[0], cy + pen[1], w, h)
        self.boxes[oid] = (cx, cy, w, h)
        return (cx, cy)

    def place(
        self, o: SceneObject, anchors: dict | None = None, had_position: bool = True
    ) -> SceneObject:
        """Resolve anchors -> clamp into the panel -> de-collide -> register."""
        w, h = approx_extent(o)
        fixed = o.type in ("line", "arrow") or bool(o.points)  # self-positioned: box as-is
        cx, cy = _center(o)
        if not fixed:
            spot = self._anchor_spot(anchors or {}, w, h)
            if spot is not None:
                cx, cy = spot
            elif not had_position:
                cx, cy = self._flow_spot(w, h)  # no hint at all: first free slot
            cx, cy = self._clamp(cx, cy, w, h)
            for _ in range(10):
                pen = self._worst_overlap(cx, cy, w, h)
                if pen is None:
                    break
                cx, cy = self._clamp(cx + pen[0], cy + pen[1], w, h)
            o.position = (cx, cy, 0.0)
        self.boxes[o.id] = (cx, cy, w, h)
        return o

    # -- anchor resolution -------------------------------------------------
    def _anchor_spot(self, a: dict, w: float, h: float):
        if a.get("at"):
            return self._region_point(str(a["at"]), w, h)
        if a.get("on") in self.boxes:  # standing on: bottom touches top
            ox, oy, ow, oh = self.boxes[a["on"]]
            return (ox, oy + oh / 2 + h / 2)
        if a.get("near") in self.boxes:
            return self._side_spot(a["near"], w, h, str(a.get("side") or ""))
        between = a.get("between")
        if (
            isinstance(between, list)
            and len(between) >= 2
            and all(b in self.boxes for b in between[:2])
        ):
            (ax, ay, *_), (bx, by, *_) = self.boxes[between[0]], self.boxes[between[1]]
            return ((ax + bx) / 2, (ay + by) / 2)
        return None

    def _region_point(self, name: str, w: float, h: float):
        x0, y0, x1, y1 = self.panel
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ml, mb = w / 2 + 0.4, h / 2 + 0.4  # margins off the panel edge
        pts = {
            "center": (cx, cy),
            "top": (cx, y1 - mb),
            "bottom": (cx, y0 + mb),
            "left": (x0 + ml, cy),
            "right": (x1 - ml, cy),
            "top-left": (x0 + ml, y1 - mb),
            "top-right": (x1 - ml, y1 - mb),
            "bottom-left": (x0 + ml, y0 + mb),
            "bottom-right": (x1 - ml, y0 + mb),
        }
        return pts.get(name.strip().lower().replace("_", "-"))

    def _side_spot(self, of_id: str, w: float, h: float, side: str = ""):
        """Best free spot beside `of_id`: score candidate sides by overlap
        area + panel violation, take the minimum (greedy discrete argmin)."""
        cx, cy, ow, oh = self.boxes[of_id]
        pad = 0.35
        sides = {
            "below": (cx, cy - oh / 2 - h / 2 - pad),
            "above": (cx, cy + oh / 2 + h / 2 + pad),
            "right": (cx + ow / 2 + w / 2 + pad, cy),
            "left": (cx - ow / 2 - w / 2 - pad, cy),
        }
        if side in sides:
            return sides[side]
        x0, y0, x1, y1 = self.panel
        best, best_score = None, float("inf")
        for px, py in sides.values():
            score = self._overlap_area(px, py, w, h)
            score += 10 * (
                max(0, x0 - (px - w / 2))
                + max(0, (px + w / 2) - x1)
                + max(0, y0 - (py - h / 2))
                + max(0, (py + h / 2) - y1)
            )
            if score < best_score:
                best, best_score = (px, py), score
        return best

    def _flow_spot(self, w: float, h: float):
        """First zero-overlap slot scanning the panel top-down, left-right —
        how a hand fills a board when nothing dictates the spot."""
        x0, y0, x1, y1 = self.panel
        step = 0.7
        y = y1 - h / 2 - 0.3
        while y >= y0 + h / 2:
            x = x0 + w / 2 + 0.3
            while x <= x1 - w / 2:
                if self._overlap_area(x, y, w, h) == 0:
                    return (x, y)
                x += step
            y -= step
        return ((x0 + x1) / 2, (y0 + y1) / 2)  # crowded: center; separation shoves

    def label_spot(self, of_id: str, text: str, font_size: float = 26) -> tuple[float, float]:
        lh = font_size / 48
        lw = max(0.6, 0.62 * lh * len(text))
        return self._side_spot(of_id, lw, lh) or (0, 0)

    def edge_points(self, a: str, b: str) -> tuple[tuple, tuple]:
        """Arrow endpoints between two boxes: centers pulled back to the
        box borders along the center line, so arrows touch, not pierce."""
        ax, ay, aw, ah = self.boxes.get(a, (0, 0, 1, 1))
        bx, by, bw, bh = self.boxes.get(b, (1, 1, 1, 1))
        dx, dy = bx - ax, by - ay
        L = (dx * dx + dy * dy) ** 0.5 or 1.0
        ux, uy = dx / L, dy / L
        ra = 0.5 * min(aw, ah) + 0.15
        rb = 0.5 * min(bw, bh) + 0.15
        return ((ax + ux * ra, ay + uy * ra), (bx - ux * rb, by - uy * rb))

    # -- internals --
    def _clamp(self, cx, cy, w, h):
        """Project the center into the active panel (feasibility region)."""
        x0, y0, x1, y1 = self.panel
        lo_x, hi_x = x0 + w / 2, x1 - w / 2
        lo_y, hi_y = y0 + h / 2, y1 - h / 2
        cx = (x0 + x1) / 2 if lo_x > hi_x else max(lo_x, min(hi_x, cx))
        cy = (y0 + y1) / 2 if lo_y > hi_y else max(lo_y, min(hi_y, cy))
        return cx, cy

    def _overlap_area(self, cx, cy, w, h) -> float:
        area = 0.0
        for ox, oy, ow, oh in self.boxes.values():
            ow, oh = ow + 2 * PAD, oh + 2 * PAD
            ix = min(cx + w / 2, ox + ow / 2) - max(cx - w / 2, ox - ow / 2)
            iy = min(cy + h / 2, oy + oh / 2) - max(cy - h / 2, oy - oh / 2)
            if ix > 0 and iy > 0:
                area += ix * iy
        return area

    def _worst_overlap(self, cx, cy, w, h) -> tuple[float, float] | None:
        """Minimum-penetration push vector out of the deepest overlap."""
        worst, push = 0.0, None
        for ox, oy, ow, oh in self.boxes.values():
            ow, oh = ow + 2 * PAD, oh + 2 * PAD
            ix = min(cx + w / 2, ox + ow / 2) - max(cx - w / 2, ox - ow / 2)
            iy = min(cy + h / 2, oy + oh / 2) - max(cy - h / 2, oy - oh / 2)
            if ix > 0.05 and iy > 0.05 and ix * iy > worst:
                worst = ix * iy
                if ix < iy:  # cheapest escape is horizontal
                    push = (ix if cx >= ox else -ix, 0.0)
                else:
                    push = (0.0, iy if cy >= oy else -iy)
        return push


# --------------------------------------------------------------------------- #
# Line validation + macro expansion
# --------------------------------------------------------------------------- #
# Default durations by animation when the model omits one — set so playback
# mass per draw token clears the saturation bound (PAPER.md §4.7). Drawing
# slowly is also simply how teachers draw. Behavior verbs are performances:
# give them room to play out.
_DEFAULT_DUR = {
    "write": 1.6,
    "create": 1.6,
    "move": 1.5,
    "transform": 1.5,
    "fadein": 1.0,
    "fadeout": 1.0,
    "scale": 1.0,
    "wait": 1.0,
    "spin": 2.5,
    "orbit": 3.0,
    "bounce": 1.8,
    "wave": 2.2,
    "dance": 3.5,
    "walk": 3.0,
}
VERB_MAX_DUR = 6.0  # performances may run longer than draw strokes


VERBS = {"spin", "orbit", "bounce", "wave", "dance", "walk"}


def _clamp_step(s: Step) -> Step:
    hi = VERB_MAX_DUR if s.animation in VERBS else MAX_DUR
    s.duration = max(MIN_DUR, min(hi, float(s.duration or 1.0)))
    return s


def parse_action_line(
    line: str, layout: BoardLayout, seg_ids: set[str], meta: dict | None = None
) -> list[dict]:
    """One NDJSON line -> zero or more board actions (already laid out).

    Returns [] for junk — dropping a bad line is free; regenerating isn't.
    `seg_ids` accumulates ids added in the current segment (for auto-reveal).
    `meta`, if given, collects {"title": ..., "plan": [...]} lines (call 1).
    """
    m = _LINE_JSON.search(line)
    if not m:
        return []
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    return actions_from_dict(d, layout, seg_ids, meta)


def actions_from_dict(
    d, layout: BoardLayout, seg_ids: set[str], meta: dict | None = None
) -> list[dict]:
    if not isinstance(d, dict):
        return []

    if meta is not None and ("title" in d or "plan" in d or "segments" in d):
        if "title" in d:
            meta["title"] = d["title"]
        plan = d.get("plan") or d.get("segments")
        if isinstance(plan, list) and plan:
            meta["plan"] = plan
        return []
    if d.get("end"):
        return [{"kind": "end"}]
    if d.get("clear"):
        # A teacher wipes the board *before* a new part, never mid-thought:
        # once this segment has put anything up, clear lines are dropped.
        if seg_ids:
            return []
        layout.clear()
        return [{"kind": "clear"}]
    if "say" in d:
        # A block can carry narration AND a payload (common when a model
        # pretty-prints several actions into one object) — emit both.
        text = str(d.pop("say") or "").strip()
        out = [{"kind": "say", "text": text}] if text else []
        return (
            out + actions_from_dict(d, layout, seg_ids, meta)
            if any(
                k in d
                for k in ("add", "object", "play", "step", "animation", "macro", "clear", "id")
            )
            else out
        )

    if "add" in d or "object" in d or ("id" in d and "type" in d):
        raw = d.get("add") or d.get("object") or d
        anchors, had_position = {}, True
        if isinstance(raw, dict):
            had_position = "position" in raw
            for k in ("at", "near", "side", "on", "between"):
                if k in raw:
                    anchors[k] = raw.pop(k)
        try:
            obj = SceneObject.model_validate(_coerce_obj(raw))
        except (ValidationError, ValueError):
            return []
        if obj.id in layout.ids():
            # Re-adding something on the board = the teacher gesturing at it.
            # A pulse (scale up, scale back) shows the intent; dropping the
            # line would buy silence with the same tokens.
            return [
                {
                    "kind": "play",
                    "step": Step(
                        animation="scale", target=obj.id, factor=1.15, duration=0.5
                    ).model_dump(),
                },
                {
                    "kind": "play",
                    "step": Step(
                        animation="scale", target=obj.id, factor=1 / 1.15, duration=0.5
                    ).model_dump(),
                },
            ]
        # Size sanity: a sun the size of a dot, or 8px text, reads as a bug.
        if obj.type == "asset":
            obj.scale = max(obj.scale or 1.0, 0.55)
        elif obj.type in ("text", "mathtex"):
            obj.font_size = max(obj.font_size or 40, 20)
        if obj.type != "group":
            layout.place(obj, anchors, had_position)
        seg_ids.add(obj.id)
        return [{"kind": "add", "object": obj.model_dump()}]

    if "play" in d or "step" in d or "animation" in d:
        raw = d.get("play") or d.get("step") or d
        if isinstance(raw, dict) and "duration" not in raw:
            raw["duration"] = _DEFAULT_DUR.get(raw.get("animation"), 1.0)
        try:
            step = _clamp_step(Step.model_validate(raw))
        except (ValidationError, ValueError):
            return []
        known = layout.ids() | seg_ids
        if step.animation != "wait":
            if not step.target or step.target not in known:
                return []
            if step.animation == "transform" and (step.into not in known):
                return []
            if step.animation == "orbit" and (step.around not in known):
                return []
        if step.animation == "fadeout" and step.target:
            layout.remove(step.target)
        elif step.animation in ("move", "walk") and step.target and step.to:
            # The destination is de-collided too — a moved object must not
            # land on something already drawn.
            nx, ny = layout.move(step.target, step.to)
            step.to = (nx, ny, 0.0)
        return [{"kind": "play", "step": step.model_dump()}]

    if "macro" in d:
        return _expand_macro(d, layout, seg_ids)
    return []


def _coerce_obj(raw: dict) -> dict:
    """Same nudge as planner._coerce, per object: unknown type -> asset."""
    from planner import IR_TYPES

    if isinstance(raw, dict):
        t = raw.get("type")
        if t not in IR_TYPES:
            raw["asset"] = raw.get("asset") or raw.get("name") or t or "asset"
            raw["type"] = "asset"
        if raw.get("type") == "asset" and not raw.get("asset"):
            raw["asset"] = raw.get("name") or "asset"
    return raw


_macro_n = 0


def _mid(prefix: str) -> str:
    global _macro_n
    _macro_n += 1
    return f"{prefix}_{_macro_n}"


def _expand_macro(d: dict, layout: BoardLayout, seg_ids: set[str]) -> list[dict]:
    """A macro is one cheap line that expands into several laid-out actions."""
    name = str(d.get("macro", "")).lower()

    if name == "label" and d.get("of") in layout.ids():
        text = str(d.get("text", "")).strip()
        if not text:
            return []
        x, y = layout.label_spot(d["of"], text)
        obj = SceneObject(
            id=_mid(f"{d['of']}_lbl"),
            type="text",
            text=text,
            font_size=26,
            position=(x, y, 0.0),
            color=str(d.get("color") or "#C9D1D9"),
        )
        layout.place(obj)
        seg_ids.add(obj.id)
        return [
            {"kind": "add", "object": obj.model_dump()},
            {
                "kind": "play",
                "step": Step(animation="write", target=obj.id, duration=1.4).model_dump(),
            },
        ]

    if name == "flow" and d.get("from") in layout.ids() and d.get("to") in layout.ids():
        (sx, sy), (ex, ey) = layout.edge_points(d["from"], d["to"])
        arrow = SceneObject(
            id=_mid("flow"),
            type="arrow",
            start=(sx, sy, 0.0),
            end=(ex, ey, 0.0),
            color=str(d.get("color") or "#E6EDF3"),
        )
        layout.place(arrow)
        seg_ids.add(arrow.id)
        out = [
            {"kind": "add", "object": arrow.model_dump()},
            {
                "kind": "play",
                "step": Step(animation="create", target=arrow.id, duration=1.4).model_dump(),
            },
        ]
        text = str(d.get("text", "")).strip()
        if text:
            lbl = SceneObject(
                id=_mid("flow_lbl"),
                type="text",
                text=text,
                font_size=24,
                position=((sx + ex) / 2, (sy + ey) / 2 + 0.45, 0.0),
                color="#8B949E",
            )
            layout.place(lbl)
            seg_ids.add(lbl.id)
            out += [
                {"kind": "add", "object": lbl.model_dump()},
                {
                    "kind": "play",
                    "step": Step(animation="write", target=lbl.id, duration=0.8).model_dump(),
                },
            ]
        return out
    return []


class LineAssembler:
    """Feed raw stream lines, get actions — tolerant of pretty-printing.

    Fast path: a complete JSON object on one line. Slow path: a line that
    *opens* an object without closing it starts an accumulator; lines are
    appended until braces balance, then the whole block parses at once.
    This recovers models that pretty-print the {"title"/"plan"} block (or
    any action) across lines, without giving up per-line streaming.
    """

    _SAY_RE = re.compile(r'"say"\s*:\s*"((?:\\.|[^"\\])*)"')

    def __init__(
        self,
        layout: BoardLayout,
        seg_ids: set[str],
        meta: dict | None = None,
        max_pending: int = 4000,
    ):
        self.layout, self.seg_ids, self.meta = layout, seg_ids, meta
        self.max_pending = max_pending
        self.pending = ""
        self._said: set[str] = set()  # says already emitted from this block

    def feed(self, line: str) -> list[dict]:
        if self.pending:
            self.pending += "\n" + line
            if self.pending.count("{") <= self.pending.count("}"):
                block, self.pending = self.pending, ""
                acts = self._parse_block(block)
                # Don't double-speak says that were emitted early below.
                return [a for a in acts if not (a["kind"] == "say" and a["text"] in self._said)]
            if len(self.pending) > self.max_pending:
                self.pending = ""  # runaway block: abandon, resume line mode
                return []
            # The board shouldn't sit silent while a block accumulates:
            # surface any completed "say" string immediately.
            early = []
            for m in self._SAY_RE.finditer(self.pending):
                try:
                    text = json.loads(f'"{m.group(1)}"')
                except json.JSONDecodeError:
                    continue
                if text.strip() and text not in self._said:
                    self._said.add(text)
                    early.append({"kind": "say", "text": text})
            return early
        acts = parse_action_line(line, self.layout, self.seg_ids, self.meta)
        if acts:
            return acts
        s = line.strip().strip("`")
        if s and s.count("{") > s.count("}"):
            self.pending = line
        return []

    def flush(self, tail: str = "") -> list[dict]:
        block = (self.pending + "\n" + tail).strip()
        self.pending = ""
        return self._parse_block(block) if block else []

    def _parse_block(self, block: str) -> list[dict]:
        m = re.search(r"\{.*\}", block, re.DOTALL)
        if not m:
            return []
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
        return actions_from_dict(d, self.layout, self.seg_ids, self.meta)


def auto_reveal(seg_ids: set[str], played: set[str]) -> list[dict]:
    """End-of-segment safety net: a play for every added-but-never-animated id."""
    out = []
    for oid in seg_ids - played:
        out.append(
            {
                "kind": "play",
                "step": Step(animation="create", target=oid, duration=1.4).model_dump(),
            }
        )
    return out
