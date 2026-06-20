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

A paid CLOUD provider (`gemini` = AI Studio API key, `vertex` = Google Cloud Vertex AI
credits/ADC) runs ONLY when explicitly named AND configured — never a silent default.
If it's named but unconfigured/unreachable we fall back and SAY so (no silent paid calls,
no crash). `describe()` is the one place the product reads to show exactly which
provider + model is resolved per job.

Brain-model preference (best-first): Qwen leads because the brain emits schema-
constrained JSON and Qwen is the most reliable at structured output for its size; the
moment a better local model is installed it's auto-picked, no config change.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional in minimal envs
    load_dotenv = None

if load_dotenv is not None:
    # Load repo-local .env for normal dev runs, but never override explicit shell env.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)

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
        return Resolved(
            job,
            requested,
            "gemini",
            model,
            False,
            f"AI Studio Gemini · {model} (API-key opt-in)",
        )
    fallback = "template" if job == "story" else "off"
    return Resolved(
        job, requested, fallback, None, False, "gemini selected but GEMINI_API_KEY is not set"
    )


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


def _resolve_vertex(job: str, requested: str) -> Resolved:
    project = _vertex_project()
    fallback = "template" if job == "story" else "off"
    if not project:
        return Resolved(
            job,
            requested,
            fallback,
            None,
            False,
            "vertex selected but VERTEX_PROJECT/GOOGLE_CLOUD_PROJECT is not set",
        )
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    location = _vertex_location()
    return Resolved(
        job,
        requested,
        "vertex",
        model,
        False,
        f"Vertex AI Gemini · {model} in {project}/{location} (Google Cloud credits)",
    )


def resolve_story() -> Resolved:
    requested = os.environ.get("STORY_PROVIDER", "auto").strip().lower()
    if requested == "template":
        return Resolved(
            "story", requested, "template", None, False, "deterministic offline template (no model)"
        )
    if requested == "gemini":
        return _resolve_gemini("story", requested)
    if requested == "vertex":
        return _resolve_vertex("story", requested)
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
    if requested == "vertex":
        return _resolve_vertex("svg", requested)
    return _resolve_ollama("svg", requested, "OLLAMA_SVG_MODEL", auto=False)


# Voice provider for narration + lip-sync (docs/ROADMAP-story-voice.md §5). Default is the FREE,
# zero-install browser path; local-gen (kokoro/headtts) and paid cloud are opt-in only — never a
# silent default, exactly like the story/svg providers (NOTEBOOK O2).
VOICE_LOCAL = ("kokoro", "headtts", "piper")  # free, local, precise word/viseme timing
VOICE_CLOUD_KEYS = {  # paid, opt-in, key-gated
    "elevenlabs": "ELEVENLABS_API_KEY",
    "azure": "AZURE_SPEECH_KEY",
    "openai": "OPENAI_API_KEY",
}


def resolve_voice() -> Resolved:
    """Which voice drives narration + lip-sync. Default `webspeech` (free, in-browser, coarse
    text-estimated visemes — the Phase-4b bootstrap). `kokoro`/`headtts`/`piper` are free LOCAL
    opt-ins with precise word/viseme timing (Phase 5). Cloud (elevenlabs/azure/openai) is paid and
    runs ONLY when named AND keyed; otherwise it falls back to webspeech and SAYS so."""
    requested = os.environ.get("VOICE_PROVIDER", "webspeech").strip().lower()
    if requested in ("", "auto", "webspeech", "browser"):
        return Resolved(
            "voice",
            requested or "webspeech",
            "webspeech",
            None,
            False,
            "browser Web Speech — free, zero-install; coarse (text-estimated) lip-sync",
        )
    if requested in ("say", "system"):  # macOS native — zero-install server-side TTS
        return Resolved(
            "voice",
            requested,
            "say",
            None,
            False,
            "macOS `say` — free, zero-install server-side TTS (real audio track for exports)",
        )
    if requested in VOICE_LOCAL:
        return Resolved(
            "voice",
            requested,
            requested,
            None,
            False,
            f"local {requested} — free, precise word/viseme timing (opt-in)",
        )
    if requested in VOICE_CLOUD_KEYS:
        key = VOICE_CLOUD_KEYS[requested]
        if os.environ.get(key):
            return Resolved("voice", requested, requested, None, False, f"cloud {requested} (paid)")
        return Resolved(
            "voice",
            requested,
            "webspeech",
            None,
            False,
            f"{requested} selected but {key} is not set — using browser Web Speech",
        )
    return Resolved(
        "voice",
        requested,
        "webspeech",
        None,
        False,
        f"unknown VOICE_PROVIDER '{requested}' — using browser Web Speech",
    )


def describe() -> dict:
    """The whole model config, for /api/engine/status + the Studio. The single
    source of truth so the product can SHOW exactly what's running (no guessing)."""
    story, svg, voice = resolve_story(), resolve_svg(), resolve_voice()
    tags = ollama_tags()
    warnings = [r.warning for r in (story, svg, voice) if r.warning]
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
        "voice": {
            "provider": voice.provider,
            "model": voice.model,
            "requested": voice.requested,
            "note": voice.note,
        },
        "ollama_reachable": tags is not None,
        "ollama_models": tags or [],
        "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "vertex_project": _vertex_project(),
        "vertex_location": _vertex_location(),
        "warnings": warnings,
    }
