"""QuickDraw sketch corpus — real human strokes for the live board.

Google's QuickDraw dataset (CC BY 4.0) holds 50M human drawings in 345
categories, stored as *stroke sequences* — which is exactly the live
board's native format: the renderer replays them stroke by stroke under
the pen tip, so a "cat" is drawn the way a person actually draws a cat.

We keep one good sample per category, lazily fetched (a few KB each — the
source files are huge NDJSON, but we stream and stop at the first good
drawing) and cached forever under backend/assets/sketches/. No network
after the first hit; fully offline once warmed.

Coordinates: QuickDraw is 0-255 with y DOWN; we normalize to board units,
centered, y UP, ~2.2 units tall.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import urllib.request
from pathlib import Path

SKETCH_DIR = Path(__file__).resolve().parent / "assets" / "sketches"
QD_URL = "https://storage.googleapis.com/quickdraw_dataset/full/simplified/{}.ndjson"

# Teaching-relevant QuickDraw categories (a curated slice of the 345).
CURATED = [
    "airplane",
    "apple",
    "banana",
    "bed",
    "bee",
    "bicycle",
    "bird",
    "book",
    "bridge",
    "bus",
    "butterfly",
    "cactus",
    "camera",
    "candle",
    "car",
    "cat",
    "chair",
    "clock",
    "cloud",
    "computer",
    "cow",
    "crab",
    "crocodile",
    "crown",
    "cup",
    "dog",
    "dolphin",
    "door",
    "dragon",
    "drums",
    "duck",
    "ear",
    "elephant",
    "envelope",
    "eye",
    "face",
    "fence",
    "fish",
    "flower",
    "fork",
    "frog",
    "giraffe",
    "grapes",
    "grass",
    "guitar",
    "hammer",
    "hand",
    "hat",
    "helicopter",
    "horse",
    "hospital",
    "hourglass",
    "house",
    "ice cream",
    "key",
    "knife",
    "ladder",
    "leaf",
    "light bulb",
    "lightning",
    "lion",
    "map",
    "megaphone",
    "monkey",
    "moon",
    "mountain",
    "mouse",
    "mushroom",
    "ocean",
    "octopus",
    "owl",
    "palm tree",
    "panda",
    "pencil",
    "penguin",
    "piano",
    "pig",
    "pizza",
    "rabbit",
    "rain",
    "rainbow",
    "river",
    "sailboat",
    "scissors",
    "shark",
    "sheep",
    "shoe",
    "skull",
    "snake",
    "snowflake",
    "snowman",
    "spider",
    "spoon",
    "star",
    "strawberry",
    "sun",
    "swan",
    "sword",
    "table",
    "telephone",
    "television",
    "tent",
    "tiger",
    "tornado",
    "tractor",
    "train",
    "tree",
    "truck",
    "turtle",
    "umbrella",
    "violin",
    "whale",
    "wheel",
    "windmill",
    "zebra",
]
# Common synonyms -> category names.
SKETCH_ALIASES = {
    "puppy": "dog",
    "kitten": "cat",
    "boat": "sailboat",
    "ship": "sailboat",
    "bike": "bicycle",
    "plane": "airplane",
    "bulb": "light bulb",
    "lamp": "light bulb",
    "phone": "telephone",
    "tv": "television",
    "storm": "lightning",
    "thunder": "lightning",
    "wave": "ocean",
    "sea": "ocean",
    "insect": "bee",
    "rat": "mouse",
    "bunny": "rabbit",
}


def _norm(name: str) -> str:
    n = (name or "").strip().lower().replace("_", " ").replace("-", " ")
    return SKETCH_ALIASES.get(n, n)


def _cache_path(cat: str) -> Path:
    return SKETCH_DIR / f"{cat.replace(' ', '_')}.json"


def _normalize(strokes: list) -> list:
    """QuickDraw [xs, ys] pairs (0-255, y down) -> board polylines, y up."""
    xs = [x for s in strokes for x in s[0]]
    ys = [y for s in strokes for y in s[1]]
    if not xs:
        return []
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1)
    k = 2.2 / span
    return [
        [
            [round((x - cx) * k, 3), round(-(y - cy) * k, 3)]
            for x, y in zip(s[0], s[1], strict=False)
        ]
        for s in strokes
    ]


def fetch_sketch(cat: str, timeout: float = 6.0) -> dict | None:
    """Stream the category file, keep the first clean drawing, cache it."""
    url = QD_URL.format(urllib.parse.quote(cat))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            for _ in range(60):  # a good one is almost always in the first few
                line = resp.readline()
                if not line:
                    break
                d = json.loads(line)
                n = len(d.get("drawing", []))
                if d.get("recognized") and 2 <= n <= 14:
                    data = {"name": cat, "strokes": _normalize(d["drawing"])}
                    SKETCH_DIR.mkdir(parents=True, exist_ok=True)
                    _cache_path(cat).write_text(json.dumps(data))
                    return data
    except Exception:
        return None  # offline or unknown category: caller falls back
    return None


def get_sketch(name: str) -> dict | None:
    """Cached sketch for `name` (lazy network fetch on first request)."""
    cat = _norm(name)
    p = _cache_path(cat)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    if cat in CURATED or cat in set(SKETCH_ALIASES.values()):
        return fetch_sketch(cat)
    # Not curated — still try once; QuickDraw may know it (404 is cheap).
    return fetch_sketch(cat)


def get_cached(name: str) -> dict | None:
    """Cache-only lookup — NO network. The v3 Drawing engine's rung-2 hot path."""
    p = _cache_path(_norm(name))
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def cached_names() -> list[str]:
    if not SKETCH_DIR.exists():
        return []
    return sorted(p.stem.replace("_", " ") for p in SKETCH_DIR.glob("*.json"))


def sketch_vocabulary() -> str:
    """One catalog line: what the model may simply name and get a drawing."""
    return ", ".join(CURATED)


def warm(names: list[str] | None = None) -> None:
    """Background-fetch a starter set so first lessons hit the cache."""
    todo = [c for c in (names or CURATED[:30]) if not _cache_path(_norm(c)).exists()]

    def _run():
        for c in todo:
            fetch_sketch(_norm(c))

    if todo:
        threading.Thread(target=_run, daemon=True).start()


if __name__ == "__main__":
    import sys

    for name in sys.argv[1:] or ["cat"]:
        s = get_sketch(name)
        print(name, "->", f"{len(s['strokes'])} strokes" if s else "not found")
