"""The cartoon DIRECTION grammar + compiler (docs/CARTOON.md).

The layered plan a director emits BEFORE anything is drawn — the language between vague
Beats and concrete pixels:

    DirectorSpec → LessonPlan → ScenePlan → Shot → Action → [compile] → events → renderer

A Scene has a SETTING (where) and a CAST (who). A Shot has FRAMING (camera) + a set of
ACTIONS (semantic verbs on actors, with timing) + NARRATION. `compile_plan` turns this
into the timed event stream the vector renderer already understands (start/background/
camera/draw/say/action/clear/done) — reusing measure (drawing), compose_cartoon (staging),
the camera, and paint. The engine owns geometry/timing/framing; the plan owns intent.

`lift_beats` lifts the old flat Beats into a single-scene LessonPlan, so the existing
content runs through the SAME compiler (no fork). The Story engine will emit LessonPlans
directly next; for now the bring-your-own lane + templates can author them.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field, replace

from engine import character, palette
from engine.contracts import (
    Beat,
    Board,
    Connector,
    Drawable,
    Extent,
    Mark,
    Relation,
    Thing,
    split_paint_attrs,
)
from engine.drawing import measure, paint
from engine.layout import _band, compose_cartoon
from engine.positioning import place
from engine.route import route
from engine.serialize import op_to_dict

# The motion language — a CLOSED, reusable verb vocabulary (semantic, not per-object).
# Each verb is one parameterized transform-over-time the renderer applies to ANY actor.
VERBS = frozenset(
    {
        "exit",
        "rise",
        "fall",
        "flow",
        "pulse",
        "emphasize",
        "grow",
        "shrink",
        "point",
        "look",
        "transform",
        "connect",
        "wobble",
    }
)
_DUR_MS = {"short": 450, "med": 800, "long": 1300}
_HOLD_MS = {"none": 0, "short": 250, "med": 480, "long": 950}  # the pause/beat after a shot
_HOST_POSE = {"learn": "present", "draw": "present", "explain": "point", "story": "wave"}

# A scene's EMOTION (how it should feel) and PURPOSE (why it exists) are first-class
# director intent — the felt layer above staging. Both are CLOSED sets; emotion carries
# the visible weight: it sets the host's face, scales the post-shot pause, and warms the
# backdrop (palette.apply_mood). Purpose nudges structural defaults (framing/hold).
EMOTIONS = frozenset({"calm", "curious", "wonder", "tense", "joyful"})
PURPOSES = frozenset({"introduce", "explain", "contrast", "build", "resolve"})
# emotion -> the presenter's expression (character.EXPRESSIONS = neutral/happy/surprised/curious)
_EMOTION_FACE = {
    "calm": "happy",
    "curious": "curious",
    "wonder": "surprised",
    "tense": "neutral",
    "joyful": "happy",
}
# emotion -> a multiplier on the post-shot hold: tension COMPRESSES (urgency), wonder/calm
# let a beat BREATHE. Pacing is felt, so the same `hold="med"` reads differently per mood.
_EMOTION_PACE = {"tense": 0.5, "calm": 1.4, "wonder": 1.5, "curious": 1.0, "joyful": 1.1}
# purpose -> the host's body language (pose). The scene's JOB shapes how the presenter
# stands: greet on introduce, open-handed to explain, point to contrast two things.
_PURPOSE_POSE = {
    "introduce": "wave",
    "explain": "present",
    "contrast": "point",
    "build": "present",
    "resolve": "present",
}
# emotion -> the host's ENTRANCE gesture clip (character.CLIPS). The presenter ACTS its mood
# on arrival — a joyful host cheers, a curious one waves — instead of holding one frame.
_EMOTION_CLIP = {
    "joyful": "cheer",
    "curious": "explain",
    "wonder": "surprised",
    "calm": "present",
    "tense": "alive",  # even a still, tense host breathes (idle sway + blink), never frozen
}


def _host_clip_frames(thing: Thing, p, d: Drawable, style: str, scene, clip: str):
    """Render a gesture CLIP for the host into placed+painted frame strokes (a server-side
    flipbook the board plays). Reuses paint() so each frame lands exactly on the static op."""
    ga = thing.geometry_attrs
    locals_ = character.clip_drawables(
        clip,
        expression=str(ga.get("expression", "happy")),
        theme=ga.get("theme"),
        size=float(ga.get("size", 2.8)),
        character=str(ga.get("role") or thing.concept),
    )
    frames = []
    for strokes in locals_:
        fop = paint(thing, p, Drawable(strokes, d.extent, 1, "character"), style=style, scene=scene)
        frames.append(op_to_dict(fop)["strokes"])
    return frames


def _host_mouths(thing: Thing, p, d: Drawable, style: str, scene) -> dict:
    """Render the host's viseme mouth shapes (the mouth SLOT) to placed+painted board strokes,
    so the board can swap them during speech for lip-sync (Phase 4). Same paint transform as the
    body, so each shape lands exactly on the host's mouth."""
    ga = thing.geometry_attrs
    shapes = character.mouth_shapes(
        theme=ga.get("theme"), character=str(ga.get("role") or thing.concept)
    )
    out = {}
    for name, strokes in shapes.items():
        fop = paint(
            thing, p, Drawable(tuple(strokes), d.extent, 1, "character"), style=style, scene=scene
        )
        out[name] = op_to_dict(fop)["strokes"]
    return out


# Semantic SCALE by role — the director's visual hierarchy. The SAME concept reads as a
# hero (big, central) or a particle (small) depending on its role in the scene, which
# fixes "droplet-as-main-object vs droplet-as-particle". The layout preserves the ratio.
_ROLE_SIZE = {"hero": 3.6, "main": 3.6, "prop": 2.2, "particle": 1.1, "setting": 5.0}
# Concepts that are inherently small-and-many — they read as PARTICLES (a droplet beside
# a cloud, a spark beside a fire), never as the hero. This is the lexical half of semantic
# scale; the structural half (which prop is the hero) is inferred from the beats.
_PARTICLE = frozenset(
    {
        "drop",
        "droplet",
        "raindrop",
        "rain",
        "snowflake",
        "snow",
        "bubble",
        "spark",
        "ember",
        "ash",
        "dust",
        "grain",
        "seed",
        "leaf",
        "petal",
        "flake",
        "crumb",
        "bee",
        "ant",
        "fly",
        "bird",
        "star",
        "atom",
        "molecule",
        "cell",
        "germ",
        "pixel",
        "coin",
        "dot",
        "particle",
        "electron",
        "photon",
        "drip",
        "pebble",
    }
)


def _infer_roles(ents: list[Entity], shots: list[Shot], title: str) -> list[Entity]:
    """Give role-less prop entities a semantic role so beat content gets the SAME visual
    hierarchy as a directed template (fixes "beats leak through, no semantic scale"). A
    particle-lexicon concept → particle; otherwise the title subject (or, failing that, the
    most-connected prop) becomes the lone HERO and the rest are props. Characters/text and
    already-roled entities are left untouched. Deterministic — no model, no coordinates."""
    from collections import Counter

    degree: Counter[str] = Counter()
    for sh in shots:
        for a in sh.actions:
            if a.verb == "connect":
                degree[a.actor] += 1
                if a.target:
                    degree[a.target] += 1
    title_words = {w for w in title.lower().replace("-", " ").split() if len(w) > 2}

    props = [e for e in ents if e.kind == "prop" and e.role is None]
    particles = {e.id for e in props if ((e.concept or "").lower().split() or [""])[0] in _PARTICLE}
    candidates = [e for e in props if e.id not in particles]
    hero_id = None
    if candidates:
        titled = [e for e in candidates if title_words & set((e.concept or "").lower().split())]
        pool = titled or candidates
        # the subject is the most-connected of the title-matching props (else the first)
        hero_id = max(pool, key=lambda e: (degree[e.id], -ents.index(e))).id

    out: list[Entity] = []
    for e in ents:
        if e.kind != "prop" or e.role is not None:
            out.append(e)
        elif e.id in particles:
            out.append(replace(e, role="particle"))
        elif e.id == hero_id:
            out.append(replace(e, role="hero"))
        else:
            out.append(replace(e, role="prop"))
    return out


# --------------------------------------------------------------------------- #
# The grammar (typed contracts). No coordinates, no ms — intent only.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Entity:
    """A thing in a scene: a character (pose/expression) or a prop, placed by intent."""

    id: str
    concept: str
    kind: str = "prop"  # prop | character | text
    role: str | None = None
    appearance: dict = field(default_factory=dict)  # pose/expression/theme/size/text
    place: Relation | None = None  # spatial intent (else staged by band)


@dataclass(frozen=True)
class Action:
    verb: str  # one of VERBS
    actor: str  # entity id
    target: str | None = None  # for point/look/transform/connect
    params: dict = field(default_factory=dict)
    at: int = 0  # order within the shot (0,1,2 …)
    dur: str = "med"  # short | med | long — the engine times it


@dataclass(frozen=True)
class Shot:
    framing: str = "wide"  # wide | establishing | medium | close
    focus: str | None = None  # actor id to frame the camera on
    enter: tuple[str, ...] = ()  # entity ids revealed this shot
    actions: tuple[Action, ...] = ()
    say: str | None = None  # narration for this shot
    hold: str = "med"  # pause after
    marks: tuple[Mark, ...] = ()  # [concept] narration↔visual bindings (resolved at compile)


@dataclass(frozen=True)
class ScenePlan:
    id: str
    setting: str = ""  # background scene concept (water/space/forest…) — "" = from title
    cast: tuple[str, ...] = ()  # character entity ids present
    entities: tuple[Entity, ...] = ()
    shots: tuple[Shot, ...] = ()
    transition: str = "cut"  # cut | fade | pan | wipe
    purpose: str = ""  # introduce | explain | contrast | build | resolve — why this scene
    emotion: str = ""  # calm | curious | wonder | tense | joyful — how it should feel


@dataclass(frozen=True)
class LessonPlan:
    title: str
    scenes: tuple[ScenePlan, ...]
    style: str = "cartoon"


# --------------------------------------------------------------------------- #
# Compile: LessonPlan → the timed event stream (the AnimationPlan, serialized).
# --------------------------------------------------------------------------- #
# Shot SIZE = emotional distance (Katz, *Film Directing Shot by Shot*): framing sets the camera
# WIDTH as a fraction of the board — a close-up is INTIMACY, not a crop of the prop. wide/
# establishing = the whole stage (low intimacy); medium = the actor + its surroundings; close =
# tight on one actor (high intimacy). This replaces "zoom to the prop's own width".
_FRAMING_SCALE = {"establishing": 1.0, "wide": 1.0, "medium": 0.6, "close": 0.4}


def _camera_shot(framing: str, p, board: Board, cut: bool) -> dict:
    """One shot's camera frame. Framing SIZE picks the width (a board fraction = emotional
    distance); the focus placement `p` (or board center) picks where. A CUT is instant (ms=0 —
    comparing a new subject/POV); otherwise a smooth push-in/pan (intensifying one subject). The
    focal subject is never cropped below its own width (+ margin)."""
    vw = board.w * _FRAMING_SCALE.get(framing, 1.0)
    if p is not None:
        vw = max(vw, p.w * 1.3)  # the subject always fits
    vw = min(vw, board.w)
    vh = vw * (board.h / board.w)
    vw, vh = round(vw, 3), round(vh, 3)
    cx, cy = (p.x, p.y) if p is not None else (0.0, 0.0)
    bx, by = board.hw - vw / 2, board.hh - vh / 2  # keep the rect fully on-board
    cx = max(-bx, min(bx, cx))
    cy = max(-by, min(by, cy))
    ms = 0 if cut else 700
    return {"type": "camera", "x": round(cx, 4), "y": round(cy, 4), "w": vw, "h": vh, "ms": ms}


def _effective_framing(
    shot: Shot, shi: int, emotion: str, to_draw, pmap, framable
) -> tuple[str, str | None]:
    """Resolve a shot's (framing, focus) for the camera, INFERRING them when unset so beat-derived
    lessons (whose shots default to 'wide') still get real shot sizes. An explicit framing/focus
    wins; otherwise the opening shot establishes the stage, and a later shot frames the focal prop
    it reveals (close when the beat is tense, else medium). An establishing/wide shot frames the
    whole stage (no single subject). Returns (framing, focus_id | None)."""
    focus_id = shot.focus
    if not focus_id:  # the prop this shot reveals, else what a point/look calls attention to
        focus_id = next((e for e in to_draw if e in framable and e in pmap), None)
        if focus_id is None:
            focus_id = next(
                (
                    a.target
                    for a in shot.actions
                    if a.verb in ("point", "look") and a.target in pmap
                ),
                None,
            )
    framing = shot.framing
    if framing == "wide":  # default/unset → infer from position + mood
        if shi == 0 or focus_id is None:
            framing = "establishing"
        elif emotion == "tense":
            framing = "close"
        else:
            framing = "medium"
    if framing in ("establishing", "wide"):
        focus_id = None  # an establishing shot frames the whole stage, not one subject
    return framing, focus_id


def _snap_to_ground(op: dict, grass_y: float, max_reach: float = 2.4) -> None:
    """Plant a floating prop on the grass: drop its strokes so the INK bottom sits on the ground
    line (a recipe's box often pads below the actual shape, so 'grounding the box' leaves the shape
    hovering). Only nudges props already NEAR the ground — a sky prop (sun, cloud) sits far above and
    is left alone. Mutates the op's strokes/label in place."""
    ys = [pt[1] for s in op.get("strokes", []) for pt in s.get("points", [])]
    if not ys:
        return
    float_amt = min(ys) - grass_y  # >0 = hovering above the grass
    if not (0.04 < float_amt < max_reach):
        return  # already grounded, sunk, or a high sky prop → leave it
    dy = -float_amt
    for s in op.get("strokes", []):
        s["points"] = [[round(x, 4), round(y + dy, 4)] for x, y in s["points"]]
    if op.get("label_pos"):
        op["label_pos"] = [op["label_pos"][0], round(op["label_pos"][1] + dy, 4)]


def _camera_full(board: Board, ms: int = 900) -> dict:
    return {"type": "camera", "x": 0.0, "y": 0.0, "w": board.w, "h": board.h, "ms": ms}


def _entity_thing(e: Entity) -> Thing:
    """An Entity → a Thing the drawing/staging engines consume (appearance → attrs).
    The ROLE sets a base size (semantic scale) unless the appearance pins one."""
    geom, paint_attrs = split_paint_attrs(dict(e.appearance))
    if e.kind != "text" and e.role in _ROLE_SIZE and not (geom.keys() & {"size", "radius", "w"}):
        geom["size"] = _ROLE_SIZE[e.role]
    return Thing(
        id=e.id,
        concept=e.concept,
        extent=Extent(1.0, 1.0),
        relations=(e.place,) if e.place else (),
        geometry_attrs=geom,
        paint_attrs=paint_attrs,
    )


def _host_entity(spec, emotion: str = "", purpose: str = "") -> Entity:
    pose = _PURPOSE_POSE.get(purpose) or _HOST_POSE.get(spec.mode, "wave")
    # A neutral "presenter" — compile_plan RECASTS it per scene (scene setting/content), so a
    # multi-scene story can change character (lab→scientist, field→farmer). The id stays "guide".
    return Entity(
        "guide",
        "presenter",
        "character",
        appearance={
            "pose": pose,
            "expression": _EMOTION_FACE.get(emotion, "happy"),
            "size": 2.8,
            "entrance": "rise",
            "ambient": "bob",
            "z": 3,
        },
    )


def _concept_tokens(concept: str) -> set[str]:
    """Normalized match tokens for an entity concept: the whole concept + its words."""
    c = (concept or "").strip().lower()
    return {t for t in {c, *c.split()} if t}


def _resolve_marks(marks: tuple[Mark, ...], entities: list[Entity]) -> list[dict]:
    """Bind each parsed [concept] mark to a STAGED entity id; drop unmatched (drop-don't-
    repair). Returns serializable dicts for the say event, so a later choreographer can
    reveal `entity` when the marked word is spoken. Resolution is authoritative HERE —
    against the entities actually staged — covering both the lifted-Beats and BYO-plan paths."""
    if not marks:
        return []
    lookup: dict[str, str] = {}
    for e in entities:
        if e.kind in ("text", "character"):
            continue  # markers bind to CONTENT props, never the title or the host (scaffolding)
        lookup.setdefault(e.id.strip().lower(), e.id)
        for tok in _concept_tokens(e.concept):
            lookup.setdefault(tok, e.id)
    out: list[dict] = []
    for m in marks:
        eid = lookup.get(m.concept)
        if eid:
            out.append(
                {
                    "concept": m.concept,
                    "word": m.word,
                    "start": m.start,
                    "end": m.end,
                    "entity": eid,
                }
            )
    return out


def compile_plan(
    lesson: LessonPlan,
    spec,
    board: Board | None = None,
    generate: bool = True,
    provenance: dict | None = None,
) -> Iterator[dict]:
    """Compile a LessonPlan into the renderer's timed event stream. Scenes stage their
    full cast (compose_cartoon), then shots reveal + act + narrate, with camera framing
    per shot and a hold/beat after. Pre-stage-then-reveal keeps the composition balanced.
    A cartoon scene with no character gets a host injected (the director adds a presenter);
    a `point`/`look` on a character RE-POSES the rig (it actually gestures), not just a tilt."""
    board = board or Board()
    style = lesson.style or spec.style
    cinematic = style == palette.CARTOON and spec.energy != "calm"
    grass_y = -board.hh + palette.HORIZON_FRAC * board.h  # the ground line props should sit on
    real = placeholders = dropped = 0
    by_source: dict[str, int] = {}

    yield {
        "type": "start",
        "topic": lesson.title,
        "mode": spec.mode,
        "style": style,
        "board": {"w": board.w, "h": board.h},
        "pacing": {"draw_speed": spec.draw_speed, "say_dwell": spec.say_dwell},
        "story": provenance
        or {"requested": "plan", "used": "plan", "fallback": False, "reason": None},
    }

    for si, scene in enumerate(lesson.scenes):
        emotion = scene.emotion if scene.emotion in EMOTIONS else ""
        purpose = scene.purpose if scene.purpose in PURPOSES else ""
        bg = palette.background(scene.setting or lesson.title, spec.mode, style)
        if bg is not None and emotion:  # the felt layer: emotion warms the backdrop
            bg = palette.apply_mood(bg, emotion)
        scene_name = bg["scene"] if bg else None
        edge_ink = palette.LABEL_INK_DARK if scene_name in palette.DARK_SCENES else None
        if si > 0:
            yield {"type": "clear", "scene": si}
        if bg is not None:
            yield {"type": "background", **bg, "emotion": emotion}
        if cinematic:
            yield _camera_full(board, ms=0 if si else 900)  # hard-cut to the (new) scene's stage

        # The director adds a host to any cartoon scene without one — emotion sets its
        # face, the scene's purpose sets its body language. We CAST that injected host per
        # scene (lab->scientist, field->farmer) from the scene's setting+narration, so a
        # multi-scene story changes who hosts. AUTHORED characters keep their own concepts
        # (a scene can stage its own distinct cast — they must NOT all collapse to one role).
        entities = list(scene.entities)
        if style == palette.CARTOON and not any(e.kind == "character" for e in entities):
            # Cast the host from the LESSON topic ONCE so the SAME presenter hosts every scene —
            # per-scene casting morphed the teacher (e.g. into a pirate when a scene said 'ocean').
            host = _host_entity(spec, emotion, purpose)
            host = replace(
                host, concept=character.cast_concept(host.concept, lesson.title, spec.mode)
            )
            entities.insert(0, host)
        chars = {e.id for e in entities if e.kind == "character"}
        framable = {e.id for e in entities if e.kind == "prop"}  # camera-focus subjects (content)

        # Measure + STAGE every entity in the scene (cast + props) as one composition.
        things, tmap, dmap = [], {}, {}
        for e in entities:
            t = _entity_thing(e)
            d = measure(t, generate=generate, style=style)
            tmap[e.id] = replace(t, extent=d.extent)
            dmap[e.id] = d
            things.append(tmap[e.id])
        # Cartoon STAGES a scene (layout.compose_cartoon); whiteboard PACKS a diagram
        # (positioning.place) — the style picks the layout strategy.
        placements, drops = (
            compose_cartoon(things, board) if style == palette.CARTOON else place(things, board)
        )
        dropped += len(drops)
        pmap = {p.id: p for p in placements}

        explicit = {eid for sh in scene.shots for eid in sh.enter}
        opening = [e.id for e in entities if e.id not in explicit]

        # Camera state (per scene): the subject we last framed + whether we're wide — so a NEW
        # subject hard-cuts and the SAME subject pushes in (Katz: cut to compare POVs, move to
        # intensify one). The scene opened on a full establishing frame.
        prev_focus: str | None = None
        cam_full = True
        shots = scene.shots or (Shot(enter=tuple(e.id for e in entities)),)
        for shi, shot in enumerate(shots):
            to_draw = (opening if shi == 0 else []) + [e for e in shot.enter if e not in opening]
            if cinematic:
                framing, focus_id = _effective_framing(shot, shi, emotion, to_draw, pmap, framable)
                if focus_id is None:  # an establishing/wide shot frames the whole stage
                    if not cam_full:
                        yield _camera_full(board)  # pull back out (smooth)
                        cam_full, prev_focus = True, None
                else:  # frame a subject — CUT to a new one, push IN on the same one
                    yield _camera_shot(framing, pmap[focus_id], board, cut=focus_id != prev_focus)
                    cam_full, prev_focus = False, focus_id
            for eid in to_draw:
                p = pmap.get(eid)
                if p is None:
                    continue
                d = dmap[eid]
                by_source[d.source] = by_source.get(d.source, 0) + 1
                placeholders += d.source == "box"
                real += d.source != "box"
                ev = {
                    "type": "draw",
                    "op": op_to_dict(paint(tmap[eid], p, d, style=style, scene=scene_name)),
                }
                if (
                    style == palette.CARTOON
                    and eid in framable
                    and _band(tmap[eid].concept or "") != "sky"
                ):
                    _snap_to_ground(
                        ev["op"], grass_y
                    )  # plant GROUND props on the grass (sky props float)
                # The host ACTS its mood: an emotion-driven gesture clip (mined poses),
                # rendered to placed frames the board flips through. Cartoon only.
                if cinematic and eid in chars:
                    clip = _EMOTION_CLIP.get(emotion, "wave")
                    frames = _host_clip_frames(tmap[eid], p, d, style, scene_name, clip)
                    if frames:
                        ev["op"]["frames"] = frames
                        ev["op"]["fps"] = 14
                        ev["op"]["loop"] = character.loops(clip)
                        if not ev["op"]["loop"]:  # after a one-shot gesture, BREATHE (idle-life
                            ev["op"]["idle"] = _host_clip_frames(  # loop) instead of freezing
                                tmap[eid], p, d, style, scene_name, "alive"
                            )
                    # the mouth SLOT: viseme shapes the board swaps during speech (lip-sync)
                    ev["op"]["mouths"] = _host_mouths(tmap[eid], p, d, style, scene_name)
                yield ev
            if shot.say:
                say_ev: dict = {"type": "say", "text": shot.say}
                marks = _resolve_marks(shot.marks, entities)  # bind [concept] words to staged ids
                if marks:
                    say_ev["marks"] = marks
                yield say_ev
            for a in sorted(shot.actions, key=lambda a: a.at):
                if a.verb == "connect" and a.target:
                    # Cartoon is FILM: drop the connector LABEL (narration + the host
                    # pointing + semantic motion carry the relationship, not a diagram tag).
                    label = None if style == palette.CARTOON else a.params.get("label")
                    conn = Connector(f"{a.actor}->{a.target}", a.actor, a.target, "arrow", label)
                    op = route(conn, pmap, style=style, color=edge_ink)
                    if op is not None:
                        yield {"type": "connector", "op": op_to_dict(op)}
                elif a.verb in ("point", "look") and a.actor in chars and a.actor in pmap:
                    # Character ACTS: re-pose the rig (a real gesture) AND turn its head toward
                    # the target's position (it looks at what it points to), then emphasize it.
                    pose = "point" if a.verb == "point" else "think"
                    ga2 = {**tmap[a.actor].geometry_attrs, "pose": pose}
                    if a.target in pmap:  # head turns toward the target's side of the board
                        dx = pmap[a.target].x - pmap[a.actor].x
                        ga2["turn"] = round(max(-0.8, min(0.8, dx / 4.0)), 2)
                    t2 = replace(tmap[a.actor], geometry_attrs=ga2)
                    d2 = measure(t2, generate=generate, style=style)
                    op = paint(
                        replace(t2, extent=d2.extent),
                        pmap[a.actor],
                        d2,
                        style=style,
                        scene=scene_name,
                    )
                    yield {
                        "type": "draw",
                        "op": op_to_dict(replace(op, entrance="pop")),
                    }  # quick swap
                    if a.target in pmap:
                        yield {
                            "type": "action",
                            "verb": "pulse",
                            "id": a.target,
                            "ms": _DUR_MS["med"],
                        }
                elif cinematic and a.verb in VERBS and a.actor in pmap:
                    # Motion is FILM — whiteboard stays a clean static diagram (connectors aside).
                    yield {
                        "type": "action",
                        "verb": a.verb,
                        "id": a.actor,
                        "target": a.target,
                        "params": a.params,
                        "ms": _DUR_MS.get(a.dur, 800),
                    }
            if cinematic and shot.hold and _HOLD_MS.get(shot.hold):
                # emotion paces the beat: tension cuts quick, wonder lingers.
                yield {
                    "type": "hold",
                    "ms": round(_HOLD_MS[shot.hold] * _EMOTION_PACE.get(emotion, 1.0)),
                }

    if cinematic:
        yield _camera_full(board)
    yield {
        "type": "done",
        "summary": {
            "story": (provenance or {}).get("used", "plan"),
            "fallback": (provenance or {}).get("fallback", False),
            "real_drawings": real,
            "placeholders": placeholders,
            "dropped": dropped,
            "by_source": by_source,
            "scenes": len(lesson.scenes),
            "shots": sum(len(s.shots) for s in lesson.scenes),
        },
    }


# --------------------------------------------------------------------------- #
# Back-compat: lift flat Beats into a single-scene LessonPlan (one shot per `say`).
# --------------------------------------------------------------------------- #
def parse_plan(data: dict, title: str | None = None, style: str | None = None) -> LessonPlan | None:
    """Build a LessonPlan from pasted JSON (a directed storyboard). Defensive: skips
    malformed entities/shots/actions rather than crashing. Returns None if it isn't a
    plan (no `scenes`), so the caller can fall back to flat-Beat parsing."""
    if not isinstance(data, dict) or "scenes" not in data:
        return None
    from engine.story import _relation, parse_marks

    scenes: list[ScenePlan] = []
    for s in data.get("scenes", []):
        if not isinstance(s, dict):
            continue
        ents = [
            Entity(
                id=e["id"],
                concept=e.get("concept", e["id"]),
                kind=e.get("kind", "prop"),
                role=e.get("role"),
                appearance=e.get("appearance") or {},
                place=_relation(e.get("place")) if e.get("place") else None,
            )
            for e in s.get("entities", [])
            if isinstance(e, dict) and e.get("id")
        ]
        shots: list[Shot] = []
        for sh in s.get("shots", []):
            if not isinstance(sh, dict):
                continue
            raw_say = sh.get("say")
            say_text, marks = parse_marks(raw_say) if isinstance(raw_say, str) else (raw_say, ())
            shots.append(
                Shot(
                    framing=sh.get("framing", "wide"),
                    focus=sh.get("focus"),
                    enter=tuple(sh.get("enter", [])),
                    actions=tuple(
                        Action(
                            a["verb"],
                            a["actor"],
                            a.get("target"),
                            a.get("params") or {},
                            a.get("at", 0),
                            a.get("dur", "med"),
                        )
                        for a in sh.get("actions", [])
                        if isinstance(a, dict) and a.get("verb") in VERBS and a.get("actor")
                    ),
                    say=say_text,
                    hold=sh.get("hold", "med"),
                    marks=marks,
                )
            )
        scenes.append(
            ScenePlan(
                id=s.get("id", f"s{len(scenes)}"),
                setting=s.get("setting", ""),
                cast=tuple(s.get("cast", [])),
                entities=tuple(ents),
                shots=tuple(shots),
                transition=s.get("transition", "cut"),
                purpose=s.get("purpose", ""),
                emotion=s.get("emotion", ""),
            )
        )
    if not scenes:
        return None
    return LessonPlan(
        title=title or data.get("title", "lesson"),
        scenes=tuple(scenes),
        style=style or data.get("style", "cartoon"),
    )


def lift_beats(beats: list[Beat], title: str = "lesson", style: str = "cartoon") -> LessonPlan:
    """Beats → a LessonPlan: each `clear` starts a Scene, each `say` opens a Shot, each
    `show` is an Entity entering the current shot, each `connect` a connect Action."""
    scenes: list[ScenePlan] = []
    ents: list[Entity] = []
    shots: list[Shot] = []
    cur_enter: list[str] = []
    cur_actions: list[Action] = []
    cur_say: str | None = None
    cur_marks: tuple[Mark, ...] = ()

    def flush_shot():
        nonlocal cur_enter, cur_actions, cur_say, cur_marks
        if cur_enter or cur_actions or cur_say:
            shots.append(
                Shot(
                    enter=tuple(cur_enter),
                    actions=tuple(cur_actions),
                    say=cur_say,
                    marks=cur_marks,
                )
            )
            cur_enter, cur_actions = [], []
            cur_say, cur_marks = None, ()  # keep types clean (cur_say is str | None)

    def flush_scene():
        nonlocal ents, shots
        flush_shot()
        if ents or shots:
            cast = tuple(e.id for e in ents if e.kind == "character")
            # Cartoon gives beat content a visual hierarchy (hero/prop/particle) AND a felt
            # default mood (an engaged, curious host) — the whiteboard stays a uniform,
            # mood-less diagram, so both are left off there.
            cartoon = style == palette.CARTOON
            staged = _infer_roles(ents, shots, title) if cartoon else ents
            scenes.append(
                ScenePlan(
                    id=f"s{len(scenes)}",
                    cast=cast,
                    entities=tuple(staged),
                    shots=tuple(shots),
                    emotion="curious" if cartoon else "",
                )
            )
            ents, shots = [], []

    for b in beats:
        if b.kind == "clear":
            flush_scene()
        elif b.kind == "show" and b.entity:
            kind = (
                "character"
                if character.is_character(b.concept or "")
                else ("text" if (b.concept or "") == "text" else "prop")
            )
            geom, paint_attrs = split_paint_attrs(dict(b.geometry))
            ents.append(
                Entity(
                    b.entity,
                    b.concept or b.entity,
                    kind,
                    appearance={**geom, **paint_attrs},
                    place=b.relation,
                )
            )
            cur_enter.append(b.entity)
        elif b.kind == "connect" and b.entity and b.target:
            cur_actions.append(
                Action("connect", b.entity, b.target, {"label": b.text} if b.text else {})
            )
        elif b.kind == "say" and b.text:
            if cur_say is not None:  # a new narration line starts a new shot
                flush_shot()
            cur_say = b.text
            cur_marks = b.marks  # carry the [concept] bindings onto this shot
    flush_scene()
    # A gentle emotional ARC: a multi-scene lift lands on a joyful close (a satisfying end);
    # a single scene stays curious. Whiteboard scenes carry no mood.
    if style == palette.CARTOON and len(scenes) >= 2:
        scenes[-1] = replace(scenes[-1], emotion="joyful")
    return LessonPlan(title=title, scenes=tuple(scenes) or (ScenePlan("s0"),), style=style)
