"""Bioicons importer — SVG → COLORED board strokes → candidate packs → publish → resolve.

Hermetic: builds a tiny fake Bioicons checkout on disk and imports it; the global fixture
isolates the candidate store. No network.
"""

from __future__ import annotations

import json

import pytest

from engine import bioicons, candidates_store, drawing, semantics
from engine.contracts import Extent, Thing

# A colored, closed square path — exercises fill + stroke color preservation.
_SQUARE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    '<path d="M10 10 H90 V90 H10 Z" fill="#4caf50" stroke="#1b5e20"/></svg>'
)
_SCRIPT = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
    "<script>alert(1)</script>"
    '<path d="M0 0 H10 V10 Z" fill="#000000"/></svg>'
)


def test_svg_to_strokes_preserves_color_and_normalizes():
    strokes = bioicons.svg_to_strokes(_SQUARE)
    assert len(strokes) == 1
    s = strokes[0]
    assert s.closed and s.fill == "#4caf50" and s.color == "#1b5e20"  # color kept, not flattened
    # normalized into a board box centered at the origin (target 2.4 ⇒ within ±1.2)
    assert all(abs(x) <= 1.21 and abs(y) <= 1.21 for x, y in s.points)


def test_security_rejects_script():
    with pytest.raises(ValueError):
        bioicons.svg_to_strokes(_SCRIPT)
    # build_item swallows the rejection → a non-renderable record (drop-don't-repair)
    item = bioicons.build_item("bad", "Chemistry", "CC0", "", _SCRIPT)
    assert item["renderable"] is False and item["strokes"] == []


def _fake_tree(root):
    """A minimal Bioicons checkout: <root>/static/icons/<license>/<category>/<name>.svg + manifest."""
    icons = root / "static" / "icons"
    (icons / "cc-0" / "Intracellular_components").mkdir(parents=True)
    (icons / "cc-by-4.0" / "Chemistry").mkdir(parents=True)
    (icons / "cc-0" / "Intracellular_components" / "spliceosome.svg").write_text(_SQUARE)
    (icons / "cc-by-4.0" / "Chemistry" / "benzene.svg").write_text(_SQUARE)
    (icons / "icons.json").write_text(
        json.dumps(
            [
                {
                    "name": "spliceosome",
                    "category": "Intracellular_components",
                    "license": "cc-0",
                    "author": "Jane Doe",
                },
                {
                    "name": "benzene",
                    "category": "Chemistry",
                    "license": "cc-by-4.0",
                    "author": "Bob",
                },
            ]
        )
    )
    return root


def test_import_tree_builds_per_icon_licensed_packs(tmp_path):
    res = bioicons.import_tree(_fake_tree(tmp_path / "bio"))
    assert res["categories"] == 2 and res["renderable"] == 2
    # per-icon license comes from the FOLDER, author from the manifest
    spliceo = candidates_store.get("spliceosome")
    assert spliceo["license"] == "CC0" and spliceo["author"] == "Jane Doe"
    assert candidates_store.get("benzene")["license"] == "CC-BY-4.0"


def test_published_bioicon_resolves_through_the_ladder(tmp_path):
    bioicons.import_tree(_fake_tree(tmp_path / "bio"))
    candidates_store.publish(["spliceosome"])
    drawing._cache.clear()
    d = drawing.measure(
        Thing(id="x", concept="spliceosome", extent=Extent(1, 1)), generate=False, style="cartoon"
    )
    assert d.source == "published"  # a published bioicon draws as a real icon, not a box


def test_import_domain_restricts_to_domain_categories(tmp_path):
    bioicons.import_domain(_fake_tree(tmp_path / "bio"), "biology")  # only Intracellular_components
    assert candidates_store.has("spliceosome")
    assert not candidates_store.has("benzene")  # Chemistry is not a biology category


def test_bioicons_packs_are_domain_tagged():
    # a pack's set_name/library tags it to a subject domain (prompt vocab + lookup scoring)
    assert semantics._set_domain("Bioicons · Cell types", "bioicons-cell-types") == "biology"
    assert semantics._set_domain("Bioicons · Chemistry", "bioicons-chemistry") == "chemistry"
