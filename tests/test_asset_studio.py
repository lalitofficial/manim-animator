"""Asset Studio — manifest, bundles, coverage, gates, Excalidraw import, and routes.

Hermetic: the bundle/override/request-log state is redirected to tmp paths so tests
never touch the committed registry or the repo, and the Excalidraw routes are
monkeypatched so nothing hits GitHub.
"""

from __future__ import annotations

import pytest

from engine import (
    asset_registry,
    asset_studio,
    bundles,
    candidates_store,
    coverage,
    excalidraw_libraries,
)
from engine.contracts import Extent, Thing


@pytest.fixture(autouse=True)
def isolate_state(tmp_path, monkeypatch):
    """Point every persisted surface at tmp and reset the in-memory caches before/after.
    Crucially redirects the candidate store to an EMPTY tmp dir so the suite never sees the
    real synced Excalidraw candidates on disk (hermeticity)."""
    monkeypatch.setenv("BUNDLE_STATE", str(tmp_path / "bundle_state.json"))
    monkeypatch.setenv("ASSET_REQUEST_LOG", str(tmp_path / "requests.jsonl"))
    monkeypatch.setenv("EXCALIDRAW_LIBRARY_CACHE", str(tmp_path / "excal"))
    monkeypatch.setattr(asset_studio, "_OVERRIDES", tmp_path / "asset_overrides.json")
    monkeypatch.setattr(asset_registry, "_OVERRIDES", tmp_path / "asset_overrides.json")
    monkeypatch.setattr(candidates_store, "_DIR", tmp_path / "candidates")
    bundles.reload()
    asset_registry.refresh()
    yield
    bundles.reload()
    asset_registry.refresh()


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
def test_manifest_enumerates_all_sources():
    m = asset_registry.manifest()
    assert len(m) > 400
    by_concept = {e.concept: e for e in m}
    # cat is in cartoon_recipes.json, so the colored recipe wins over the family rung
    assert by_concept["cat"].kind == "cartoon"
    assert by_concept["cat"].bundle == "animals"
    assert "sun" in by_concept
    # a family-only concept keeps its family + params recorded
    fam_entry = next(e for e in m if e.kind == "family")
    assert fam_entry.family and isinstance(fam_entry.params, dict)
    kinds = {e.kind for e in m}
    assert {"family", "core", "cartoon", "catalog"} <= kinds


def test_manifest_dedupes_by_concept_with_precedence():
    m = asset_registry.manifest()
    concepts = [e.concept for e in m]
    assert len(concepts) == len(set(concepts))  # one winning entry per concept


def test_stats_shape():
    s = asset_registry.stats()
    assert s["total"] == len(asset_registry.manifest())
    assert "family" in s["by_kind"]
    assert "animals" in s["by_bundle"]


# --------------------------------------------------------------------------- #
# Bundles + runtime gate
# --------------------------------------------------------------------------- #
def test_bundle_for_concept_routing():
    assert bundles.bundle_for_concept("cat").id == "animals"
    assert bundles.bundle_for_concept("sun").id == "weather"
    assert bundles.bundle_for_concept("rocket").id  # claimed by something, never crashes
    # an unclaimed concept falls to core (the always-on default)
    assert bundles.bundle_for_concept("zzz-not-a-thing").id == "core"


def test_imported_bundle_disabled_but_runtime_unaffected():
    # the `imported` bundle ships DISABLED (so technical icons never pollute cartoons),
    # so any_disabled() is True — but normal cartoon concepts still resolve untouched.
    imported = bundles.get("imported")
    assert imported is not None and imported.enabled is False
    assert bundles.concept_enabled("cat") is True
    assert bundles.concept_enabled("sun") is True


def test_core_bundle_is_locked():
    res = bundles.set_enabled("core", False)
    assert res["ok"] is False
    assert bundles.concept_enabled("sun") is True


def test_disable_bundle_gates_resolution():
    from engine import drawing

    drawing._cache.clear()
    bundles.set_enabled("animals", True)  # ensure baseline
    cat = Thing(id="cat", concept="cat", extent=Extent(1.0, 1.0))
    assert drawing.measure(cat, generate=False, style="cartoon").source == "icon"

    res = bundles.set_enabled("animals", False)
    assert res["ok"] and res["enabled"] is False
    assert bundles.any_disabled() is True
    assert bundles.concept_enabled("cat") is False
    drawing._cache.clear()
    assert drawing.measure(cat, generate=False, style="cartoon").source == "box"

    bundles.set_enabled("animals", True)
    drawing._cache.clear()


# --------------------------------------------------------------------------- #
# Coverage
# --------------------------------------------------------------------------- #
def test_coverage_analyze_reports_rates():
    c = coverage.analyze()
    assert c["total"] > 0
    assert 0.0 <= c["composed_rate"] <= 1.0
    assert 0.0 <= c["fallback_rate"] <= 1.0
    assert isinstance(c["boxed"], list)
    assert "by_bundle" in c and "source_breakdown" in c


def test_request_log_feeds_missing_nouns(tmp_path):
    coverage.log_request("flibbertigibbet")  # a concept that resolves to box
    missing = coverage.missing_nouns()
    assert any(m["concept"] == "flibbertigibbet" for m in missing)


# --------------------------------------------------------------------------- #
# Studio service — catalog, preview, families, gates, publish
# --------------------------------------------------------------------------- #
def test_catalog_filters_by_bundle():
    page = asset_studio.catalog(bundle="animals", limit=500)
    assert page["total"] > 0
    assert all(it["bundle"] == "animals" for it in page["items"])


def test_preview_existing_concept_renders_svg():
    out = asset_studio.preview("sun")
    assert out.startswith("<svg") and "</svg>" in out


def test_families_schema_exposes_params():
    fams = {f["family"]: f for f in asset_studio.families_schema()}
    assert "quad" in fams
    names = {p["name"] for p in fams["quad"]["params"]}
    assert "body" in names and "line" in names


def _first_passing_variant():
    from engine import families

    for concept, (fam, params) in families.CONCEPT_FAMILIES.items():
        report = asset_studio.gate_variant(fam, params)
        if report["approvable"]:
            return concept, fam, params, report
    raise AssertionError("no family variant passes the gates")


def test_gate_variant_flags_line_only():
    # a variant with no colored fill must fail the cartoon style gate
    report = asset_studio.gate_variant("quad", {"body": "", "line": "#000000"})
    style = next(c for c in report["checks"] if c["name"] == "style")
    assert style["pass"] is False
    assert report["approvable"] is False


def test_publish_requires_gates_and_approval():
    _concept, fam, params, report = _first_passing_variant()
    assert report["approvable"] is True

    # missing approval is refused even when gates pass
    denied = asset_studio.save_variant("my-variant", fam, params, approved=False)
    assert denied["ok"] is False
    assert "approval" in denied["error"]

    # approved + passing → published into the override layer
    ok = asset_studio.save_variant("my-variant", fam, params, approved=True)
    assert ok["ok"] is True
    assert (asset_studio._OVERRIDES).exists()
    data = __import__("json").loads(asset_studio._OVERRIDES.read_text())
    assert "my-variant" in data["variants"]


# --------------------------------------------------------------------------- #
# Excalidraw importer (pure parsing, offline)
# --------------------------------------------------------------------------- #
_SAMPLE_LIB = {
    "type": "excalidrawlib",
    "version": 2,
    "source": "test",
    "libraryItems": [
        {
            "id": "a",
            "name": "Tree",
            "status": "published",
            "elements": [
                {
                    "type": "rectangle",
                    "x": 0,
                    "y": 0,
                    "width": 10,
                    "height": 20,
                    "strokeColor": "#222",
                    "backgroundColor": "#3c3",
                },
                {"type": "line", "x": 0, "y": 0, "points": [[0, 0], [5, 5], [10, 0]]},
                {
                    "type": "ellipse",
                    "x": 2,
                    "y": 2,
                    "width": 6,
                    "height": 6,
                    "strokeColor": "#222",
                    "backgroundColor": "transparent",
                },
                {"type": "text", "x": 0, "y": 30, "text": "leaf", "fontSize": 12},
            ],
        }
    ],
}


def test_excalidraw_parse_counts_elements_and_types():
    pack = excalidraw_libraries.parse(_SAMPLE_LIB, path="libraries/foo/bar.excalidrawlib")
    assert pack.name == "bar"
    assert len(pack.items) == 1
    item = pack.items[0]
    assert item.elements == 4
    assert item.types["rectangle"] == 1 and item.types["line"] == 1
    assert item.bbox is not None


def test_excalidraw_preview_svg_is_valid():
    els = _SAMPLE_LIB["libraryItems"][0]["elements"]
    out = excalidraw_libraries.preview_svg(els)
    assert out.startswith("<svg") and out.rstrip().endswith("</svg>")
    assert "<rect" in out and "<polyline" in out and "<ellipse" in out


def test_excalidraw_rejects_paths_outside_libraries():
    with pytest.raises(ValueError):
        excalidraw_libraries.load("../../etc/passwd")


_SAMPLE_INDEX = [
    {
        "name": "Azure Compute",
        "description": "azure",
        "authors": [{"name": "Gordon Howes"}],
        "source": "7demonsrising/azure-compute.excalidrawlib",
        "preview": "7demonsrising/azure-compute.jpg",
        "itemNames": ["Container Apps", "Workspaces"],
        "id": "abc",
    },
    {"name": "broken", "source": "x/y.png"},  # not an .excalidrawlib → skipped
]


def test_excalidraw_index_maps_all_libraries(monkeypatch, tmp_path):
    monkeypatch.setenv("EXCALIDRAW_LIBRARY_CACHE", str(tmp_path / "c"))
    monkeypatch.setattr(excalidraw_libraries, "_request_json", lambda url: _SAMPLE_INDEX)
    out = excalidraw_libraries.index(refresh=True)
    assert out["count"] == 1  # the .png entry is filtered out
    lib = out["libraries"][0]
    assert lib["name"] == "Azure Compute"
    assert lib["path"] == "libraries/7demonsrising/azure-compute.excalidrawlib"
    assert lib["preview"].endswith("/libraries/7demonsrising/azure-compute.jpg")
    assert lib["item_names"] == ["Container Apps", "Workspaces"]


def test_build_pack_parses_coords_to_strokes_and_stores():
    """The sync pipeline: item coordinates -> normalized board strokes -> candidate store
    -> manifest (imported bundle) -> previewable. All hermetic (no network)."""
    pack = excalidraw_libraries._build_pack(
        "libraries/foo/azure-bits.excalidrawlib", _SAMPLE_LIB, "Azure Bits"
    )
    assert len(pack["items"]) == 1
    it = pack["items"][0]
    assert it["concept"].startswith("azure-bits-")  # library-prefixed for uniqueness
    assert it["title"] == "Tree"
    assert it["renderable"] is True and it["strokes"]

    candidates_store.save_pack("azure-bits", pack)
    asset_registry.refresh()
    assert candidates_store.has(it["concept"])
    assert candidates_store.svg_for(it["concept"]).startswith("<svg")

    # surfaces in the manifest, in the disabled `imported` bundle, with a clean title
    entry = next(
        e for e in asset_registry.manifest() if e.concept == candidates_store._norm(it["concept"])
    )
    assert entry.kind == "candidate"
    assert entry.bundle == "imported"
    assert entry.bundle_enabled is False
    assert entry.title == "Tree"
    # and the catalog preview renders the stored strokes, not a box
    assert asset_studio.preview(entry.concept).startswith("<svg")


_SAMPLE_V1 = {
    "type": "excalidrawlib",
    "version": 1,
    "library": [
        [
            {
                "type": "rectangle",
                "x": 0,
                "y": 0,
                "width": 10,
                "height": 10,
                "strokeColor": "#222",
                "backgroundColor": "#3c3",
            }
        ],
    ],
}


def test_build_pack_handles_v1_list_format():
    pack = excalidraw_libraries._build_pack("libraries/a/old.excalidrawlib", _SAMPLE_V1)
    assert len(pack["items"]) == 1
    assert "item-1" in pack["items"][0]["concept"]  # unnamed v1 item gets a positional name


def _seed_candidate():
    pack = excalidraw_libraries._build_pack(
        "libraries/foo/azure-bits.excalidrawlib", _SAMPLE_LIB, "Azure Bits"
    )
    candidates_store.save_pack("azure-bits", pack)
    asset_registry.refresh()
    return pack["items"][0]["concept"]


def test_publish_makes_candidate_engine_drawable():
    from engine import drawing

    concept = _seed_candidate()
    # before publish: a candidate, not drawable by the engine (imported bundle is off)
    assert candidates_store.is_published(concept) is False
    drawing._cache.clear()
    assert (
        drawing.measure(
            Thing(id=concept, concept=concept, extent=Extent(1, 1)), generate=False, style="cartoon"
        ).source
        == "box"
    )

    n = candidates_store.publish([concept])
    assert n == 1
    asset_registry.refresh()
    assert candidates_store.is_published(concept) is True

    # after publish: the engine resolves it via the low `published` rung
    drawing._cache.clear()
    d = drawing.measure(
        Thing(id=concept, concept=concept, extent=Extent(1, 1)), generate=False, style="cartoon"
    )
    assert d.source == "published" and len(d.strokes) >= 1

    entry = next(
        e for e in asset_registry.manifest() if e.concept == candidates_store._norm(concept)
    )
    assert (
        entry.status == "published" and entry.source == "published" and entry.bundle_enabled is True
    )


def test_publish_does_not_shadow_cartoon_assets():
    # publishing imported icons must never override a real cartoon concept
    from engine import drawing

    _seed_candidate()
    candidates_store.publish_all()
    asset_registry.refresh()
    drawing._cache.clear()
    cat = drawing.measure(
        Thing(id="cat", concept="cat", extent=Extent(1, 1)), generate=False, style="cartoon"
    )
    assert cat.source == "icon"  # the cartoon cat still wins (published is a LOW rung)


def test_route_publish_and_unpublish(client):
    concept = _seed_candidate()
    r = client.post("/api/asset-studio/publish", json={"concepts": [concept]})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert r.json()["total_published"] >= 1
    assert candidates_store.is_published(concept) is True

    u = client.post("/api/asset-studio/unpublish", json={"concepts": [concept]})
    assert u.status_code == 200 and u.json()["ok"] is True
    assert candidates_store.is_published(concept) is False


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
def test_asset_studio_page_served(client):
    assert client.get("/asset-studio").status_code == 200


def test_route_catalog_and_stats(client):
    r = client.get("/api/asset-studio/catalog", params={"bundle": "animals", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 0 and len(body["items"]) <= 5
    assert "stats" in body and body["stats"]["total"] > 0


def test_route_bundles_and_coverage_and_families(client):
    b = client.get("/api/asset-studio/bundles").json()
    assert any(x["id"] == "animals" for x in b["bundles"])
    # the imported bundle is disabled by default → at least one bundle is off
    assert b["any_disabled"] is True

    c = client.get("/api/asset-studio/coverage").json()
    assert "fallback_rate" in c

    f = client.get("/api/asset-studio/families").json()
    assert any(x["family"] == "quad" for x in f["families"])


def test_route_preview_returns_svg(client):
    r = client.get("/api/asset-studio/preview", params={"concept": "cloud"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert r.text.startswith("<svg")


def test_route_variant_gate(client):
    r = client.post(
        "/api/asset-studio/variant/gate",
        json={"family": "quad", "params": {"body": "", "line": "#000"}},
    )
    assert r.status_code == 200
    assert r.json()["approvable"] is False


def test_route_excalidraw_authors_monkeypatched(client, monkeypatch):
    monkeypatch.setattr(
        excalidraw_libraries,
        "authors",
        lambda refresh=False: {
            "source": "test",
            "count": 1,
            "authors": [{"name": "x", "path": "libraries/x"}],
        },
    )
    r = client.get("/api/asset-studio/excalidraw/authors")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_route_excalidraw_library_monkeypatched(client, monkeypatch):
    monkeypatch.setattr(
        excalidraw_libraries,
        "load",
        lambda path: excalidraw_libraries.parse(
            _SAMPLE_LIB, path="libraries/foo/bar.excalidrawlib"
        ),
    )
    r = client.get(
        "/api/asset-studio/excalidraw/library", params={"path": "libraries/foo/bar.excalidrawlib"}
    )
    assert r.status_code == 200
    assert r.json()["item_count"] == 1
