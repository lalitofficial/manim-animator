"""SVG generators — the live long-tail rung (ARCHITECTURE §5.3 rung 3, §6.1).

A pluggable provider returns raw SVG for a concept; drawing.py sanitizes it
(svgnorm) before it ever touches the engine. The default is a deterministic
FIXTURE provider so the whole rung stays in the hermetic test suite; real
frontier/local providers sit behind ENGINE_SVG_PROVIDER and are never hit in tests.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Protocol

_FIXTURES = Path(__file__).parent / "fixtures" / "svg"

_PROMPT = (
    "Draw '{concept}' as a single, simple, recognizable black-and-white line drawing. "
    "Output ONLY one self-contained <svg> element, viewBox 0 0 100 100, using stroke-only "
    'paths (fill="none", stroke="#000"). No text, no comments, no markdown fences.'
)

_SVG_RE = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)


class SvgProvider(Protocol):
    def generate(self, concept: str, attrs: dict) -> str | None: ...


def _extract_svg(text: str) -> str | None:
    m = _SVG_RE.search(text or "")
    return m.group(0) if m else None


class FixtureProvider:
    """Serves recorded SVGs from fixtures/svg/<concept>.svg. Deterministic, offline."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _FIXTURES
        self.calls: dict[str, int] = {}

    def generate(self, concept: str, attrs: dict) -> str | None:
        c = concept.strip().lower()
        self.calls[c] = self.calls.get(c, 0) + 1
        f = self.root / f"{c}.svg"
        return f.read_text() if f.exists() else None


class OllamaProvider:
    """Free-local: ask a local Ollama model for stroke-only SVG."""

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self.model = model or os.environ.get("OLLAMA_SVG_MODEL", "qwen2.5:7b")
        self.host = host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")

    def generate(self, concept: str, attrs: dict) -> str | None:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "options": {"temperature": 0.2},
                "messages": [{"role": "user", "content": _PROMPT.format(concept=concept)}],
            }
        ).encode()
        try:
            req = urllib.request.Request(
                f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                content = json.loads(resp.read())["message"]["content"]
            return _extract_svg(content)
        except Exception:
            return None


class GeminiProvider:
    """Paid frontier tier (opt-in): Gemini via the Generative Language REST API."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.key = os.environ.get("GEMINI_API_KEY", "")

    def generate(self, concept: str, attrs: dict) -> str | None:
        if not self.key:
            return None
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.key}"
        )
        body = json.dumps(
            {"contents": [{"parts": [{"text": _PROMPT.format(concept=concept)}]}]}
        ).encode()
        try:
            req = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_svg(text)
        except Exception:
            return None


class VertexProvider:
    """Paid cloud tier through Google Cloud Vertex AI credits (opt-in)."""

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        self.project = _vertex_project()
        self.location = _vertex_location()

    def generate(self, concept: str, attrs: dict) -> str | None:
        if not self.project:
            return None
        body = json.dumps(
            {"contents": [{"role": "user", "parts": [{"text": _PROMPT.format(concept=concept)}]}]}
        ).encode()
        try:
            req = urllib.request.Request(
                _vertex_generate_url(self.project, self.location, self.model),
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_google_access_token()}",
                },
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return _extract_svg(text)
        except Exception:
            return None


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
    for cmd in (
        ["gcloud", "auth", "application-default", "print-access-token"],
        ["gcloud", "auth", "print-access-token"],
    ):
        with contextlib.suppress(Exception):
            out = subprocess.check_output(cmd, text=True, timeout=10).strip()
            if out:
                return out
    raise RuntimeError(
        "could not get Google Cloud access token; run `gcloud auth application-default login` "
        "or set GOOGLE_APPLICATION_CREDENTIALS/GOOGLE_OAUTH_ACCESS_TOKEN"
    )


class NullProvider:
    """No generation (the default). Unknown concepts fall straight to the labeled-box
    backstop — recipes + composition + the Tabler catalog already cover ~98%, and
    live LLM-SVG is slow + unreliable, so generation is opt-in only."""

    def generate(self, concept: str, attrs: dict) -> str | None:
        return None


def default_provider() -> SvgProvider:
    """Local-first via models.resolve_svg(): off by default (NullProvider), fixture
    for tests/dev, ollama/gemini only when explicitly opted in."""
    from engine import models

    r = models.resolve_svg()
    if r.provider == "ollama":
        return OllamaProvider(model=r.model)
    if r.provider == "gemini":
        return GeminiProvider()
    if r.provider == "vertex":
        return VertexProvider()
    if r.provider == "fixture":
        return FixtureProvider()
    return NullProvider()
