"""Shared fixtures. Keep tests hermetic: no Ollama, no network."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def hermetic(monkeypatch, tmp_path):
    """Force the deterministic, OFFLINE providers for EVERY test. The product now
    defaults to local-first `auto` (probe Ollama, auto-pick a model) — without this
    the suite would hit the dev's running Ollama (network + non-deterministic). Tests
    that exercise resolution (test_models) re-set these via their own monkeypatch."""
    monkeypatch.setenv("STORY_PROVIDER", "template")
    monkeypatch.setenv("ENGINE_SVG_PROVIDER", "fixture")
    from engine import models

    monkeypatch.setattr(models, "ollama_tags", lambda *a, **k: None)  # the one probe point

    # Isolate the imported-candidate store so no test reads the real synced/published
    # icons on disk (drawing.measure consults it; keep that hermetic + empty).
    from engine import candidates_store

    monkeypatch.setattr(candidates_store, "_DIR", tmp_path / "candidates")
    candidates_store.refresh()


@pytest.fixture
def client(monkeypatch):
    """A FastAPI TestClient with startup side effects neutralized.

    The real startup warms the Ollama model and pre-fetches QuickDraw sketches
    over the network. Both are disabled here so the suite runs offline and fast.
    """
    import app as app_module
    import sketches

    monkeypatch.setattr(app_module, "ollama_available", lambda: False)
    monkeypatch.setattr(sketches, "warm", lambda *a, **k: None)

    from fastapi.testclient import TestClient

    with TestClient(app_module.app) as c:
        yield c
