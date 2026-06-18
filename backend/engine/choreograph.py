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


def _op_center(op: dict) -> tuple[float, float] | None:
    """The board-space center of a draw op (bbox midpoint of its strokes; else its label)."""
    xs: list[float] = []
    ys: list[float] = []
    for s in op.get("strokes") or []:
        for pt in s.get("points") or []:
            xs.append(pt[0])
            ys.append(pt[1])
    if xs:
        return (round((min(xs) + max(xs)) / 2, 3), round((min(ys) + max(ys)) / 2, 3))
    lp = op.get("label_pos")
    return (lp[0], lp[1]) if lp else None


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

    # 3) the CAMERA follows the narrated concept: a gentle pan/zoom to each, anchored to its
    # marker (Phase 6). Non-blocking — the scheduler supersedes an in-flight move, so it reads
    # as a follow. cinematic-gated (the still/calm board stays a wide static frame).
    cams = _follow_cameras(tl, entries, anchor) if cinematic else []
    return replace(tl, entries=tuple(entries) + tuple(points) + tuple(cams))


def _follow_cameras(tl: Timeline, entries: list[TLEntry], anchor: dict[str, str]) -> list[TLEntry]:
    """A gentle camera focus on each anchored concept, anchored to its marker. The focus window
    is a soft ~62% zoom (a follow, not a tight crop), clamped on-board."""
    board = tl.meta.get("board") or {"w": 14.0, "h": 8.0}
    bw, bh = float(board["w"]), float(board["h"])
    vw = round(bw * 0.62, 3)
    vh = round(vw * bh / bw, 3)
    mx, my = bw / 2 - vw / 2, bh / 2 - vh / 2  # max center offset that keeps the window on-board
    cams: list[TLEntry] = []
    seen: set[str] = set()
    for e in entries:
        if e.id not in anchor or anchor[e.id] in seen:
            continue
        center = _op_center(e.payload.get("op") or {})
        if center is None:
            continue
        seen.add(anchor[e.id])
        cx = max(-mx, min(mx, center[0]))
        cy = max(-my, min(my, center[1]))
        cams.append(
            TLEntry(
                id=f"cam_{anchor[e.id]}",
                track="camera",
                kind="camera",
                blocking=False,
                payload={"x": round(cx, 3), "y": round(cy, 3), "w": vw, "h": vh, "ms": 650},
                at=anchor[e.id],
                dur_ms=650,
            )
        )
    return cams
