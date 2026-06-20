"""Per-concept semantic SIZE — the scale hierarchy of a scene.

Every icon used to default to 2.0 board units, so a cloud and a coin came out the same
size. Real scenes have hierarchy: a mountain dwarfs a person, a person dwarfs a coin.
`size_for(concept)` returns a relative board-unit size; the cartoon layout already applies
ONE scene scale across placed things, so these ratios are preserved on the board.

Purely advisory: an explicit `size` in a Thing's geometry_attrs always wins.
"""

from __future__ import annotations

DEFAULT = 2.0

# Tiered by real-world scale. A concept inherits a tier by exact match or word overlap.
_TIERS: dict[float, frozenset[str]] = {
    3.6: frozenset(
        {
            "mountain",
            "volcano",
            "building",
            "castle",
            "tower",
            "skyscraper",
            "mountains",
            "whale",
            "elephant",
            "dinosaur",
            "ship",
            "rocket",
            "planet",
            "earth",
            "sun",
            "moon",
            "rainbow",
            "galaxy",
            "ocean",
            "sea",
            "forest",
            "city",
            "factory",
            "dam",
            "bridge",
        }
    ),
    2.8: frozenset(
        {
            "tree",
            "house",
            "home",
            "cloud",
            "car",
            "bus",
            "truck",
            "train",
            "airplane",
            "plane",
            "boat",
            "lion",
            "bear",
            "horse",
            "cow",
            "giraffe",
            "robot",
            "dragon",
            "person",
            "people",
            "crowd",
            "dinosaur",
            "tractor",
            "windmill",
            "lighthouse",
            "rocketship",
        }
    ),
    # 2.0 is the implicit default tier (cat, dog, bird, fish, book, heart, brain, …)
    1.4: frozenset(
        {
            "apple",
            "banana",
            "orange",
            "leaf",
            "flower",
            "star",
            "key",
            "cup",
            "ball",
            "gear",
            "lightbulb",
            "bulb",
            "fruit",
            "mushroom",
            "egg",
            "shell",
            "clock",
            "lock",
            "phone",
            "candle",
            "feather",
            "snowflake",
            "stars",
        }
    ),
    0.95: frozenset(
        {
            "ant",
            "bee",
            "atom",
            "molecule",
            "cell",
            "seed",
            "drop",
            "raindrop",
            "droplet",
            "water",
            "coin",
            "button",
            "pebble",
            "crumb",
            "germ",
            "bacteria",
            "electron",
            "spark",
        }
    ),
}

# Flattened concept -> size, built once.
_SIZE: dict[str, float] = {c: s for s, group in _TIERS.items() for c in group}


def _norm(concept: str) -> str:
    return concept.strip().lower().replace("_", " ").replace("-", " ")


def size_for(concept: str, default: float = DEFAULT) -> float:
    """The semantic board-unit size for a concept, or `default`. Tries an exact match,
    then any word in a multi-word concept (so 'red apple' → apple's size)."""
    c = _norm(concept)
    if c in _SIZE:
        return _SIZE[c]
    for w in c.split():
        if w in _SIZE:
            return _SIZE[w]
    return default
