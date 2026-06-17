"""The single model-config surface — which provider + model does each job (§ models).

The engine uses a model for two jobs:
  - STORY: topic -> Beats (the brain). The important one.
  - SVG:   a rare drawing fallback (recipes + composition + Tabler catalog already
           cover ~98% of concepts, so this is OFF by default).

Defaults are LOCAL-FIRST and never paid:
  - STORY_PROVIDER       default `auto` -> local Ollama (best installed model) if it's
                         running, else the deterministic offline TEMPLATE.
  - ENGINE_SVG_PROVIDER  default `off`  -> unknown concepts resolve to an instant
                         labeled box (no slow/unreliable LLM-SVG). Opt-in only.

A paid CLOUD provider (gemini) runs ONLY when explicitly named AND its key is set —
never a silent default. If it's named but unkeyed/unreachable we fall back and SAY so
(no silent paid calls, no crash). `describe()` is the one place the product reads to
show exactly which provider + model is resolved per job.

Brain-model preference (best-first): Qwen leads because the brain emits schema-
constrained JSON and Qwen is the most reliable at structured output for its size; the
moment a better local model is installed it's auto-picked, no config change.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

# Best-first preference for the brain (structured Beat JSON). Matched by family
# (prefix before ':'), so `qwen3:4b`, `qwen3:8b`, … all count as `qwen3`.
STORY_PREFERRED = (
    "qwen3",
    "qwen2.5",
    "llama3.1",
    "llama3",
    "gemma3",
    "gemma2",
    "mistral",
    "qwen2",
    "phi4",
    "phi3",
)


def _host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def ollama_tags(host: str | None = None, timeout: float = 1.5) -> list[str] | None:
    """Installed Ollama model names, or None if Ollama is unreachable. This is the
    ONE probe point (tests monkeypatch it to stay hermetic)."""
    host = host or _host()
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as resp:
            return [m["name"] for m in json.loads(resp.read()).get("models", [])]
    except Exception:
        return None


def _family(name: str) -> str:
    return name.split(":")[0]


def pick_model(installed: list[str], preferred=STORY_PREFERRED, override: str | None = None):
    """Pick the best installed model: an exact `override` wins; else the first
    `preferred` family present; else the first installed model."""
    if override:
        return override
    if not installed:
        return None
    for p in preferred:
        for m in installed:
            if m == p or _family(m) == _family(p):
                return m
    return installed[0]


# --------------------------------------------------------------------------- #
# Resolution — env (+ live Ollama probe) -> a concrete plan, with a human note.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Resolved:
    job: str  # "story" | "svg"
    requested: str  # the env value (or default): auto/off/template/ollama/gemini/fixture
    provider: str  # what will actually run: template/ollama/gemini/off/fixture
    model: str | None
    reachable: bool  # Ollama reachable (when relevant)
    note: str  # one-line human explanation (incl. any warning)

    @property
    def warning(self) -> str | None:
        # A warning is a requested!=provider downgrade the user should see.
        return self.note if self.requested not in (self.provider, "auto", "off") else None


def _resolve_ollama(job: str, requested: str, model_env: str, auto: bool) -> Resolved:
    tags = ollama_tags()
    if tags is None:
        why = "not running" if auto else "unreachable"
        note = (
            f"Ollama {why} — using the offline template"
            if job == "story"
            else f"Ollama {why} — drawing falls back to a labeled box"
        )
        return Resolved(job, requested, "template" if job == "story" else "off", None, False, note)
    model = pick_model(tags, override=os.environ.get(model_env))
    if not model:
        return Resolved(
            job,
            requested,
            "template" if job == "story" else "off",
            None,
            True,
            "Ollama has no installed model",
        )
    return Resolved(job, requested, "ollama", model, True, f"local Ollama · {model}")


def _resolve_gemini(job: str, requested: str) -> Resolved:
    if os.environ.get("GEMINI_API_KEY"):
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        return Resolved(job, requested, "gemini", model, False, f"cloud Gemini · {model} (opt-in)")
    fallback = "template" if job == "story" else "off"
    return Resolved(
        job, requested, fallback, None, False, "gemini selected but GEMINI_API_KEY is not set"
    )


def resolve_story() -> Resolved:
    requested = os.environ.get("STORY_PROVIDER", "auto").strip().lower()
    if requested == "template":
        return Resolved(
            "story", requested, "template", None, False, "deterministic offline template (no model)"
        )
    if requested == "gemini":
        return _resolve_gemini("story", requested)
    # auto (default) or explicit ollama -> local first.
    return _resolve_ollama("story", requested, "OLLAMA_STORY_MODEL", auto=requested == "auto")


def resolve_svg() -> Resolved:
    requested = os.environ.get("ENGINE_SVG_PROVIDER", "off").strip().lower()
    if requested in ("off", "none"):
        return Resolved(
            "svg",
            requested,
            "off",
            None,
            False,
            "off — recipes/catalog cover ~98%; unknown -> labeled box",
        )
    if requested == "fixture":
        return Resolved(
            "svg", requested, "fixture", None, False, "deterministic fixtures (test/dev)"
        )
    if requested == "gemini":
        return _resolve_gemini("svg", requested)
    return _resolve_ollama("svg", requested, "OLLAMA_SVG_MODEL", auto=False)


def describe() -> dict:
    """The whole model config, for /api/engine/status + the Studio. The single
    source of truth so the product can SHOW exactly what's running (no guessing)."""
    story, svg = resolve_story(), resolve_svg()
    tags = ollama_tags()
    warnings = [r.warning for r in (story, svg) if r.warning]
    if story.provider == "template":
        warnings.append(
            "Story is the offline TEMPLATE (generic lessons). Start Ollama (local, free) "
            "for real per-topic lessons — it auto-uses your installed model."
        )
    return {
        "story": {
            "provider": story.provider,
            "model": story.model,
            "requested": story.requested,
            "note": story.note,
        },
        "svg": {
            "provider": svg.provider,
            "model": svg.model,
            "requested": svg.requested,
            "note": svg.note,
        },
        "ollama_reachable": tags is not None,
        "ollama_models": tags or [],
        "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "warnings": warnings,
    }
