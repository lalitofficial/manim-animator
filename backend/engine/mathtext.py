"""Deterministic math-equation rendering — a math-expression concept → board strokes.

A math topic names expressions ("E = mc^2", "a^2 + b^2 = c^2") that no recipe/family covers.
We render them with **matplotlib mathtext** (local, offline, reproducible — unlike LLM-SVG gen):
mathtext → SVG → board strokes. The SVG is parsed with the FILL-preserving svgelements path
(`bioicons.svg_to_strokes`, which resolves matplotlib's `<use>` glyph refs and keeps the glyph
fill → SOLID letters); `svgnorm` is deliberately not used here because it strips fill to hollow
outlines and rejects `<use>`. matplotlib is imported lazily so it never touches the common path.

docs/PLAN-director-domains-and-liveliness.md, P3.
"""

from __future__ import annotations

import io
import re

from engine.contracts import Stroke

# Treat a concept as an equation only if it carries genuine math tokens — so plain nouns
# (and snake_case ids) are never rendered as "text". An explicit $…$ always qualifies. NOTE:
# a bare `_`/`^` is intentionally NOT a trigger (it would catch snake_case); a superscript
# must sit against an alphanumeric (`\w^`), and a LaTeX command needs ≥2 letters (`\frac`).
_MATH_HINT = re.compile(r"=|\w\^|\\[A-Za-z]{2,}|\d\s*[+\-*/×·]\s*\d|[α-ωΑ-Ω∑∫√π±∞≈≤≥≠→]")
_INK = "#26354d"  # equation ink (mono); the board's palette may restyle at paint time


def as_expression(concept: str) -> str | None:
    """The mathtext source for a concept if it looks like an equation, else None."""
    c = (concept or "").strip()
    if len(c) < 2:
        return None
    if c.startswith("$") and c.endswith("$") and len(c) > 2:
        return c
    return f"${c}$" if _MATH_HINT.search(c) else None


def render(concept: str, target: float = 2.4) -> tuple[Stroke, ...]:
    """Filled glyph strokes for an equation concept, or () for a non-expression / failure."""
    expr = as_expression(concept)
    if not expr:
        return ()
    try:
        from engine.bioicons import svg_to_strokes

        return tuple(svg_to_strokes(_mathtext_svg(expr), target=target))
    except Exception:  # noqa: BLE001 - a bad expression is dropped, never patched
        return ()


def _mathtext_svg(expr: str) -> str:
    import matplotlib

    matplotlib.use("Agg")  # headless, no display
    import matplotlib.pyplot as plt

    plt.rcParams["svg.fonttype"] = "path"  # inline glyph geometry (not system-font <text>)
    fig = plt.figure(figsize=(4.0, 1.4))
    fig.text(0.5, 0.5, expr, fontsize=28, ha="center", va="center", color=_INK)
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", pad_inches=0.06, transparent=True)
    plt.close(fig)
    m = re.search(r"<svg\b.*?</svg>", buf.getvalue(), re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("matplotlib produced no <svg>")
    return m.group(0)
