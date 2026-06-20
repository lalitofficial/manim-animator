"""Quantity / multiplicity — a plural concept (or explicit count) draws as N copies."""

from __future__ import annotations

from engine import drawing, multiplicity, story
from engine.contracts import Extent, Thing


def _measure(concept: str, **geom):
    drawing._cache.clear()
    t = Thing(id="x", concept=concept, extent=Extent(1, 1), geometry_attrs=geom)
    return drawing.measure(t, generate=False, style="cartoon")


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
def test_intrinsic_profiles():
    assert multiplicity.profile("rain", {}).base == "water"
    assert multiplicity.profile("rain", {}).count > 1
    assert multiplicity.profile("forest", {}).base == "tree"
    assert multiplicity.profile("tree", {}) is None  # a single glyph
    assert multiplicity.profile("sun", {}) is None


def test_explicit_count_repeats_the_concept():
    p = multiplicity.profile("server", {"count": 3})
    assert p is not None and p.base == "server" and p.count == 3
    # explicit base override
    p2 = multiplicity.profile("group", {"count": 4, "base": "star", "arrangement": "grid"})
    assert p2.base == "star" and p2.arrangement == "grid"


def test_count_one_is_single():
    assert multiplicity.profile("server", {"count": 1}) is None


# --------------------------------------------------------------------------- #
# Tiling geometry
# --------------------------------------------------------------------------- #
def test_tile_makes_n_copies():
    base = drawing._compose("star")  # a single star's strokes
    assert base
    tiled = multiplicity.tile(base, 7, "scatter", box=2.8)
    # 7 copies of a 1-stroke star → 7 strokes, all within the box
    assert len(tiled) == 7 * len(base)
    xs = [p[0] for s in tiled for p in s.points]
    assert max(xs) - min(xs) <= 3.0  # contained in ~box


def test_tile_is_deterministic():
    base = drawing._compose("star")
    a = multiplicity.tile(base, 6, "scatter")
    b = multiplicity.tile(base, 6, "scatter")
    assert [s.points for s in a] == [s.points for s in b]  # no global RNG


# --------------------------------------------------------------------------- #
# measure() expansion
# --------------------------------------------------------------------------- #
def test_measure_expands_plural_to_many():
    rain = _measure("rain")
    one = _measure("water")
    assert rain.source == one.source  # same rung (icon), just repeated
    assert len(rain.strokes) >= 8 * len(one.strokes) - 2  # ~9 drops
    # the group is a real box (not a thin sliver)
    assert rain.extent.w > 1.5


def test_measure_single_concept_unchanged():
    assert len(_measure("tree").strokes) == len(drawing._compose("tree"))


def test_measure_explicit_count_in_a_row():
    three = _measure("server", count=3, base="star", arrangement="row")
    one = _measure("star")
    assert len(three.strokes) == 3 * len(one.strokes)


# --------------------------------------------------------------------------- #
# Story integration: count survives parse_beats (top-level or geometry)
# --------------------------------------------------------------------------- #
def test_parse_beats_folds_top_level_count():
    beats = story.parse_beats(
        {"beats": [{"kind": "show", "entity": "stars", "concept": "star", "count": 7}]}
    )
    assert beats[0].geometry.get("count") == 7
