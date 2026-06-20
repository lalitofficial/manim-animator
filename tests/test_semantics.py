"""Domain-aware semantic concept resolution (Phases 1+2).

Hermetic: candidate store is isolated (empty) by the global fixture; tests that need
imported icons seed their own published candidate.
"""

from __future__ import annotations

from dataclasses import replace

from engine import candidates_store, director, semantics, story
from engine.contracts import show


def _seed(concept: str, title: str, set_name: str):
    """Publish one imported candidate (a colored square) so resolution can find it."""
    pack = {
        "library": set_name.lower().replace(" ", "-"),
        "set_name": set_name,
        "license": "MIT",
        "items": [
            {
                "concept": concept,
                "title": title,
                "renderable": True,
                "complexity": 1,
                "strokes": [
                    {
                        "points": [[0, 0], [1, 0], [1, 1], [0, 1]],
                        "closed": True,
                        "color": "#333",
                        "fill": "#39c",
                    }
                ],
            }
        ],
    }
    candidates_store.save_pack("seed_" + concept, pack)
    candidates_store.publish([concept])


# --------------------------------------------------------------------------- #
# Domain inference
# --------------------------------------------------------------------------- #
def test_infer_domain():
    assert semantics.infer_domain("whats azure cloud") == "cloud-computing"
    assert semantics.infer_domain("kubernetes basics") == "cloud-computing"
    assert semantics.infer_domain("aws architecture") == "cloud-computing"
    # weather/general topics must NOT classify as cloud-computing
    assert semantics.infer_domain("types of clouds") == "weather"
    assert semantics.infer_domain("the water cycle") == "weather"
    assert semantics.infer_domain("photosynthesis") == ""
    assert semantics.infer_domain("why the sky is blue") == "weather"


def test_director_infers_domain():
    spec = director.direct("whats azure cloud", mode="learn", style="cartoon")
    assert spec.domain == "cloud-computing"
    spec2 = director.direct("photosynthesis", mode="learn")
    assert spec2.domain == ""


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #
def test_cartoon_concepts_are_kept():
    # a real cartoon concept must never be rewritten to a tech icon
    assert semantics.resolve_concept("tree", "cloud-computing") == "tree"
    assert semantics.resolve_concept("sun", "cloud-computing") == "sun"


def test_gap_noun_maps_to_published_icon():
    _seed("azure-server", "Server", "Azure Compute")
    out = semantics.resolve_concept("server", "cloud-computing")
    assert out == "azure server"  # normalized published key
    # and it draws as a real published icon, not a box
    from engine import drawing
    from engine.contracts import Extent, Thing

    drawing._cache.clear()
    d = drawing.measure(
        Thing(id="s", concept=out, extent=Extent(1, 1)), generate=False, style="cartoon"
    )
    assert d.source == "published"


def test_force_overrides_ambiguous_cloud():
    _seed("azure-cloud-svc", "Cloud", "Azure cloud services")
    # in a cloud lesson, "cloud" is FORCED to the tech icon even though a cartoon sky cloud exists
    assert semantics.resolve_concept("cloud", "cloud-computing") == "azure cloud svc"
    # but with no domain (general lesson), the cartoon cloud is preserved
    assert semantics.resolve_concept("cloud", "") == "cloud"


def test_resolution_is_noop_without_a_domain():
    beats = [show("s", "server"), show("t", "tree")]
    spec = director.direct("general topic", mode="learn")  # domain == ""
    out = story._resolve_domain_concepts(beats, spec)
    assert [b.concept for b in out] == ["server", "tree"]  # untouched


def test_story_rewrites_show_concepts_for_domain():
    _seed("aws-server", "Server", "AWS Compute")
    beats = [show("s", "server"), show("t", "tree")]
    spec = replace(director.direct("aws lesson", mode="learn"), domain="cloud-computing")
    out = story._resolve_domain_concepts(beats, spec)
    by_id = {b.entity: b.concept for b in out}
    assert by_id["s"] == "aws server"  # gap noun → published icon
    assert by_id["t"] == "tree"  # cartoon kept


# --------------------------------------------------------------------------- #
# Prompt vocabulary (Phase 1)
# --------------------------------------------------------------------------- #
def test_vocabulary_filters_cryptic_titles():
    _seed("azure-vm", "Virtual Machine", "Azure Compute")
    _seed("azure-ns", "NS", "Azure Network")  # cryptic 2-char title → filtered
    vocab = semantics.vocabulary("cloud-computing", 40)
    assert "virtual machine" in vocab
    assert "ns" not in vocab


def test_domain_prompt_line():
    _seed("azure-storage", "Storage", "Azure Storage")
    line = story._domain_prompt_line("cloud-computing")
    assert "cloud-computing" in line and "storage" in line
    assert story._domain_prompt_line("") == ""
