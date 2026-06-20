"""Engine 1 — Story (ARCHITECTURE §3). Topic + mode -> a stream of Beats.

Story emits ABSTRACT beats (entities + spatial relation + narration) — no geometry,
no coordinates. A deterministic TemplateStory is the default so the end-to-end
pipeline stays hermetic; an LLM story (Ollama/Gemini) sits behind STORY_PROVIDER and
emits Beats as JSON, parsed by parse_beats(). The cheap, structured part is the only
place a big model is needed (NOTEBOOK B4/J2).
"""

from __future__ import annotations

import contextlib
import copy
import json
import os
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from typing import Protocol

from engine.contracts import (
    Beat,
    Mark,
    above,
    at,
    below,
    between,
    clear,
    connect,
    in_panel,
    left_of,
    near,
    on,
    right_of,
    say,
    show,
)
from engine.director import DirectorSpec, coerce

_provider: StoryProvider | None = None

_RELATION_PROMPT = (
    "Relations: at(region in center/left/right/top/bottom/top_left/...), "
    "right_of(id), left_of(id), above(id), below(id), on(id), between(idA,idB), near(id)."
)
_MODE_HINT = {
    "learn": (
        "Build ONE cumulative concept map of 4-6 labeled concepts, placed with relations and "
        'connected by edges. Do NOT use {"kind":"clear"} — the board accumulates, never wipes.'
    ),
    "story": (
        'Tell it as a 3-scene narrative. Emit a {"kind":"clear"} beat between scenes; each scene '
        "introduces a couple of entities (the first with at(...)) plus a sentence of narration."
    ),
    "draw": (
        "Produce ONE central illustration: a single main entity at center, plus a few labels. "
        'Do NOT use {"kind":"clear"}.'
    ),
    "explain": (
        "A terse 30-second version: 2-3 entities, one connection, one or two sentences. "
        'Do NOT use {"kind":"clear"}.'
    ),
}
# JSON-schema for Ollama structured outputs (proved: plain format="json" malforms
# ~1/3 — NOTEBOOK §K7). Forcing each beat to be an OBJECT kills the string-fragment
# failure at the source; parse_beats stays defensive as belt-and-suspenders.
BEAT_SCHEMA = {
    "type": "object",
    "properties": {
        "beats": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["show", "connect", "say", "clear"]},
                    "entity": {"type": "string"},
                    "concept": {"type": "string"},
                    "relation": {"type": "object"},
                    "src": {"type": "string"},
                    "dst": {"type": "string"},
                    "label": {"type": "string"},
                    "text": {"type": "string"},
                    "count": {"type": "integer"},  # draw MANY of the concept (rain/stars/…)
                },
                "required": ["kind"],
            },
        }
    },
    "required": ["beats"],
}


_LLM_MAX_SCENES = 6  # a single local-model call can't coherently fill more scenes than this


def _min_beats(spec) -> int:
    """A structural FLOOR so a small local model can't truncate the lesson to 1-2 lines
    (NOTEBOOK O1/K7 — under-production is the visible story failure). Enforced as the
    beats-array minItems below; Ollama (llama.cpp GBNF) honours it during decoding."""
    if spec.mode == "explain":
        return 4  # explain is meant terse (2-3 entities, one connection)
    cc = spec.concept_count
    if spec.mode == "draw":
        return cc + 1  # ONE central illustration + a few labels/lines, not a full map
    base = 2 * cc + 2  # each concept paired with a say, + an intro + a closer
    if spec.mode == "story":
        # the floor scales with scenes but is CAPPED — a single local-model call can't coherently
        # fill a long (e.g. 16-scene / 10-min) lesson; that's the outline-then-scenes follow-on.
        # The deterministic TEMPLATE delivers the full length; the LLM stays modest for now.
        base += max(0, min(spec.scenes, _LLM_MAX_SCENES) - 1)  # + one clear between scenes
    return base


def _beat_schema(spec) -> dict:
    """BEAT_SCHEMA with a per-lesson minItems/maxItems on the beats array — structured
    decoding then forces a FULL lesson, not a stub. minItems is the truncation fix; the
    prompt still guides composition (show/say pairing, concrete drawable nouns)."""
    s = copy.deepcopy(BEAT_SCHEMA)
    lo = _min_beats(spec)
    s["properties"]["beats"]["minItems"] = lo
    s["properties"]["beats"]["maxItems"] = lo * 3 + 6
    return s


_PROMPT = (
    "You are a teacher planning an animated lesson on '{topic}' as a JSON object "
    '{{"beats": [...]}}. Each beat is one of:\n'
    '  {{"kind":"show","entity":"id","concept":"what to draw","relation":{{"<rel>":"<arg>"}}}}\n'
    '  {{"kind":"connect","src":"id","dst":"id","label":"short verb"}}\n'
    '  {{"kind":"say","text":"one sentence of narration"}}\n'
    '  {{"kind":"clear"}}   (story mode ONLY — wipe the board for a new scene)\n'
    f"{_RELATION_PROMPT}\n"
    "RULES (follow exactly):\n"
    "- ids are SHORT lowercase words that match the concept (cloud, rain, river) — never numbers.\n"
    "- every `show.concept` is a CONCRETE, DRAWABLE noun (sun, cloud, rain, river, tree, leaf, "
    "fish, bird, heart, brain, rocket, planet, atom, gear, book, house) — NOT an abstract phrase.\n"
    "- a `relation` arg must be the id of an ALREADY-shown thing (or a region for at(...)).\n"
    "- every `connect` needs BOTH src and dst, each an id you already showed.\n"
    "- {concept_count}-6 `show` beats total; pair most with one short `say`.\n"
    "- for MANY of one thing, add a number `count` to the show (e.g. "
    '{{"kind":"show","entity":"stars","concept":"star","count":7}}); concepts like rain, '
    "snow, forest, crowd already render as many automatically.\n"
    "- in each `say`, WRAP the word naming a thing you `show` in [brackets], using the show's "
    'id/concept word, e.g. {{"kind":"say","text":"The [sun] warms the [ground]."}} after showing sun '
    "and ground. Bracket ONLY words that match a `show`; the word is still spoken normally.\n"
    "MODE: {mode_hint}\n"
    "{domain_line}"
    "STYLE: {style}. If STYLE is cartoon and MODE is not explain, plan a fuller mini-cartoon: "
    "5-7 short narration beats, concrete scene props, and visible action moments. Do not stop "
    "after only two or three lines unless MODE is explain.\n"
    "AUDIENCE: {audience} · TONE: {tone} · DEPTH: {depth} — match vocabulary and length to these.\n"
    "Output ONLY the JSON object."
)


def _domain_prompt_line(domain: str) -> str:
    """Phase 1: tell the model which domain-specific items it can actually DRAW, so it
    names 'virtual machine'/'storage' (real icons) instead of inventing un-drawable nouns."""
    if not domain:
        return ""
    from engine import semantics

    vocab = semantics.vocabulary(domain, 40)
    if not vocab:
        return f"DOMAIN: {domain}.\n"
    items = ", ".join(vocab)
    return (
        f"DOMAIN: {domain}. PREFER these exact drawable item names where they fit "
        f"(they render as real icons, not plain boxes): {items}.\n"
    )


def _resolve_domain_concepts(beats: list[Beat], spec: DirectorSpec) -> list[Beat]:
    """Phase 2: rewrite each show concept to the best concrete asset for the lesson's
    domain (server→a published server icon; cloud→cloud-service in a cloud lesson; tree/sun
    stay cartoon). No-op when no domain was inferred, so general lessons are untouched."""
    domain = getattr(spec, "domain", "")
    if not domain:
        return beats
    from engine import semantics

    out: list[Beat] = []
    for b in beats:
        if b.kind == "show" and b.concept:
            new = semantics.resolve_concept(b.concept, domain)
            if new != b.concept:
                b = replace(b, concept=new)
        out.append(b)
    return out


class StoryProvider(Protocol):
    name: str

    def tell(self, spec: DirectorSpec) -> list[Beat]: ...


@dataclass(frozen=True)
class StoryResult:
    """What actually happened — so the product can SHOW it (no silent fallback)."""

    beats: list[Beat]
    requested: str  # the configured provider (template/ollama/gemini)
    used: str  # what produced these beats
    reason: str | None = None  # why it fell back, if it did

    @property
    def fallback(self) -> bool:
        return self.requested != self.used


def set_provider(p: StoryProvider | None) -> None:
    global _provider
    _provider = p


def plan(topic: str, spec=None) -> StoryResult:
    """Plan a lesson AND report provenance. LLM providers no longer fall back
    silently; the fallback to the template is decided here and recorded."""
    global _provider
    if _provider is None:
        _provider = _default_provider()
    s = coerce(topic, spec)
    requested = getattr(_provider, "name", "template")

    def dress(raw: list[Beat]) -> list[Beat]:
        # drop-don't-repair, resolve concepts to domain assets, then add the cartoon host.
        return _with_presenter(_resolve_domain_concepts(sanitize_beats(raw, s), s), s)

    if isinstance(_provider, TemplateStory):
        return StoryResult(dress(_provider.tell(s)), "template", "template")
    try:
        beats = dress(_provider.tell(s))
        if any(b.kind == "show" and b.entity != "guide" for b in beats):
            return StoryResult(beats, requested, requested)
        reason = f"{requested} returned no usable beats"
    except Exception as e:  # noqa: BLE001 - surface the failure, don't hide it
        reason = f"{requested} error: {e}"
    return StoryResult(dress(TemplateStory().tell(s)), requested, "template", reason)


def tell(topic: str, spec=None) -> list[Beat]:
    """Beats only (back-compat). Use plan() when you need provenance."""
    return plan(topic, spec).beats


def plan_from_beats(raw_beats: list[Beat], spec: DirectorSpec) -> StoryResult:
    """Animate a story supplied DIRECTLY — bring-your-own, authored by a stronger
    external model (GPT-4/Claude) and pasted in. Same drop-don't-repair sanitation +
    cartoon-host injection as plan(), but NO provider call: the engine just animates
    the IR it's handed. This is the 'IR -> pixels' contract, opened to the user."""
    beats = _with_presenter(sanitize_beats(raw_beats, spec, max_concepts=8), spec)
    return StoryResult(beats, "script", "script")


def script_prompt(spec: DirectorSpec, fmt: str = "beats") -> str:
    """The prompt to hand a STRONG external model so its output animates well here:
    `beats` = the simple flat format; `plan` = a directed STORYBOARD (scenes/shots/actions
    — a film). Both embed our drawable vocabulary so concepts render as icons, not boxes."""
    from engine import icons

    vocab = ", ".join(icons.known())
    if fmt == "plan":
        return _plan_prompt(spec, vocab)
    hint = _MODE_HINT.get(spec.mode, _MODE_HINT["learn"])
    return (
        f'Write an animated {spec.mode} lesson on "{spec.topic}" as a STORYBOARD for a kids\' '
        f"explainer board. Audience: {spec.audience}. Tone: {spec.tone}. Depth: {spec.depth}.\n\n"
        'Output ONLY a JSON object (no markdown, no prose): {"beats":[ ... ]}.\n'
        "Each beat is exactly one of:\n"
        '  {"kind":"show","entity":"id","concept":"drawable noun","relation":{"<rel>":"<arg>"}}\n'
        '  {"kind":"connect","src":"id","dst":"id","label":"short verb"}\n'
        '  {"kind":"say","text":"one sentence of narration"}\n'
        f"{_RELATION_PROMPT}\n"
        "RULES:\n"
        "- ids are short lowercase words that match the concept (cloud, rain, river) — never numbers.\n"
        "- every `show.concept` MUST be a concrete, DRAWABLE noun. PREFER this vocabulary so each "
        f"concept renders as a colorful icon instead of a plain box:\n  {vocab}\n"
        "- a `relation` arg must reference an id you ALREADY showed (or a region for at()).\n"
        "- every `connect` needs BOTH src and dst, each an id you already showed.\n"
        f"- {hint}\n"
        "- in each `say`, wrap the word naming a thing you `show` in [brackets] (matching its "
        'id/concept), e.g. {"kind":"say","text":"The [sun] warms the [ground]."} — this links the '
        "narration to the picture; the word is still spoken normally.\n"
        "- 4-7 `show` beats, each paired with one short, vivid, accurate `say`."
    )


def _plan_prompt(spec: DirectorSpec, vocab: str) -> str:
    """The DIRECTED-STORYBOARD prompt — scenes, shots, characters acting, camera. A film."""
    return (
        f'Direct an animated cartoon lesson on "{spec.topic}" as a STORYBOARD (a short film) for a '
        f"kids' explainer. Audience: {spec.audience}. Tone: {spec.tone}.\n\n"
        'Output ONLY a JSON object (no markdown): {"title":"...","style":"cartoon","scenes":[ ... ]}.\n'
        'A SCENE = {"id","setting":"water/space/forest/classroom/...","purpose":"introduce|explain|'
        'contrast|build|resolve","emotion":"calm|curious|wonder|tense|joyful","entities":[...],"shots":[...]}.\n'
        'An ENTITY = {"id","concept":"DRAWABLE noun","kind":"prop","role":"hero|prop|particle"} '
        "(a presenter is added for you).\n"
        'A SHOT = {"framing":"establishing|medium|close","focus":"<entity id>","enter":["ids shown now"],'
        '"say":"one narration line","actions":[...]}.\n'
        'An ACTION = {"verb":"<point|pulse|rise|fall|grow|shrink|transform|connect|wobble>",'
        '"actor":"<id>","target":"<id?>","params":{"label":"for connect"}}.\n'
        "RULES (follow exactly):\n"
        "- ids are short lowercase words matching the concept (cloud, rain, river).\n"
        "- entity `concept`s are concrete drawable nouns. PREFER this vocabulary so they render as "
        f"icons, not boxes:\n  {vocab}\n"
        '- ROLE sets size: the scene\'s SUBJECT is "hero" (big, central); small/many things '
        '(a droplet, a spark, a bird) are "particle" (tiny); everything else is "prop". ONE hero per scene.\n'
        "- PURPOSE is the scene's job; EMOTION is how it should feel (tension cuts quick, wonder lingers, "
        "joy warms the frame). Give a multi-scene lesson a real arc (curious → tense → joyful).\n"
        '- the host is "guide": use {"verb":"point","actor":"guide","target":"<id>"} so it gestures '
        "at what you explain.\n"
        "- `pulse` emphasizes, `rise`/`fall` move (evaporation up, rain down), `connect` links two ideas.\n"
        "- in a shot's `say`, wrap the word naming an entity in [brackets] (matching its id/concept), "
        'e.g. "say":"The [sun] heats the [water]." — it binds the narration to the visual on screen.\n'
        "- 1-3 scenes (a new scene changes the setting/place), 2-4 shots each; every shot has a `say` "
        "and 1-2 actions. Build the story beat by beat — this is a film, not a diagram."
    )


# --------------------------------------------------------------------------- #
# Deterministic templates — one per mode, parameterized by the DirectorSpec, so
# the offline board honors policy (depth/density/audience/tone/scene_count).
# Real per-topic content still needs an LLM.
# --------------------------------------------------------------------------- #
_PARTS = (
    "What it is",
    "Why it matters",
    "An example",
    "A key detail",
    "Another angle",
    "The big picture",
)

# Words that are never the drawable subject of a topic (articles, qualifiers, abstractions).
_NON_SUBJECT = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "how",
        "why",
        "what",
        "is",
        "are",
        "to",
        "and",
        "in",
        "on",
        "for",
        "with",
        "from",
        "into",
        "little",
        "big",
        "tiny",
        "great",
        "brave",
        "first",
        "new",
        "old",
        "story",
        "journey",
        "world",
        "life",
        "its",
        "their",
        "our",
        "your",
        "my",
        "this",
        "that",
    }
)


def _subject(topic: str, style: str = "cartoon") -> str:
    """The most DRAWABLE noun in a topic → the hero's concept, so the star of the scene is
    a real drawing, not a labeled box. 'how a volcano erupts' → 'volcano'; 'the human heart'
    → 'heart'. Drawability is tested THE WAY this style will actually render it (cartoon
    skips the catalog rung, so a catalog-only word still boxes) — scanning from the end,
    since the subject usually trails. Falls back to the last content word, then the topic."""
    from engine.contracts import Extent, Thing
    from engine.drawing import measure

    words = [w.strip(".,!?;:'\"") for w in (topic or "").lower().split()]
    words = [w for w in words if w and w not in _NON_SUBJECT]
    if not words:
        return topic
    for w in reversed(words):  # the last word that draws as something REAL in this style
        if measure(Thing("probe", w, Extent(1, 1)), generate=False, style=style).source != "box":
            return w
    return words[-1]


def _title(topic: str, font: float = 0.6) -> Beat:
    return show("title", "text", at("top"), text=topic, font=font)


def _intro(spec: DirectorSpec) -> str:
    t = spec.topic
    if spec.audience == "child":
        return f"Let's explore {t} together!"
    if spec.audience == "expert":
        return f"An overview of {t}."
    return f"Let's learn about {t}."


# --------------------------------------------------------------------------- #
# Directed PLANS — the Story now emits a LessonPlan (scenes/shots/actions), not just
# flat Beats. The template builds the directed plan directly (the offline film); an
# LLM stays on the simpler Beats format (more reliable for small local models) and we
# LIFT those into a single-scene plan. Same compiler (plan.compile_plan) renders both.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class PlanResult:
    plan: object  # LessonPlan
    requested: str
    used: str
    reason: str | None = None

    @property
    def fallback(self) -> bool:
        return self.requested != self.used


def _learn_plan(spec: DirectorSpec, P):
    # place relations give whiteboard a tidy concept map (title->row); cartoon ignores
    # them and stages by band — the compiler picks the layout by style.
    cartoon = spec.style == "cartoon"
    ents = [
        P.Entity(
            "title", "text", "text", appearance={"text": spec.topic, "font": 0.6}, place=at("top")
        )
    ]
    shots = [P.Shot(framing="establishing", enter=("title",), say=_intro(spec))]
    prev = None
    for i, part in enumerate(_PARTS[: spec.concept_count]):
        cid = f"c{i}"
        ents.append(P.Entity(cid, part, place=below("title") if prev is None else right_of(prev)))
        acts = [P.Action("point", "guide", cid)] if cartoon else []  # host points at it
        acts.append(P.Action("pulse", cid))
        if prev:
            acts.append(P.Action("connect", prev, cid))
        shots.append(
            P.Shot(
                "medium", focus=cid, enter=(cid,), say=f"{part}.", actions=tuple(acts), hold="short"
            )
        )
        prev = cid
    closer = f"And that's {spec.topic}!" if spec.tone == "playful" else f"That's {spec.topic}."
    shots.append(P.Shot(say=closer, hold="med"))
    scene = P.ScenePlan(
        "s0",
        setting=spec.topic,
        entities=tuple(ents),
        shots=tuple(shots),
        purpose="explain",
        emotion="curious",
    )
    return P.LessonPlan(spec.topic, (scene,), style=spec.style)


def _draw_plan(spec: DirectorSpec, P):
    ents = [
        P.Entity(
            "title", "text", "text", appearance={"text": spec.topic, "font": 0.6}, place=at("top")
        ),
        P.Entity("main", _subject(spec.topic, spec.style), role="hero", place=at("center")),
    ]
    shots = [
        P.Shot(
            "establishing",
            enter=("title", "main"),
            say=_intro(spec),
            actions=(P.Action("pulse", "main"),),
        ),
        P.Shot(focus="main", say=f"This is {spec.topic}.", hold="med"),
    ]
    scene = P.ScenePlan(
        "s0",
        setting=spec.topic,
        entities=tuple(ents),
        shots=tuple(shots),
        purpose="introduce",
        emotion="wonder",
    )
    return P.LessonPlan(spec.topic, (scene,), style=spec.style)


def _explain_plan(spec: DirectorSpec, P):
    ents = [
        P.Entity("cause", "Cause", place=at("left")),
        P.Entity("effect", "Effect", place=right_of("cause")),
    ]
    shots = [
        P.Shot(
            "establishing",
            enter=("cause", "effect"),
            say=f"{spec.topic} — in one breath.",
            actions=(P.Action("connect", "cause", "effect", {"label": "leads to"}),),
        ),
        P.Shot(say=f"That's the core of {spec.topic}.", hold="med"),
    ]
    scene = P.ScenePlan(
        "s0",
        setting=spec.topic,
        entities=tuple(ents),
        shots=tuple(shots),
        purpose="explain",
        emotion="calm",
    )
    return P.LessonPlan(spec.topic, (scene,), style=spec.style)


# Story mode is a real emotional ARC, not N flat scenes: curiosity → tension → release.
# Each entry is (label, purpose, emotion, line1, line2): the two LINEs give every scene a
# pair of narration beats so the deterministic floor reads as a story with rhythm, not a
# stub of "Scene N" labels. (Real per-topic narrative still needs the LLM — this is the
# template floor, the §K8 honest fallback.)
_STORY_ARC = [
    (
        "Setup",
        "introduce",
        "curious",
        "Let's begin the story of {topic}.",
        "Here's where it starts.",
    ),
    (
        "Turning point",
        "build",
        "tense",
        "Then {topic} starts to change.",
        "This is the turning point.",
    ),
    (
        "Resolution",
        "resolve",
        "joyful",
        "Finally, {topic} comes together.",
        "And that's how it resolves!",
    ),
    (
        "Aftermath",
        "resolve",
        "calm",
        "Afterwards, {topic} settles down.",
        "A calm, satisfying end.",
    ),
    ("Reflection", "resolve", "calm", "Looking back on {topic}.", "What a journey it was."),
]
_STORY_MAX = 24  # cap scenes so even a 10-min target stays sane


def _arc(i: int, n: int) -> tuple[str, str, str, str, str]:
    """Scene i of n on the emotional arc (setup → build → turn → resolve). A SHORT story
    (n ≤ the hand-authored arc) uses the authored beats verbatim (byte-identical to before);
    a LONG story STRETCHES the same shape across n scenes by position, so any length still reads
    as a story — curious open, rising middle, joyful close — not N flat 'Scene k' stubs. Real
    per-scene narrative still needs the LLM; this is the honest template floor (§K8)."""
    if n <= len(_STORY_ARC):
        return _STORY_ARC[i]
    if i == 0:
        return _STORY_ARC[0]  # Setup / curious
    if i == n - 1:
        return _STORY_ARC[2]  # Resolution / joyful — a satisfying close
    pos = i / (n - 1)  # position through the middle, 0..1
    k = i + 1
    if pos < 0.45:
        return (
            f"Building {k}",
            "build",
            "curious",
            "Then {topic} grows and develops.",
            "The story moves forward.",
        )
    if pos < 0.75:
        return (
            f"Turning point {k}",
            "build",
            "tense",
            "Now {topic} reaches a turning point.",
            "The tension rises.",
        )
    return (
        f"Toward the end {k}",
        "resolve",
        "wonder",
        "Things come together for {topic}.",
        "We're nearly there.",
    )


def _story_plan(spec: DirectorSpec, P):
    n = max(2, min(spec.scenes, _STORY_MAX))  # length → scenes-over-time (each scene clears)
    subj = _subject(spec.topic, spec.style)
    cartoon = spec.style == "cartoon"
    scenes = []
    for i in range(n):
        label, purpose, emotion, line1, line2 = _arc(i, n)
        ents = [
            P.Entity(
                f"t{i}",
                "text",
                "text",
                appearance={"text": f"Scene {i + 1} · {label}", "font": 0.5},
                place=at("top"),
            ),
            P.Entity(f"o{i}", subj, role="hero", place=at("center")),
        ]
        # Two shots per scene: establish (pulse the hero) then a beat where the host points
        # at it — so each scene narrates TWICE and the presenter acts, instead of one line.
        point = [P.Action("point", "guide", f"o{i}")] if cartoon else []
        shots = [
            P.Shot(
                "establishing",
                enter=(f"t{i}", f"o{i}"),
                say=line1.format(topic=spec.topic),
                actions=(P.Action("pulse", f"o{i}"),),
                hold="short",
            ),
            P.Shot(
                "medium",
                focus=f"o{i}",
                say=line2.format(topic=spec.topic),
                actions=tuple(point),
                hold="med",
            ),
        ]
        scenes.append(
            P.ScenePlan(
                f"s{i}",
                setting=spec.topic,
                entities=tuple(ents),
                shots=tuple(shots),
                transition="fade",
                purpose=purpose,
                emotion=emotion,
            )
        )
    return P.LessonPlan(spec.topic, tuple(scenes), style=spec.style)


_PLAN_MODES = {
    "learn": _learn_plan,
    "story": _story_plan,
    "draw": _draw_plan,
    "explain": _explain_plan,
}


# --------------------------------------------------------------------------- #
# Process EXEMPLARS — a few well-known processes authored as DIRECTED, ANIMATED
# scenes: multiple staged entities, each acting (rise/grow/fall/flow), revealed shot
# by shot, with the presenter pointing at each step. Offline templates are generic by
# nature, so an authored exemplar is what proves + demos the directed-cartoon pipeline
# and is the reference shape the LLM story prompt targets (Phase A).
# --------------------------------------------------------------------------- #
def _water_cycle_plan(spec: DirectorSpec, P):
    cartoon = spec.style == "cartoon"

    def point(target: str):  # the presenter physically points at the concept being taught
        return (P.Action("point", "guide", target),) if cartoon else ()

    # The sea is the scene's environment (the sky scene's horizon), so we don't stage a giant
    # water "prop" — the cycle is carried by the sun + the vapor/cloud/rain that act through it.
    ents = [
        P.Entity(
            "title",
            "text",
            "text",
            appearance={"text": "The Water Cycle", "font": 0.55},
            place=at("top"),
        ),
        P.Entity("sun", "sun", role="hero"),
        P.Entity("vapor", "droplet", role="particle"),  # evaporation — small + rising
        P.Entity(
            "cloud", "cloud", role="prop"
        ),  # prop, not hero — it GROWS, so keep its base small
        P.Entity("rain", "rain", role="particle"),
        P.Entity("mountain", "mountain", role="prop"),
    ]
    shots = [
        P.Shot(
            "establishing",
            enter=("title", "sun"),
            say="The sun warms the water of the oceans below.",
            actions=(P.Action("pulse", "sun", dur="long"), *point("sun")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="vapor",
            enter=("vapor",),
            say="The water heats up, evaporates, and rises as invisible vapor.",
            actions=(P.Action("rise", "vapor", dur="long"), *point("vapor")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="cloud",
            enter=("cloud",),
            say="High in the sky it cools and condenses into clouds.",
            actions=(P.Action("grow", "cloud", dur="long"), *point("cloud")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="rain",
            enter=("rain",),
            say="The clouds grow heavy, and rain falls back to the earth.",
            actions=(P.Action("fall", "rain", dur="long"), *point("rain")),
            hold="short",
        ),
        P.Shot(
            "wide",
            enter=("mountain",),
            say="It collects on the land and flows back to the ocean — and the cycle begins again.",
            actions=(P.Action("flow", "mountain", dur="long"), *point("mountain")),
            hold="long",
        ),
    ]
    scene = P.ScenePlan(
        "s0",
        setting="sky",
        entities=tuple(ents),
        shots=tuple(shots),
        purpose="explain",
        emotion="wonder",
    )
    return P.LessonPlan("The Water Cycle", (scene,), style=spec.style)


def _day_night_plan(spec: DirectorSpec, P):
    cartoon = spec.style == "cartoon"

    def point(target: str):
        return (P.Action("point", "guide", target),) if cartoon else ()

    ents = [
        P.Entity(
            "title",
            "text",
            "text",
            appearance={"text": "Day and Night", "font": 0.55},
            place=at("top"),
        ),
        P.Entity("sun", "sun", role="hero"),
        P.Entity("house", "house", role="prop"),
        P.Entity("moon", "moon", role="hero"),
        P.Entity("stars", "star", role="particle"),
    ]
    shots = [
        P.Shot(
            "establishing",
            enter=("title", "sun", "house"),
            say="By day, the sun lights up the sky over our homes.",
            actions=(P.Action("pulse", "sun", dur="long"), *point("sun")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="sun",
            enter=(),
            say="As the Earth slowly spins, the sun sinks toward the horizon and sets.",
            actions=(P.Action("fall", "sun", dur="long"), *point("sun")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="moon",
            enter=("moon",),
            say="Night falls, and the moon takes the sun's place in the sky.",
            actions=(P.Action("rise", "moon", dur="long"), *point("moon")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="stars",
            enter=("stars",),
            say="Tiny stars glimmer across the dark.",
            actions=(P.Action("pulse", "stars", dur="long"), *point("stars")),
            hold="short",
        ),
        P.Shot(
            "wide",
            enter=(),
            say="And as the Earth keeps turning, the sun returns — a brand new day.",
            actions=(P.Action("pulse", "sun", dur="long"), *point("sun")),
            hold="long",
        ),
    ]
    scene = P.ScenePlan(
        "s0",
        setting="sky",
        entities=tuple(ents),
        shots=tuple(shots),
        purpose="explain",
        emotion="wonder",
    )
    return P.LessonPlan("Day and Night", (scene,), style=spec.style)


def _photosynthesis_plan(spec: DirectorSpec, P):
    cartoon = spec.style == "cartoon"

    def point(target: str):
        return (P.Action("point", "guide", target),) if cartoon else ()

    # Real things draw as icons (sun/tree/water); the gases (CO2/O2) have no icon, so they land
    # as the kinetic-text backstop — a deliberate showcase of typography-as-asset in a real lesson.
    ents = [
        P.Entity(
            "title",
            "text",
            "text",
            appearance={"text": "Photosynthesis", "font": 0.55},
            place=at("top"),
        ),
        P.Entity("sun", "sun", role="hero"),
        P.Entity("plant", "tree", role="hero"),
        P.Entity("water", "water", role="particle"),
        P.Entity("co2", "carbon dioxide", role="prop"),
        P.Entity("oxygen", "oxygen", role="prop"),
    ]
    shots = [
        P.Shot(
            "establishing",
            enter=("title", "plant", "sun"),
            say="A green plant makes its own food from light, air, and water.",
            actions=(P.Action("pulse", "plant", dur="long"), *point("plant")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="sun",
            enter=(),
            say="Its leaves capture energy from the sun's light.",
            actions=(P.Action("pulse", "sun", dur="long"), *point("sun")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="water",
            enter=("water",),
            say="Its roots drink water from the soil, and it rises up the stem.",
            actions=(P.Action("rise", "water", dur="long"), *point("water")),
            hold="short",
        ),
        P.Shot(
            "medium",
            focus="co2",
            enter=("co2",),
            say="The leaves breathe in carbon dioxide from the air.",
            actions=point("co2"),
            hold="short",
        ),
        P.Shot(
            "wide",
            enter=("oxygen",),
            say="With the sun's energy it makes sugar to grow — and breathes out fresh oxygen.",
            actions=(P.Action("rise", "oxygen", dur="long"), *point("oxygen")),
            hold="long",
        ),
    ]
    scene = P.ScenePlan(
        "s0",
        setting="sky",
        entities=tuple(ents),
        shots=tuple(shots),
        purpose="explain",
        emotion="wonder",
    )
    return P.LessonPlan("Photosynthesis", (scene,), style=spec.style)


_PROCESS_CUES: tuple[tuple[str, object], ...] = (
    ("water cycle", _water_cycle_plan),
    ("day and night", _day_night_plan),
    ("photosynthesis", _photosynthesis_plan),
)


def _process_plan(spec: DirectorSpec, P):
    """A directed exemplar for a recognized process topic, else None (fall to the modes).
    Story mode is a narrative ARC (its own multi-scene structure), so the process exemplar
    only applies to the explain-the-concept modes (learn/draw/explain)."""
    if spec.mode == "story":
        return None
    t = spec.topic.strip().lower()
    for cue, fn in _PROCESS_CUES:
        if cue in t:
            return fn(spec, P)
    return None


def tell_plan(spec: DirectorSpec):
    """The deterministic template as a directed LessonPlan (the offline film)."""
    from engine import plan as P

    proc = _process_plan(spec, P)  # a rich authored exemplar wins over the generic modes
    return proc if proc is not None else _PLAN_MODES.get(spec.mode, _learn_plan)(spec, P)


def plan_lesson(topic: str, spec=None) -> PlanResult:
    """Topic -> a directed LessonPlan + provenance. Template builds the plan; an LLM
    stays on Beats (reliable) and we lift them into a plan via the SAME compiler."""
    global _provider
    if _provider is None:
        _provider = _default_provider()
    s = coerce(topic, spec)
    if isinstance(_provider, TemplateStory):
        return PlanResult(tell_plan(s), "template", "template")
    from engine import plan as P

    r = plan(topic, spec)  # Beats with provenance + sanitation (+ host beat)
    return PlanResult(P.lift_beats(r.beats, topic, s.style), r.requested, r.used, r.reason)


def _learn(spec: DirectorSpec) -> list[Beat]:
    beats = [say(_intro(spec)), _title(spec.topic)]
    prev: str | None = None
    for i, p in enumerate(_PARTS[: spec.concept_count]):
        sid = f"c{i}"
        rel = below("title") if prev is None else right_of(prev)
        beats += [show(sid, p, rel), say(f"{p}.")]
        if prev is not None:
            beats.append(connect(prev, sid))
        prev = sid
    closer = f"And that's {spec.topic}!" if spec.tone == "playful" else f"That's {spec.topic}."
    beats.append(say(closer))
    return beats


def _story(spec: DirectorSpec) -> list[Beat]:
    n = max(2, min(spec.scenes, _STORY_MAX))  # length → scenes-over-time
    beats: list[Beat] = []
    for i in range(n):
        if i:
            beats.append(clear())  # new scene
        label = _arc(i, n)[0]
        beats += [
            say(f"Scene {i + 1}: {label.lower()} of {spec.topic}."),
            show(f"t{i}", "text", at("top"), text=f"Scene {i + 1} · {label}", font=0.5),
            show(f"o{i}", _subject(spec.topic, spec.style), at("center"), size=2.4),
            say(f"{label}."),
        ]
    return beats


def _draw(spec: DirectorSpec) -> list[Beat]:
    return [
        say(_intro(spec)),
        _title(spec.topic),
        show("main", _subject(spec.topic, spec.style), at("center"), size=3.2),
        say(f"This is {spec.topic}."),
    ]


def _explain(spec: DirectorSpec) -> list[Beat]:
    return [
        say(f"{spec.topic} — in one breath."),
        show("cause", "Cause", at("left")),
        show("effect", "Effect", right_of("cause")),
        connect("cause", "effect", "arrow", "leads to"),
        say(f"That's the core of {spec.topic}."),
    ]


_MODES = {"learn": _learn, "story": _story, "draw": _draw, "explain": _explain}

# A presenter pose per mode — the cartoon guide that hosts the lesson.
_PRESENTER_POSE = {"learn": "point", "draw": "present", "explain": "point", "story": "wave"}


def _greeting(spec: DirectorSpec) -> str:
    if spec.audience == "child":
        return f"Hi friends! I'm here to show you all about {spec.topic}."
    return f"Welcome — let's explore {spec.topic} together."


def _with_presenter(beats: list[Beat], spec: DirectorSpec) -> list[Beat]:
    """Cartoon lessons get a reusable host: a presenter waves in at the corner,
    greets, and stays (bob ambient). Whiteboard is untouched (no presenter)."""
    if spec.style != "cartoon":
        return beats
    pose = _PRESENTER_POSE.get(spec.mode, "wave")
    guide = show(
        "guide",
        "presenter",
        at("bottom_left"),
        pose=pose,
        expression="happy",
        size=2.8,
        entrance="rise",
        ambient="bob",
        z=3,
    )
    return [say(_greeting(spec)), guide, *beats]


class TemplateStory:
    name = "template"

    def tell(self, spec: DirectorSpec) -> list[Beat]:
        # The cartoon host is injected in plan() (after sanitation) so BOTH the
        # template and the LLM paths get a presenter, consistently.
        return _MODES.get(spec.mode, _learn)(spec)


# --------------------------------------------------------------------------- #
# Beat JSON parsing (shared by the LLM providers and any recorded fixtures).
# --------------------------------------------------------------------------- #
_REL = {
    "at": at,
    "right_of": right_of,
    "left_of": left_of,
    "above": above,
    "below": below,
    "on": on,
    "near": near,
    "in_panel": in_panel,
}


def _relation(d: dict | None):
    if not d:
        return None
    for k, v in d.items():
        if k == "between" and isinstance(v, (list, tuple)) and len(v) >= 2:
            return between(v[0], v[1])
        if k == "near" and isinstance(v, (list, tuple)):
            return near(v[0], v[1] if len(v) > 1 else "right")
        if k in _REL:
            return _REL[k](v)
    return None


_CAPS = {"learn": 6, "explain": 3, "draw": 4, "story": 4}  # max concepts (per-scene for story)


def sanitize_beats(
    beats: list[Beat], spec: DirectorSpec, max_concepts: int | None = None
) -> list[Beat]:
    """Drop-don't-repair for Story output (the §K philosophy, applied to beats).

    Real LLMs emit structurally-off plans; rather than trust them we DROP what would
    break the board: stray `clear`s outside story mode (which would wipe a concept
    map mid-build), over-long concept lists (cramping/drops), relations that anchor to
    an unshown id (nulled so the thing just flows), and `connect` edges with a dangling
    endpoint. The deterministic templates pass through unchanged. `max_concepts`
    overrides the per-mode cap — a bring-your-own story is author-chosen, so we trust it
    further (the model path stays tightly capped to tame over-production)."""
    story_mode = spec.mode == "story"
    if max_concepts is not None:
        cap = max_concepts
    elif spec.mode == "learn":
        cap = min(max(spec.concept_count, 4), _CAPS["learn"])
    else:
        cap = _CAPS.get(spec.mode, 6)
    out: list[Beat] = []
    shown: set[str] = set()
    concepts = 0
    for b in beats:
        if b.kind == "clear":
            if story_mode:  # a real scene break; learn/draw/explain never wipe
                out.append(b)
                shown, concepts = set(), 0
            continue
        if b.kind == "show" and b.entity:
            is_title = (b.concept or "") == "text"
            if not is_title:
                if concepts >= cap:
                    continue  # drop excess concepts so the board stays readable
                concepts += 1
            rel = b.relation
            if rel is not None and (
                (rel.target and rel.target not in shown)
                or (rel.target2 and rel.target2 not in shown)
            ):
                b = replace(b, relation=None)  # dangling anchor -> let positioning flow it
            shown.add(b.entity)
            out.append(b)
        elif b.kind == "connect":
            if b.entity in shown and b.target in shown:
                out.append(b)  # both endpoints exist; else drop the dangling edge
        elif b.kind == "say" and b.text:
            out.append(b)
    return out


def parse_marks(raw: str) -> tuple[str, tuple[Mark, ...]]:
    """Extract inline [concept] markers from narration -> (clean_text, marks).

    'Water turns to [vapor].' -> ('Water turns to vapor.',
        (Mark(concept='vapor', word='vapor', start=15, end=20),))

    A marker is a balanced [..] whose ] comes before the next [. Drop-don't-repair:
    empty [] and stray/unbalanced brackets are STRIPPED from the clean text (TTS never
    speaks a bracket), never patched; nested brackets are unsupported. start/end are
    offsets into the returned clean text. Entity binding happens later (compile-time)."""
    if not raw or ("[" not in raw and "]" not in raw):
        return (raw or ""), ()  # fast path only when NEITHER bracket is present (a lone ] is stray)
    parts: list[str] = []
    marks: list[Mark] = []
    clen = 0  # running length of the clean text built so far
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "[":
            j = raw.find("]", i + 1)
            nxt = raw.find("[", i + 1)
            if j != -1 and (nxt == -1 or j < nxt):  # a balanced marker
                word = raw[i + 1 : j].strip()
                if word:
                    parts.append(word)
                    marks.append(Mark(word.lower(), word, clen, clen + len(word)))
                    clen += len(word)
                i = j + 1
                continue
            i += 1  # stray '[' -> drop
            continue
        if c == "]":
            i += 1  # stray ']' -> drop
            continue
        parts.append(c)
        clen += 1
        i += 1
    return "".join(parts), tuple(marks)


def parse_beats(data: dict | list) -> list[Beat]:
    arr = data.get("beats", []) if isinstance(data, dict) else data
    if not isinstance(arr, list):
        return []
    out: list[Beat] = []
    for b in arr:
        if not isinstance(b, dict):  # models sometimes emit string fragments — skip, don't crash
            continue
        kind = b.get("kind")
        if kind == "show" and b.get("entity"):
            geom = dict(b.get("geometry") or {})
            # quantity may arrive at the top level (e.g. {"kind":"show",...,"count":7}); fold
            # the recognized multiplicity keys into geometry so measure() sees them.
            for key in ("count", "arrangement"):
                if key in b and key not in geom:
                    geom[key] = b[key]
            out.append(show(b["entity"], b.get("concept"), _relation(b.get("relation")), **geom))
        elif kind == "connect":
            src, dst = b.get("src") or b.get("entity"), b.get("dst") or b.get("target")
            if src and dst:  # b["kind"] is the beat kind ("connect"), NOT a connector type
                out.append(connect(src, dst, "arrow", b.get("label")))
        elif kind == "say" and b.get("text"):
            clean, marks = parse_marks(b["text"])  # split inline [concept] markers off the text
            out.append(say(clean, marks))
        elif kind == "clear":
            out.append(clear())
    return out


# --------------------------------------------------------------------------- #
# LLM providers (behind STORY_PROVIDER) — never hit in tests.
# --------------------------------------------------------------------------- #
class _LLMStory:
    name = "llm"

    def _complete(self, prompt: str, schema: dict | None = None) -> str | None:  # pragma: no cover
        raise NotImplementedError

    def tell(self, spec: DirectorSpec) -> list[Beat]:  # pragma: no cover - network
        # No silent fallback: return [] on failure and let plan() decide + report.
        hint = _MODE_HINT.get(spec.mode, _MODE_HINT["learn"])
        prompt = _PROMPT.format(
            topic=spec.topic,
            mode_hint=hint,
            audience=spec.audience,
            tone=spec.tone,
            depth=spec.depth,
            concept_count=spec.concept_count,
            style=spec.style,
            domain_line=_domain_prompt_line(spec.domain),
        )
        # The per-lesson schema's minItems FORCES a full lesson (no 1-2-line truncation).
        raw = self._complete(prompt, _beat_schema(spec))  # may raise -> plan() reports it
        return parse_beats(json.loads(_strip_json(raw or "{}")))


class OllamaStory(_LLMStory):
    name = "ollama"

    def __init__(self, model: str | None = None) -> None:
        # The resolved model is passed in by models.resolve_story() (auto-picked
        # from installed); the env override is the fallback for direct construction.
        self.model = model or os.environ.get("OLLAMA_STORY_MODEL", "qwen2.5:7b")
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def _complete(self, prompt: str, schema: dict | None = None) -> str | None:  # pragma: no cover
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                # structured outputs: per-lesson schema (minItems forces a full lesson);
                # falls back to the base object-schema if none was passed.
                "format": schema or BEAT_SCHEMA,
                "messages": [{"role": "user", "content": prompt}],
            }
        ).encode()
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        return _http_json(req)["message"]["content"]


class GeminiStory(_LLMStory):
    name = "gemini"

    def __init__(self) -> None:
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.key = os.environ.get("GEMINI_API_KEY", "")

    def _complete(self, prompt: str, schema: dict | None = None) -> str | None:  # pragma: no cover
        # Gemini follows the prompt's count guidance well; we keep responseMimeType=json
        # (its responseSchema dialect differs from Ollama's, so we don't reuse `schema` here).
        if not self.key:
            return None
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.key}"
        )
        body = json.dumps(
            {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},  # force valid JSON
            }
        ).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        data = _http_json(req)
        return data["candidates"][0]["content"]["parts"][0]["text"]


class VertexStory(_LLMStory):
    name = "vertex"

    def __init__(self) -> None:
        self.model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.project = _vertex_project()
        self.location = _vertex_location()

    def _complete(self, prompt: str, schema: dict | None = None) -> str | None:  # pragma: no cover
        if not self.project:
            return None
        url = _vertex_generate_url(self.project, self.location, self.model)
        body = json.dumps(
            {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_google_access_token()}",
            },
        )
        data = _http_json(req)
        return data["candidates"][0]["content"]["parts"][0]["text"]


def _vertex_project() -> str:
    return (
        os.environ.get("VERTEX_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or ""
    ).strip()


def _vertex_location() -> str:
    return (
        os.environ.get("VERTEX_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or "us-central1"
    ).strip()


def _vertex_generate_url(project: str, location: str, model: str) -> str:
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1/projects/{project}/locations/{location}/publishers/google/"
        f"models/{model}:generateContent"
    )


def _google_access_token() -> str:
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "").strip()
    if token:
        return token
    with contextlib.suppress(Exception):
        import google.auth
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(Request())
        if creds.token:
            return creds.token
    commands = (
        ["gcloud", "auth", "application-default", "print-access-token"],
        ["gcloud", "auth", "print-access-token"],
    )
    for cmd in commands:
        with contextlib.suppress(Exception):
            out = subprocess.check_output(cmd, text=True, timeout=10).strip()
            if out:
                return out
    try:
        raise RuntimeError("gcloud token command returned no token")
    except Exception as e:  # noqa: BLE001 - surface a setup hint through StoryResult.reason
        raise RuntimeError(
            "could not get Google Cloud access token; run `gcloud auth application-default login` "
            "or set GOOGLE_APPLICATION_CREDENTIALS/GOOGLE_OAUTH_ACCESS_TOKEN"
        ) from e


def _http_json(req: urllib.request.Request, timeout: int = 120) -> dict:
    """POST and parse JSON; on an HTTP error, raise with the SERVER's message
    (e.g. Google's 'API key not valid' / 'PERMISSION_DENIED'), not a bare code."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        with contextlib.suppress(Exception):
            detail = json.loads(detail).get("error", {}).get("message", detail)
        raise RuntimeError(f"HTTP {e.code}: {detail[:240]}") from None


def _strip_json(s: str) -> str:
    i, j = s.find("{"), s.rfind("}")
    return s[i : j + 1] if i != -1 and j != -1 else s


def _default_provider() -> StoryProvider:
    """Local-first: models.resolve_story() picks Ollama (auto) with the best
    installed model when it's running, else the deterministic template. Cloud
    only when explicitly named + keyed (never a silent default)."""
    from engine import models

    r = models.resolve_story()
    if r.provider == "ollama":
        # EXPERIMENT (opt-in): generate the lesson scene-by-scene (autoregressively) instead of
        # in one big call — scales to long lessons a 7B model can't emit in a single shot.
        if os.environ.get("STORY_METHOD", "").strip().lower() in ("ar", "autoregressive"):
            from engine.autostory import AutoregressiveStory

            return AutoregressiveStory(model=r.model)
        return OllamaStory(model=r.model)
    if r.provider == "gemini":
        return GeminiStory()
    if r.provider == "vertex":
        return VertexStory()
    return TemplateStory()
