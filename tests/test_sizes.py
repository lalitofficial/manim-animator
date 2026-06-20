"""Per-concept semantic sizing — the scene's scale hierarchy."""

from __future__ import annotations

from engine import drawing, sizes
from engine.contracts import Extent, Thing


def test_size_tiers_form_a_hierarchy():
    assert sizes.size_for("mountain") > sizes.size_for("cloud") > sizes.size_for("cat")
    assert sizes.size_for("cat") > sizes.size_for("apple") > sizes.size_for("ant")
    assert sizes.size_for("cat") == sizes.DEFAULT  # an unprofiled concept is the default tier


def test_unknown_concept_is_default():
    assert sizes.size_for("flibbertigibbet") == sizes.DEFAULT
    assert sizes.size_for("flibbertigibbet", 9.9) == 9.9


def test_multiword_concept_inherits_word_size():
    assert sizes.size_for("red apple") == sizes.size_for("apple")
    assert sizes.size_for("tall mountain") == sizes.size_for("mountain")


def _extent(concept: str, **geom) -> float:
    drawing._cache.clear()
    d = drawing.measure(
        Thing(id="x", concept=concept, extent=Extent(1, 1), geometry_attrs=geom),
        generate=False,
        style="cartoon",
    )
    return max(d.extent.w, d.extent.h)


def test_measure_applies_semantic_size():
    assert _extent("mountain") > _extent("cat") > _extent("ant")


def test_explicit_size_overrides_profile():
    assert round(_extent("mountain", size=1.0), 2) == 1.0
