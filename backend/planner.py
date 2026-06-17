"""Planner — turns natural-language text into a Scene IR.

Two-stage, with a repair loop, on a local Ollama model (free, no API key):

  stage 1  text  -> outline {title, entities, beats}   (decide WHAT is in the scene)
  stage 2  outline -> full Scene IR                     (lay it out on a timeline)
  repair   validate; on Pydantic error, re-prompt with the error (<=2 retries)

Splitting "what" from "where" makes small local models far more reliable on
complex prompts. The asset catalog is injected into both prompts, so the model
selects real building blocks (man, road, car...) instead of faking them.

The model never writes Manim code — only IR (safe, no exec; reusable by a
future realtime renderer). If Ollama is unreachable or every repair fails, we
fall back to a deterministic mock so a job never hard-fails.

Config (env):
  OLLAMA_HOST   default http://localhost:11434
  OLLAMA_MODEL  override the auto-picked model
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from pydantic import ValidationError

from assets import catalog
from ir import Scene

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# Preference order when OLLAMA_MODEL isn't set; first one that's installed wins.
PREFERRED_MODELS = ["qwen2.5:7b", "qwen2.5", "llama3.1:8b", "llama3.1", "gemma3"]

IR_TYPES = {
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
    "asset",
    "group",
}


# --------------------------------------------------------------------------- #
# Prompts.  Built with .replace (not .format) because they contain literal {}.
# --------------------------------------------------------------------------- #
OUTLINE_SYSTEM = """You are an animation director. Given a topic, produce a SHORT
plan as a single JSON object (no markdown, no commentary):
{
  "title": "...",
  "entities": [{"id": "short_id", "kind": "asset-name-or-shape", "note": "what it is"}],
  "beats": ["ordered thing that happens", "..."]
}

"kind" rules:
- A real-world thing (person, vehicle, nature, building...) -> an ASSET name below.
  Never describe a person/car/tree as a circle — use the asset.
- A plain geometric shape (a circle, square, dot, line, arrow, "the board/screen")
  -> the PRIMITIVE word itself: "circle","square","rectangle","dot","line","arrow","text".
  Do NOT use an asset (e.g. dot_label/road) for plain shapes.

AVAILABLE ASSETS:
__CATALOG__

Keep it to 3-7 entities and 3-7 beats. Output JSON only."""

IR_SYSTEM = """You convert an outline into a Scene IR JSON for a Manim whiteboard
animation. Output ONLY one JSON object (no markdown):
{
  "title": str,
  "background": hex color str,
  "objects": [ {object} ],
  "steps":   [ {step} ]
}

OBJECT shapes — EVERY object MUST start with a unique "id" string:
- {"id":str,"type":"asset","asset":"<name>","params":{"color":hex},"position":[x,y],"scale":num}
    use ONLY for real-world things: people, vehicles, nature, buildings, etc.
- {"id":str,"type":"text","text":str,"font_size":num,"position":[x,y],"color":hex}
- {"id":str,"type":"circle","radius":num,...} / {"id":str,"type":"square","width":num,...}
- {"id":str,"type":"rectangle","width":num,"height":num,...}
- {"id":str,"type":"triangle"|"polygon","points":[[x,y],...]}   (>=3 vertices)
- {"id":str,"type":"line"|"arrow","start":[x,y],"end":[x,y]}
- {"id":str,"type":"dot"} / {"id":str,"type":"mathtex","tex":"..."}  (mathtex only if essential)
- {"id":str,"type":"group","members":["id1","id2"]}   bundle objects to animate together

AVAILABLE ASSET names (use these for real things; do NOT fake them with shapes):
__CATALOG__

STEP shapes (run in order on a timeline):
{"animation":"write|create|fadein|fadeout|move|scale|transform|wait",
 "target":"object id", "to":[x,y] (move), "into":"id" (transform),
 "factor":num (scale), "duration":seconds}

RULES:
- EVERY object needs a unique "id"; "steps" may only target ids you defined.
- Plain geometric shapes (a circle, square, dot, line, the "board") are
  PRIMITIVES, not assets. Use an asset ONLY for a real thing (man, car, tree...).
- Use a DARK "background" (e.g. "#0E1116"); text/assets are tuned for dark.
- Coordinates: origin is screen center, +y up. Keep within x:[-6.5,6.5], y:[-3.5,3.5].
- Put a road/ground asset near y:-2.5 when relevant; characters stand just above it
  (y ~ -1.4). "walking/driving" = a "move" step translating the asset across.
- Title text near y:3. Reference only ids you defined. 4-12 steps.
- color/scale optional; assets have good defaults (recolor via params.color).
Output JSON only."""


# --------------------------------------------------------------------------- #
# Ollama plumbing
# --------------------------------------------------------------------------- #
def _strip_to_json(s: str) -> str:
    s = s.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.DOTALL)
    if fence:
        return fence.group(1)
    brace = re.search(r"\{.*\}", s, re.DOTALL)
    return brace.group(0) if brace else s


def ollama_available() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def list_models() -> list[str]:
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=3) as resp:
            return [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except (urllib.error.URLError, OSError, KeyError):
        return []


def pick_model() -> str | None:
    """OLLAMA_MODEL override, else best installed from PREFERRED_MODELS, else any."""
    env = os.environ.get("OLLAMA_MODEL")
    if env:
        return env
    avail = list_models()
    if not avail:
        return None
    base = lambda n: n.split(":")[0]
    for p in PREFERRED_MODELS:
        for m in avail:
            if m == p or base(m) == base(p):
                return m
    return avail[0]


def _payload(
    model, messages, temperature, num_predict, keep_alive, fmt: str | None = "json"
) -> bytes:
    options = {"temperature": temperature}
    if num_predict:
        options["num_predict"] = num_predict  # hard cap on output tokens (latency)
    body = {
        "model": model,
        "options": options,
        "keep_alive": keep_alive,  # keep weights resident between calls
        "messages": messages,
    }
    if fmt:  # "json" forces ONE object — leave None for NDJSON action streams
        body["format"] = fmt
    return json.dumps(body).encode()


def _chat(
    model: str,
    messages: list[dict],
    temperature: float = 0.4,
    num_predict: int | None = None,
    keep_alive: str = "30m",
) -> str:
    body = json.loads(_payload(model, messages, temperature, num_predict, keep_alive))
    body["stream"] = False
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())["message"]["content"]


def chat_stream(
    model: str,
    messages: list[dict],
    temperature: float = 0.4,
    num_predict: int | None = None,
    keep_alive: str = "30m",
    fmt: str | None = "json",
):
    """Yield content chunks as the model generates — lets callers act on
    early fields (e.g. speak the narration) long before the JSON is done."""
    body = json.loads(_payload(model, messages, temperature, num_predict, keep_alive, fmt))
    body["stream"] = True
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        for line in resp:
            d = json.loads(line)
            chunk = d.get("message", {}).get("content", "")
            if chunk:
                yield chunk
            if d.get("done"):
                break


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #
def plan_outline(text: str, model: str) -> dict:
    system = OUTLINE_SYSTEM.replace("__CATALOG__", catalog())
    raw = _chat(
        model,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Topic: {text}"},
        ],
    )
    try:
        return json.loads(_strip_to_json(raw))
    except json.JSONDecodeError:
        return {"title": text[:40], "entities": [], "beats": [text]}


def _coerce(data: dict) -> dict:
    """Nudge near-miss model output toward the schema before validation.

    Most common slip: the model uses a semantic word as `type` (e.g. "figure",
    "person", "car"). Rewrite any unknown type to an asset reference so the
    library/fallback handles it instead of Pydantic rejecting it.
    """
    if not isinstance(data, dict):
        return data
    for o in data.get("objects", []) or []:
        if not isinstance(o, dict):
            continue
        t = o.get("type")
        if t not in IR_TYPES:
            o["asset"] = o.get("asset") or o.get("name") or t or "asset"
            o["type"] = "asset"
        if o.get("type") == "asset" and not o.get("asset"):
            o["asset"] = o.get("name") or "asset"
    return data


def build_ir(text: str, outline: dict, model: str, attempts: int = 4) -> Scene:
    """Stage 2 + repair loop: outline -> validated Scene, self-correcting."""
    system = IR_SYSTEM.replace("__CATALOG__", catalog())
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Topic: {text}\n\nOutline:\n{json.dumps(outline)}"},
    ]
    last_err: Exception | None = None
    for _ in range(attempts):
        raw = _chat(model, messages)
        try:
            data = _coerce(json.loads(_strip_to_json(raw)))
            return Scene.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": f"That JSON was invalid:\n{e}\n"
                    "Fix ALL of these errors and return the full corrected Scene IR JSON only.",
                }
            )
    raise last_err if last_err else RuntimeError("planner produced no output")


def plan_with_ollama(text: str, model: str) -> Scene:
    return build_ir(text, plan_outline(text, model), model)


def plan_mock(text: str) -> Scene:
    """Deterministic plan so the pipeline runs even with no model available."""
    title = (text.strip().split("\n")[0] or "Animation")[:40]
    return Scene.model_validate(
        {
            "title": title,
            "background": "#0E1116",
            "objects": [
                {
                    "id": "title",
                    "type": "text",
                    "text": title,
                    "font_size": 48,
                    "position": [0, 2.5, 0],
                    "color": "#58A6FF",
                },
                {
                    "id": "orb",
                    "type": "circle",
                    "radius": 1.0,
                    "position": [-3, -0.5, 0],
                    "color": "#3FB950",
                },
                {
                    "id": "caption",
                    "type": "text",
                    "text": "(mock planner — start Ollama for real plans)",
                    "font_size": 22,
                    "position": [0, -3, 0],
                    "color": "#8B949E",
                },
            ],
            "steps": [
                {"animation": "write", "target": "title", "duration": 1.2},
                {"animation": "create", "target": "orb", "duration": 1.0},
                {"animation": "move", "target": "orb", "to": [3, -0.5, 0], "duration": 1.5},
                {"animation": "scale", "target": "orb", "factor": 1.4, "duration": 0.8},
                {"animation": "fadein", "target": "caption", "duration": 0.8},
                {"animation": "wait", "duration": 0.5},
            ],
        }
    )


def plan(text: str) -> Scene:
    model = pick_model() if ollama_available() else None
    if not model:
        return plan_mock(text)
    try:
        return plan_with_ollama(text, model)
    except Exception:
        # Repair exhausted or the server errored — never fail the job.
        return plan_mock(text)


if __name__ == "__main__":
    import sys

    prompt = " ".join(sys.argv[1:]) or "a man walking on a road"
    print(f"# model: {pick_model()}\n")
    print(plan(prompt).model_dump_json(indent=2))
