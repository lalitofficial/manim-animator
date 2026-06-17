"""Phase-3 gate (docs/ARCHITECTURE.md §5.4, §6.1): the live generative rung.

Hermetic — a fixture/counting provider stands in for the frontier API, so the
whole rung is deterministic and offline. Covers: SVG sanitize/normalize, the
rung-3 ladder integration, the quality gate, negative caching, and the
placeholder-then-swap cache-miss policy.
"""

from __future__ import annotations

import pytest

from engine import drawing, invariants, svgnorm
from engine.contracts import Board, Thing
from engine.generators import FixtureProvider
from engine.scene import Scene, render

BOARD = Board()


class CountingProvider:
    """Wraps the fixtures and counts calls per concept (for negative-cache tests)."""

    def __init__(self):
        self.inner = FixtureProvider()
        self.calls: dict[str, int] = {}

    def generate(self, concept, attrs):
        self.calls[concept] = self.calls.get(concept, 0) + 1
        return self.inner.generate(concept, attrs)


@pytest.fixture(autouse=True)
def fresh_engine():
    """Reset caches + a counting provider; disable rung 2 (QuickDraw) so these
    tests isolate the LLM rung regardless of which sketches are cached locally."""
    drawing.reset()
    drawing.set_sketch_lookup(lambda name: None)
    drawing.set_compose(lambda concept: None)  # isolate the LLM rung from icons
    drawing.set_catalog_lookup(lambda concept: None)  # ...and from the Tabler catalog
    prov = CountingProvider()
    drawing.set_provider(prov)
    yield prov
    drawing.reset()
    drawing.set_provider(None)
    drawing.set_sketch_lookup(None)
    drawing.set_compose(None)
    drawing.set_catalog_lookup(None)


def _thing(id_, concept, **geom):
    from engine.contracts import Extent

    return Thing(id_, concept, Extent(1, 1), geometry_attrs=dict(geom))


# --------------------------------------------------------------------------- #
# Sanitize / geometric-normalize (the §5.4 boundary)
# --------------------------------------------------------------------------- #
def test_transform_is_flattened():
    # star.svg wraps the polygon in translate+scale; the normalized extent must
    # reflect the baked transform, not the raw points.
    svg = FixtureProvider().generate("star", {})
    d = svgnorm.sanitize_to_drawable(svg, target=1.8)
    assert d is not None and d.rung == 3
    assert max(d.extent.w, d.extent.h) == pytest.approx(1.8, abs=0.02)


def test_curves_are_sampled_to_polylines():
    svg = FixtureProvider().generate("leaf", {})
    d = svgnorm.sanitize_to_drawable(svg, target=1.8)
    assert d is not None
    # The leaf path (two cubics) + midrib line -> >=2 strokes, many points.
    assert len(d.strokes) >= 2
    assert sum(len(s.points) for s in d.strokes) >= 12


@pytest.mark.parametrize(
    "bad",
    [
        '<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script><rect width="9" height="9"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><image href="http://evil/x.png"/></svg>',
        "<svg><rect",  # malformed
        '<svg xmlns="http://www.w3.org/2000/svg"></svg>',  # empty -> quality gate
    ],
)
def test_unsafe_or_empty_svg_is_rejected(bad):
    assert svgnorm.sanitize_to_drawable(bad) is None


# --------------------------------------------------------------------------- #
# Ladder integration
# --------------------------------------------------------------------------- #
def test_generated_concept_resolves_to_rung3():
    d = drawing.measure(_thing("s", "star"))
    assert d.rung == 3 and d.strokes


def test_unknown_concept_falls_through_to_backstop():
    d = drawing.measure(_thing("u", "definitely_not_a_fixture"))
    assert d.rung == 6 and d.label == "definitely_not_a_fixture"


def test_negative_cache_calls_provider_once(fresh_engine):
    for _ in range(3):
        drawing.measure(_thing("u", "no_such_concept"))
    assert fresh_engine.calls.get("no_such_concept") == 1, "provider re-called for a known miss"


def test_extent_honesty_on_generated(fresh_engine):
    t = _thing("s", "star")
    d = drawing.measure(t)
    from engine.contracts import Placement

    op = drawing.paint(t, Placement("s", 0.0, 0.0, d.extent.w, d.extent.h))
    err = invariants.extent_error(d.extent.w, d.extent.h, op.strokes, 1.0)
    assert err <= 0.10


# --------------------------------------------------------------------------- #
# Placeholder-then-swap (§6.1): never block, warm, swap
# --------------------------------------------------------------------------- #
def test_placeholder_then_swap():
    t = _thing("s", "star")
    placeholder = drawing.measure(t, generate=False)
    assert placeholder.rung == 6, "live path must not block on the provider"
    assert drawing.pregenerate(t), "background warm should produce a real drawable"
    swapped = drawing.measure(t, generate=False)
    assert swapped.rung == 3, "after warm, the next render swaps in the real drawable"


# --------------------------------------------------------------------------- #
# End-to-end scene with generated concepts
# --------------------------------------------------------------------------- #
def test_generated_scene_renders_and_holds_invariants():
    from engine.contracts import at, right_of

    star = _thing("star", "star")
    star.relations = (at("left"),)
    leaf = _thing("leaf", "leaf")
    leaf.relations = (right_of("star"),)
    r = render(Scene("gen", [star, leaf]), BOARD)
    rep = invariants.evaluate([star, leaf], r.placements, BOARD)
    assert rep.passes
    assert all(r.drawables[i].rung == 3 for i in ("star", "leaf"))
