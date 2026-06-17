"""Line-icon catalog — license-clean, stroke-only sets that match our aesthetic.

PRIMARY: Lucide (ISC, ~1800 icons) vendored offline as one Iconify JSON; concepts
resolve by NAME (+ article/plural/kebab normalization + a few teaching aliases), so
coverage is ~20x the old hand-vendored set with zero network. FALLBACK: the small
curated Tabler dir, kept for its tag-alias index (e.g. "idea" -> bulb). The raw SVG
is flattened to polylines by svgnorm, like any other drawing.

Refresh Lucide with `make vendor-icons`.
"""

from __future__ import annotations

import json
from pathlib import Path

_DIR = Path(__file__).parent / "assets"

# --- Lucide (Iconify JSON: {"icons":{name:{body}}, "aliases":{name:{parent}}}) --- #
_LUCIDE: dict[str, str] = {}
_LW = _LH = 24
_lf = _DIR / "iconify" / "lucide.json"
if _lf.exists():
    try:
        _d = json.loads(_lf.read_text())
        _LW, _LH = _d.get("width", 24), _d.get("height", 24)
        _LUCIDE = {n: ic["body"] for n, ic in _d.get("icons", {}).items() if "body" in ic}
        for _a, _info in _d.get("aliases", {}).items():  # alias name -> parent body
            if (_p := _info.get("parent")) in _LUCIDE:
                _LUCIDE[_a] = _LUCIDE[_p]
    except Exception:
        _LUCIDE = {}

# --- Tabler dir (curated fallback, with the tag-alias index) --- #
_TDIR = _DIR / "tabler"
_TINDEX: dict[str, str] = {}
if (_ti := _TDIR / "index.json").exists():
    try:
        _TINDEX = json.loads(_ti.read_text())
    except Exception:
        _TINDEX = {}

# Teaching concepts Lucide names differently (concept -> lucide icon name).
_ALIASES = {
    "idea": "lightbulb",
    "bulb": "lightbulb",
    "person": "user",
    "people": "users",
    "human": "user",
    "plant": "sprout",
    "seedling": "sprout",
    "raindrop": "droplet",
    "water drop": "droplet",
    "car": "car-front",
    "money": "banknote",
    "cash": "banknote",
    "energy": "zap",
    "electricity": "zap",
    "lightning": "zap",
    "gear": "settings",
    "cog": "settings",
    "love": "heart",
    "time": "clock",
    "earth": "globe",
    "world": "globe",
    "rocket ship": "rocket",
    "test tube": "test-tube",
    "magnet": "magnet",
}


def _norm(concept: str) -> str:
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def _variants(concept: str) -> list[str]:
    """kebab-case lookup candidates: article-stripped + de-pluralized."""
    c = _norm(concept).replace(" ", "-")
    out = [c]
    for art in ("the-", "a-", "an-"):
        if c.startswith(art):
            out.append(c[len(art) :])
    base = out[-1]
    if base.endswith("ies") and len(base) > 4:
        out.append(base[:-3] + "y")
    if base.endswith("es") and len(base) > 4:
        out.append(base[:-2])
    if base.endswith("s") and len(base) > 3:
        out.append(base[:-1])
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _wrap(body: str) -> str:
    body = body.replace("currentColor", "#000")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_LW} {_LH}" '
        f'fill="none" stroke="#000" stroke-width="2">{body}</svg>'
    )


def lookup(concept: str) -> str | None:
    """Raw stroke-only SVG for a concept (Lucide by name, else the Tabler index)."""
    norm = _norm(concept)
    candidates = []
    if norm in _ALIASES:
        candidates.append(_ALIASES[norm])
    candidates += _variants(concept)
    for cand in candidates:
        if cand in _LUCIDE:
            return _wrap(_LUCIDE[cand])
    # Tabler dir fallback (curated tag-aliases, e.g. weather -> sun).
    name = _TINDEX.get(norm) or (_TINDEX.get(norm[:-1]) if norm.endswith("s") else None)
    if name and (f := _TDIR / f"{name}.svg").exists():
        return f.read_text()
    return None


def known() -> list[str]:
    return sorted(set(_LUCIDE) | set(_TINDEX.values()))
