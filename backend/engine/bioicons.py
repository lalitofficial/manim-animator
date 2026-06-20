"""Bioicons importer — open scientific SVG icons → board-unit COLORED candidate strokes.

Bioicons (github.com/duerrsimon/bioicons — ~2,800 SVG icons across ~37 scientific fields)
lays its icons out as ``static/icons/<license>/<category>/<name>.svg``. So LICENSE and
CATEGORY are authoritative from the path, and a sibling ``icons.json`` adds the per-icon
AUTHOR (attribution). Bioicons licensing is PER-ICON (CC0 / CC-BY / CC-BY-SA / MIT / BSD),
so each candidate carries its own ``license`` + ``author``.

We parse each SVG's COORDINATES *and per-shape color* into board-unit colored strokes — the
same color-preserving path as the Excalidraw importer. ``svgnorm`` is deliberately NOT used
here: it flattens to monochrome (color is paint-time for the generative rung), but a bio
icon's whole value is its color, which the candidate store preserves per stroke.

Like Excalidraw imports, these land as DISABLED candidates for Asset Studio review; a human
publishes them through the gates before the engine will draw them. The actual fetch (a git
checkout of the repo) is a dev-time sync (scripts/sync_bioicons.py); this module only parses
a LOCAL checkout, so it stays import-safe + hermetic (no network at import or in tests).
"""

from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from svgelements import SVG, Close, Line, Move, Shape
from svgelements import Path as SvgPath

from engine.contracts import Stroke

# license folder name -> the human label carried into each candidate's `license` field.
LICENSE_LABEL = {
    "cc-0": "CC0",
    "cc-by-3.0": "CC-BY-3.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-sa-3.0": "CC-BY-SA-3.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0",
    "mit": "MIT",
    "bsd": "BSD",
}

# Which of Bioicons' ~37 categories map to our subject domains. The rest (Lab_apparatus,
# Machine_Learning, Computer_hardware, Scientific_graphs, Safety_symbols, …) are general/other
# and import fine — they're just not claimed by a subject domain.
DOMAIN_CATEGORIES = {
    "biology": (
        "Animals",
        "Blood_Immunology",
        "Cell_culture",
        "Cell_lines",
        "Cell_membrane",
        "Cell_types",
        "Epigenetics",
        "Extracellular_matrix",
        "Genetics",
        "Genomics",
        "Human_physiology",
        "Intracellular_components",
        "Microbiology",
        "Nucleic_acids",
        "Peptides",
        "Plants_Algae",
        "Receptors_channels",
        "Tissues",
        "Viruses",
    ),
    "chemistry": (
        "Amino-Acids",
        "Chemistry",
        "Chemo-_and_Bioinformatics",
        "Molecular_modelling",
        "Nanotechnology",
    ),
}

_CURVE_SAMPLES = 8
_MAX_POINTS = 6000
# Unlike svgnorm we ALLOW <style>/<use> (svgelements resolves CSS + internal <use> while
# parsing, and we never emit the source SVG — only extracted polylines). Still block the
# genuinely dangerous bits + raster we can't draw.
_DISALLOWED = {"script", "foreignobject", "image", "animate", "animatetransform", "set"}


def _slug(text: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in str(text).strip().lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "icon"


def _title(name: str) -> str:
    return str(name).replace("_", " ").replace("-", " ").strip()


def _security_check(svg_text: str) -> None:
    root = ET.fromstring(svg_text)  # raises on malformed XML -> rejected
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1].lower()
        if tag in _DISALLOWED:
            raise ValueError(f"disallowed <{tag}>")
        for k, v in el.attrib.items():
            key = k.rsplit("}", 1)[-1].lower()
            if key.startswith("on"):  # onload/onclick/…
                raise ValueError("event handler attribute")
            if key in ("href", "xlink:href") and "://" in str(v):
                raise ValueError("external reference")


def _hex(c) -> str | None:
    """A svgelements color -> '#rrggbb', or None for none/transparent/non-solid (gradient)."""
    if c is None:
        return None
    try:
        if getattr(c, "value", "solid") is None:  # Color('none') has value None
            return None
        alpha = getattr(c, "alpha", 255)
        if alpha is not None and int(alpha) == 0:  # fully transparent
            return None
        return f"#{int(c.red):02x}{int(c.green):02x}{int(c.blue):02x}"
    except Exception:
        return None


def _polylines(svg_text: str):
    """(points, closed, stroke_hex, fill_hex) per subpath, in SVG (y-down) coordinates.
    Fill is kept only for CLOSED subpaths (open polylines never carry a fill)."""
    svg = SVG.parse(io.StringIO(svg_text), reify=True)  # bake the transform stack
    out: list[tuple[list[tuple[float, float]], bool, str | None, str | None]] = []
    n_points = 0
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        try:
            path = SvgPath(el)
        except Exception:
            continue
        if len(path) == 0:
            continue
        stroke = _hex(getattr(el, "stroke", None))
        fill = _hex(getattr(el, "fill", None))
        cur: list[tuple[float, float]] = []
        for seg in path:
            if isinstance(seg, Move):
                if len(cur) >= 2:
                    out.append((cur, False, stroke, None))
                cur = [(float(seg.end.x), float(seg.end.y))]
            elif isinstance(seg, Close):
                if len(cur) >= 2:
                    out.append((cur, True, stroke, fill))
                cur = []
            elif isinstance(seg, Line):
                cur.append((float(seg.end.x), float(seg.end.y)))
            else:  # Cubic/Quadratic/Arc — sample along the curve
                for i in range(1, _CURVE_SAMPLES + 1):
                    p = seg.point(i / _CURVE_SAMPLES)
                    cur.append((float(p.x), float(p.y)))
            n_points += 1
            if n_points > _MAX_POINTS:
                raise ValueError("too many points")
        if len(cur) >= 2:
            out.append((cur, False, stroke, None))
    return out


def svg_to_strokes(svg_text: str, target: float = 2.4) -> list[Stroke]:
    """Parse an SVG into COLORED board-unit strokes (centered, scaled to `target`, Y flipped
    to board-up). Raises on a security rejection; returns [] on empty/degenerate geometry."""
    _security_check(svg_text)
    raw = _polylines(svg_text)
    allpts = [p for r in raw for p in r[0]]
    if len(allpts) < 4:
        return []
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    w0, h0 = maxx - minx, maxy - miny
    if w0 < 1e-6 and h0 < 1e-6:
        return []
    scale = target / max(w0, h0, 1e-6)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2

    def tf(p: tuple[float, float]) -> tuple[float, float]:
        return (round((p[0] - cx) * scale, 4), round(-(p[1] - cy) * scale, 4))  # flip Y -> up

    return [
        Stroke(tuple(tf(p) for p in pts), closed, color, fill) for pts, closed, color, fill in raw
    ]


def build_item(name: str, category: str, license_label: str, author: str, svg_text: str) -> dict:
    """One candidate item carrying its OWN license + author (Bioicons is per-icon licensed)."""
    from engine import candidates_store

    try:
        strokes = svg_to_strokes(svg_text)
    except Exception:  # noqa: BLE001 - a rejected/garbage icon is dropped, never patched
        strokes = []
    pts = sum(len(s.points) for s in strokes)
    renderable = bool(strokes) and pts <= _MAX_POINTS
    return {
        "concept": _slug(name),
        "title": _title(name),
        "renderable": renderable,
        "complexity": len(strokes),
        "strokes": candidates_store.serialize_strokes(strokes) if renderable else [],
        "license": license_label,
        "author": author,
        "category": category,
    }


def _authors(icons_dir: Path) -> dict[tuple[str, str, str], str]:
    """(license, category, name) -> author, from the icons.json manifest (best-effort)."""
    out: dict[tuple[str, str, str], str] = {}
    try:
        for ic in json.loads((icons_dir / "icons.json").read_text()):
            out[(ic.get("license"), ic.get("category"), ic.get("name"))] = str(
                ic.get("author") or ""
            )
    except Exception:
        pass
    return out


def import_tree(
    root, categories=None, limit_per_category: int | None = None, progress=None
) -> dict:
    """Walk a LOCAL Bioicons checkout (``<root>/static/icons/<license>/<category>/<author>/*.svg``)
    and save ONE candidate pack per category. `categories` (category folder names) restricts the
    import; None imports everything. Returns a summary dict."""
    from engine import candidates_store

    root = Path(root)
    icons_dir = root / "static" / "icons"
    if not icons_dir.exists():
        raise FileNotFoundError(f"no Bioicons icons dir at {icons_dir}")
    want = set(categories) if categories else None
    authors = _authors(icons_dir)
    packs: dict[str, list[dict]] = {}

    for lic_dir in sorted(p for p in icons_dir.iterdir() if p.is_dir() and p.name in LICENSE_LABEL):
        lic, label = lic_dir.name, LICENSE_LABEL[lic_dir.name]
        for cat_dir in sorted(p for p in lic_dir.iterdir() if p.is_dir()):
            cat = cat_dir.name
            if want is not None and cat not in want:
                continue
            files = sorted(cat_dir.rglob("*.svg"))  # icons nest under an AUTHOR folder
            if limit_per_category:
                files = files[:limit_per_category]
            for svg_file in files:
                try:
                    svg_text = svg_file.read_text()
                except Exception:  # noqa: BLE001 - one unreadable file never sinks the pack
                    continue
                # the icon's folder IS its author (…/<category>/<author>/<name>.svg); fall back to
                # the manifest when a file sits directly in the category (flat layouts / tests).
                if svg_file.parent != cat_dir:
                    author = svg_file.parent.name.replace("-", " ")
                else:
                    author = authors.get((lic, cat, svg_file.stem), "")
                packs.setdefault(cat, []).append(
                    build_item(svg_file.stem, cat, label, author, svg_text)
                )

    items = renderable = 0
    cats = sorted(packs)
    for i, cat in enumerate(cats, 1):
        records = packs[cat]
        key = f"bioicons-{_slug(cat)}"
        candidates_store.save_pack(
            key,
            {
                "library": key,
                "set_name": f"Bioicons · {_title(cat)}",
                "source": "bioicons",
                "license": "various (per-icon)",
                "items": records,
            },
        )
        items += len(records)
        renderable += sum(1 for r in records if r["renderable"])
        if progress:
            progress(i, len(cats), cat)
    return {"ok": True, "categories": len(cats), "items": items, "renderable": renderable}


def import_domain(root, domain: str, **kw) -> dict:
    """Import only the categories that belong to a subject domain (biology / chemistry)."""
    cats = DOMAIN_CATEGORIES.get(domain)
    if not cats:
        raise ValueError(f"no Bioicons category mapping for domain '{domain}'")
    return import_tree(root, categories=cats, **kw)
