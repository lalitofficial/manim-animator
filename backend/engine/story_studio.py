"""Text-only Story Studio.

This module is intentionally separate from engine.story/plan/stream: it experiments
with story-writing quality and feedback loops without changing the live cartoon
pipeline. The output is a directed text story package: outline, draft, critique,
and machine-checkable scores. Later we can promote the useful parts into Script V0.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine import models

ARCS = ("explainer", "folk_tale", "adventure", "mystery", "comedy")
TONES = ("warm", "playful", "dramatic", "formal")
AUDIENCES = ("child", "general", "expert")

EXAMPLES = [
    {
        "id": "water_cycle",
        "prompt": "the water cycle",
        "arc": "explainer",
        "audience": "child",
        "tone": "warm",
    },
    {
        "id": "photosynthesis",
        "prompt": "photosynthesis as a forest adventure",
        "arc": "explainer",
        "audience": "child",
        "tone": "warm",
    },
    {
        "id": "gravity",
        "prompt": "gravity for children",
        "arc": "explainer",
        "audience": "child",
        "tone": "playful",
    },
    {
        "id": "volcano",
        "prompt": "how a volcano erupts",
        "arc": "explainer",
        "audience": "general",
        "tone": "dramatic",
    },
    {
        "id": "heart",
        "prompt": "how the human heart pumps blood",
        "arc": "explainer",
        "audience": "general",
        "tone": "warm",
    },
    {
        "id": "brushing_teeth",
        "prompt": "why brushing teeth matters",
        "arc": "explainer",
        "audience": "child",
        "tone": "playful",
    },
    {
        "id": "moon_phases",
        "prompt": "moon phases as a night sky story",
        "arc": "explainer",
        "audience": "general",
        "tone": "warm",
    },
    {
        "id": "tenali",
        "prompt": "Tenali Rama solves a funny problem in the royal court",
        "arc": "folk_tale",
        "audience": "general",
        "tone": "playful",
    },
    {
        "id": "lighthouse",
        "prompt": "a young reporter and his dog solve a lighthouse mystery",
        "arc": "mystery",
        "audience": "general",
        "tone": "dramatic",
    },
    {
        "id": "lost_robot",
        "prompt": "a lost robot finds its way home",
        "arc": "adventure",
        "audience": "child",
        "tone": "warm",
    },
]


@dataclass(frozen=True)
class StoryStudioRequest:
    prompt: str
    arc: str = "explainer"
    audience: str = "general"
    tone: str = "warm"
    length: str = "short"
    provider: str = "auto"  # auto | template | ollama | vertex


@dataclass(frozen=True)
class StoryScene:
    title: str
    purpose: str
    emotion: str
    focus: str
    beat: str
    direction: str = ""
    goal: str = ""
    conflict: str = ""
    turn: str = ""
    reaction: str = ""
    decision: str = ""


@dataclass(frozen=True)
class CharacterArc:
    protagonist: str
    want: str
    need: str
    obstacle: str
    stakes: str
    revelation: str


@dataclass(frozen=True)
class StoryPackage:
    title: str
    logline: str
    characters: list[str]
    promise: str
    character_arc: CharacterArc
    scenes: list[StoryScene]
    story: str
    critique: list[str]
    scores: dict[str, int]
    provider: dict
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["character_arc"] = asdict(self.character_arc)
        d["scenes"] = [asdict(s) for s in self.scenes]
        return d


def examples() -> list[dict]:
    """The first no-cost benchmark corpus for the story loop."""
    return list(EXAMPLES)


def save_feedback(package: dict[str, Any], rating: int | None = None, note: str = "") -> dict:
    """Append one human/model feedback record to a JSONL file.

    This is the cheap dataset-building loop: prompt + generated package + critique +
    human rating/notes. It deliberately stores JSONL so later DPO/fine-tune/eval scripts
    can consume it without needing a database.
    """
    path = Path(os.environ.get("STORY_STUDIO_LOG", "data/story_studio_feedback.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "rating": max(1, min(5, int(rating))) if rating is not None else None,
        "note": (note or "").strip(),
        "package": package,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"saved": True, "path": str(path), "rating": record["rating"]}


def generate(req: StoryStudioRequest) -> StoryPackage:
    """Generate a text story package. Template is the hermetic fallback; Ollama is opt-in
    or auto when available. Failures return the template with provenance instead of
    touching the cartoon pipeline."""
    clean = _normalize_request(req)
    resolved = _resolve_provider(clean.provider)
    start = time.time()
    if resolved["provider"] in ("ollama", "vertex"):
        try:
            pkg = (
                _ollama_story(clean, resolved["model"])
                if resolved["provider"] == "ollama"
                else _vertex_story(clean, resolved["model"])
            )
            return _with_feedback(pkg, {**resolved, "elapsed_s": round(time.time() - start, 2)})
        except Exception as e:  # noqa: BLE001 - Studio should show the downgrade, not crash
            resolved = {
                **resolved,
                "provider": "template",
                "fallback": True,
                "reason": f"{resolved['requested']} error: {e}",
            }
    pkg = _template_story(clean)
    return _with_feedback(pkg, {**resolved, "elapsed_s": round(time.time() - start, 2)})


def _normalize_request(req: StoryStudioRequest) -> StoryStudioRequest:
    return StoryStudioRequest(
        prompt=(req.prompt or "a curious child learns why rain falls").strip(),
        arc=req.arc if req.arc in ARCS else "explainer",
        audience=req.audience if req.audience in AUDIENCES else "general",
        tone=req.tone if req.tone in TONES else "warm",
        length=req.length if req.length in ("short", "medium", "long") else "short",
        provider=(req.provider or "auto").strip().lower(),
    )


def _resolve_provider(provider: str) -> dict:
    if provider == "template":
        return {
            "requested": provider,
            "provider": "template",
            "model": None,
            "fallback": False,
            "reason": "deterministic text-story template",
        }
    if provider in ("auto", "ollama", "vertex"):
        r = models.resolve_story()
        if r.provider in ("ollama", "vertex") and (provider == "auto" or provider == r.provider):
            return {
                "requested": provider,
                "provider": r.provider,
                "model": r.model,
                "fallback": False,
                "reason": r.note,
            }
        return {
            "requested": provider,
            "provider": "template",
            "model": None,
            "fallback": provider in ("ollama", "vertex"),
            "reason": r.note,
        }
    return {
        "requested": provider,
        "provider": "template",
        "model": None,
        "fallback": True,
        "reason": f"unknown provider '{provider}'",
    }


def _template_story(req: StoryStudioRequest) -> StoryPackage:
    if "tenali" in req.prompt.lower():
        return _tenali_template(req)
    subject = _subject(req.prompt)
    hero, guide = _cast(req.prompt, req.audience, req.arc)
    scenes = _template_scenes(req, subject, hero, guide)
    title = _title(req.prompt)
    story = _template_prose(req, subject, hero, guide)
    return StoryPackage(
        title=title,
        logline=f"A short {req.tone} {req.arc} about {subject}, written for a {req.audience} audience.",
        characters=[hero, guide],
        promise=_promise(hero, subject, scenes),
        character_arc=_character_arc(hero, subject, req.arc, scenes),
        scenes=scenes,
        story=story,
        critique=[],
        scores={},
        provider={},
    )


def _template_scenes(
    req: StoryStudioRequest, subject: str, hero: str, guide: str
) -> list[StoryScene]:
    low = req.prompt.lower()
    if "water cycle" in low:
        return [
            _scene(
                "The Vanishing Puddle",
                "introduce the question",
                "curious",
                "puddle",
                "Mira sees a puddle shrink under the sun.",
                "Start close on the puddle, then tilt up to the sun.",
            ),
            _scene(
                "Clouds Gather",
                "build the process",
                "wonder",
                "rising vapor",
                "Vapor rises and gathers into clouds in the cooler sky.",
                "Follow the invisible rise with small dots becoming a cloud.",
            ),
            _scene(
                "Rain Returns",
                "resolve the cycle",
                "joyful",
                "falling rain",
                "Rain falls, runs into streams, and begins the cycle again.",
                "Let rain fall into a stream, then pull back to the whole loop.",
            ),
        ]
    if "photosynthesis" in low:
        return [
            _scene(
                "A Busy Leaf",
                "introduce the hidden work",
                "curious",
                "leaf",
                "Mira realizes a quiet leaf is working in the sunlight.",
                "Frame the leaf large, with sunlight entering from one side.",
            ),
            _scene(
                "Ingredients Meet",
                "build the transformation",
                "wonder",
                "leaf ingredients",
                "Sunlight, water, and air meet inside the green leaf.",
                "Show three inputs arriving at the leaf one at a time.",
            ),
            _scene(
                "Sugar From Light",
                "resolve the idea",
                "joyful",
                "tree",
                "The plant makes sugar and releases oxygen into the forest.",
                "Pull back from the leaf to the whole living tree.",
            ),
        ]
    if "gravity" in low:
        return [
            _scene(
                "The Falling Ball",
                "introduce the question",
                "curious",
                "ball",
                "Mira drops a ball and asks why it always comes back.",
                "Hold on the ball leaving her hand, then landing by her shoe.",
            ),
            _scene(
                "The Quiet Pull",
                "make the invisible force visible",
                "wonder",
                "downward pull",
                "Ari shows that gravity is an invisible pull toward Earth.",
                "Use soft downward arrows, but keep Mira and the ball as the focus.",
            ),
            _scene(
                "Back To The Ground",
                "resolve with a felt example",
                "joyful",
                "Mira",
                "Mira jumps and lands safely, understanding the pull.",
                "Show one jump arc, then a satisfying landing.",
            ),
        ]
    if "reporter" in low or "lighthouse" in low:
        return [
            _scene(
                "The Silent Lighthouse",
                "introduce the mystery",
                "curious",
                "lighthouse",
                "Nico and Pip arrive when the foghorn has gone quiet.",
                "Wide foggy lighthouse shot, with Pip sniffing the steps.",
            ),
            _scene(
                "Clues In The Lantern Room",
                "build suspicion",
                "tense",
                "map",
                "Nico finds a torn map, missing oil, and tiny pawprints.",
                "Cut between each clue, ending on Nico's worried face.",
            ),
            _scene(
                "The Lamp Relit",
                "resolve with compassion",
                "joyful",
                "lamp",
                "They find why the lamp went dark and relight it before ships arrive.",
                "Let the lamp glow through fog, then reveal safer ships offshore.",
            ),
        ]
    return [
        _scene(
            "Setup",
            "introduce the world and question",
            "curious",
            hero,
            f"{hero} notices something puzzling about {subject}.",
            f"Open on {hero} facing the ordinary world before the odd detail appears.",
        ),
        _scene(
            "Build",
            "make the problem visible",
            "tense" if req.arc in ("mystery", "adventure") else "wonder",
            subject,
            f"{guide} helps test one idea, but {subject} behaves in a surprising way.",
            f"Keep the focus on one visible change in {subject}, not a pile of facts.",
        ),
        _scene(
            "Payoff",
            "resolve the question with a satisfying turn",
            "joyful",
            subject,
            f"The pattern becomes clear, and {hero} can explain {subject} in simple words.",
            f"End with {hero} pointing to the clue that made the answer feel earned.",
        ),
    ]


def _scene(
    title: str,
    purpose: str,
    emotion: str,
    focus: str,
    beat: str,
    direction: str,
    goal: str | None = None,
    conflict: str | None = None,
    turn: str | None = None,
    reaction: str | None = None,
    decision: str | None = None,
) -> StoryScene:
    """A scene card with Swain/McKee-style craft fields.

    The fields are deliberately semantic, not renderer instructions: they tell the
    later director what should turn emotionally and visually, while geometry stays
    with the engines.
    """
    clean_beat = _clean_clause(beat)
    return StoryScene(
        title,
        purpose,
        emotion,
        focus,
        beat,
        direction,
        goal or _default_goal(purpose, focus),
        conflict or _default_conflict(purpose, focus),
        turn or f"The scene turns when {_lower_first(clean_beat or focus)}.",
        reaction or _default_reaction(purpose, focus),
        decision or _default_decision(purpose),
    )


def _promise(hero: str, subject: str, scenes: list[StoryScene]) -> str:
    obstacle = (
        _lower_first(_clean_clause(scenes[1].conflict))
        if len(scenes) > 1
        else f"{subject} refuses to explain itself"
    )
    story_kind = f"{subject} {hero}".lower()
    action = (
        "solve" if any(w in story_kind for w in ("puzzle", "mystery", "case")) else "understand"
    )
    method = (
        "by finding proof the audience can see"
        if action == "solve"
        else "by making the hidden pattern visible"
    )
    return f"{hero} wants to {action} {subject} {method}; the pressure is that {obstacle}."


def _character_arc(hero: str, subject: str, arc: str, scenes: list[StoryScene]) -> CharacterArc:
    obstacle = (
        _clean_clause(scenes[1].conflict) if len(scenes) > 1 else f"{subject} hides its pattern"
    )
    revelation = _clean_clause(scenes[-1].turn) if scenes else f"{subject} has a pattern"
    want = (
        f"to solve {subject}"
        if arc in ("mystery", "folk_tale", "adventure")
        else f"to make {subject} feel visible and simple"
    )
    stakes = (
        "the truth stays hidden"
        if arc in ("mystery", "folk_tale", "adventure")
        else "the idea stays confusing"
    )
    return CharacterArc(
        protagonist=hero,
        want=want,
        need="to look for the small visible clue instead of accepting the first answer",
        obstacle=obstacle,
        stakes=stakes,
        revelation=revelation,
    )


def _clean_clause(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    return cleaned.rstrip(" .!?;:")


def _lower_first(text: str) -> str:
    cleaned = _clean_clause(text)
    return cleaned[:1].lower() + cleaned[1:] if cleaned else ""


def _default_goal(purpose: str, focus: str) -> str:
    p = purpose.lower()
    if "resolve" in p or "payoff" in p:
        return f"Prove the answer through {focus}."
    if "build" in p or "test" in p or "transform" in p or "trick" in p:
        return f"Test what changes when {focus} is watched closely."
    if "mystery" in p or "challenge" in p:
        return f"Find the contradiction hiding around {focus}."
    return f"Find the question hiding in {focus}."


def _default_conflict(purpose: str, focus: str) -> str:
    p = purpose.lower()
    if "resolve" in p or "payoff" in p:
        return "The ending has to prove the answer through action, not explanation."
    if "build" in p or "test" in p or "trick" in p or "suspicion" in p:
        return f"The obvious explanation fails once {focus} is tested."
    if "mystery" in p or "challenge" in p:
        return "The truth is present, but nobody has read the clue correctly."
    return "The ordinary explanation does not fit what the audience can see."


def _default_reaction(purpose: str, focus: str) -> str:
    p = purpose.lower()
    if "resolve" in p or "payoff" in p:
        return "Everyone reacts to the proof instead of another speech."
    if "build" in p or "trick" in p or "suspicion" in p:
        return f"The protagonist notices that {focus} is carrying the real clue."
    return "The protagonist becomes curious enough to follow the clue."


def _default_decision(purpose: str) -> str:
    p = purpose.lower()
    if "resolve" in p or "payoff" in p:
        return "Name the pattern and close the story."
    if "build" in p or "test" in p or "trick" in p:
        return "Run the next test instead of adding more facts."
    return "Follow the clue into the next scene."


def _tenali_template(req: StoryStudioRequest) -> StoryPackage:
    scenes = [
        _scene(
            "The Impossible Pot",
            "introduce the challenge",
            "curious",
            "the brass pot",
            "The king asks the court to prove who owns a mysterious cooking pot.",
            "Wide court shot: king centered, two merchants on opposite sides, pot between them.",
            goal="Make the ownership problem visible without trusting either speech.",
            conflict="Both merchants tell the same story, so words cannot solve the case.",
            turn="The court needs proof from the pot itself.",
            reaction="Tenali stops listening for louder claims and starts watching the object.",
            decision="Inspect the pot for a clue everyone else missed.",
        ),
        _scene(
            "Tenali Watches",
            "build the comic trick",
            "playful",
            "soot on the handle",
            "Tenali notices soot on one handle and a nervous merchant hiding his hands.",
            "Medium on Tenali's face, then close on the soot and the merchant's hidden palm.",
            goal="Find a visible clue that separates habit from performance.",
            conflict="The liar can copy a story, but cannot copy daily use.",
            turn="The soot and hidden palm reveal which handle someone knows too well.",
            reaction="Tenali smiles because the solution can be acted out in public.",
            decision="Turn the clue into a test the whole court can see.",
        ),
        _scene(
            "The Clever Test",
            "resolve with a reveal",
            "joyful",
            "the hot handles",
            "Tenali asks both claimants to lift the hot pot, revealing who used it every day.",
            "Reveal through action: both lift the pot, one yelps, the court reacts.",
            goal="Prove the owner through behavior, not argument.",
            conflict="The false owner must perform knowledge he does not have.",
            turn="One merchant yelps while the real owner instinctively chooses the cooler grip.",
            reaction="The court laughs because the proof is obvious the moment it happens.",
            decision="Name the rightful owner and reward careful observation.",
        ),
    ]
    story = "\n\n".join(
        [
            (
                "In the royal court, two merchants argued over the same brass cooking pot. "
                "The king listened patiently, but both men told the same polished story, "
                "and the courtiers began to whisper that no one could solve it."
            ),
            (
                "Tenali did not interrupt. He smiled, walked around the pot, and noticed a "
                "dark patch of soot near one handle. Then he saw one merchant rubbing his palm "
                "as if he already knew where the metal grew hottest."
            ),
            (
                "So Tenali asked both men to lift the pot by its handles. The liar grabbed it "
                "carelessly and yelped; the true owner lifted it from the cooler side without "
                "thinking. The court burst into laughter, and the king nodded. Tenali had not "
                "guessed the answer. He had watched the story the object was already telling."
            ),
        ]
    )
    return StoryPackage(
        title="Tenali And The Impossible Pot",
        logline=f"A {req.tone} folk tale where Tenali solves a court puzzle by watching one tiny clue.",
        characters=["Tenali", "the king", "two merchants"],
        promise=_promise("Tenali", "the court puzzle", scenes),
        character_arc=_character_arc("Tenali", "the court puzzle", req.arc, scenes),
        scenes=scenes,
        story=story,
        critique=[],
        scores={},
        provider={},
    )


def _ollama_story(req: StoryStudioRequest, model: str | None) -> StoryPackage:
    if not model:
        raise RuntimeError("no Ollama story model resolved")
    prompt = _prompt(req)
    body = json.dumps(
        {
            "model": model,
            "stream": False,
            "format": _schema(),
            "messages": [{"role": "user", "content": prompt}],
            "options": {
                "temperature": 0.85,
                "top_p": 0.9,
                "num_predict": 900,
            },
        }
    ).encode()
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    timeout = float(os.environ.get("STORY_STUDIO_TIMEOUT", "28"))
    call = urllib.request.Request(
        f"{host}/api/chat", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(call, timeout=timeout) as resp:
        raw = json.loads(resp.read())["message"]["content"]
    data = json.loads(_strip_json(raw))
    return _parse_package(data)


def _vertex_story(req: StoryStudioRequest, model: str | None) -> StoryPackage:
    if not model:
        raise RuntimeError("no Vertex story model resolved")
    from engine.story import _google_access_token, _vertex_generate_url

    project = (
        os.environ.get("VERTEX_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
        or ""
    ).strip()
    location = (
        os.environ.get("VERTEX_LOCATION")
        or os.environ.get("GOOGLE_CLOUD_LOCATION")
        or "us-central1"
    ).strip()
    if not project:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT/VERTEX_PROJECT is not set")
    body = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": _prompt(req)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _schema(),  # force the exact shape (title/story/scenes/…)
            },
        }
    ).encode()
    call = urllib.request.Request(
        _vertex_generate_url(project, location, model),
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {_google_access_token()}",
        },
    )
    timeout = float(os.environ.get("STORY_STUDIO_TIMEOUT", "28"))
    with urllib.request.urlopen(call, timeout=timeout) as resp:
        data = json.loads(resp.read())
    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    return _parse_package(json.loads(_strip_json(raw)))


def _prompt(req: StoryStudioRequest) -> str:
    return (
        "Write a TEXT-ONLY directed story package. This is not for rendering yet; it is for testing "
        "story quality before animation.\n"
        f"Prompt: {req.prompt}\n"
        f"Arc: {req.arc}. Audience: {req.audience}. Tone: {req.tone}. Length: {req.length}.\n"
        "Output a single valid JSON OBJECT with EXACTLY these top-level keys: title, logline, "
        "characters, promise, character_arc, scenes, story. Do NOT invent other top-level keys "
        "(no setup/build/payoff keys — fold those into the `story` and `scenes`). Requirements:\n"
        "- `story`: 5-8 plain sentences with a real beginning, middle, and end (not a teaser).\n"
        "- `scenes`: 3-5 scenes. Each scene needs purpose, emotion, focus, beat, direction, "
        "goal, conflict, turn, reaction, and decision.\n"
        "- For ANIMATION, make each scene's `focus` and `direction` name CONCRETE, drawable "
        "subjects that ACT (e.g. 'a cloud', 'rising vapor', 'lava bursting up'), not abstractions.\n"
        "- `character_arc` with protagonist, want, need, obstacle, stakes, revelation.\n"
        "- Avoid generic AI phrases like 'in a world where' and 'little did they know'.\n"
        "- Keep prose clear, concrete, and visual, but no coordinates or renderer instructions."
    )


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "logline": {"type": "string"},
            "characters": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "promise": {"type": "string"},
            "character_arc": {
                "type": "object",
                "properties": {
                    "protagonist": {"type": "string"},
                    "want": {"type": "string"},
                    "need": {"type": "string"},
                    "obstacle": {"type": "string"},
                    "stakes": {"type": "string"},
                    "revelation": {"type": "string"},
                },
                "required": ["protagonist", "want", "need", "obstacle", "stakes", "revelation"],
            },
            "scenes": {
                "type": "array",
                "minItems": 3,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "purpose": {"type": "string"},
                        "emotion": {"type": "string"},
                        "focus": {"type": "string"},
                        "beat": {"type": "string"},
                        "direction": {"type": "string"},
                        "goal": {"type": "string"},
                        "conflict": {"type": "string"},
                        "turn": {"type": "string"},
                        "reaction": {"type": "string"},
                        "decision": {"type": "string"},
                    },
                    "required": [
                        "title",
                        "purpose",
                        "emotion",
                        "focus",
                        "beat",
                        "direction",
                        "goal",
                        "conflict",
                        "turn",
                        "reaction",
                        "decision",
                    ],
                },
            },
            "story": {"type": "string"},
        },
        "required": [
            "title",
            "logline",
            "characters",
            "promise",
            "character_arc",
            "scenes",
            "story",
        ],
    }


def _parse_package(data: dict) -> StoryPackage:
    scenes = [
        StoryScene(
            title=str(s.get("title", "Scene")),
            purpose=str(s.get("purpose", "")),
            emotion=str(s.get("emotion", "")),
            focus=str(s.get("focus", "")),
            beat=str(s.get("beat", "")),
            direction=str(s.get("direction", "")),
            goal=str(s.get("goal", "")),
            conflict=str(s.get("conflict", "")),
            turn=str(s.get("turn", "")),
            reaction=str(s.get("reaction", "")),
            decision=str(s.get("decision", "")),
        )
        for s in data.get("scenes", [])
        if isinstance(s, dict)
    ][:5]
    if len(scenes) < 3:
        raise RuntimeError("model returned fewer than 3 scenes")
    story = str(data.get("story", "")).strip()
    if len(_sentences(story)) < 5:
        # The model gave rich SCENES but a thin/absent prose blob (e.g. it emitted setup/build/
        # payoff keys instead of `story`). The scenes ARE the narrative — synthesize the prose
        # from their beats rather than discard good content. Animation consumes scenes, not prose.
        beats = [s.beat.strip() for s in scenes if s.beat.strip()]
        synth = " ".join(b if b.endswith((".", "!", "?")) else b + "." for b in beats)
        story = f"{story} {synth}".strip() if story else synth
        if len(_sentences(story)) < 3:
            raise RuntimeError("model returned neither a story nor usable scene beats")
    characters = [str(c) for c in data.get("characters", []) if str(c).strip()]
    protagonist = characters[0] if characters else "the protagonist"
    arc = data.get("character_arc") if isinstance(data.get("character_arc"), dict) else {}
    return StoryPackage(
        title=str(data.get("title", "Untitled story")),
        logline=str(data.get("logline", "")),
        characters=characters,
        promise=str(data.get("promise") or _promise(protagonist, "the story problem", scenes)),
        character_arc=CharacterArc(
            protagonist=str(arc.get("protagonist") or protagonist),
            want=str(arc.get("want") or "to solve the story problem"),
            need=str(arc.get("need") or "to notice what changes"),
            obstacle=str(arc.get("obstacle") or (scenes[1].conflict if len(scenes) > 1 else "")),
            stakes=str(arc.get("stakes") or "the answer remains unclear"),
            revelation=str(arc.get("revelation") or (scenes[-1].turn if scenes else "")),
        ),
        scenes=scenes,
        story=story,
        critique=[],
        scores={},
        provider={},
    )


def _with_feedback(pkg: StoryPackage, provider: dict) -> StoryPackage:
    scores, critique = evaluate(pkg)
    warnings = []
    if provider.get("fallback"):
        warnings.append(str(provider.get("reason") or "fell back to template"))
    if any(v < 3 for v in scores.values()):
        warnings.append("Story needs revision before it becomes animation input")
    return StoryPackage(
        title=pkg.title,
        logline=pkg.logline,
        characters=pkg.characters,
        promise=pkg.promise,
        character_arc=pkg.character_arc,
        scenes=pkg.scenes,
        story=pkg.story,
        critique=critique,
        scores=scores,
        provider=provider,
        warnings=warnings,
    )


def evaluate(pkg: StoryPackage) -> tuple[dict[str, int], list[str]]:
    """Small deterministic feedback loop. It is not taste; it catches the failures we
    already see: too short, no arc, weak direction, vague prose."""
    story = pkg.story or ""
    sentences = _sentences(story)
    words = re.findall(r"[A-Za-z']+", story)
    scene_count = len(pkg.scenes)
    purposes = " ".join(s.purpose.lower() for s in pkg.scenes)
    emotions = {s.emotion.lower() for s in pkg.scenes if s.emotion}
    concrete = sum(1 for w in words if len(w) > 4)
    dialogue = '"' in story or "'" in story
    arc = pkg.character_arc
    scene_craft = all(
        s.goal and s.conflict and s.turn and s.reaction and s.decision for s in pkg.scenes
    )

    scores = {
        "completeness": _score(scene_count >= 3, len(sentences) >= 5, _has_payoff(pkg)),
        "promise": _score(bool(pkg.promise), bool(arc.want), bool(arc.obstacle), bool(arc.stakes)),
        "character_arc": _score(bool(arc.want), bool(arc.need), bool(arc.revelation)),
        "structure": _score(
            "introduce" in purposes or "setup" in purposes, _has_build(pkg), _has_payoff(pkg)
        ),
        "scene_turns": _score(scene_craft, all(s.turn for s in pkg.scenes), _has_build(pkg)),
        "direction": _score(
            all(s.focus for s in pkg.scenes),
            all(s.beat for s in pkg.scenes),
            all(s.direction for s in pkg.scenes),
            len(emotions) >= 2,
        ),
        "prose": _score(len(words) >= 120, concrete >= 45, not _has_cliche(story)),
        "performance": _score(dialogue, _has_reaction(story), _has_change(story)),
    }
    critique = []
    if scores["completeness"] < 3:
        critique.append("Make the story complete: setup, development, and a clear ending.")
    if scores["promise"] < 4:
        critique.append(
            "Clarify the story promise: protagonist wants X because stakes, but obstacle."
        )
    if scores["character_arc"] < 4:
        critique.append("Strengthen character arc: want, need, obstacle, and final revelation.")
    if scores["scene_turns"] < 4:
        critique.append(
            "Give each scene a real turn: goal, conflict, surprise, reaction, decision."
        )
    if scores["direction"] < 3:
        critique.append("Add stronger scene direction: focus, visible beat, and changing emotion.")
    if scores["performance"] < 3:
        critique.append(
            "Add character performance: reaction, choice, dialogue, or a turning gesture."
        )
    if scores["prose"] < 3:
        critique.append("Use more concrete, visual prose and avoid stock AI phrases.")
    if not critique:
        critique.append("Good V0 text story: complete enough to test visual direction next.")
    return scores, critique


def _score(*checks: bool) -> int:
    return min(5, max(1, 2 + sum(bool(c) for c in checks)))


def _has_payoff(pkg: StoryPackage) -> bool:
    blob = f"{pkg.scenes[-1].purpose} {pkg.scenes[-1].beat}".lower() if pkg.scenes else ""
    return any(w in blob for w in ("resolve", "payoff", "end", "answer", "clear", "together"))


def _has_build(pkg: StoryPackage) -> bool:
    blob = " ".join(f"{s.purpose} {s.title}" for s in pkg.scenes).lower()
    return any(w in blob for w in ("build", "change", "turn", "problem", "conflict", "tension"))


def _has_cliche(text: str) -> bool:
    t = text.lower()
    return any(c in t for c in ("in a world where", "little did they know", "embark on a journey"))


def _has_reaction(text: str) -> bool:
    t = text.lower()
    return any(
        w in t
        for w in (
            "smiled",
            "frowned",
            "noticed",
            "asked",
            "laughed",
            "paused",
            "wondered",
            "barked",
            "yelped",
            "chased",
            "sniffed",
            "found",
            "worried",
        )
    )


def _has_change(text: str) -> bool:
    t = text.lower()
    return any(
        w in t for w in ("changed", "turned", "finally", "then", "but", "until", "by the end")
    )


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"[.!?]+", text or "") if s.strip()]


def _subject(prompt: str) -> str:
    t = (prompt or "").strip()
    low = t.lower()
    if "tenali" in low:
        return "Tenali Rama's court puzzle"
    if "water cycle" in low:
        return "the water cycle"
    if "photosynthesis" in low:
        return "photosynthesis"
    if "gravity" in low:
        return "gravity"
    if "volcano" in low:
        return "a volcano"
    if "lighthouse" in low:
        return "the lighthouse mystery"
    words = [w.strip(".,!?;:'\"").lower() for w in prompt.split()]
    stop = {
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
        "solves",
        "solve",
        "funny",
        "problem",
        "learns",
        "learn",
        "explains",
        "explain",
    }
    words = [w for w in words if w and w not in stop]
    return " ".join(words[-3:]) if words else "the idea"


def _template_prose(req: StoryStudioRequest, subject: str, hero: str, guide: str) -> str:
    low = req.prompt.lower()
    if "water cycle" in low:
        return "\n\n".join(
            [
                (
                    "Mira found a puddle shining on the path after morning rain. By lunch, the "
                    'puddle had shrunk. "Did someone drink it?" she asked. Ari shook his head '
                    "and pointed up at the warm sun."
                ),
                (
                    "The sun had been lifting tiny bits of water into the air. The water was still "
                    "there, only changed into invisible vapor. Higher up, the air grew cooler, and "
                    "the vapor gathered into soft gray clouds."
                ),
                (
                    "By evening, those clouds became heavy and let the water fall as rain. It ran "
                    "into streams, slid toward rivers, and returned to the sea. Mira smiled at the "
                    "new puddles. They were not endings. They were the water cycle starting another lap."
                ),
            ]
        )
    if "photosynthesis" in low:
        return "\n\n".join(
            [
                (
                    "In a bright forest clearing, Mira watched a small leaf tremble in the sun. "
                    '"It just sits there," she said. Ari laughed softly. "It is busier than it looks."'
                ),
                (
                    "The leaf opened tiny gates and took in air. Sunlight struck the green cells, "
                    "while water climbed up from the roots. Inside the leaf, those simple ingredients "
                    "were turned into sugar the plant could use."
                ),
                (
                    "Mira touched the bark and looked up at the branches. The tree had been cooking "
                    "with light all day, feeding itself and sharing oxygen with the forest. Photosynthesis "
                    "was not a word on a page anymore. It was breakfast made from sunshine."
                ),
            ]
        )
    if "gravity" in low:
        return "\n\n".join(
            [
                (
                    "Mira dropped a ball, and it bounced back against her shoe. She dropped a leaf, "
                    'and it floated down more slowly. "Why does everything come back?" she asked.'
                ),
                (
                    "Ari held up a stone and a feather. Gravity pulled on both, but air pushed against "
                    "the feather more. The pull was quiet, invisible, and always there, tugging things "
                    "toward Earth."
                ),
                (
                    "Mira jumped as high as she could. For one bright second she felt free, and then "
                    "gravity brought her safely back. She laughed because the force was not only about "
                    "falling. It was also the reason her feet could find the ground again."
                ),
            ]
        )
    if "reporter" in low or "lighthouse" in low:
        return "\n\n".join(
            [
                (
                    "Nico, a young reporter, reached the old lighthouse just as the foghorn fell silent. "
                    "His dog Pip sniffed the wet steps and barked at a trail of black sand by the door."
                ),
                (
                    "Inside, the lantern room was cold. Nico found a torn map, a missing oil can, and "
                    "fresh pawprints that were much too small for Pip. The mystery was not a ghost. "
                    "Someone had been using the fog as cover."
                ),
                (
                    "Pip chased the pawprints to a shed where a frightened child had hidden the oil can "
                    "to stop ships from coming near the rocks. Nico relit the lamp and wrote the truth "
                    "carefully: the lighthouse had not failed. It had been asking for help."
                ),
            ]
        )
    return "\n\n".join(
        [
            (
                f"{hero} began with a small question: what is really happening with {subject}? "
                f"The answer did not arrive as a lecture. It arrived as a clue."
            ),
            (
                f"First, {hero} watched closely. Then {guide} pointed out the moment that mattered: "
                f"{subject} changes when one hidden condition changes. That tiny shift made the whole "
                "scene feel less like magic and more like a pattern."
            ),
            (
                f"By the end, {hero} could tell the story back clearly. {subject.capitalize()} was not "
                "a pile of facts anymore. It was a beginning, a change, and a reason that finally made sense. "
                "The best part was that the answer felt earned, because every clue had been seen before."
            ),
        ]
    )


def _cast(prompt: str, audience: str, arc: str) -> tuple[str, str]:
    low = (prompt or "").lower()
    if "tenali" in low:
        return "Tenali", "the king"
    if "reporter" in low or "lighthouse" in low:
        return "Nico", "Pip"
    if arc in ("folk_tale", "adventure", "mystery"):
        return ("Mira", "Ari") if audience != "expert" else ("the protagonist", "the witness")
    return ("Mira", "the guide") if audience != "expert" else ("the narrator", "the guide")


def _title(prompt: str) -> str:
    subject = _subject(prompt)
    return " ".join(w.capitalize() for w in subject.split()) or "Story Test"


def _strip_json(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        t = t[4:] if t.lstrip().lower().startswith("json") else t
    a, b = t.find("{"), t.rfind("}")
    return t[a : b + 1] if a != -1 and b > a else t
