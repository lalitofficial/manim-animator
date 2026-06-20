"""Candidate store — imported assets, normalized to board-unit strokes.

External art (Excalidraw libraries, AI drafts) is brought in as CANDIDATES: parsed
from the source COORDINATES into board-unit strokes (via svgnorm), stored on disk, and
surfaced in the Asset Studio for review. They are deliberately NOT trusted runtime
cartoon assets — they live in the disabled-by-default ``imported`` bundle until a human
publishes them through the gates.

Storage is ONE pack file per source library (``candidates/<key>.json``) holding all its
items' normalized strokes — far fewer files than one-per-icon across thousands of icons.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.contracts import Stroke

_DIR = Path(__file__).parent / "candidates"
IMPORTED_BUNDLE = "imported"


def _norm(concept: str) -> str:
    """Match asset_registry._norm so candidate keys line up with manifest concepts."""
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def dir_() -> Path:
    return _DIR


def serialize_strokes(strokes) -> list[dict]:
    return [
        {
            "points": [[round(x, 4), round(y, 4)] for x, y in s.points],
            "closed": bool(s.closed),
            "color": s.color,
            "fill": s.fill,
        }
        for s in strokes
    ]


def deserialize_strokes(data: list[dict]) -> tuple[Stroke, ...]:
    return tuple(
        Stroke(
            tuple((float(p[0]), float(p[1])) for p in s.get("points", [])),
            bool(s.get("closed")),
            s.get("color"),
            s.get("fill"),
        )
        for s in (data or [])
    )


_PX = 90.0  # px per board unit for the standalone preview


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def strokes_svg(stroke_dicts: list[dict]) -> str:
    """Render stored candidate strokes to a faithful preview SVG — preserving each
    stroke's own color + fill, on a TRANSPARENT background (imported icons keep their
    original look instead of being recolored to the cartoon board)."""
    strokes = [s for s in deserialize_strokes(stroke_dicts) if s.points]
    if not strokes:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
    xs = [p[0] for s in strokes for p in s.points]
    ys = [p[1] for s in strokes for p in s.points]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = 0.08 * max(maxx - minx, maxy - miny, 1.0)
    minx, maxx, miny, maxy = minx - pad, maxx + pad, miny - pad, maxy + pad
    w, h = (maxx - minx) * _PX, (maxy - miny) * _PX

    def pt(x: float, y: float) -> str:
        return f"{round((x - minx) * _PX, 1)},{round((maxy - y) * _PX, 1)}"  # board y-up -> svg

    # Dark backing matches the Excalidraw panel preview (where these icons "really look"
    # right) so white/light strokes stay visible — the original colors are otherwise kept.
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="0 0 {w:.0f} {h:.0f}">',
        f'<rect width="{w:.0f}" height="{h:.0f}" rx="6" fill="#0d1117"/>',
    ]
    for s in strokes:
        coords = " ".join(pt(x, y) for x, y in s.points)
        fill = s.fill or "none"
        stroke = s.color or "#888888"
        tag = "polygon" if (s.closed and s.fill) else "polyline"
        parts.append(
            f'<{tag} points="{_esc(coords)}" fill="{_esc(fill)}" stroke="{_esc(stroke)}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    parts.append("</svg>")
    return "".join(parts)


def pack_path(key: str) -> Path:
    return _DIR / f"{key}.json"


def save_pack(key: str, pack: dict) -> Path:
    _DIR.mkdir(parents=True, exist_ok=True)
    path = pack_path(key)
    path.write_text(json.dumps(pack, indent=2))
    refresh()
    return path


# ----- index (concept -> item) built from all packs, cached --------------- #
_INDEX: dict[str, dict] | None = None
_VERSION = 0  # bumped on any mutation so downstream caches (semantics) invalidate safely


def version() -> int:
    return _VERSION


def _build_index() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not _DIR.exists():
        return out
    for f in sorted(_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            pack = json.loads(f.read_text())
        except Exception:
            continue
        set_name = pack.get("set_name") or pack.get("library") or f.stem
        for it in pack.get("items", []):
            concept = it.get("concept")
            if not concept:
                continue
            key = _norm(concept)
            if not key or key in out:
                continue
            out[key] = {**it, "library": pack.get("library", f.stem), "set_name": set_name}
    return out


def index() -> dict[str, dict]:
    global _INDEX
    if _INDEX is None:
        _INDEX = _build_index()
    return _INDEX


def refresh() -> None:
    global _INDEX, _PUBLISHED, _VERSION
    _INDEX = None
    _PUBLISHED = None
    _VERSION += 1


# ----- publish state: which candidates are promoted to engine-drawable --------- #
_PUBLISHED_FILE = "_published.json"
_PUBLISHED: set[str] | None = None


def _published_path() -> Path:
    return _DIR / _PUBLISHED_FILE


def published_set() -> set[str]:
    global _PUBLISHED
    if _PUBLISHED is None:
        try:
            data = json.loads(_published_path().read_text())
            _PUBLISHED = {_norm(c) for c in data.get("published", [])}
        except Exception:
            _PUBLISHED = set()
    return _PUBLISHED


def is_published(concept: str) -> bool:
    return _norm(concept) in published_set()


def _write_published(keys: set[str]) -> None:
    global _PUBLISHED, _VERSION
    _DIR.mkdir(parents=True, exist_ok=True)
    _published_path().write_text(json.dumps({"published": sorted(keys)}, indent=2))
    _PUBLISHED = keys
    _VERSION += 1


def publish(concepts: list[str]) -> int:
    """Promote candidates to engine-drawable. Only renderable ones (with strokes) count."""
    keys = set(published_set())
    idx = index()
    added = 0
    for c in concepts:
        k = _norm(c)
        if k in idx and idx[k].get("strokes") and k not in keys:
            keys.add(k)
            added += 1
    _write_published(keys)
    return added


def publish_all() -> int:
    """Publish every renderable candidate in the store."""
    renderable = [k for k, v in index().items() if v.get("strokes")]
    _write_published(set(renderable))
    return len(renderable)


def unpublish(concepts: list[str]) -> int:
    keys = set(published_set())
    removed = sum(1 for c in concepts if _norm(c) in keys)
    keys.difference_update(_norm(c) for c in concepts)
    _write_published(keys)
    return removed


def unpublish_all() -> None:
    _write_published(set())


def published_strokes(concept: str):
    """Deserialized strokes for a PUBLISHED candidate, else None (for drawing.measure)."""
    k = _norm(concept)
    if k not in published_set():
        return None
    it = index().get(k)
    if not it or not it.get("strokes"):
        return None
    return deserialize_strokes(it["strokes"])


def has(concept: str) -> bool:
    return _norm(concept) in index()


def get(concept: str) -> dict | None:
    return index().get(_norm(concept))


def svg_for(concept: str) -> str | None:
    it = index().get(_norm(concept))
    if it is None or not it.get("strokes"):
        return None
    return strokes_svg(it.get("strokes", []))


def entries() -> list[dict]:
    """Manifest rows for every imported candidate (one per item across all packs).
    `concept` is normalized so it lines up with the manifest's concept keys."""
    out = []
    for key, it in index().items():
        out.append(
            {
                "concept": key,
                "title": it.get("title", key),
                "library": it.get("library", ""),
                "set_name": it.get("set_name", ""),
                "license": it.get("license", "MIT"),
                "renderable": bool(it.get("renderable")),
                "complexity": int(it.get("complexity", 0)),
            }
        )
    return out


def stats() -> dict:
    idx = index()
    return {
        "count": len(idx),
        "renderable": sum(1 for v in idx.values() if v.get("renderable")),
        "published": len(published_set()),
        "packs": len([f for f in _DIR.glob("*.json") if not f.name.startswith("_")])
        if _DIR.exists()
        else 0,
    }
