"""Scene IR — the renderer-agnostic intermediate representation.

This is the contract between the *planner* (text -> IR) and any *renderer*
(IR -> pixels). Manim is the first renderer; a web/canvas renderer for the
realtime board (Phase 2) will consume the exact same schema.

Design rules:
- Objects are declared once with a stable `id`.
- Steps reference objects by `id` and run in order on a timeline.
- Coordinates are Manim-style 3D [x, y, z]; origin is screen center,
  +y is up. Most 2D scenes use z=0. The frame is ~14.2 wide x 8 tall.
- Keep it small and explicit. Add fields only when a renderer needs them.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _to_vec3(v):
    """Accept [x, y] or [x, y, z]; pad a 2D point to z=0.

    The board is flat, so models naturally emit 2D coordinates — normalize
    them here instead of forcing every point to carry a trailing zero.
    """
    if isinstance(v, (list, tuple)):
        vals = [float(x) for x in v]
        if len(vals) == 2:
            vals.append(0.0)
        if len(vals) == 3:
            return tuple(vals)
    raise ValueError("expected [x, y] or [x, y, z]")


Vec3 = Annotated[tuple[float, float, float], BeforeValidator(_to_vec3)]

ObjectType = Literal[
    "text",
    "mathtex",
    "circle",
    "square",
    "rectangle",
    "triangle",
    "polygon",
    "line",
    "arrow",
    "dot",
    "asset",  # a named composite from the asset library (man, road, car, ...)
    "group",  # a VGroup of other objects, referenced by `members`
]

AnimationType = Literal[
    "write",  # text appears as if written (text/mathtex)
    "create",  # shape draws itself
    "fadein",
    "fadeout",
    "move",  # move an existing object to `to`
    "scale",  # scale by `factor`
    "transform",  # morph `target` into object `into`
    "wait",  # no-op pause
    # Behavior verbs — performed by the live renderer (runtime kinematics,
    # zero extra tokens). The offline Manim renderer skips them gracefully.
    "spin",  # rotate in place; on a globe, phase-shift the meridians
    "orbit",  # circle the target around object `around`
    "bounce",  # vertical hops in place
    "wave",  # rig: wave a hand
    "dance",  # rig: dance cycle
    "walk",  # rig: walk cycle, moving to `to` if given
]


class SceneObject(BaseModel):
    id: str = Field(..., description="Stable unique id referenced by steps.")
    type: ObjectType
    # text / mathtex
    text: str | None = None
    tex: str | None = None
    font_size: float = 40
    # geometry
    radius: float = 1.0
    width: float = 2.0
    height: float = 1.0
    start: Vec3 | None = None
    end: Vec3 | None = None
    # triangle / polygon: explicit vertices (triangle defaults to equilateral if omitted)
    points: list[Vec3] | None = None
    # asset: name from the library (or an alias); params passed to its factory
    asset: str | None = None
    params: dict = Field(default_factory=dict)
    # group: ids of previously-declared objects to bundle into one VGroup
    members: list[str] | None = None
    # common
    position: Vec3 = (0.0, 0.0, 0.0)
    scale: float = 1.0
    color: str = "#FFFFFF"


class Step(BaseModel):
    animation: AnimationType
    target: str | None = Field(None, description="Object id this step acts on.")
    into: str | None = Field(None, description="For 'transform': id to morph into.")
    to: Vec3 | None = Field(None, description="For 'move'/'walk': destination.")
    factor: float = Field(1.5, description="For 'scale'.")
    around: str | None = Field(None, description="For 'orbit': center object id.")
    revs: float = Field(1.0, description="For 'spin'/'orbit': revolutions.")
    duration: float = 1.0


class Scene(BaseModel):
    title: str = "Untitled"
    background: str = "#0E1116"
    objects: list[SceneObject] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)

    def object_ids(self) -> set[str]:
        return {o.id for o in self.objects}
