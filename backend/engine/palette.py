"""The cartoon color system — the render-time STYLE layer (docs/CARTOON.md).

A *Style* decides how a geometry-only Drawable is PAINTED, not how it is built:

    whiteboard : mono strokes, no fill (the original product) — untouched here.
    cartoon    : flat saturated fills + a darker outline + colored scene
                 backgrounds (the Kurzgesagt look).

Geometry is color-independent and cached (drawing.measure); color is applied at
PAINT time through `apply()`, so the SAME recipe renders in either style with no
per-asset fork. Whiteboard is returned byte-for-byte unchanged so the existing
board/tests stay identical — cartoon only ever ADDS color.

The palette is DATA: a concept -> (fill, line) map for primitives + un-authored
recipes + line-art tinting, and a topic -> background scene picker. Recipes that
already carry authored colors (icons.py) win; this fills the gaps.
"""

from __future__ import annotations

from dataclasses import replace

from engine.contracts import Stroke

WHITEBOARD = "whiteboard"
CARTOON = "cartoon"
STYLES = (WHITEBOARD, CARTOON)

# Default cartoon fill for a closed shape with no concept color. A WARM amber —
# warm-on-cool is the Kurzgesagt staple, so an unknown shape pops on every (mostly
# cool) scene backdrop instead of vanishing into the blue sky/underwater grounds.
DEFAULT_FILL = "#ffb347"
DEFAULT_LINE = "#d6862b"  # the matching warm outline
LABEL_INK = "#1b2430"  # label text on a LIGHT scene background
LABEL_INK_DARK = "#eef3fb"  # label text on a DARK scene (space/night/underwater)


# --------------------------------------------------------------------------- #
# Concept -> (fill, line). Seeds primitives, un-authored recipes, and line-art
# tinting. Authored recipe colors (icons.py) override these. Keyed on a
# normalized concept; substring fallback catches compounds (e.g. "rain cloud").
# --------------------------------------------------------------------------- #
CONCEPT_COLORS: dict[str, tuple[str, str]] = {
    # sky / weather
    "sun": ("#ffd23f", "#e0991b"),
    "moon": ("#e8ecf3", "#9aa4b2"),
    "star": ("#ffe066", "#e0a800"),
    "cloud": ("#ffffff", "#bcc9d6"),
    "rain": ("#7cc4ff", "#4a90d9"),
    "snow": ("#eef6ff", "#bcd4ee"),
    "lightning": ("#ffd23f", "#e0991b"),
    "rainbow": ("#ff8fa3", "#d65f74"),
    "sky": ("#bfe3ff", "#8fc3ef"),
    # water / nature
    "water": ("#5b8def", "#2f6fd0"),
    "wave": ("#5b8def", "#2f6fd0"),
    "ocean": ("#3f8fd0", "#2566a0"),
    "river": ("#5b8def", "#2f6fd0"),
    "ice": ("#cdeaff", "#92c3ea"),
    "fire": ("#ff7a3c", "#d8501a"),
    "flame": ("#ff7a3c", "#d8501a"),
    "tree": ("#3fa46a", "#2b7a4b"),
    "leaf": ("#5cbf7e", "#2b7a4b"),
    "grass": ("#7cc47f", "#4f9c58"),
    "plant": ("#5cbf7e", "#2b7a4b"),
    "flower": ("#ff8fb0", "#d65f86"),
    "mountain": ("#8a93a6", "#5b6478"),
    "rock": ("#9aa3b0", "#6b7280"),
    "sand": ("#f2d59a", "#cfa85e"),
    "soil": ("#8a5a2b", "#5e3c1a"),
    "wood": ("#b9824f", "#8a5a2b"),
    "trunk": ("#8a5a2b", "#5e3c1a"),
    # life / body
    "heart": ("#ff5d73", "#d63852"),
    "brain": ("#ffb0b8", "#d97b86"),
    "blood": ("#e23b46", "#a8222b"),
    "person": ("#f4c08a", "#c98b4d"),
    "skin": ("#f4c08a", "#c98b4d"),
    "eye": ("#ffffff", "#26354d"),
    "cell": ("#bfe3a0", "#7aa85a"),
    "atom": ("#9ad0ff", "#4a90d9"),
    "molecule": ("#9ad0ff", "#4a90d9"),
    "dna": ("#a0e0c0", "#4aa884"),
    "egg": ("#fff4d6", "#e6cf94"),
    # objects / abstract
    "house": ("#ffcaa8", "#d68a5e"),
    "roof": ("#e2614b", "#b03a28"),
    "book": ("#ffba6b", "#d68a2a"),
    "lightbulb": ("#ffe066", "#e0a800"),
    "idea": ("#ffe066", "#e0a800"),
    "rocket": ("#e8ecf3", "#9aa4b2"),
    "planet": ("#7c9cf0", "#4a6fd0"),
    "earth": ("#5ca86a", "#2b7a4b"),
    "gear": ("#aab4c4", "#6b7686"),
    "coin": ("#ffd23f", "#e0a800"),
    "money": ("#7cc47f", "#4f9c58"),
    "battery": ("#7cc47f", "#4f9c58"),
    "energy": ("#ffd23f", "#e0a800"),
    "arrow": ("#ff7a3c", "#d8501a"),
    "box": ("#ffcaa8", "#d68a5e"),
}

# Substring buckets: a concept that CONTAINS one of these tints accordingly.
_SUBSTR = [
    ("cloud", "cloud"),
    ("water", "water"),
    ("sun", "sun"),
    ("fire", "fire"),
    ("leaf", "leaf"),
    ("tree", "tree"),
    ("heart", "heart"),
    ("star", "star"),
    ("mountain", "mountain"),
    ("flower", "flower"),
    ("rocket", "rocket"),
    ("planet", "planet"),
    ("energy", "energy"),
]


def _norm(concept: str) -> str:
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def concept_colors(concept: str | None) -> tuple[str, str]:
    """(fill, line) for a concept. Exact match, then substring, then default."""
    if not concept:
        return (DEFAULT_FILL, DEFAULT_LINE)
    c = _norm(concept)
    if c in CONCEPT_COLORS:
        return CONCEPT_COLORS[c]
    for needle, key in _SUBSTR:
        if needle in c:
            return CONCEPT_COLORS[key]
    return (DEFAULT_FILL, DEFAULT_LINE)


def tint(hex_color: str, amount: float) -> str:
    """Mix a hex color toward white by `amount` (0..1) — a soft pastel of the color."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    mix = lambda v: round(v + (255 - v) * amount)  # noqa: E731
    return f"#{mix(r):02x}{mix(g):02x}{mix(b):02x}"


def _blend(hex_color: str, target: str, amount: float) -> str:
    """Mix a hex color toward an arbitrary target hex by `amount` (0..1)."""
    a = hex_color.lstrip("#")
    b = target.lstrip("#")
    ch = (int(a[i : i + 2], 16) for i in (0, 2, 4))
    tg = [int(b[i : i + 2], 16) for i in (0, 2, 4)]
    out = (round(c + (t - c) * amount) for c, t in zip(ch, tg, strict=True))
    return "#" + "".join(f"{v:02x}" for v in out)


# A scene's EMOTION nudges the backdrop warmth — the same staging FEELS different. The
# anchor (warm gold / cool blue) is blended in by a small amount so the scene identity
# survives; "calm"/"curious" are the neutral baseline (no shift). This is the felt half
# of direction: purpose says why the scene exists, emotion says how it should feel.
_MOOD_ANCHOR: dict[str, tuple[str, float]] = {
    "joyful": ("#ffd98a", 0.12),  # warm, sunny
    "wonder": ("#ffe1b0", 0.09),  # golden awe
    "tense": ("#9fb4d6", 0.12),  # cool, drained
    "curious": ("#fff0cf", 0.04),  # a hint of warmth
    "calm": ("#ffffff", 0.0),  # baseline
}


def apply_mood(bg: dict, emotion: str | None) -> dict:
    """Tint a backdrop toward an emotion's warmth (returns a new bg; bg unchanged if the
    emotion is unknown or neutral). Only the sky gradient shifts — the ground stays put."""
    anchor = _MOOD_ANCHOR.get(emotion or "")
    if not anchor or anchor[1] == 0.0:
        return bg
    hexc, amt = anchor
    g = bg.get("gradient")
    if not g:
        return bg
    grad = {"top": _blend(g["top"], hexc, amt), "bottom": _blend(g["bottom"], hexc, amt)}
    return {**bg, "gradient": grad, "fill": grad["bottom"]}


# --------------------------------------------------------------------------- #
# apply(): the paint-time stylizer. Whiteboard -> untouched. Cartoon -> fill
# closed shapes + outline strokes, honoring any authored color already on a stroke.
# --------------------------------------------------------------------------- #
def apply(strokes: tuple[Stroke, ...], style: str, concept: str | None) -> tuple[Stroke, ...]:
    if style != CARTOON:
        # Whiteboard: STRIP any authored color so the mono board stays intact even
        # when a recipe carries cartoon hex. Style is the single source of color.
        return tuple(replace(s, color=None, fill=None) for s in strokes)
    fill_default, line_default = concept_colors(concept)
    out = []
    for s in strokes:
        # Fill only CLOSED shapes — an authored fill on an open stroke (a stray
        # `fill:` on a line/arc) is dropped, so the IR is self-consistent.
        fill = (s.fill or fill_default) if s.closed else None
        line = s.color if s.color else line_default
        out.append(replace(s, fill=fill, color=line))
    return tuple(out)


def op_color(
    style: str, concept: str | None, requested: str | None, scene: str | None = None
) -> str:
    """The DrawOp's top-level color (label text + open-stroke fallback). In cartoon,
    labels must contrast the scene: dark ink on a light stage, light ink on a dark one."""
    if requested:
        return requested
    if style == CARTOON:
        return LABEL_INK_DARK if scene in DARK_SCENES else LABEL_INK
    return "#e6edf3"  # whiteboard ink (drawing.DEFAULT_COLOR)


# --------------------------------------------------------------------------- #
# Scene backgrounds — a topic/mode -> a full-board backdrop layer (cartoon only).
# A backdrop is flat fill + an optional vertical 2-stop gradient (cheap depth).
# --------------------------------------------------------------------------- #
# name -> (top_color, bottom_color). A vertical gradient = instant depth.
SCENES: dict[str, tuple[str, str]] = {
    "sky": ("#cdeeff", "#8fc8f0"),
    "space": ("#0b1026", "#241a4d"),
    "underwater": ("#1f7fb8", "#0c3d63"),
    "classroom": ("#f3ead6", "#e3d2ad"),
    "sunset": ("#ffd6a5", "#ff8fa3"),
    "forest": ("#cdeeb0", "#7cc47f"),
    "night": ("#10162e", "#27315c"),
    "desert": ("#ffe6b0", "#e3b56b"),
    "body": ("#ffe0e4", "#f3b9c2"),
    "default": ("#7fb8ec", "#cfe9ff"),  # a real sky: deeper blue up top, light haze at the horizon
}

# Dark backdrops need LIGHT label ink (op_color) for contrast.
DARK_SCENES = frozenset({"space", "underwater", "night"})

# Topic keyword -> scene. First match wins (order matters: specific before broad).
# Night precedes space so "a starry night"/"the moon at night" get the gentle navy
# stage, not the deep-space void; space keeps the astronomy terms.
_SCENE_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("night", "sleep", "dream", "moon", "starry"), "night"),
    (
        (
            "space",
            "planet",
            "galaxy",
            "star",
            "universe",
            "orbit",
            "rocket",
            "astronom",
            "solar",
            "comet",
            "asteroid",
            "satellite",
        ),
        "space",
    ),
    (("ocean", "sea", "underwater", "fish", "marine", "coral", "whale", "tide"), "underwater"),
    (("desert", "sand", "dune", "cactus"), "desert"),
    (("body", "organ", "heart", "blood", "cell", "anatomy", "lungs", "muscle"), "body"),
    (
        (
            "forest",
            "jungle",
            "plant",
            "tree",
            "photosynth",
            "ecosystem",
            "rainforest",
            "leaf",
            "leaves",
        ),
        "forest",
    ),
    (("sunset", "evening", "dusk", "dawn"), "sunset"),
    (("school", "class", "math", "history", "grammar", "learn", "lesson"), "classroom"),
    (("sky", "weather", "cloud", "rain", "water cycle", "wind", "storm", "atmosphere"), "sky"),
]


def scene_for(topic: str, mode: str = "learn") -> str:
    t = _norm(topic)
    for needles, scene in _SCENE_KEYWORDS:
        if any(n in t for n in needles):
            return scene
    return "default"


# --------------------------------------------------------------------------- #
# Motion defaults (cartoon only) — "life in the frame" without authoring. A
# concept's ambient idle loop + how it enters. Explicit beat hints override these.
# --------------------------------------------------------------------------- #
_CHARACTERS = frozenset(
    {"presenter", "teacher", "narrator", "guide", "host", "character", "avatar", "buddy"}
)

# EXPLANATORY idle motion — a concept's nature drives how it moves, so a lesson is
# meaningful in motion without anyone authoring it: water rises, rain falls, rivers flow,
# the sun glows. Matched by word, so "rain cloud" floats but "rain" falls.
_AMBIENT: dict[str, str] = {
    **dict.fromkeys(
        ("vapor", "steam", "evaporation", "smoke", "gas", "heat", "bubble", "balloon", "smell"),
        "rise",
    ),
    **dict.fromkeys(
        (
            "rain",
            "snow",
            "hail",
            "precipitation",
            "raindrop",
            "droplet",
            "drop",
            "leaf",
            "meteor",
            "gravity",
            "anchor",
        ),
        "fall",
    ),
    **dict.fromkeys(
        (
            "river",
            "stream",
            "wave",
            "current",
            "water",
            "ocean",
            "sea",
            "flow",
            "wind",
            "flag",
            "ribbon",
            "snake",
            "electricity",
        ),
        "flow",
    ),
    **dict.fromkeys(
        (
            "sun",
            "star",
            "fire",
            "flame",
            "heart",
            "energy",
            "lightbulb",
            "idea",
            "lightning",
            "spark",
            "glow",
            "battery",
            "atom",
        ),
        "glow",
    ),
    **dict.fromkeys(
        (
            "cloud",
            "bird",
            "kite",
            "butterfly",
            "bee",
            "moon",
            "planet",
            "rainbow",
            "ghost",
            "spirit",
        ),
        "float",
    ),
}


def ambient_for(concept: str | None) -> str:
    if not concept:
        return ""
    c = _norm(concept)
    if c in _CHARACTERS:
        return "bob"
    words = set(c.split())
    if c in _AMBIENT:
        return _AMBIENT[c]
    for k in words:  # match a whole word (so "starfish" doesn't glow)
        if k in _AMBIENT:
            return _AMBIENT[k]
    return ""


def entrance_for(concept: str | None) -> str:
    """Characters rise/pop in; everything else inks on (the teaching reveal)."""
    if concept and _norm(concept) in _CHARACTERS:
        return "rise"
    return "draw"


# A ground band gives the scene a HORIZON — props stand on the ground, not float.
# Some scenes have no ground (space/night/underwater are full-bleed). frac = band height.
HORIZON_FRAC = 0.30  # the ground occupies the bottom 30% of the board
_SCENE_GROUND: dict[str, str] = {
    "sky": "#86c86a",
    "forest": "#6aae54",
    "classroom": "#caa472",
    "sunset": "#b98a5a",
    "desert": "#e0b86a",
    "default": "#84c45f",  # a richer grass green (was a washed-out pale #bcd9a0)
}


def background(topic: str, mode: str = "learn", style: str = CARTOON) -> dict | None:
    """The backdrop event payload (board units handled client-side), or None for
    whiteboard. `gradient` is a 2-stop vertical gradient; `ground` is the horizon band."""
    if style != CARTOON:
        return None
    scene = scene_for(topic, mode)
    top, bottom = SCENES.get(scene, SCENES["default"])
    bg = {"scene": scene, "fill": bottom, "gradient": {"top": top, "bottom": bottom}}
    if scene in _SCENE_GROUND:
        bg["ground"] = {"fill": _SCENE_GROUND[scene], "frac": HORIZON_FRAC}
    return bg
