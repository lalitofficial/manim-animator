"""Bundle registry — named, toggleable groups of assets.

A *bundle* is a first-class engine resource: a named group (core, animals, science,
weather, …) the runtime resolves in PRIORITY order. Membership is declared by FAMILY
(a whole parametric family) and/or explicit CONCEPTS in ``bundles.json``. A concept's
primary bundle is the highest-priority bundle that claims it; anything unclaimed falls
to ``core`` (always enabled), so adding bundles never strands a concept.

Enable/disable is the control surface: disabling a bundle removes its concepts from
runtime resolution (they fall to the labeled-box backstop). The catalog of bundles +
their default ``enabled`` flag lives in ``bundles.json`` (committed); the live
enabled-state is overlaid from ``data/bundle_state.json`` (gitignored) so toggling in
the Studio persists without dirtying the committed registry.

Non-breaking by design: every bundle ships enabled, so ``any_disabled()`` is False and
the runtime is byte-identical until someone actually flips a bundle off.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

_DIR = Path(__file__).parent
_REGISTRY = _DIR / "bundles.json"


def _state_path() -> Path:
    return Path(os.environ.get("BUNDLE_STATE", "data/bundle_state.json"))


@dataclass
class Bundle:
    id: str
    name: str
    category: str
    priority: int
    enabled: bool
    description: str = ""
    locked: bool = False  # core can't be disabled
    families: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "priority": self.priority,
            "enabled": self.enabled,
            "locked": self.locked,
            "description": self.description,
            "families": list(self.families),
            "concepts": list(self.concepts),
        }


# Loaded once; enabled-state overlaid from the gitignored state file each load.
_BUNDLES: dict[str, Bundle] | None = None


def _norm(concept: str) -> str:
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def _load() -> dict[str, Bundle]:
    out: dict[str, Bundle] = {}
    try:
        raw = json.loads(_REGISTRY.read_text())
    except Exception:
        raw = {"bundles": []}
    for b in raw.get("bundles", []):
        out[b["id"]] = Bundle(
            id=b["id"],
            name=b.get("name", b["id"].title()),
            category=b.get("category", "misc"),
            priority=int(b.get("priority", 0)),
            enabled=bool(b.get("enabled", True)),
            description=b.get("description", ""),
            locked=bool(b.get("locked", False)),
            families=[str(f) for f in b.get("families", [])],
            concepts=[_norm(c) for c in b.get("concepts", [])],
        )
    # Overlay persisted enabled-state (Studio toggles).
    try:
        state = json.loads(_state_path().read_text())
        for bid, on in state.get("enabled", {}).items():
            if bid in out and not out[bid].locked:
                out[bid].enabled = bool(on)
    except Exception:
        pass
    return out


def _registry() -> dict[str, Bundle]:
    global _BUNDLES
    if _BUNDLES is None:
        _BUNDLES = _load()
    return _BUNDLES


def reload() -> None:
    """Drop the cached registry (after editing bundles.json or the state file)."""
    global _BUNDLES
    _BUNDLES = None


def all_bundles() -> list[Bundle]:
    """Every bundle, highest priority first."""
    return sorted(_registry().values(), key=lambda b: (-b.priority, b.id))


def get(bundle_id: str) -> Bundle | None:
    return _registry().get(bundle_id)


def enabled_bundles() -> list[Bundle]:
    return [b for b in all_bundles() if b.enabled]


def any_disabled() -> bool:
    """Fast gate: True iff at least one bundle is off. When False the runtime
    resolution is identical to having no bundle layer at all (the non-breaking path)."""
    return any(not b.enabled for b in _registry().values())


def _family_of(concept: str) -> str | None:
    """The parametric family a concept belongs to, if any (lazy import to avoid cycles)."""
    try:
        from engine import families

        entry = families.CONCEPT_FAMILIES.get(_norm(concept))
        return entry[0] if entry else None
    except Exception:
        return None


def claims(bundle: Bundle, concept: str, family: str | None) -> bool:
    c = _norm(concept)
    if c in bundle.concepts:
        return True
    return family is not None and family in bundle.families


def bundle_for_concept(concept: str, family: str | None = None) -> Bundle:
    """The primary bundle that owns a concept: highest-priority claimant, else core.

    `family` may be passed when the caller already knows it (avoids a re-lookup);
    otherwise it's resolved from the concept tables.
    """
    fam = family if family is not None else _family_of(concept)
    for b in all_bundles():
        if b.id == "core":
            continue
        if claims(b, concept, fam):
            return b
    return _registry().get("core") or Bundle("core", "Core", "core", 100, True, locked=True)


def concept_enabled(concept: str, family: str | None = None) -> bool:
    """Is the concept's owning bundle enabled? Core/unclaimed concepts are always on."""
    return bundle_for_concept(concept, family).enabled


def set_enabled(bundle_id: str, enabled: bool) -> dict:
    """Toggle a bundle and persist to the gitignored state file. Core is locked."""
    reg = _registry()
    b = reg.get(bundle_id)
    if b is None:
        return {"ok": False, "error": f"unknown bundle '{bundle_id}'"}
    if b.locked:
        return {"ok": False, "error": f"'{bundle_id}' is locked and cannot be disabled"}
    b.enabled = bool(enabled)
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {"enabled": {bid: bn.enabled for bid, bn in reg.items() if not bn.locked}}
    path.write_text(json.dumps(state, indent=2))
    return {"ok": True, "id": bundle_id, "enabled": b.enabled}


def resolve_order() -> list[str]:
    """Enabled bundle ids in the order the runtime would consult them."""
    return [b.id for b in enabled_bundles()]
