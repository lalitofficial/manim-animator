"""Asset manifest — every drawable the engine knows, as first-class data.

Assets today live across several rungs (hand-built recipes, colored cartoon recipes,
parametric family variants, mono fallbacks, the vendored line-icon catalog) plus
Studio-authored overrides and un-trusted candidates. This module ENUMERATES all of
them into one deduped manifest of :class:`AssetEntry`, so the Studio, coverage
dashboard, and bundle layer can reason about assets uniformly instead of poking each
source module.

It only READS the existing sources (it never mutates the recipe corpus). The winner
for a concept follows the live ``icons.compose`` precedence — override > core >
cartoon > family > mono > catalog — and every entry records the bundle that owns it
and whether that bundle is currently enabled.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from engine import bundles

_DIR = Path(__file__).parent
_OVERRIDES = _DIR / "asset_overrides.json"
_CANDIDATES = _DIR / "candidates"

# Winner precedence (low number wins) — mirrors icons.compose + the override layer.
_RANK = {
    "override": 0,
    "core": 1,
    "cartoon": 2,
    "family": 3,
    "mono": 4,
    "catalog": 5,
    "candidate": 9,  # candidates never win runtime resolution
}

_STYLE = {
    "override": "colored",
    "core": "colored",
    "cartoon": "colored",
    "family": "colored",
    "mono": "mono",
    "catalog": "line",
    "candidate": "candidate",
}

_LICENSE = {
    "override": "studio",
    "core": "builtin",
    "cartoon": "builtin",
    "family": "builtin",
    "mono": "builtin",
    "catalog": "MIT (Tabler)",
    "candidate": "unverified",
}

_SOURCE = {  # the runtime `source` tag this rung paints with
    "override": "icon",
    "core": "icon",
    "cartoon": "icon",
    "family": "icon",
    "mono": "icon",
    "catalog": "catalog",
    "candidate": "candidate",
}


@dataclass
class AssetEntry:
    id: str
    concept: str
    kind: str  # override | core | cartoon | family | mono | catalog | candidate
    source: str  # runtime paint source tag
    style: str  # colored | mono | line | candidate
    bundle: str
    bundle_enabled: bool
    origin: str  # builtin | override | candidate
    license: str
    status: str  # active | shadowed | candidate
    complexity: int = 0
    title: str = ""  # human display name (candidates keep their original item name)
    family: str | None = None
    params: dict = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    also_in: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "concept": self.concept,
            "kind": self.kind,
            "source": self.source,
            "style": self.style,
            "bundle": self.bundle,
            "bundle_enabled": self.bundle_enabled,
            "origin": self.origin,
            "license": self.license,
            "status": self.status,
            "complexity": self.complexity,
            "title": self.title or self.concept,
            "family": self.family,
            "params": self.params,
            "aliases": self.aliases,
            "also_in": self.also_in,
        }


_MANIFEST: list[AssetEntry] | None = None


def _norm(concept: str) -> str:
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def _alias_index() -> dict[str, list[str]]:
    """canonical concept -> [aliases that point at it] (from icons.ALIASES)."""
    from engine import icons

    rev: dict[str, list[str]] = {}
    for alias, canon in icons.ALIASES.items():
        rev.setdefault(_norm(canon), []).append(alias)
    return rev


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _raw_sources() -> dict[str, list[dict]]:
    """concept -> list of per-rung records {kind, parts, family, params}."""
    from engine import families, icons

    cartoon_keys = {_norm(k) for k in _read_json(_DIR / "cartoon_recipes.json")}
    out: dict[str, list[dict]] = {}

    def add(concept: str, rec: dict) -> None:
        out.setdefault(_norm(concept), []).append(rec)

    # core (hand-built) vs cartoon (JSON-merged) — both live in ICON_RECIPES now.
    for concept, recipe in icons.ICON_RECIPES.items():
        nrec = _norm(concept)
        kind = "cartoon" if nrec in cartoon_keys else "core"
        add(concept, {"kind": kind, "parts": len(recipe.get("parts", []))})

    # parametric family variants (the scalable colored corpus).
    for concept, (fam, params) in families.CONCEPT_FAMILIES.items():
        parts = 0
        with contextlib.suppress(Exception):
            parts = len(families.compose_family(concept).get("parts", []))
        add(concept, {"kind": "family", "parts": parts, "family": fam, "params": dict(params)})

    # mono long-tail fallback.
    for concept, recipe in icons._MONO_RECIPES.items():  # noqa: SLF001 - intentional read
        add(concept, {"kind": "mono", "parts": len(recipe.get("parts", []))})

    # vendored line-icon catalog (Tabler) — the license-clean stroke-only stems.
    tdir = _DIR / "assets" / "tabler"
    if tdir.exists():
        for f in sorted(tdir.glob("*.svg")):
            add(f.stem, {"kind": "catalog", "parts": 0})

    # Studio-approved overrides (highest precedence).
    for concept, v in _read_json(_OVERRIDES).get("variants", {}).items():
        add(
            concept,
            {
                "kind": "override",
                "parts": int(v.get("complexity", 0)),
                "family": v.get("family"),
                "params": dict(v.get("params", {})),
            },
        )

    # un-trusted imported candidates (Excalidraw icons / AI drafts) — never win runtime.
    from engine import candidates_store

    published = candidates_store.published_set()
    for c in candidates_store.entries():
        add(
            c["concept"],
            {
                "kind": "candidate",
                "parts": int(c.get("complexity", 0)),
                "library": c.get("set_name") or c.get("library"),
                "title": c.get("title"),
                "license": c.get("license", "MIT"),
                "published": c["concept"] in published,
            },
        )

    return out


def build() -> list[AssetEntry]:
    """Enumerate all sources into one deduped, winner-resolved manifest."""
    from engine import candidates_store

    aliases = _alias_index()
    entries: list[AssetEntry] = []
    for concept, recs in _raw_sources().items():
        recs = sorted(recs, key=lambda r: _RANK.get(r["kind"], 99))
        win = recs[0]
        kind = win["kind"]
        owning_family = win.get("family")
        is_candidate = kind == "candidate"
        is_published = is_candidate and win.get("published")
        # imported candidates always live in the (disabled-by-default) `imported` bundle,
        # so thousands of technical icons never shadow or pollute the cartoon runtime.
        bundle = (
            bundles.get(candidates_store.IMPORTED_BUNDLE)
            if is_candidate
            else bundles.bundle_for_concept(concept, owning_family)
        ) or bundles.bundle_for_concept(concept, owning_family)
        entries.append(
            AssetEntry(
                id=concept,
                concept=concept,
                kind=kind,
                # a published candidate is engine-drawable now, so it reads as `published`
                source="published" if is_published else _SOURCE.get(kind, "icon"),
                style=_STYLE.get(kind, "colored"),
                bundle=bundle.id,
                bundle_enabled=True if is_published else bundle.enabled,
                origin=(
                    "override" if kind == "override" else "candidate" if is_candidate else "builtin"
                ),
                license=win.get("license") or _LICENSE.get(kind, "builtin"),
                status="published" if is_published else "candidate" if is_candidate else "active",
                complexity=int(win.get("parts", 0)),
                title=win.get("title") or concept,
                family=owning_family,
                params=win.get("params", {}),
                aliases=sorted(aliases.get(concept, [])),
                also_in=[r["kind"] for r in recs[1:]],
            )
        )
    entries.sort(key=lambda e: (e.bundle, e.concept))
    return entries


def manifest() -> list[AssetEntry]:
    global _MANIFEST
    if _MANIFEST is None:
        _MANIFEST = build()
    return _MANIFEST


def refresh() -> None:
    """Drop the cached manifest (after a Studio save / bundle reload / candidate sync)."""
    global _MANIFEST
    _MANIFEST = None
    bundles.reload()
    from engine import candidates_store

    candidates_store.refresh()


def stats() -> dict:
    """Headline counts for the Studio header."""
    m = manifest()
    by_kind: dict[str, int] = {}
    by_bundle: dict[str, int] = {}
    by_style: dict[str, int] = {}
    for e in m:
        by_kind[e.kind] = by_kind.get(e.kind, 0) + 1
        by_bundle[e.bundle] = by_bundle.get(e.bundle, 0) + 1
        by_style[e.style] = by_style.get(e.style, 0) + 1
    return {
        "total": len(m),
        "by_kind": by_kind,
        "by_bundle": by_bundle,
        "by_style": by_style,
        "candidates": sum(1 for e in m if e.status == "candidate"),
    }
