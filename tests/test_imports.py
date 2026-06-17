"""Smoke test: every backend module imports cleanly.

Catches syntax errors, broken imports, and circular-import regressions the
instant they happen — the cheapest possible signal for a coding agent.
"""

from __future__ import annotations

import importlib

import pytest

MODULES = [
    "ir",
    "modes",
    "assets",
    "actions",
    "sketches",
    "planner",
    "lesson",
    "renderer",  # pulls in manim — also verifies the heavy dep is installed
    "app",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    assert importlib.import_module(name) is not None
