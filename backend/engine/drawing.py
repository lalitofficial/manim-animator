"""Engine 3 — Drawing: measure / paint (ARCHITECTURE §5).

Phase 2 = the DETERMINISTIC rungs of the resolution ladder (§5.3):
  rung 1  parametric shapes (circle/square/rect/triangle/dot)
  rung 1  text (sized by a font metric)
  rung 6  labeled-box backstop — never fails

measure() resolves a Thing to a LOCAL Drawable (cached by concept+geometry_attrs,
color-independent); paint() places it into board space as a DrawOp. The generative
rungs 3-5 (LLM-SVG / StarVector / DiffSketcher) plug in later behind the same seam.
"""

from __future__ import annotations

from dataclasses import replace

from engine import catalog, character, generators, icons, palette, svgnorm
from engine import geometry as g
from engine.contracts import Drawable, DrawOp, Extent, Placement, Stroke, Thing

DEFAULT_COLOR = "#e6edf3"
_CHAR_W = 0.32  # board units per char at font height 1.0 (rough metric)
_PAD = 0.4

# Concept aliases -> canonical parametric shape.
_ALIASES = {
    "box": "rect",
    "rectangle": "rect",
    "dot": "dot",
    "square": "square",
    "circle": "circle",
    "triangle": "triangle",
}

_cache: dict[tuple, Drawable] = {}
_negative: set[tuple] = set()  # cache keys known to fall through to backstop (don't re-call)
_provider: generators.SvgProvider | None = None
_sketch_lookup = None  # rung 2: concept -> QuickDraw sketch dict (cache-only)
_compose = icons.compose  # composable-icon resolver (tests can swap it out)
_catalog_lookup = catalog.lookup  # Tabler line-icon catalog (concept -> SVG)
_GEN_TARGET = 1.8  # board-unit size a generated drawable is normalized to


def set_compose(fn) -> None:
    """Inject the composable-icon resolver (tests pass a no-op to isolate a rung)."""
    global _compose
    _compose = fn if fn is not None else icons.compose


def set_catalog_lookup(fn) -> None:
    """Inject the Tabler catalog lookup (tests pass a no-op to isolate a rung)."""
    global _catalog_lookup
    _catalog_lookup = fn if fn is not None else catalog.lookup


def set_provider(p: generators.SvgProvider | None) -> None:
    """Inject the SVG provider (tests use a fixture/counting provider)."""
    global _provider
    _provider = p


def _none_lookup(name: str):
    return None


def set_sketch_lookup(fn) -> None:
    """Inject the rung-2 sketch lookup (tests pass a fake or a no-op)."""
    global _sketch_lookup
    _sketch_lookup = fn


def _get_sketch_lookup():
    global _sketch_lookup
    if _sketch_lookup is None:
        try:
            import sketches  # the QuickDraw human-stroke library (board-unit strokes)

            _sketch_lookup = sketches.get_cached
        except Exception:
            _sketch_lookup = _none_lookup
    return _sketch_lookup


def _get_provider() -> generators.SvgProvider:
    global _provider
    if _provider is None:
        _provider = generators.default_provider()
    return _provider


def reset() -> None:
    """Clear the in-process caches (provisional cache + negative cache)."""
    _cache.clear()
    _negative.clear()


def _norm(concept: str) -> str:
    c = concept.strip().lower()
    return _ALIASES.get(c, c)


def _key(thing: Thing, style: str = "whiteboard") -> tuple:
    # geometry_attrs are part of the key; paint_attrs (color) are NOT (§2). style is in
    # the key because cartoon skips the line-catalog rung (so the resolution differs).
    return (_norm(thing.concept), tuple(sorted(thing.geometry_attrs.items())), style)


def measure(thing: Thing, generate: bool = True, style: str = "whiteboard") -> Drawable:
    """Resolve a Thing through the ladder (§5.3) to a local Drawable.

    Deterministic rungs (parametric/text) resolve inline. For everything else we
    try the live generative rung (3) — sanitized SVG — then fall to the rung-6
    labeled-box backstop. `generate=False` is the live-board PLACEHOLDER path
    (§6.1): return the backstop instantly, never block on the provider; a
    background `pregenerate()` warms the cache and the next render swaps it in.

    Successful resolutions are cached (provisional); the backstop is NOT cached,
    so a later pregenerate can swap it.
    """
    k = _key(thing, style)
    cached = _cache.get(k)
    if cached is not None:
        return cached

    # Bundle gate (non-breaking): only consulted when a bundle is actually disabled, so
    # the default all-enabled runtime is byte-identical. A concept whose owning bundle is
    # off falls to the labeled-box backstop instead of resolving its asset. PUBLISHED
    # imported candidates are exempt — publishing is the explicit "make it drawable" act.
    from engine import bundles, candidates_store

    if (
        bundles.any_disabled()
        and not bundles.concept_enabled(thing.concept)
        and not candidates_store.is_published(thing.concept)
    ):
        return _backstop(thing.concept)

    local = _resolve_local(thing)  # rung 1 (parametric, text)
    if local is not None:
        _cache[k] = local
        return local

    char = _character(thing)  # the parameterized presenter rig (pose + expression)
    if char is not None:
        _cache[k] = char
        return char

    icon = _icon(thing)  # the visual LANGUAGE — composed from primitives (preferred)
    if icon is not None:
        _cache[k] = icon
        return icon

    # Line-icon catalog (Lucide): great for whiteboard, but a UI icon breaks a cartoon
    # FILM — so cartoon skips it and falls to the designed concept card instead.
    cat = _catalog(thing) if style != palette.CARTOON else None
    if cat is not None:
        _cache[k] = cat
        return cat

    sketch = _sketch(thing)  # QuickDraw human strokes — specific catalog object
    if sketch is not None:
        _cache[k] = sketch
        return sketch

    pub = _published(thing)  # a PUBLISHED imported icon — low rung, fills a coverage gap
    if pub is not None:
        _cache[k] = pub
        return pub

    if generate and k not in _negative:  # negative cache forks per (concept, geometry, STYLE)
        gen = _try_generate(thing)
        if gen is not None:
            _cache[k] = gen  # provisional cache
            return gen
        _negative.add(k)  # don't re-call the provider for a known miss (this style)

    return _backstop(thing.concept)  # placeholder — intentionally not cached


def pregenerate(thing: Thing, style: str = "whiteboard") -> bool:
    """Warm the cache for a long-tail concept (the async step behind the placeholder-then-
    swap). Returns True if a real (rung 3) drawable was cached. `style` must match the render
    style — the cache key forks on it, so warming whiteboard doesn't satisfy a cartoon render."""
    k = _key(thing, style)
    existing = _cache.get(k)
    if existing is not None and existing.rung != 6:
        return True
    gen = _try_generate(thing)
    if gen is not None:
        _cache[k] = gen
        _negative.discard(k)
        return True
    _negative.add(k)
    return False


def _try_generate(thing: Thing) -> Drawable | None:
    svg = _get_provider().generate(thing.concept, thing.geometry_attrs)
    if not svg:
        return None
    target = float(thing.geometry_attrs.get("size", _GEN_TARGET))
    d = svgnorm.sanitize_to_drawable(svg, target=target)  # quality-gated inside
    return replace(d, source="generated") if d is not None else None


def _catalog(thing: Thing) -> Drawable | None:
    """Tabler catalog (MIT) — look up the concept's SVG and flatten it via svgnorm."""
    svg = _catalog_lookup(thing.concept)
    if not svg:
        return None
    target = float(thing.geometry_attrs.get("size", 2.0))
    d = svgnorm.sanitize_to_drawable(svg, target=target)
    return replace(d, source="catalog") if d is not None else None


def _character(thing: Thing) -> Drawable | None:
    """The presenter rig — a parameterized cartoon character (character.py). Pose +
    expression ride in geometry_attrs, so each variant caches separately and the
    SAME character stays consistent across a lesson."""
    if not character.is_character(thing.concept):
        return None
    ga = thing.geometry_attrs
    # The CONCEPT selects the cast ROLE (teacher/scientist/…); presenter/guide → default.
    # turn/facing/head overrides (e.g. the host LOOKING toward a target) ride in geometry_attrs.
    look = {k: float(ga[k]) for k in ("turn", "facing", "head") if k in ga}
    pose = (
        character.posed(str(ga.get("pose", "idle")), **look)
        if look
        else str(ga.get("pose", "idle"))
    )
    strokes = character.build(
        pose=pose,
        expression=str(ga.get("expression", "happy")),
        theme=ga.get("theme"),
        character=str(ga.get("role") or thing.concept),
    )
    if not strokes:
        return None
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    span = max(x1 - x0, y1 - y0, 1e-6)
    target = float(ga.get("size", 2.8))
    strokes = g.transform(strokes, 0.0, 0.0, target / span)
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    return Drawable(
        strokes=strokes,
        extent=Extent(round(x1 - x0, 4), round(y1 - y0, 4)),
        rung=1,
        source="character",
    )


def _published(thing: Thing) -> Drawable | None:
    """A PUBLISHED imported candidate (Excalidraw icon), normalized to board strokes.
    Resolves LOW (after icon/catalog/sketch) so it only fills gaps, never shadows a
    cartoon asset — and keyed by the candidate's unique id, so plain lesson nouns never
    accidentally hit a technical diagram icon."""
    from engine import candidates_store

    strokes = candidates_store.published_strokes(thing.concept)
    if not strokes:
        return None
    # Keep the imported look: a CLOSED shape with no fill is an OUTLINE — render it as a
    # visually-closed open path so cartoon paint() doesn't tint-fill it. Filled shapes and
    # colored strokes are preserved as-is (the whole point of importing with color).
    strokes = tuple(
        replace(s, closed=False, points=(*s.points, s.points[0]))
        if (s.closed and not s.fill and s.points)
        else s
        for s in strokes
    )
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    span = max(x1 - x0, y1 - y0, 1e-6)
    target = float(thing.geometry_attrs.get("size", 2.0))
    strokes = g.transform(strokes, 0.0, 0.0, target / span)
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    return Drawable(
        strokes=strokes,
        extent=Extent(round(x1 - x0, 4), round(y1 - y0, 4)),
        rung=1,
        source="published",
    )


def _icon(thing: Thing) -> Drawable | None:
    """The visual language — compose the concept from primitives (icons.py)."""
    strokes = _compose(thing.concept)
    if not strokes:
        return None
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    span = max(x1 - x0, y1 - y0, 1e-6)
    target = float(thing.geometry_attrs.get("size", 2.0))
    strokes = g.transform(strokes, 0.0, 0.0, target / span)
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    return Drawable(
        strokes=strokes,
        extent=Extent(round(x1 - x0, 4), round(y1 - y0, 4)),
        rung=1,
        source="icon",
    )


def _sketch_candidates(concept: str) -> list[str]:
    """Normalize an LLM-named concept toward a QuickDraw category: underscores ->
    spaces, drop leading articles, a naive singular. (carbon_dioxide, the_sun, cats.)"""
    c = concept.strip().lower().replace("_", " ").replace("-", " ")
    out = [c]
    for art in ("the ", "a ", "an "):
        if c.startswith(art):
            out.append(c[len(art) :])
    base = out[-1]
    if base.endswith("s") and len(base) > 3:
        out.append(base[:-1])
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _sketch(thing: Thing) -> Drawable | None:
    """Rung 2 — a real human-stroke drawing from the QuickDraw library, scaled to
    a target size. Cache-only/offline; ~110 categories (cat, cloud, tree, …)."""
    lookup = _get_sketch_lookup()
    data = None
    for name in _sketch_candidates(thing.concept):
        d = lookup(name)
        if d and d.get("strokes"):
            data = d
            break
    if data is None:
        return None
    raw = tuple(
        Stroke(tuple((float(p[0]), float(p[1])) for p in poly))
        for poly in data["strokes"]
        if isinstance(poly, list) and len(poly) >= 2
    )
    if not raw:
        return None
    x0, y0, x1, y1 = g.strokes_bbox(raw)
    span = max(x1 - x0, y1 - y0, 1e-6)
    target = float(thing.geometry_attrs.get("size", 2.2))
    raw = g.transform(raw, 0.0, 0.0, target / span)  # scale about the origin (already centered)
    x0, y0, x1, y1 = g.strokes_bbox(raw)
    return Drawable(
        strokes=raw, extent=Extent(round(x1 - x0, 4), round(y1 - y0, 4)), rung=2, source="sketch"
    )


def _resolve_local(thing: Thing) -> Drawable | None:
    c = _norm(thing.concept)
    ga = thing.geometry_attrs
    if c == "circle":
        return _from_strokes([g.circle(float(ga.get("radius", 0.7)))], rung=1)
    if c == "dot":
        return _from_strokes([g.circle(float(ga.get("radius", 0.12)))], rung=1)
    if c == "square":
        s = float(ga.get("size", 1.4))
        return _from_strokes([g.rectangle(s, s)], rung=1)
    if c == "rect":
        return _from_strokes(
            [g.rectangle(float(ga.get("w", 1.8)), float(ga.get("h", 1.0)))], rung=1
        )
    if c == "triangle":
        return _from_strokes([g.triangle(float(ga.get("w", 1.6)), float(ga.get("h", 1.4)))], rung=1)
    if c == "text":
        return _text(str(ga.get("text", "")), float(ga.get("font", 0.5)))
    return None


def _from_strokes(
    strokes, rung: int, label: str | None = None, source: str = "primitive"
) -> Drawable:
    x0, y0, x1, y1 = g.strokes_bbox(strokes)
    return Drawable(
        strokes=tuple(strokes),
        extent=Extent(round(x1 - x0, 4), round(y1 - y0, 4)),
        rung=rung,
        source=source,
        label=label,
    )


def _text(text: str, font: float) -> Drawable:
    w = max(len(text) * _CHAR_W * font, 0.5)
    h = font * 1.4
    # Text has no outline strokes; the board renders the glyphs. Extent = metric.
    return Drawable(
        strokes=(), extent=Extent(round(w, 4), round(h, 4)), rung=1, source="primitive", label=text
    )


def _backstop(concept: str) -> Drawable:
    """The long-tail fallback — a DESIGNED concept card (not a gray box): a rounded
    panel tinted with the concept's palette color + a small accent dot + the label.
    Whiteboard strips the color to a mono card; it stays honest (source='box', so the
    Studio still counts it as a placeholder) but reads as intentional, not generic."""
    label = concept.strip()
    w = max(len(label) * _CHAR_W * 0.5 + _PAD, 1.6)  # same footprint as the old box
    h = 1.0
    fill, line = palette.concept_colors(concept)
    body = replace(g.rounded_rect(w, h, 0.16), fill=palette.tint(fill, 0.78), color=line)
    dot = g.transform([g.circle(0.1)], -w / 2 + 0.28, h / 2 - 0.28, 1.0)[0]
    dot = replace(dot, fill=fill, color=line)
    return _from_strokes([body, dot], rung=6, label=label, source="box")


def paint(
    thing: Thing,
    placement: Placement,
    drawable: Drawable | None = None,
    style: str = palette.WHITEBOARD,
    scene: str | None = None,
) -> DrawOp:
    """Place a Drawable into board space (translate + scale) as a DrawOp.

    `style` is the render-time color decision (docs/CARTOON.md): whiteboard leaves
    strokes mono (unchanged); cartoon fills closed shapes + outlines them via the
    palette. Color is applied HERE, not in measure(), so geometry stays cacheable.
    """
    d = drawable or measure(thing, style=style)
    board_strokes = g.transform(d.strokes, placement.x, placement.y, placement.scale)
    board_strokes = palette.apply(board_strokes, style, thing.concept)
    cartoon = style == palette.CARTOON
    pa = thing.paint_attrs
    # Motion: explicit beat hints win; otherwise cartoon derives a tasteful default
    # from the concept (characters bob/rise, sky props float), whiteboard stays still.
    entrance = pa.get("entrance") or (palette.entrance_for(thing.concept) if cartoon else "draw")
    ambient = pa.get("ambient") or (palette.ambient_for(thing.concept) if cartoon else "")
    is_char = cartoon and d.source == "character"  # the rig paints on top (z=3), any role
    return DrawOp(
        thing_id=thing.id,
        kind="draw",
        strokes=board_strokes,
        length=round(g.total_length(board_strokes), 4),
        color=palette.op_color(style, thing.concept, pa.get("color"), scene),
        fill=bool(d.fill) or any(s.fill for s in board_strokes),
        label=d.label,
        label_pos=(placement.x, placement.y) if d.label else None,
        rung=d.rung,
        source=d.source,
        z=int(pa.get("z", 3 if is_char else 1)),
        entrance=str(entrance),
        ambient=str(ambient),
    )
