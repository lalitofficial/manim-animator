"""Cartoon staging — semantic band routing (sky / mid / ground)."""

from __future__ import annotations

from engine import layout
from engine.contracts import Board, Extent, Thing


def test_band_routing():
    # weather / aerial → sky
    assert layout._band("cloud") == "sky"
    assert layout._band("sun") == "sky"
    # precipitation / vapor → mid (in transit between sky and ground: rising vapor, falling rain)
    for c in ("rain", "droplet", "vapor", "snow"):
        assert layout._band(c) == "mid"
    # abstract / science / body → mid (floats in the diagram middle, not on the ground)
    for c in ("atom", "heart", "gear", "dna", "cell", "brain"):
        assert layout._band(c) == "mid"
    # imported TECH ids → mid (a *technical* cloud must NOT drift into the weather sky)
    assert layout._band("azure cloud services cloud") == "mid"
    assert layout._band("common home network basics server") == "mid"
    assert layout._band("aws architecture icons internet gateway") == "mid"
    # physical props → ground
    for c in ("tree", "house", "car", "mountain", "dog"):
        assert layout._band(c) == "ground"


def test_three_band_scene_stacks_top_to_bottom():
    things = [
        Thing(id="sun", concept="sun", extent=Extent(2, 2)),
        Thing(id="atom", concept="atom", extent=Extent(2, 2)),
        Thing(id="house", concept="house", extent=Extent(2, 2)),
    ]
    placements, _ = layout.compose_cartoon(things, Board())
    y = {p.id: p.y for p in placements}
    # sky above mid above ground
    assert y["sun"] > y["atom"] > y["house"]


def test_mid_props_float_above_ground_props():
    # in a mixed scene, abstract/tech props sit in the mid band, above the ground props
    things = [
        Thing(id="house", concept="house", extent=Extent(2, 2)),
        Thing(id="atom", concept="atom", extent=Extent(2, 2)),
        Thing(id="gear", concept="gear", extent=Extent(2, 2)),
    ]
    placements, _ = layout.compose_cartoon(things, Board())
    y = {p.id: p.y for p in placements}
    assert y["atom"] > y["house"] and y["gear"] > y["house"]


def test_mid_only_scene_uses_the_abstract_grid():
    # a purely abstract/tech scene (no sky, no ground) degrades to a centered grid
    things = [Thing(id=f"s{i}", concept="server", extent=Extent(2, 1)) for i in range(4)]
    placements, _ = layout.compose_cartoon(things, Board())
    assert len(placements) == 4  # all placed, never overlapping by construction
