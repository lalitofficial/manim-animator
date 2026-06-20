"""Excalidraw public-library importer.

The public repo is a useful *source* of hand-drawn assets, but not a trusted
foreground cartoon bundle. This module indexes and previews `.excalidrawlib`
packs as import candidates for the Asset Studio. Publishing into the runtime
asset ladder is intentionally a later, gated step.
"""

from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

REPO = "excalidraw/excalidraw-libraries"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}/contents"
RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
LICENSE = "MIT"


def _cache_dir() -> Path:
    return Path(os.environ.get("EXCALIDRAW_LIBRARY_CACHE", "data/excalidraw_libraries"))


def _request_json(url: str) -> Any:
    headers = {"User-Agent": "manim-animator-asset-studio"}
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _safe_repo_path(path: str) -> str:
    p = path.strip().strip("/")
    if not p.startswith("libraries/") or ".." in p.split("/"):
        raise ValueError("expected a path under libraries/")
    return p


def _raw_url(path: str) -> str:
    return f"{RAW}/{urllib.parse.quote(_safe_repo_path(path))}"


@dataclass(frozen=True)
class LibraryItem:
    id: str
    name: str
    status: str
    elements: int
    types: dict[str, int]
    bbox: tuple[float, float, float, float] | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "elements": self.elements,
            "types": self.types,
            "bbox": self.bbox,
        }


@dataclass(frozen=True)
class LibraryPack:
    path: str
    name: str
    source: str
    version: int | None
    items: list[LibraryItem] = field(default_factory=list)
    element_types: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "name": self.name,
            "source": self.source,
            "license": LICENSE,
            "version": self.version,
            "items": [i.to_dict() for i in self.items],
            "item_count": len(self.items),
            "element_types": self.element_types,
        }


def _slug(text: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in str(text).strip().lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "item"


def index(refresh: bool = False) -> dict:
    """The WHOLE catalog: every published library from the repo-root `libraries.json`,
    with preview image + item names — one request, cached. This is what powers the
    "browse all" grid (230+ sets: Azure, AWS, GCP, clouds, …) and the cross-set search.
    """
    cache = _cache_dir() / "index.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    raw = _request_json(f"{RAW}/libraries.json")
    libs = []
    for lib in raw if isinstance(raw, list) else []:
        source = str(lib.get("source") or "")
        if not source.endswith(".excalidrawlib"):
            continue
        preview = str(lib.get("preview") or "")
        item_names = [str(n) for n in (lib.get("itemNames") or [])]
        libs.append(
            {
                "id": str(lib.get("id") or source),
                "name": str(lib.get("name") or Path(source).stem),
                "description": str(lib.get("description") or ""),
                "authors": [str(a.get("name") or a) for a in lib.get("authors", [])],
                "path": f"libraries/{source}",  # the repo path load()/item() expect
                "preview": f"{RAW}/libraries/{urllib.parse.quote(preview)}" if preview else None,
                "item_names": item_names,
                "item_count": len(item_names),
                "updated": str(lib.get("updated") or ""),
                "license": LICENSE,
            }
        )
    out = {"source": "libraries.json", "count": len(libs), "libraries": libs}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, indent=2))
    return out


def _pack_key(path: str) -> str:
    """A stable per-library pack filename from a repo path (author__libname)."""
    rel = _safe_repo_path(path)[len("libraries/") :]
    return _slug(rel.replace(".excalidrawlib", "").replace("/", "__"))


def _normalize_item(elements: list[dict], name: str, index_: int, prefix: str = "") -> dict:
    """Parse one item's COORDINATES into a board-unit, normalized candidate record.

    elements -> approximate SVG -> svgnorm (flatten curves, normalize to a board box,
    quality-gate). Non-renderable items (too complex / rejected) keep a record but no
    strokes, so the Studio can still surface and triage them. `prefix` (the library) keeps
    the concept id unique + searchable across sets (so unnamed v1 items don't collide)."""
    from engine import candidates_store

    strokes = _elements_to_strokes(elements)
    pts = sum(len(s.points) for s in strokes)
    renderable = bool(strokes) and pts <= _MAX_POINTS
    return {
        "concept": _slug(f"{prefix}-{name}") if prefix else _slug(name),
        "title": name,
        "index": index_,
        "renderable": renderable,
        "complexity": len(strokes),
        "strokes": candidates_store.serialize_strokes(strokes) if renderable else [],
        "license": LICENSE,
    }


_MAX_POINTS = 6000
_ELLIPSE_SEGMENTS = 28
# Excalidraw "transparent" + the obvious no-fill spellings.
_NO_FILL = {"", "transparent", "none", None}


def _shape_polylines(e: dict) -> list[tuple[list[tuple[float, float]], bool]]:
    """A drawable element -> one or more (points, closed) polylines, in Excalidraw
    coordinates (y-down). Shapes become real outlines (not just a diagonal)."""
    typ = str(e.get("type") or "")
    x, y = float(e.get("x", 0) or 0), float(e.get("y", 0) or 0)
    w, h = float(e.get("width", 0) or 0), float(e.get("height", 0) or 0)
    if typ in ("line", "arrow", "freedraw", "draw"):
        pts = _element_points(e)
        return [(pts, False)] if len(pts) >= 2 else []
    if typ == "ellipse":
        cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
        pts = [
            (
                cx + rx * math.cos(2 * math.pi * i / _ELLIPSE_SEGMENTS),
                cy + ry * math.sin(2 * math.pi * i / _ELLIPSE_SEGMENTS),
            )
            for i in range(_ELLIPSE_SEGMENTS)
        ]
        return [(pts, True)]
    if typ == "diamond":
        return [([(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)], True)]
    if typ in ("text", "image", "frame", "embeddable"):
        return []  # text/raster have no vector outline we can keep
    # rectangle (and unknown box-like elements)
    if w and h:
        return [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
    return []


def _elements_to_strokes(elements: list[dict], target: float = 2.4):
    """Parse Excalidraw elements into COLORED board-unit strokes — preserving each
    element's stroke color and background fill (svgnorm would have flattened these to
    monochrome). Normalizes to a centered board box and flips Y to board-up."""
    from engine.contracts import Stroke

    raw: list[tuple[list[tuple[float, float]], bool, str, str | None]] = []
    for e in elements:
        stroke = str(e.get("strokeColor") or "#1e1e1e")
        bg = e.get("backgroundColor")
        fill = None if bg in _NO_FILL else str(bg)
        for pts, closed in _shape_polylines(e):
            raw.append((pts, closed, stroke, fill if closed else None))
    allpts = [p for r in raw for p in r[0]]
    if not allpts:
        return []
    xs = [p[0] for p in allpts]
    ys = [p[1] for p in allpts]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    cx, cy = (minx + maxx) / 2, (miny + maxy) / 2
    scale = target / max(maxx - minx, maxy - miny, 1e-6)

    def tf(p: tuple[float, float]) -> tuple[float, float]:
        return (round((p[0] - cx) * scale, 4), round(-(p[1] - cy) * scale, 4))  # flip Y

    return [
        Stroke(tuple(tf(p) for p in pts), closed, color, fill) for pts, closed, color, fill in raw
    ]


def _items_of(data: dict) -> list[dict]:
    items = data.get("libraryItems") or data.get("library") or []
    return items if isinstance(items, list) else []


def _item_name_elements(it, i: int) -> tuple[str, list[dict]]:
    """Handle both Excalidraw formats: v2 items are {name, elements:[…]}; v1 items are a
    bare LIST of elements (no name)."""
    if isinstance(it, dict):
        raw = it.get("elements", [])
        name = str(it.get("name") or f"Item {i + 1}")
    elif isinstance(it, list):
        raw = it
        name = f"Item {i + 1}"
    else:
        raw, name = [], f"Item {i + 1}"
    elements = [e for e in raw if isinstance(e, dict) and not e.get("isDeleted")]
    return name, elements


def _build_pack(path: str, data: dict, set_name: str = "") -> dict:
    items = _items_of(data)
    prefix = Path(path).stem
    records = []
    for i, it in enumerate(items):
        name, elements = _item_name_elements(it, i)
        try:
            records.append(_normalize_item(elements, name, i, prefix=prefix))
        except Exception:  # noqa: BLE001 - one bad item never sinks the pack
            continue
    return {
        "library": Path(path).stem,
        "source": _safe_repo_path(path),
        "set_name": set_name or Path(path).stem,
        "license": LICENSE,
        "items": records,
    }


def import_library(path: str, set_name: str = "") -> dict:
    """Fetch ONE `.excalidrawlib` once and convert ALL its items to candidate strokes."""
    from engine import candidates_store

    path = _safe_repo_path(path)
    raw = urllib.request.urlopen(_raw_url(path), timeout=30).read().decode("utf-8")
    pack = _build_pack(path, json.loads(raw), set_name)
    candidates_store.save_pack(_pack_key(path), pack)
    renderable = sum(1 for r in pack["items"] if r["renderable"])
    return {
        "ok": True,
        "library": pack["library"],
        "items": len(pack["items"]),
        "renderable": renderable,
    }


def import_item(path: str, index_: int, concept: str = "") -> dict:
    """Import a single item — implemented as a whole-set import (one fetch yields the set),
    so one click brings in the icon's entire family. Returns the one concept's status."""
    from engine import candidates_store

    res = import_library(path)
    # find the concept for the requested index, for the caller's message
    pack = json.loads(candidates_store.pack_path(_pack_key(path)).read_text())
    target = next((r for r in pack["items"] if r["index"] == index_), None)
    return {
        "ok": True,
        "candidate": (concept and _slug(concept)) or (target["concept"] if target else None),
        "renderable": bool(target and target["renderable"]),
        "imported": res["items"],
    }


def sync_all(progress=None, limit: int | None = None, refresh: bool = False) -> dict:
    """Sync EVERY published library into candidate packs. One fetch per `.excalidrawlib`;
    all items parsed locally from their coordinates. `progress(done, total, name)` is called
    per library. This is the bulk "pull all icons in" pipeline (run from the CLI/route)."""
    libs = index(refresh=refresh)["libraries"]
    if limit:
        libs = libs[:limit]
    total = len(libs)
    items = renderable = failed = 0
    for done, lib in enumerate(libs, 1):
        try:
            r = import_library(lib["path"], lib.get("name", ""))
            items += r["items"]
            renderable += r["renderable"]
        except Exception:  # noqa: BLE001 - skip a failed set, keep syncing
            failed += 1
        if progress:
            progress(done, total, lib.get("name", lib["path"]))
    return {
        "ok": True,
        "libraries": total,
        "failed": failed,
        "items": items,
        "renderable": renderable,
    }


def authors(refresh: bool = False) -> dict:
    """Top-level contributor directories under `/libraries/`.

    One GitHub request, cached locally. Item counts are intentionally lazy because
    walking every folder would cost ~191 API calls.
    """
    cache = _cache_dir() / "authors.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text())
    rows = _request_json(f"{API}/libraries?ref={BRANCH}")
    dirs = [
        {
            "name": r["name"],
            "path": r["path"],
            "type": "library-author",
            "source": "excalidraw-libraries",
            "license": LICENSE,
        }
        for r in rows
        if r.get("type") == "dir"
    ]
    out = {"source": "github", "count": len(dirs), "authors": dirs}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out, indent=2))
    return out


def files(author_path: str) -> dict:
    """List `.excalidrawlib` files inside one author folder."""
    path = _safe_repo_path(author_path)
    rows = _request_json(f"{API}/{urllib.parse.quote(path)}?ref={BRANCH}")
    libs = [
        {
            "name": r["name"],
            "path": r["path"],
            "download_url": r.get("download_url"),
            "size": r.get("size", 0),
            "license": LICENSE,
        }
        for r in rows
        if r.get("type") == "file" and r.get("name", "").endswith(".excalidrawlib")
    ]
    previews = [
        {"name": r["name"], "path": r["path"], "download_url": r.get("download_url")}
        for r in rows
        if r.get("type") == "file" and r.get("name", "").lower().endswith((".png", ".jpg", ".jpeg"))
    ]
    return {"author_path": path, "files": libs, "previews": previews, "count": len(libs)}


def load(path: str) -> LibraryPack:
    """Fetch and parse one `.excalidrawlib` file."""
    path = _safe_repo_path(path)
    if not path.endswith(".excalidrawlib"):
        raise ValueError("expected an .excalidrawlib path")
    raw = urllib.request.urlopen(_raw_url(path), timeout=30).read().decode("utf-8")
    data = json.loads(raw)
    return parse(data, path=path)


def parse(data: dict, *, path: str = "") -> LibraryPack:
    items = data.get("libraryItems") or data.get("library") or []
    if not isinstance(items, list):
        items = []
    parsed: list[LibraryItem] = []
    all_types: dict[str, int] = {}
    for idx, item in enumerate(items):
        elements = [
            e for e in item.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")
        ]
        types: dict[str, int] = {}
        for e in elements:
            typ = str(e.get("type", "unknown"))
            types[typ] = types.get(typ, 0) + 1
            all_types[typ] = all_types.get(typ, 0) + 1
        parsed.append(
            LibraryItem(
                id=str(item.get("id") or f"item-{idx}"),
                name=str(item.get("name") or f"Item {idx + 1}"),
                status=str(item.get("status") or ""),
                elements=len(elements),
                types=types,
                bbox=_bbox(elements),
            )
        )
    return LibraryPack(
        path=path,
        name=Path(path).stem if path else "excalidraw-library",
        source=str(data.get("source") or "excalidraw"),
        version=data.get("version") if isinstance(data.get("version"), int) else None,
        items=parsed,
        element_types=all_types,
    )


def item(path: str, index: int) -> dict:
    """One item with its approximate SVG preview."""
    path = _safe_repo_path(path)
    raw = urllib.request.urlopen(_raw_url(path), timeout=30).read().decode("utf-8")
    data = json.loads(raw)
    items = data.get("libraryItems") or data.get("library") or []
    if index < 0 or index >= len(items):
        raise IndexError("library item index out of range")
    pack = parse(data, path=path)
    elements = [
        e
        for e in items[index].get("elements", [])
        if isinstance(e, dict) and not e.get("isDeleted")
    ]
    return {
        "pack": {"path": pack.path, "name": pack.name, "license": LICENSE},
        "index": index,
        "item": pack.items[index].to_dict(),
        "svg": preview_svg(elements),
        "elements": elements,
    }


def _element_points(e: dict) -> list[tuple[float, float]]:
    x, y = float(e.get("x", 0) or 0), float(e.get("y", 0) or 0)
    pts = e.get("points")
    if isinstance(pts, list) and pts:
        return [
            (x + float(p[0]), y + float(p[1])) for p in pts if isinstance(p, list) and len(p) >= 2
        ]
    w, h = float(e.get("width", 0) or 0), float(e.get("height", 0) or 0)
    return [(x, y), (x + w, y + h)]


def _bbox(elements: list[dict]) -> tuple[float, float, float, float] | None:
    pts: list[tuple[float, float]] = []
    for e in elements:
        pts.extend(_element_points(e))
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (round(min(xs), 2), round(min(ys), 2), round(max(xs), 2), round(max(ys), 2))


def preview_svg(elements: list[dict], width: int = 280, height: int = 200) -> str:
    """Approximate Excalidraw elements as plain SVG for Studio review."""
    box = _bbox(elements)
    if box is None:
        return _empty_svg(width, height)
    x0, y0, x1, y1 = box
    pad = max(x1 - x0, y1 - y0, 1.0) * 0.08
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    vbw, vbh = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="{x0:.2f} {y0:.2f} {vbw:.2f} {vbh:.2f}">',
        f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{vbw:.2f}" height="{vbh:.2f}" fill="#0d1117"/>',
    ]
    for e in elements:
        parts.append(_element_svg(e))
    parts.append("</svg>")
    return "\n".join(p for p in parts if p)


def _empty_svg(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}"><rect width="{width}" height="{height}" fill="#0d1117"/>'
        '<text x="50%" y="50%" fill="#8b949e" text-anchor="middle">empty item</text></svg>'
    )


def _paint(e: dict) -> tuple[str, str, str, float]:
    stroke = str(e.get("strokeColor") or "#e6edf3")
    bg = str(e.get("backgroundColor") or "transparent")
    fill = "none" if bg in ("transparent", "none", "") else bg
    opacity = max(0.0, min(1.0, float(e.get("opacity", 100) or 100) / 100.0))
    sw = max(1.0, float(e.get("strokeWidth", 1) or 1))
    return stroke, fill, f"{sw:.2f}", opacity


def _element_svg(e: dict) -> str:
    typ = str(e.get("type") or "")
    x, y = float(e.get("x", 0) or 0), float(e.get("y", 0) or 0)
    w, h = float(e.get("width", 0) or 0), float(e.get("height", 0) or 0)
    stroke, fill, sw, opacity = _paint(e)
    common = f'stroke="{escape(stroke)}" stroke-width="{sw}" opacity="{opacity:.3f}"'
    if typ in ("line", "arrow", "freedraw"):
        pts = _element_points(e)
        if len(pts) < 2:
            return ""
        d = " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)
        return f'<polyline points="{d}" fill="none" {common} stroke-linecap="round" stroke-linejoin="round"/>'
    if typ == "ellipse":
        return (
            f'<ellipse cx="{x + w / 2:.2f}" cy="{y + h / 2:.2f}" rx="{abs(w) / 2:.2f}" '
            f'ry="{abs(h) / 2:.2f}" fill="{escape(fill)}" {common}/>'
        )
    if typ == "diamond":
        pts = [
            (x + w / 2, y),
            (x + w, y + h / 2),
            (x + w / 2, y + h),
            (x, y + h / 2),
        ]
        d = " ".join(f"{px:.2f},{py:.2f}" for px, py in pts)
        return f'<polygon points="{d}" fill="{escape(fill)}" {common} stroke-linejoin="round"/>'
    if typ == "text":
        text = escape(str(e.get("text") or e.get("rawText") or ""))
        size = max(8.0, float(e.get("fontSize", 20) or 20))
        return f'<text x="{x:.2f}" y="{y + size:.2f}" fill="{escape(stroke)}" font-size="{size:.2f}" font-family="sans-serif">{text}</text>'
    # rectangle + fallback for frame/embeddable-like boxes.
    rx = min(abs(w), abs(h)) * 0.05
    return f'<rect x="{min(x, x + w):.2f}" y="{min(y, y + h):.2f}" width="{abs(w):.2f}" height="{abs(h):.2f}" rx="{rx:.2f}" fill="{escape(fill)}" {common}/>'
