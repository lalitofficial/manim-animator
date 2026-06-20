"""The Director — the intent/policy layer above the engines (ARCHITECTURE: above §3).

A typed DirectorSpec captures HOW a lesson should be taught (mode, depth, audience,
tone, density, energy, scene count). Every field maps to either a Story-prompt
modifier (depth/audience/tone) or a deterministic engine knob (density->concept
count, energy->pacing, scene_count->segments) — NOT to more LLM planning stages.

`direct()` builds a spec deterministically from a request + explicit controls
(heuristics, hermetic). An LLM interpreter can refine it later behind a flag.

Pipeline:  request -> DirectorSpec -> Story(Beats) -> Drawing/Positioning/Board.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

MODES = ("learn", "story", "draw", "explain")
DEPTHS = ("brief", "normal", "deep")
AUDIENCES = ("child", "general", "expert")
TONES = ("neutral", "playful", "formal")
DENSITIES = ("sparse", "normal", "dense")
ENERGIES = ("calm", "normal", "lively")
STYLES = ("whiteboard", "cartoon")  # render style (docs/CARTOON.md) — a separate axis from mode
LENGTHS = (
    "1min",
    "2min",
    "5min",
    "10min",
)  # target duration — drives scene count (scenes-over-time)


@dataclass(frozen=True)
class DirectorSpec:
    topic: str
    mode: str = "learn"
    depth: str = "normal"
    audience: str = "general"
    tone: str = "neutral"
    density: str = "normal"
    energy: str = "normal"
    length: str = "2min"  # target duration (1min/2min/5min/10min) → scene count
    scene_count: int = 0  # 0 = derive from `length`; an explicit >0 overrides it
    style: str = "whiteboard"  # whiteboard (mono) | cartoon (filled, colored)
    domain: str = ""  # inferred subject domain (cloud-computing/weather/…) — drives
    #                   semantic concept resolution + which imported icon sets apply

    # ---- derived, deterministic engine knobs ----
    @property
    def concept_count(self) -> int:
        base = {"sparse": 2, "normal": 3, "dense": 5}.get(self.density, 3)
        if self.depth == "deep":
            base += 1
        if self.depth == "brief":
            base = max(2, base - 1)
        if (
            self.style == "cartoon"
            and self.mode in {"learn", "draw", "story"}
            and self.depth != "brief"
        ):
            base += 1
        base = min(base, 6)
        return base

    @property
    def draw_speed(self) -> float:
        return {"calm": 0.7, "normal": 1.0, "lively": 1.5}.get(self.energy, 1.0)

    @property
    def say_dwell(self) -> float:
        return {"calm": 1.3, "normal": 1.0, "lively": 0.7}.get(self.energy, 1.0)

    @property
    def cinematic(self) -> bool:
        # Cartoon lessons get a camera that follows the lesson (zoom to each concept,
        # pull back to reveal). Calm energy keeps the classic static wide shot.
        return self.style == "cartoon" and self.energy != "calm"

    @property
    def target_seconds(self) -> int:
        return {"1min": 60, "2min": 120, "5min": 300, "10min": 600}.get(self.length, 120)

    @property
    def target_scenes(self) -> int:
        """A lesson's LENGTH is scenes-over-time (each scene clears the board, ~30-40s each),
        NOT more concepts crammed on one board — that just overflows the layout. Duration →
        scene count. ('2min' = 3, the historical default, so existing behavior is unchanged.)"""
        return {"1min": 2, "2min": 3, "5min": 8, "10min": 16}.get(self.length, 3)

    @property
    def scenes(self) -> int:
        """The effective scene count: an explicit `scene_count` wins; else derive from `length`."""
        return self.scene_count if self.scene_count > 0 else self.target_scenes


def to_dict(spec: DirectorSpec) -> dict:
    d = asdict(spec)
    d.update(
        concept_count=spec.concept_count,
        draw_speed=spec.draw_speed,
        say_dwell=spec.say_dwell,
        cinematic=spec.cinematic,
        scene_count=spec.scenes,  # report the EFFECTIVE count (length-derived unless overridden)
        scenes=spec.scenes,
        target_seconds=spec.target_seconds,
    )
    return d


# --------------------------------------------------------------------------- #
# Heuristic interpreter: natural-language cues + explicit controls -> spec.
# Deterministic and hermetic; explicit controls always win over inferred cues.
# --------------------------------------------------------------------------- #
def _heuristic(request: str, spec: DirectorSpec) -> DirectorSpec:
    r = f" {request.lower()} "
    ch: dict = {}

    def has(*ks: str) -> bool:
        return any(k in r for k in ks)

    if has("story", "tale", "narrative"):
        ch["mode"] = "story"
    if has("quick", "brief", "tl;dr", "30 second", "in short"):
        ch["depth"] = "brief"
    if has("deep", "detailed", "in depth", "thorough", "comprehensive"):
        ch["depth"] = "deep"
    if has("like i'm 5", "like im 5", "eli5", " kid", "child", "beginner", "simple"):
        ch.update(audience="child", tone="playful", energy="lively", style="cartoon")
    if has("expert", "phd", "advanced", "technical", "rigorous"):
        ch.update(audience="expert", tone="formal")
    if has("fun", "playful", "casual", "chill"):
        ch.update(tone="playful", energy="lively")
    if has("calm", "slow", "gentle"):
        ch["energy"] = "calm"
    if has("dense", "packed"):
        ch["density"] = "dense"
    if has("minimal", "sparse", " clean "):
        ch["density"] = "sparse"
    if has("cartoon", "animated", "colorful", "colourful", "for kids"):
        ch["style"] = "cartoon"
    if has("whiteboard", "sketch", "diagram", "mono"):
        ch["style"] = "whiteboard"
    # target duration cues (check longest first so "10 min" isn't caught by "1 min")
    if has("10 min", "10-min", "10min", "ten min", "ten-minute"):
        ch["length"] = "10min"
    elif has("5 min", "5-min", "5min", "five min"):
        ch["length"] = "5min"
    elif has("2 min", "2min", "two min"):
        ch["length"] = "2min"
    elif has("1 min", "1min", "one min", "a minute"):
        ch["length"] = "1min"
    return replace(spec, **ch) if ch else spec


def _audience_profile(aud: str | None) -> dict:
    # Choosing an audience implies a default tone/energy/style (overridable).
    # Kids get the cartoon look by default — that's the product (docs/CARTOON.md).
    if aud == "child":
        return {"audience": "child", "tone": "playful", "energy": "lively", "style": "cartoon"}
    if aud == "expert":
        return {"audience": "expert", "tone": "formal"}
    return {"audience": aud} if aud else {}


def direct(
    topic: str, mode: str | None = None, request: str | None = None, **overrides
) -> DirectorSpec:
    """Build a DirectorSpec. Precedence (low -> high): audience profile -> text
    cues in `request` -> explicit `mode` / field overrides."""
    spec = DirectorSpec(topic=topic)
    spec = replace(spec, **_audience_profile(overrides.get("audience")))
    if request:  # only scan an EXPLICIT request for cues — never the topic itself
        spec = _heuristic(request, spec)  # ('deep sea'/'simple machine' must not reclassify)
    if mode:
        spec = replace(spec, mode=mode)
    valid = {k: v for k, v in overrides.items() if v is not None and hasattr(spec, k)}
    if valid:
        spec = replace(spec, **valid)
    # Domain is a SEPARATE axis from mode — inferring it from the topic is safe and is
    # exactly what context-aware concept resolution needs (cloud-computing vs weather).
    if not spec.domain:
        from engine import semantics

        spec = replace(spec, domain=semantics.infer_domain(topic))
    return spec


def coerce(topic: str, spec) -> DirectorSpec:
    """Normalize a spec / mode-string / None into a DirectorSpec (back-compat)."""
    if isinstance(spec, DirectorSpec):
        return spec
    if isinstance(spec, str):
        return DirectorSpec(topic=topic, mode=spec)
    return DirectorSpec(topic=topic)
