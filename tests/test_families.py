"""Parametric icon FAMILIES (engine.families) — the colored-cartoon corpus that scales
the composed visual language past the hand-built core. Hermetic: pure geometry, no model."""

from __future__ import annotations

from engine import drawing, families, icons
from engine.contracts import Extent, Thing


def test_every_family_concept_composes_to_filled_strokes():
    """No entry in the data table may be dead: each must render real, FILLED cartoon
    strokes (not empty, not a bare outline) — that's the whole point vs a line-icon."""
    assert len(families.CONCEPT_FAMILIES) >= 150  # the corpus is large
    for concept in families.CONCEPT_FAMILIES:
        strokes = icons.compose(concept)
        assert strokes, f"{concept} composed to nothing"
        assert any(s.closed and s.fill for s in strokes), f"{concept} has no filled region"


def test_family_concepts_resolve_through_measure_as_icons_in_cartoon():
    """A family concept draws for REAL in cartoon (source 'icon'), not the fallback box —
    this is the fix for the #7 fallback-leak on common concepts."""
    for concept in ("cat", "penguin", "apple", "rocket", "saturn", "firetruck", "panda"):
        drawing.reset()
        d = drawing.measure(Thing("p", concept, Extent(1, 1)), generate=False, style="cartoon")
        assert d.source == "icon", f"{concept} fell back to {d.source}"


def test_hand_built_recipes_override_families():
    """Bespoke art always wins: a concept present in both the hand-built core and a family
    composes from the core recipe (icons.compose checks ICON_RECIPES first)."""
    # 'tree' exists as a hand recipe AND a family entry — the hand one must win.
    assert "tree" in icons.ICON_RECIPES and "tree" in families.CONCEPT_FAMILIES
    from engine.icons import ICON_RECIPES, render_recipe

    assert icons.compose("tree") == render_recipe(ICON_RECIPES["tree"])


def test_family_aliases_resolve():
    assert icons.compose("kitty") and icons.compose("bunny")  # synonyms hit the corpus


def test_science_concepts_draw_as_filled_icons():
    """The education domain (delivered as composed families, not ingested BioIcons — §B10):
    common science nouns resolve to real filled cartoons in cartoon, so lessons stop boxing."""
    for concept in (
        "cell",
        "nucleus",
        "dna",
        "atom",
        "molecule",
        "virus",
        "neuron",
        "beaker",
        "lungs",
        "brain",
        "red blood cell",
        "chromosome",
    ):
        drawing.reset()
        d = drawing.measure(Thing("p", concept, Extent(1, 1)), generate=False, style="cartoon")
        assert d.source == "icon", f"{concept} boxed ({d.source})"
    # dna is a real filled helix (nucleotide nodes), not bare line-art
    dna = icons.compose("dna")
    assert any(s.closed and s.fill for s in dna)
