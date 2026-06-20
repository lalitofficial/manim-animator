"""The model-config surface (engine.models): local-first resolution, never a silent
paid default. The autouse `hermetic` fixture forces template/fixture + a dead Ollama
probe, so each test re-sets exactly the env + probe it wants."""

from __future__ import annotations

from engine import models


def _ollama(monkeypatch, installed):
    monkeypatch.setattr(models, "ollama_tags", lambda *a, **k: installed)


# --- pick_model preference -------------------------------------------------- #
def test_pick_model_prefers_qwen_then_falls_back():
    assert models.pick_model(["gemma3:latest", "qwen2.5:7b"]) == "qwen2.5:7b"
    assert models.pick_model(["qwen2.5:7b", "qwen3:8b"]) == "qwen3:8b"  # qwen3 leads
    assert models.pick_model(["mistral:latest"]) == "mistral:latest"  # only option
    assert models.pick_model(["foo:1b"]) == "foo:1b"  # unknown -> first installed
    assert models.pick_model([]) is None
    assert models.pick_model(["qwen2.5:7b"], override="llama3.1:8b") == "llama3.1:8b"  # exact wins


# --- story resolution ------------------------------------------------------- #
def test_story_auto_uses_local_ollama_when_running(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "auto")
    _ollama(monkeypatch, ["gemma3:latest", "qwen2.5:7b"])
    r = models.resolve_story()
    assert r.provider == "ollama" and r.model == "qwen2.5:7b" and r.reachable


def test_story_auto_falls_back_to_template_when_ollama_down(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "auto")
    _ollama(monkeypatch, None)  # not running
    r = models.resolve_story()
    assert r.provider == "template" and r.model is None
    assert r.warning is None  # auto down is expected, not a misconfig warning


def test_story_explicit_ollama_down_warns(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "ollama")
    _ollama(monkeypatch, None)
    r = models.resolve_story()
    assert r.provider == "template" and r.warning  # asked for ollama, didn't get it -> warn


def test_story_template_is_offline(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "template")
    r = models.resolve_story()
    assert r.provider == "template"


def test_story_gemini_needs_key(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert models.resolve_story().provider == "template"  # no key -> no paid call
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    g = models.resolve_story()
    assert g.provider == "gemini" and g.model == "gemini-2.5-flash"


def test_story_vertex_needs_project(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "vertex")
    monkeypatch.delenv("VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GCLOUD_PROJECT", raising=False)
    assert models.resolve_story().provider == "template"
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    v = models.resolve_story()
    assert v.provider == "vertex" and v.model == "gemini-2.5-flash"
    assert "demo-project" in v.note and "us-central1" in v.note


def test_never_defaults_to_paid(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")  # key present but NOT selected
    monkeypatch.setenv("STORY_PROVIDER", "auto")
    _ollama(monkeypatch, None)
    assert models.resolve_story().provider == "template"  # auto never reaches for cloud


# --- svg resolution --------------------------------------------------------- #
def test_svg_off_by_default(monkeypatch):
    monkeypatch.delenv("ENGINE_SVG_PROVIDER", raising=False)
    assert models.resolve_svg().provider == "off"


def test_svg_opt_in_ollama(monkeypatch):
    monkeypatch.setenv("ENGINE_SVG_PROVIDER", "ollama")
    _ollama(monkeypatch, ["qwen2.5:7b"])
    assert models.resolve_svg().provider == "ollama"
    _ollama(monkeypatch, None)
    assert models.resolve_svg().provider == "off"  # down -> off (not a crash)


def test_svg_opt_in_vertex(monkeypatch):
    monkeypatch.setenv("ENGINE_SVG_PROVIDER", "vertex")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    assert models.resolve_svg().provider == "vertex"


# --- describe (status surface) ---------------------------------------------- #
def test_describe_reports_both_jobs_and_warns_on_template(monkeypatch):
    monkeypatch.setenv("STORY_PROVIDER", "template")
    d = models.describe()
    assert d["story"]["provider"] == "template" and d["svg"]["provider"] == "fixture"
    assert any("template" in w.lower() for w in d["warnings"])
    assert d["ollama_reachable"] is False  # probe neutralized by the hermetic fixture


# --- voice resolution (Phase 5) --------------------------------------------- #
def test_voice_defaults_to_webspeech(monkeypatch):
    monkeypatch.delenv("VOICE_PROVIDER", raising=False)
    r = models.resolve_voice()
    assert r.provider == "webspeech" and r.warning is None  # free, zero-install default


def test_voice_local_is_free_optin(monkeypatch):
    monkeypatch.setenv("VOICE_PROVIDER", "kokoro")
    r = models.resolve_voice()
    assert r.provider == "kokoro" and r.warning is None  # local free, no key needed


def test_voice_paid_needs_key(monkeypatch):
    monkeypatch.setenv("VOICE_PROVIDER", "elevenlabs")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    r = models.resolve_voice()
    assert r.provider == "webspeech" and r.warning  # no key -> no paid call, and SAYS so
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    assert models.resolve_voice().provider == "elevenlabs"


def test_describe_includes_voice(monkeypatch):
    monkeypatch.delenv("VOICE_PROVIDER", raising=False)
    assert models.describe()["voice"]["provider"] == "webspeech"
