"""Asset Studio service layer — the engine-side of the Asset Studio UI.

Thin, hermetic functions the FastAPI routes call: query the manifest, render an asset
preview to SVG, introspect a family's parameters, preview and publish a new family
VARIANT, and run the publishing gates. It owns no Manim and no network; previews go
through the same measure→paint→svg path the engine already uses.

Publishing is GATED (the user's rule): a Studio-authored variant must pass license,
style, bbox, complexity, contrast, and renderability checks AND carry an explicit human
approval before it's written into ``asset_overrides.json`` (where the engine will then
resolve it). External SVGs / AI drafts are candidates, handled separately — they are
references, never auto-trusted runtime assets.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

from engine import asset_registry, bundles, svg
from engine import geometry as g
from engine.contracts import DrawOp, Extent, Thing
from engine.scene import Rendered, Scene, render

_DIR = Path(__file__).parent
_OVERRIDES = _DIR / "asset_overrides.json"

# Gate thresholds.
MAX_PARTS = 18
MAX_POINTS = 2000
MAX_ASPECT = 6.0

# Param typing hints for the family-variant form.
_COLOR_NAMES = {"body", "line", "belly", "beak", "fill", "eye", "snout", "horn", "wing", "trim"}
_ENUM_HINTS = {
    "ear": ["round", "point", "long"],
    "tail": ["up", "down", "puff", "long"],
    "snout": ["short", "long", "none"],
}


# --------------------------------------------------------------------------- #
# Catalog query
# --------------------------------------------------------------------------- #
def catalog(
    *,
    q: str = "",
    bundle: str = "",
    kind: str = "",
    style: str = "",
    status: str = "",
    offset: int = 0,
    limit: int = 120,
) -> dict:
    """Filtered, paginated view of the asset manifest."""
    items = asset_registry.manifest()
    ql = q.strip().lower()

    def keep(e: asset_registry.AssetEntry) -> bool:
        if ql and ql not in e.concept and not any(ql in a for a in e.aliases):
            return False
        if bundle and e.bundle != bundle:
            return False
        if kind and e.kind != kind:
            return False
        if style and e.style != style:
            return False
        return not (status and e.status != status)

    filtered = [e for e in items if keep(e)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "offset": offset,
        "limit": limit,
        "items": [e.to_dict() for e in page],
    }


# --------------------------------------------------------------------------- #
# Preview rendering (measure -> paint -> svg, hermetic)
# --------------------------------------------------------------------------- #
def _strokes_svg(strokes, target: float = 4.2) -> str:
    """Center + scale a set of strokes and render them to a standalone preview SVG."""
    if not strokes:
        return svg.to_svg(Rendered(placements=[], drops=[], ops=[], drawables={}))
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    span = max(x1 - x0, y1 - y0, 1e-6)
    scale = target / span
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    centered = g.transform(strokes, -cx * scale, -cy * scale, scale)
    op = DrawOp(
        thing_id="preview",
        kind="draw",
        strokes=tuple(centered),
        length=0.0,
        color="#e6edf3",
        fill=True,
        source="icon",
        rung=1,
    )
    return svg.to_svg(Rendered(placements=[], drops=[], ops=[op], drawables={}))


def preview(concept: str, style: str = "cartoon") -> str:
    """Render a concept's preview. Imported candidates render from their stored normalized
    strokes; everything else goes through the live engine ladder."""
    from engine import candidates_store

    cand = candidates_store.svg_for(_clean_concept(concept))
    if cand is not None:
        return cand
    t = Thing(id=concept, concept=concept, extent=Extent(1.0, 1.0), geometry_attrs={"size": 4.2})
    r = render(Scene(name="preview", things=[t]), generate=False, style=style)
    return svg.to_svg(r)


def _clean_concept(concept: str) -> str:
    return concept.strip().lower()


def _variant_strokes(family: str, params: dict):
    from engine import families, icons

    fn = families.FAMILIES.get(family)
    if fn is None:
        raise ValueError(f"unknown family '{family}'")
    recipe = fn(**_clean_params(fn, params))
    return icons.render_recipe(recipe), recipe


def preview_variant(family: str, params: dict) -> str:
    strokes, _ = _variant_strokes(family, params)
    return _strokes_svg(strokes)


# --------------------------------------------------------------------------- #
# Family introspection
# --------------------------------------------------------------------------- #
def _param_type(name: str, default) -> str:
    if isinstance(default, bool):
        return "bool"
    if name in _ENUM_HINTS:
        return "enum"
    if name in _COLOR_NAMES or (isinstance(default, str) and default.startswith("#")):
        return "color"
    return "text"


def families_schema() -> list[dict]:
    """Each parametric family + its parameter signature, for the variant-creator form."""
    from engine import families

    out = []
    for name, fn in families.FAMILIES.items():
        sig = inspect.signature(fn)
        params = []
        for p in sig.parameters.values():
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            default = None if p.default is inspect.Parameter.empty else p.default
            required = p.default is inspect.Parameter.empty
            params.append(
                {
                    "name": p.name,
                    "required": required,
                    "default": default,
                    "type": _param_type(p.name, default),
                    "options": _ENUM_HINTS.get(p.name, []),
                }
            )
        # An exemplar from the concept table makes the form pre-fillable.
        example = next(
            (c for c, (fam, _) in families.CONCEPT_FAMILIES.items() if fam == name), None
        )
        out.append(
            {
                "family": name,
                "doc": (inspect.getdoc(fn) or "").split("\n")[0],
                "params": params,
                "example_concept": example,
                "example_params": (families.CONCEPT_FAMILIES[example][1] if example else {}),
            }
        )
    return out


def _clean_params(fn, params: dict) -> dict:
    """Drop unknown keys, coerce bool-ish strings (so a JSON form maps onto kwargs)."""
    sig = inspect.signature(fn)
    valid = {p.name for p in sig.parameters.values()}
    out = {}
    for k, v in (params or {}).items():
        if k not in valid:
            continue
        if isinstance(v, str) and v.lower() in ("true", "false"):
            v = v.lower() == "true"
        if v in ("", None):
            continue
        out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Publishing gates
# --------------------------------------------------------------------------- #
def _luma(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return 0.5
    r, gg, b = (int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * gg + 0.0722 * b


def gate_variant(family: str, params: dict, *, license: str = "studio") -> dict:
    """Run the publishing gates on a family variant. Returns a per-check report and an
    `approvable` flag (all automated checks pass). Human approval is still required to
    publish."""
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    # license
    check("license", license in ("studio", "MIT", "CC0", "builtin"), f"license={license}")

    # renderability
    strokes = ()
    try:
        strokes, _ = _variant_strokes(family, params)
        renderable = bool(strokes) and all(len(s.points) >= 2 for s in strokes)
    except Exception as e:  # noqa: BLE001 - report, don't crash the gate
        renderable = False
        check("renderability", False, f"render failed: {e}")
    if strokes or renderable:
        check("renderability", renderable, f"{len(strokes)} strokes")

    # complexity
    points = sum(len(s.points) for s in strokes)
    check(
        "complexity",
        len(strokes) <= MAX_PARTS and points <= MAX_POINTS,
        f"{len(strokes)} strokes / {points} points (max {MAX_PARTS}/{MAX_POINTS})",
    )

    # style — a foreground cartoon must be colored + filled, not a line drawing
    filled = [s for s in strokes if s.fill]
    check("style", bool(filled), f"{len(filled)} filled shapes (cartoon must be filled)")

    # bbox / aspect
    if strokes:
        x0, y0, x1, y1 = g.strokes_bbox(strokes)
        w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        aspect = max(w / h, h / w)
        check("bbox", aspect <= MAX_ASPECT, f"aspect {aspect:.1f} (max {MAX_ASPECT})")
    else:
        check("bbox", False, "no geometry")

    # contrast — fill must differ from its own outline (visible edge)
    low = [s for s in filled if s.color and abs(_luma(s.fill) - _luma(s.color)) < 0.05]
    check("contrast", not low, f"{len(low)} shapes with fill≈stroke")

    approvable = all(c["pass"] for c in checks)
    return {"approvable": approvable, "checks": checks, "strokes": len(strokes)}


def save_variant(
    concept: str,
    family: str,
    params: dict,
    *,
    bundle: str = "",
    approved: bool = False,
    license: str = "studio",
) -> dict:
    """Publish an APPROVED variant into asset_overrides.json (engine then resolves it).

    Refuses if the gates fail or human approval is missing — assets only become trusted
    runtime resources through the gate.
    """
    concept = (concept or "").strip().lower()
    if not concept:
        return {"ok": False, "error": "concept name required"}
    report = gate_variant(family, params, license=license)
    if not report["approvable"]:
        return {"ok": False, "error": "gates failed", "report": report}
    if not approved:
        return {"ok": False, "error": "human approval required", "report": report}

    from engine import families

    data = {}
    if _OVERRIDES.exists():
        try:
            data = json.loads(_OVERRIDES.read_text())
        except Exception:
            data = {}
    variants = data.setdefault("variants", {})
    variants[concept] = {
        "family": family,
        "params": _clean_params(families.FAMILIES[family], params),
        "bundle": bundle or bundles.bundle_for_concept(concept, family).id,
        "license": license,
        "complexity": report["strokes"],
    }
    _OVERRIDES.write_text(json.dumps(data, indent=2, sort_keys=True))
    asset_registry.refresh()
    return {"ok": True, "concept": concept, "report": report}
