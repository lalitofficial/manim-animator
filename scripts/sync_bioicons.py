#!/usr/bin/env python
"""Sync the Bioicons library into normalized COLORED candidate packs.

Shallow-clones github.com/duerrsimon/bioicons into a local cache (or reuses an existing
checkout via $BIOICONS_DIR), then parses every SVG — or just one subject domain's
categories — into board-unit colored strokes. Output lands in backend/engine/candidates/
as one pack per scientific category, each icon carrying its OWN license + author. Review +
publish through the Asset Studio gates to make them engine-drawable.

Usage:
    python scripts/sync_bioicons.py                 # all categories
    python scripts/sync_bioicons.py biology         # just biology's categories
    python scripts/sync_bioicons.py chemistry 20    # chemistry, max 20 icons/category
    BIOICONS_DIR=~/src/bioicons python scripts/sync_bioicons.py   # reuse a local clone
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from engine import asset_registry, bioicons, candidates_store  # noqa: E402

REPO = "https://github.com/duerrsimon/bioicons"


def _checkout() -> pathlib.Path:
    """A local Bioicons checkout: reuse $BIOICONS_DIR if it has the icons, else shallow-clone."""
    env = os.environ.get("BIOICONS_DIR")
    cache = pathlib.Path(env) if env else pathlib.Path("data/bioicons")
    if (cache / "static" / "icons").exists():
        return cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    print(f"Cloning {REPO} → {cache} (shallow)…", flush=True)
    subprocess.run(["git", "clone", "--depth", "1", REPO, str(cache)], check=True)
    return cache


def main() -> None:
    args = sys.argv[1:]
    domain = next((a for a in args if a in bioicons.DOMAIN_CATEGORIES), None)
    limit = next((int(a) for a in args if a.isdigit()), None)
    root = _checkout()

    def progress(done: int, total: int, name: str) -> None:
        print(f"  [{done:>2}/{total}] {name}", flush=True)

    print(f"Importing Bioicons ({domain or 'all categories'}) → candidate packs…")
    if domain:
        res = bioicons.import_domain(root, domain, limit_per_category=limit, progress=progress)
    else:
        res = bioicons.import_tree(root, limit_per_category=limit, progress=progress)
    asset_registry.refresh()
    s = candidates_store.stats()
    print(
        f"\nDONE — {res['categories']} categories, {res['items']} items, "
        f"{res['renderable']} renderable.\n"
        f"Store now holds {s['count']} candidates across {s['packs']} packs.\n"
        f"Review + publish them in the Asset Studio (/asset-studio)."
    )


if __name__ == "__main__":
    main()
