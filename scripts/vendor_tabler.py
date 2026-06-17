"""Vendor Tabler outline icons (MIT) + build an alias index from their tags.

Fetches a curated set of teaching concepts from the Tabler GitHub raw, saves the
SVGs to backend/engine/assets/tabler/, and writes index.json {alias -> name} from
each icon's `tags:` comment. Run: PYTHONPATH=backend python build/vendor_tabler.py
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

RAW = "https://raw.githubusercontent.com/tabler/tabler-icons/main/icons/outline/{}.svg"
DEST = Path("backend/engine/assets/tabler")
DEST.mkdir(parents=True, exist_ok=True)

# Curated teaching concepts (Tabler outline filenames). Names that 404 are skipped.
CANDIDATES = [
    "book",
    "books",
    "car",
    "rocket",
    "battery",
    "bulb",
    "atom",
    "flask",
    "microscope",
    "telescope",
    "dna",
    "heart",
    "brain",
    "lungs",
    "bone",
    "eye",
    "ear",
    "clock",
    "hourglass",
    "key",
    "lock",
    "scissors",
    "hammer",
    "ruler",
    "pencil",
    "flag",
    "coin",
    "building",
    "building-bank",
    "bell",
    "umbrella",
    "anchor",
    "compass",
    "world",
    "map",
    "plane",
    "bus",
    "train",
    "ship",
    "sailboat",
    "bike",
    "camera",
    "music",
    "microphone",
    "phone",
    "mail",
    "calendar",
    "trophy",
    "gift",
    "magnet",
    "temperature",
    "ladder",
    "tools",
    "settings",
    "scale",
    "chart-bar",
    "chart-line",
    "bolt",
    "fish",
    "bird",
    "cat",
    "dog",
    "bug",
    "butterfly",
    "snowflake",
    "droplet",
    "flame",
    "wind",
    "cloud-rain",
    "rainbow",
    "leaf",
    "apple",
    "egg",
    "seeding",
    "wheel",
    "engine",
    "gas-station",
    "road",
    "bridge",
    "wallet",
    "shield",
    "sword",
    "palette",
    "ball-football",
    "run",
    "walk",
    "heartbeat",
    "virus",
    "pill",
    "stethoscope",
    "vaccine",
    "molecule",
    "math",
    "calculator",
    "abacus",
    "test-pipe",
]

TAGS_RE = re.compile(r"tags:\s*\[([^\]]*)\]")
SAVED = {}
for name in dict.fromkeys(CANDIDATES):
    try:
        with urllib.request.urlopen(RAW.format(name), timeout=15) as r:
            svg = r.read().decode("utf-8")
    except Exception:
        continue
    if "<svg" not in svg or "<path" not in svg:
        continue
    (DEST / f"{name}.svg").write_text(svg)
    tags = []
    m = TAGS_RE.search(svg)
    if m:
        tags = [t.strip().strip('"').lower() for t in m.group(1).split(",") if t.strip()]
    SAVED[name] = tags

# Build alias -> name index. Exact filename + name-words win over tags.
index: dict[str, str] = {}
for name, tags in SAVED.items():
    for tag in tags:
        index.setdefault(tag, name)
for name in SAVED:  # names override tag collisions
    index[name] = name
    index[name.replace("-", " ")] = name

(DEST / "index.json").write_text(json.dumps(dict(sorted(index.items())), indent=0))
print(f"vendored {len(SAVED)}/{len(set(CANDIDATES))} Tabler icons, {len(index)} aliases -> {DEST}")
print("missing:", sorted(set(CANDIDATES) - set(SAVED)))
