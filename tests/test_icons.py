"""The composable visual LANGUAGE — concepts drawn by composing primitives, so
generation/catalog become the rare fallback (not the default).
"""

from __future__ import annotations

import pytest

from engine import drawing, icons
from engine.contracts import Extent, Thing


@pytest.mark.parametrize("concept", ["sun", "cloud", "tree", "person", "molecule", "house", "star"])
def test_icon_composes_from_primitives(concept):
    strokes = icons.compose(concept)
    assert strokes is not None
    assert len(strokes) >= 1
    assert all(len(s.points) >= 2 for s in strokes)


def test_unknown_concept_has_no_icon():
    assert icons.compose("photosynthesis") is None


def test_aliases_resolve():
    assert icons.compose("sunlight") is not None  # -> sun
    assert icons.compose("raindrop") is not None  # -> water


def test_measure_prefers_icon_over_catalog_and_generation():
    """An icon-able concept resolves to the visual language (rung 1, source=icon),
    not the QuickDraw catalog or the generator."""
    drawing.reset()
    drawing.set_sketch_lookup(
        lambda name: {"name": name, "strokes": [[[0, 0], [1, 1]]]}
    )  # pretend cached
    d = drawing.measure(Thing("x", "sun", Extent(1, 1)), generate=False)
    assert d.source == "icon" and d.rung == 1
    drawing.set_sketch_lookup(None)
    drawing.reset()


def test_tabler_catalog_resolves_with_aliases():
    """The MIT Tabler catalog resolves concepts (and tag-aliases) to real line
    drawings via svgnorm — license-clean coverage with no generation."""
    from engine import catalog

    assert len(catalog.known()) > 20
    drawing.set_compose(lambda c: None)  # isolate the catalog from the icon language
    drawing.set_sketch_lookup(lambda n: None)
    for concept in ("rocket", "book", "microscope", "idea"):  # 'idea' -> bulb via tag alias
        drawing.reset()
        d = drawing.measure(Thing("x", concept, Extent(1, 1)), generate=False)
        assert d.source == "catalog", (concept, d.source)
        assert d.strokes
    drawing.set_compose(None)
    drawing.set_sketch_lookup(None)
    drawing.reset()


def test_visual_language_reduces_generation():
    """A spread of common concepts should DRAW deterministically (no generation,
    no boxes) thanks to primitives + icons."""
    drawing.reset()
    drawing.set_sketch_lookup(lambda name: None)  # no catalog
    concepts = [
        "sun",
        "cloud",
        "tree",
        "person",
        "house",
        "mountain",
        "star",
        "flower",
        "circle",
        "square",
    ]
    sources = []
    for c in concepts:
        sources.append(drawing.measure(Thing("x", c, Extent(1, 1)), generate=False).source)
    drawn = sum(1 for s in sources if s != "box")
    assert drawn == len(concepts), sources  # all drew without catalog or generation
    drawing.set_sketch_lookup(None)
    drawing.reset()
