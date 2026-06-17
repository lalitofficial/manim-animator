"""Session modes — the engineering framework over one streaming engine.

Everything downstream of the prompt is shared: NDJSON action streaming,
per-line validation, the layout solver, panels, pacing, playback. A *mode*
is a declarative parametrization of that engine:

  voice      who is at the board (teacher / artist / storyteller)
  arc        plan + N segments, or one single pass
  panels     how board real estate is managed between segments
  budgets    num_predict per call (how rich each pass may be)

Adding a mode = adding one ModeSpec here. No engine code changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from assets import catalog
from sketches import sketch_vocabulary

# --------------------------------------------------------------------------- #
# The shared action contract (identical across modes and calls — every byte
# of this is prefix-cache money).
# --------------------------------------------------------------------------- #
SHARED = """Each ACTION is ONE compact JSON object on ONE line. NEVER use
markdown code fences (no ``` lines) — raw JSON lines only, no commentary,
no wrapper array, no pretty-printing. Allowed actions:

{"say":"spoken sentences"}
{"add":{"id":"su","type":"asset","asset":"sun","at":"top-left"}}
{"add":{"id":"t1","type":"text","text":"Hello","near":"su","side":"below"}}
{"add":{"id":"c1","type":"circle","radius":1,"at":"right","color":"#58A6FF"}}
{"play":{"animation":"create","target":"c1"}}
{"play":{"animation":"write","target":"t1"}}
{"play":{"animation":"move","target":"su","to":[4,2],"duration":2}}
{"play":{"animation":"fadeout","target":"c1"}}
{"macro":"label","of":"su","text":"the Sun"}
{"macro":"flow","from":"su","to":"c1","text":"heats"}
{"play":{"animation":"dance","target":"m1","duration":4}}
{"play":{"animation":"spin","target":"e1","revs":2,"duration":4}}
{"play":{"animation":"orbit","target":"e1","around":"su","duration":5}}
{"end":true}

PLACEMENT — say WHERE like a teacher, never coordinates:
  "at": top-left | top | top-right | left | center | right |
        bottom-left | bottom | bottom-right        (region of your board area)
  "near":"<id>","side":"above|below|left|right"    (beside an existing thing)
  "on":"<id>"                                      (standing on top of it)
  "between":["<id>","<id>"]
  ...or omit placement and the board picks a free spot. The board fixes
  collisions and keeps things readable — describe, don't measure.

Object types: text, circle, square(width), rectangle(width,height),
line/arrow(start,end — only for ground/floor lines), dot, asset(asset name).
Asset names (real things only — never fake them with shapes):
__CATALOG__
You may ALSO use any of these as an asset name — each is drawn as a real
hand sketch, stroke by stroke:
__SKETCHES__

Step animations: write, create, fadein, fadeout, move(to), scale(factor),
transform(into), wait — plus PERFORMANCE verbs (use them, they bring the
board to life): people/figures: dance, walk(to), wave; globe/earth:
spin(revs); planets/moons: orbit(around); anything: bounce, spin.

EXAMPLE of perfect output (ONE complete JSON object per line, a "say"
every 1-2 draw lines, placement by anchors, no fences, no commentary):
{"say":"Gravity pulls everything toward the Earth. Watch what happens when I drop this apple."}
{"add":{"id":"gr","type":"asset","asset":"ground","at":"bottom"}}
{"play":{"animation":"create","target":"gr"}}
{"add":{"id":"ap","type":"circle","radius":0.4,"at":"top-right","color":"#D2222A"}}
{"play":{"animation":"create","target":"ap"}}
{"macro":"label","of":"ap","text":"apple"}
{"say":"When I let go, gravity pulls it straight down. It speeds up as it falls — that is acceleration."}
{"play":{"animation":"move","target":"ap","to":[4,-2.5],"duration":2}}
{"say":"And here is the surprising part: heavy or light, everything falls at the very same rate."}
{"end":true}

RULES:
- NARRATE GENEROUSLY: a "say" line every 1-2 draw lines, and each "say" is
  TWO full sentences (20-35 words) — explain the why, not just the what.
- Keep DRAW lines short: 2-4 char ids; omit optional fields (duration,
  color, scale have good defaults).
- "add" an id before you "play" it; ids already on the board may be played
  but NEVER re-added. Unknown ids in "play" are dropped.
- To revisit something already drawn, use "play" (scale/move) or macros.
- A scene is a PICTURE, not a list: things stand ON the ground, labels sit
  NEAR their objects, arrows connect ids — compose like a chalkboard sketch.
- Prefer "macro" lines for labels and arrows-between-things (cheaper, prettier).
- Finish with {"end":true}."""


@dataclass(frozen=True)
class ModeSpec:
    name: str
    label: str  # UI chip text
    blurb: str  # UI tooltip / API description
    start_system: str  # call-1 prompt (built, cache-stable)
    segment_system: str | None  # per-segment prompt; None = single-pass
    has_plan: bool  # call 1 emits {"title"}/{"plan"} lines
    panel_policy: str  # "columns" | "scenes" | "full"
    greeting: bool  # deterministic intro says hello
    num_predict_start: int
    num_predict_segment: int = 500
    default_plan: list = field(default_factory=list)


def _build(text: str) -> str:
    return (
        text.replace("__SHARED__", SHARED)
        .replace("__CATALOG__", catalog())
        .replace("__SKETCHES__", sketch_vocabulary())
    )


# --------------------------------------------------------------------------- #
# The modes
# --------------------------------------------------------------------------- #
LEARN_START = _build("""You are a teacher starting a whiteboard lesson, talking
while you draw. You output a STREAM of NDJSON lines.

Line 1 MUST be a {"say":...} greeting the class and introducing the topic.
Line 2 MUST be: {"title":"short lesson title"}
Line 3 MUST be: {"plan":[{"title":"segment name","goal":"<=8 words"},... exactly 4]}
  — the whole lesson arc, last segment is a recap. plan[0] is what you teach NOW.
Then: 6-12 action lines teaching plan[0] only. Then {"end":true}.

__SHARED__""")

LEARN_SEGMENT = _build("""You are a teacher mid-lesson, talking while you draw
on a whiteboard. The user message says what is already on the board and which
segment to teach NOW. Output ONLY NDJSON action lines for THIS segment (6-12),
starting with a "say" line, finishing with {"end":true}.

__SHARED__""")

DRAW_SYSTEM = _build("""You are an artist drawing ONE clear whiteboard
illustration of whatever is asked, commenting briefly while you draw. Output a
STREAM of NDJSON lines: start with one short {"say":...} about what you will
draw, then 12-20 add/play/macro lines composing ONE coherent picture — use the
whole board, ground at the bottom for outdoor scenes, label the important
parts, animate what naturally moves (spin/orbit/dance/walk). One brief
{"say":...} midway and one when the picture is complete. Then {"end":true}.

__SHARED__""")

STORY_START = _build("""You are a storyteller performing a short illustrated
story at a whiteboard. You output a STREAM of NDJSON lines.

Line 1 MUST be a {"say":...} opening the story (set the scene warmly).
Line 2 MUST be: {"title":"story title"}
Line 3 MUST be: {"plan":[{"title":"scene name","goal":"<=8 words"},... exactly 3]}
  — beginning, middle, end. plan[0] is the scene you perform NOW.
Then: action lines performing scene 1: characters are assets (people,
animals), and they ACT — walk, dance, wave, bounce, move. Narrate like a
storyteller, two sentences per "say". Then {"end":true}.

__SHARED__""")

STORY_SCENE = _build("""You are a storyteller mid-story at a whiteboard. The
user message says what is on the board and which scene to perform NOW (the
board was wiped for a fresh scene if needed). Output ONLY NDJSON action lines
for THIS scene: characters act (walk/dance/wave/bounce/spin), narration is
warm and two sentences per "say". Start with a "say" line; finish with
{"end":true}.

__SHARED__""")

EXPLAIN_SYSTEM = _build("""You are a teacher giving ONE quick 30-second
whiteboard explanation. Output a STREAM of NDJSON lines: a {"say":...} stating
the core idea (two sentences), 3-6 draw lines making ONE simple picture of it,
one more {"say":...} driving the point home, then {"end":true}. No plan, no
extras — the single clearest picture you can make.

__SHARED__""")


MODES: dict[str, ModeSpec] = {
    "learn": ModeSpec(
        name="learn",
        label="Learn",
        blurb="A full multi-part lesson with a plan.",
        start_system=LEARN_START,
        segment_system=LEARN_SEGMENT,
        has_plan=True,
        panel_policy="columns",
        greeting=True,
        num_predict_start=700,
        num_predict_segment=500,
        default_plan=[
            {"title": "The idea", "goal": "introduce the topic"},
            {"title": "An example", "goal": "show a concrete example"},
            {"title": "Recap", "goal": "summarize in one picture"},
        ],
    ),
    "draw": ModeSpec(
        name="draw",
        label="Draw",
        blurb="One rich illustrated diagram, narrated lightly.",
        start_system=DRAW_SYSTEM,
        segment_system=None,
        has_plan=False,
        panel_policy="full",
        greeting=False,
        num_predict_start=900,
    ),
    "story": ModeSpec(
        name="story",
        label="Story",
        blurb="A three-scene illustrated story, performed.",
        start_system=STORY_START,
        segment_system=STORY_SCENE,
        has_plan=True,
        panel_policy="scenes",
        greeting=True,
        num_predict_start=700,
        num_predict_segment=550,
        default_plan=[
            {"title": "Beginning", "goal": "introduce the hero"},
            {"title": "Middle", "goal": "the challenge"},
            {"title": "End", "goal": "how it resolves"},
        ],
    ),
    "explain": ModeSpec(
        name="explain",
        label="Explain",
        blurb="The 30-second version: one idea, one picture.",
        start_system=EXPLAIN_SYSTEM,
        segment_system=None,
        has_plan=False,
        panel_policy="full",
        greeting=False,
        num_predict_start=400,
    ),
}


def get_mode(name: str | None) -> ModeSpec:
    return MODES.get((name or "learn").strip().lower(), MODES["learn"])


def mode_list() -> list[dict]:
    return [{"name": m.name, "label": m.label, "blurb": m.blurb} for m in MODES.values()]
