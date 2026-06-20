#!/usr/bin/env python
"""Sync EVERY Excalidraw library into normalized candidate packs.

Pulls all published libraries (libraries.json), fetches each `.excalidrawlib` once, and
parses every item's COORDINATES into board-unit strokes (svgnorm). Output lands in
backend/engine/candidates/ as one pack per library — surfaced in the Asset Studio under
the disabled-by-default `imported` bundle.

Usage:
    python scripts/sync_excalidraw.py            # all libraries
    python scripts/sync_excalidraw.py 10         # first 10 (a quick smoke run)
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "backend"))

from engine import (
    asset_registry,  # noqa: E402
    candidates_store,  # noqa: E402
)
from engine import excalidraw_libraries as ex  # noqa: E402


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None

    def progress(done: int, total: int, name: str) -> None:
        print(f"  [{done:>3}/{total}] {name}", flush=True)

    print(f"Syncing {limit if limit else 'all'} Excalidraw libraries → candidate packs…")
    res = ex.sync_all(progress=progress, limit=limit, refresh=True)
    asset_registry.refresh()
    s = candidates_store.stats()
    print(
        f"\nDONE — {res['libraries']} libraries ({res['failed']} failed), "
        f"{res['items']} items, {res['renderable']} renderable.\n"
        f"Store now holds {s['count']} candidates across {s['packs']} packs."
    )


if __name__ == "__main__":
    main()
