"""Coverage — how well the asset corpus answers what lessons actually ask for.

This is the honesty layer: instead of trusting the catalog size, it RESOLVES a probe
set of concepts through the live drawing ladder (``generate=False``, so it's hermetic
and never calls a provider) and reports what each one actually became — a composed
cartoon, a line-icon, or the labeled-box backstop (an "unknown").

Outputs feed the Studio dashboard: source breakdown, fallback rate, the list of boxed
concepts, per-bundle coverage, and — from a request log — the most frequently asked
nouns we still can't draw. That last list is the work queue for new assets.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

from engine.contracts import Extent, Thing

# How each runtime `source` tag rolls up for the dashboard.
_COMPOSED = {"icon", "primitive", "character"}
_BUCKET = {
    "icon": "composed",
    "primitive": "composed",
    "character": "composed",
    "catalog": "catalog",
    "sketch": "sketch",
    "generated": "generated",
    "box": "box",
}

# A standing probe of common teaching nouns, so gaps surface before a lesson hits them.
PROBE = [
    "sun",
    "cloud",
    "rain",
    "tree",
    "leaf",
    "water",
    "river",
    "mountain",
    "fire",
    "cat",
    "dog",
    "bird",
    "fish",
    "lion",
    "elephant",
    "bee",
    "butterfly",
    "apple",
    "banana",
    "bread",
    "egg",
    "milk",
    "carrot",
    "car",
    "bus",
    "train",
    "rocket",
    "boat",
    "bicycle",
    "house",
    "school",
    "castle",
    "bridge",
    "tower",
    "atom",
    "molecule",
    "cell",
    "dna",
    "magnet",
    "battery",
    "planet",
    "moon",
    "star",
    "heart",
    "lung",
    "brain",
    "bone",
    "eye",
    "tooth",
    "book",
    "pencil",
    "clock",
    "globe",
    "flag",
    "key",
    "lamp",
    "crown",
    "volcano",
    "rainbow",
    "snow",
    "wind",
    "tornado",
    "lightning",
    "robot",
    "dragon",
    "ghost",
    "king",
    "queen",
    "wizard",
]


def _log_path() -> Path:
    return Path(os.environ.get("ASSET_REQUEST_LOG", "data/asset_requests.jsonl"))


def _resolve_source(concept: str, style: str = "cartoon") -> str:
    """What the drawing ladder turns a concept into — without calling any provider."""
    from engine.drawing import measure

    t = Thing(id=concept, concept=concept, extent=Extent(1.0, 1.0))
    return measure(t, generate=False, style=style).source


def _corpus_concepts() -> list[str]:
    try:
        from engine import corpus

        seen: list[str] = []
        for sc in corpus.scenes():
            for th in sc.things:
                if th.concept not in seen:
                    seen.append(th.concept)
        return seen
    except Exception:
        return []


def log_request(concept: str, source: str | None = None) -> dict:
    """Record one resolution so the dashboard can rank frequently-requested gaps."""
    concept = (concept or "").strip()
    if not concept:
        return {"ok": False}
    src = source or _resolve_source(concept)
    rec = {"ts": datetime.now(UTC).isoformat(), "concept": concept.lower(), "source": src}
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return {"ok": True, **rec}


def _logged_concepts() -> list[str]:
    path = _log_path()
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line)["concept"])
        except Exception:
            continue
    return out


def missing_nouns(top: int = 20) -> list[dict]:
    """The most frequently requested concepts that still resolve to the box backstop."""
    counts: dict[str, int] = {}
    for c in _logged_concepts():
        if _resolve_source(c) == "box":
            counts[c] = counts.get(c, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"concept": c, "requests": n} for c, n in ranked[:top]]


def analyze(concepts: list[str] | None = None, style: str = "cartoon") -> dict:
    """Resolve a probe set and report coverage. Defaults to the standing probe plus the
    positioning corpus plus anything seen in the request log."""
    if concepts is None:
        merged: list[str] = []
        for c in PROBE + _corpus_concepts() + _logged_concepts():
            cl = c.strip().lower()
            if cl and cl not in merged:
                merged.append(cl)
        concepts = merged

    buckets: dict[str, int] = {}
    sources: dict[str, int] = {}
    boxed: list[str] = []
    by_bundle: dict[str, dict[str, int]] = {}

    from engine import bundles

    for c in concepts:
        src = _resolve_source(c, style)
        bucket = _BUCKET.get(src, "other")
        buckets[bucket] = buckets.get(bucket, 0) + 1
        sources[src] = sources.get(src, 0) + 1
        bid = bundles.bundle_for_concept(c).id
        bb = by_bundle.setdefault(bid, {"total": 0, "composed": 0, "box": 0})
        bb["total"] += 1
        if src in _COMPOSED:
            bb["composed"] += 1
        if src == "box":
            bb["box"] += 1
            boxed.append(c)

    total = len(concepts)
    composed = buckets.get("composed", 0)
    box = buckets.get("box", 0)
    return {
        "total": total,
        "composed": composed,
        "composed_rate": round(composed / total, 3) if total else 0.0,
        "fallback_rate": round(box / total, 3) if total else 0.0,
        "buckets": buckets,
        "source_breakdown": sources,
        "boxed": sorted(boxed),
        "by_bundle": by_bundle,
        "missing_nouns": missing_nouns(),
        "probe_size": total,
    }
