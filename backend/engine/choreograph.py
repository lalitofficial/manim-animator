"""The deterministic CHOREOGRAPHER (docs/ROADMAP-story-voice.md, Phase 3).

"Take the LLM out of choreography" (NOTEBOOK O1): given a Timeline whose narration carries
`[concept]` markers (§O6), re-time each named concept's DRAW — and a host point at it — to the
MARKER for the word that names it, so the picture appears AS it is spoken (draw-while-talking)
instead of all-drawn-then-narrated. Pure and deterministic; the marker TIMES themselves are
resolved later by the scheduler (a char-offset within the say, or a word boundary / audio
timestamp from the voice layer).

A no-op when there are no `[concept]` markers or choreography is off (whiteboard / calm) — the
degenerate timeline passes through unchanged, so the anti-rewrite guarantee is preserved.
"""

from __future__ import annotations

from dataclasses import replace

from engine.timeline import Timeline, TLEntry


def _draw_of(entries) -> dict[str, str]:
    """entity id -> the id of the draw entry that draws it (op.id == entity; connectors excluded)."""
    out: dict[str, str] = {}
    for e in entries:
        if e.kind == "draw":
            oid = (e.payload.get("op") or {}).get("id")
            if oid and oid not in out:
                out[oid] = e.id  # first draw of an entity wins (it's drawn once, at first mention)
    return out


def choreograph(tl: Timeline, *, cinematic: bool = True, host: str = "guide") -> Timeline:
    """Anchor each narrated concept's draw (+ a host point) to its `[concept]` marker.

    Concept draws become `at="m:<entity>"` and non-blocking, so they reveal DURING the narration
    at the moment their word is spoken (the scheduler resolves the marker time) instead of all
    drawing before the say. A host point at each concept is added on the character track, anchored
    to the same marker. Concepts with no on-board draw are skipped (drop-don't-repair)."""
    concept = [m for m in tl.markers if m.get("kind") == "concept" and m.get("entity")]
    if not cinematic or not concept:
        return tl  # nothing to choreograph -> degenerate timeline unchanged (anti-rewrite)

    draw_of = _draw_of(tl.entries)
    has_host = any(e.track == "character" for e in tl.entries)

    anchor: dict[str, str] = {}  # draw-entry id -> the (first) marker naming its entity
    for m in concept:
        did = draw_of.get(m["entity"])
        if did and did not in anchor:
            anchor[did] = m["name"]

    # 1) the named concept draws now overlap the narration, anchored to their word's marker.
    entries = [
        replace(e, at=anchor[e.id], blocking=False) if e.id in anchor else e for e in tl.entries
    ]

    # 2) the host points at each named concept (first mention), anchored to the same marker.
    points: list[TLEntry] = []
    if has_host:
        seen: set[str] = set()
        for m in concept:
            if m["entity"] in draw_of and m["name"] not in seen:
                seen.add(m["name"])
                points.append(
                    TLEntry(
                        id=f"pt_{m['name']}",
                        track="character",
                        kind="action",
                        blocking=False,
                        payload={"verb": "point", "id": host, "target": m["entity"]},
                        at=m["name"],
                        dur_ms=600,
                    )
                )
    return replace(tl, entries=tuple(entries) + tuple(points))
