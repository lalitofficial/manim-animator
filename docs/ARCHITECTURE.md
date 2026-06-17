# Engine Architecture & Build Plan

The industry-level design for the three-engine rebuild. Grounded in [NOTEBOOK.md](../NOTEBOOK.md)
(why) and [RESEARCH-generative-drawing.md](RESEARCH-generative-drawing.md) (what exists).
**This is a design doc — no implementation yet.** Status: **v2, post adversarial review**
([REVIEW-architecture.md](REVIEW-architecture.md)) · 2026-06-17.

Guiding principles (from the notebook): geometry is deterministic; the model proposes *what*,
the solver decides *where*; the long tail is a *ladder*, not one model; benchmark with
machine-computable invariants; foundation (Drawing+Positioning) before Story.

**Review meta-lesson baked into v2:** every invariant (overlap, determinism, extent-honesty,
relation-fidelity) is specified with the **independent, output-derived check** that makes it
testable. "By construction" is banned as a guarantee — an invariant you can't recompute from the
output is one a broken-but-stable engine passes green.

---

## 1. Pipeline at a glance

```
Story ─Beats─▶ Drawing.measure ─Extents─▶ Positioning ─Placements─▶ route ─▶ Drawing.paint ─DrawOps─▶ board
(LLM, beats)   (resolve+size,            (kiwisolver +            (connectors   (length-reveal     (length-fraction
 no geometry)   rung ladder,              VPSC, deterministic,     drawn from     polylines +        reveal of flattened
                memoized)                 freeze-placed)           placements)    fill-fade)         polylines; no SVG DOM)
                      │                                                                  ▲
                      └────────────────── sanitization + geometric-normalize boundary ──┘
                         (LLM/VLM SVG validated, transforms flattened, paths→polylines; only intrinsic
                          geometry crosses; the model never sets on-board coordinates)
```

Build bottom-up (Drawing → Positioning → Story); run top-down. The seams are **frozen
contracts** so each engine is independently built, tested, optimized, and parallelized.
Note the four runtime stages: **measure → position → route → paint** (route added in v2 for
connectors, whose geometry only exists after their endpoints are placed).

---

## 2. Contracts (the frozen seams)

Design-level shapes (field lists, not code). These are the only things engines exchange.

- **Beat** — Story output. `{ kind, entities: [name], relation?: Relation, narration? }`.
  *No coordinates, no pixels.*
- **Thing** — a nameable drawable. `{ id, concept, geometry_attrs?, paint_attrs? }`.
  **attrs are split** (cache + paint correctness): `geometry_attrs` change the shape (and are part
  of the cache key); `paint_attrs` (color, opacity, label text) are applied at paint time to the
  same geometry — so a recolor/relabel never triggers a fresh generation.
- **Connector** — a Thing subtype for edges (`arrow`, `line`, `brace`). **Extent is undefined; it
  bypasses `measure` and the VPSC box pass**; its geometry is computed by `route` from its endpoints'
  Placements. Carries `{ id, from, to, kind, label? }`.
- **Extent** — `measure` output. `{ layout_bbox: {w,h}, ink_bbox: {w,h}, anchor }`. `layout_bbox` is
  what Positioning consumes; `ink_bbox` is the true rendered ink extent; `anchor` (`center`|`baseline`)
  defines how `(x,y)` maps to the box. Extent-honesty (§7) grades `layout_bbox` against `ink_bbox`.
- **Relation** — the spatial-intent vocabulary (Story↔Positioning seam). **Provisional set, to be
  validated before freezing (§10 task V0):** `at(region)`, `near(B,side)`, `on(B)`, `above/below/left_of/right_of(B)`,
  `between(B,C)`, `connect(A,B,kind,label?)`, `in_panel(p)`, `group_with([...])`, `emphasize`.
  Never encodes coordinates. (`connect` draws an edge — distinct from `between`, which only places a
  midpoint Thing.)
- **Placement** — Positioning output, **as data** (never a live solver reference):
  `{ id, x, y, w, h, scale, resolved: {side?, attach_points?, neighbors?} }`. The `resolved`
  artifacts let `route`/`paint` draw without re-querying the solver — keeping the engines decoupled.
- **DrawOp** — the stream the board eats: `add` / `play` / `say` / `clear`. Each drawable is a list
  of **board-unit polylines, each carrying its total arc length** for a length-parameterized reveal
  (board: length-fraction; Manim: `Create`/`stroke-dashoffset`). "Carries pathLength for dasharray"
  was wrong — see §5.2.

---

## 3. Engine 1 — Story (scoped out for now)

The LLM that turns a topic + mode into an ordered stream of **Beats** + narration. Deferred
(latency-de-prioritized, and untunable until the layer below is trustworthy). It emits Beats only —
no shapes, no coordinates. Until rebuilt, a **stub Story** (hand-written Beat sequences = the corpus
inputs, §7) drives the engines below so they can be built and benchmarked in isolation.

---

## 4. Engine 2 — Positioning (kiwisolver) · **FIRST BUILD**

A deterministic constraint solver. Adopt **kiwisolver** (Cassowary, BSD-3, pinned version).
Input: Things-with-Extents + Relations. Output: collision-free Placements.

### 4.1 Variables & hard constraints
- Per Thing: free vars `x, y` (placed via `anchor`), `scale`; `w, h` = `layout_bbox × scale` (constants).
- **On-board (required):** box within `[-W/2, W/2] × [-H/2, H/2]`, reserved title band `y < 2.5`.
- **Panel (required):** `in_panel(p)` clamps the box inside panel p's sub-rect.
- `required` constraints can **never** be edit-variables (kiwisolver raises `BadRequiredStrength`).

### 4.2 Relations → constraints (soft, prioritized)
| Relation | Constraint(s) |
|---|---|
| `at(region)` | `x==region.cx, y==region.cy` (strong) |
| `right_of(B)` | `x ≥ B.x + B.w/2 + w/2 + gap` (strong); symmetric for left/above/below |
| `near(B, side)` | side inequality (strong) **+** weak soft `x==B.x, y==B.y` *strictly below* the side strength (so the side wins) — no non-linear norm |
| `on(B)` | `y==B.y+B.h/2+h/2` (strong); `x` = `B.x + sequence_offset` (multiple `on` the same B tile, never identical x) |
| `between(B,C)` | seed `x==(B.x+C.x)/2, y==(B.y+C.y)/2` **relaxable along the B–C line** (so VPSC can slide it, not seed an overlap) |
| `connect(A,B)` | **not a box constraint** — a Connector, routed post-placement (§4.4 excludes it) |
| `group_with` | a mini row/column block: canonical member order, equal gap, shared baseline (medium) |
| flow (no relation) | **computed outside the solver** — see §4.3; Cassowary has no model of free space |

### 4.3 Priorities, flow, drop-don't-repair
Strength order: **required** (on-board, panel) ▸ **strong** (explicit relations) ▸ **medium**
(group) ▸ **weak** (near nudges). Cassowary relaxes soft conflicts by strength = graceful degradation.

- **Flow placement (the common case)** is *not* a solver objective — "minimize y then x" doesn't
  exist in Cassowary and would pile untethered Things in one corner. Instead a deterministic pre-pass
  scans the active panel top-down/left-right for the **first zero-overlap slot** given already-placed
  Things (port today's `_flow_spot`) and pins it as a weak anchor.
- **Drop-don't-repair** triggers on **two** cases: (a) a single Thing can't fit even alone (required
  infeasible); (b) **collective overflow** — VPSC can't separate everything (§4.4). Drop order is a
  deterministic total order: optional `Beat.priority`, else last-introduced-first, ties by larger area.
- **Coverage may be <100% by design** under over-subscription. Every drop is a **logged metric**
  (`{thing_id, reason}`) so a coverage miss is distinguishable from a bug (§7, §8).

### 4.4 Non-overlap — a terminating, board-aware, drop-backed procedure
Pairwise non-overlap is non-convex (OR of 4 separations) — outside LP. Port **CoLa's VPSC** as a
projection after the solve, specified (not "iterate to fixpoint"):
1. **Board-aware separation:** include the §4.1 on-board/panel walls as hard bounds in the separation
   QP, so a push can never land a box off-frame (on-board==100% and overlap==0 can't defeat each other).
2. **Order-stable:** alternate a deterministic **x-sweep then y-sweep** (not a per-pair min-axis pick,
   which limit-cycles). Connectors are excluded from this box pass.
3. **Terminating:** bounded iterations **and** require monotone non-increase of total overlap area per
   sweep. If a sweep fails to reduce overlap → **stop and drop** the lowest-priority Thing (§4.3), re-run.
   Dropping shrinks the problem until feasible, so the alternation always terminates.
4. Hitting the iteration cap **without** a successful drop is a logged FAIL, never a silent clamp.

### 4.5 Streaming (incremental == batch)
After each Beat, **freeze already-placed Things with `required` equalities** (`x==placed_x, y==placed_y`)
so later additions never move them (the teacher doesn't reshuffle what's drawn; mirrors today's
"existing boxes never move"). New Things solve against frozen predecessors → the incremental result
is deterministic and **equal to a batch solve in the same Beat order**. Edit-variables are reserved
strictly for transient `near`/`flow` nudges, never for `at/on/between` (which are `addConstraint` at
strong). §4.7 asserts incremental==batch byte-for-byte.

### 4.6 Why deterministic (settled)
Learned layout is *strictly weaker*: LaySPA (RL-trained) loses to constraint solvers on overlap
(0.0257 vs 0.0024). The model never emits coordinates.

### 4.7 Test surface (machine-computable, no model; checks are output-derived)
Feed synthetic Things+Relations → assert, **recomputing from the output, never from solver state**:
- **overlap == 0** — recomputed by a standalone AABB-intersection routine over final Placements
  expanded to boxes via *rendered* ink-bbox (§7), sharing no code with the placement/VPSC path.
- **on-board == 100%** — from rendered bbox; includes a `baseline`-anchored case.
- **relation-fidelity** — each relation checked as a **geometric predicate on final Placements**
  (`right_of(B) ⇒ x_A−w_A/2 ≥ x_B+w_B/2+gap`), evaluated *after* the VPSC pass.
- **flow reading-order** — ≥6 untethered Things land in distinct reading-order rows (not merely overlap==0).
- **incremental == batch** — each scene solved both ways, Placements diffed.
- **over-fill case** — a scene that forces the §4.4 cap proves the drop fallback fires and the
  surviving set still passes overlap==0 ∧ on-board==100%, with drop-count logged.

### 4.8 Determinism contract
The byte-identity gate is meaningless without fixed ordering. Required:
1. Sort Things by stable key (`id`) before emitting.
2. Emit each Thing's relations in canonical `Relation`-enum order.
3. VPSC visits overlapping pairs in sorted order with a deterministic axis tie-break (x, then lower id).
4. **No `set` in any layout-affecting iteration** (the existing `seg_ids - played` pattern is the anti-pattern).
5. Pin the kiwisolver version (§8).
Gate = **shuffle independent Beats → byte-identical Placements** (catches order-leak; stronger than a
bare 100×-rerun). Use byte-identity on one pinned reference platform/CI; allow ε-determinism + a
golden-layout regression (pinned expected Placements per case) across other platforms.

---

## 5. Engine 3 — Drawing (measure / paint + the generator ladder)

### 5.1 measure(Thing) → Extent
Resolve the Thing through the **ladder** (§5.3) to a drawable; return its honest Extent (board units).
Resolution is a **single memoized step** keyed by `(normalized_concept, geometry_attrs)` returning one
artifact `{drawable, Extent}`; `paint` must consume the *exact* artifact `measure` resolved; a generator
runs ≤once per key per run. Extent honesty is non-negotiable (a lie here becomes an overlap in Positioning).

### 5.2 paint(Thing, Placement) → DrawOps
Emit ops at the placed position. **Draw-on = length-parameterized reveal of flattened polylines.**
The board is a canvas length-fraction renderer (today's `partialPolyline`) — it has no SVG DOM and no
`stroke-dasharray`; SVG `<path>` assets are **flattened to polylines at the sanitization boundary**
(§5.4) and revealed by progressing each polyline's length fraction. `stroke-dasharray` is the *Manim/DOM*
detail (`SVGMobject` + `Create`), not a board mechanism. **Fills** (per the §5.4 per-asset classifier)
fade in *after* their outline polyline draws (hybrid), so it still reads as "drawn." Two backends, one
DrawOp stream; Manim shares the *contract*, not pixel-identical output.

### 5.3 The resolution ladder (the architecture of the long tail)
| # | Rung | Mode | Output | Notes |
|---|---|---|---|---|
| 0 | exact asset (catalog) | deterministic | vector | instant |
| 1 | parametric shape | deterministic | vector | circle/arrow/box/line |
| 2 | QuickDraw human stroke | deterministic | strokes | in-vocab, stroke-native |
| 3 | **frontier-LLM writes SVG** | **live** (see §6.1) | SVG→polylines | simple named subjects, sanitized, quality-gated |
| 4 | **StarVector / Mermaid** | offline | SVG→polylines | icons/diagrams/flowcharts → cache |
| 5 | **DiffSketcher / paid-raster→LIVE** | offline | strokes/vector | hard/photographic tail → cache |
| 6 | labeled box | deterministic | vector | never fails — the backstop |

Rungs 0–2, 6 exist today. Rung 3 is the only *live* generator (cache-miss policy: §6.1). Rungs 4–5 are
**offline-only** (minutes–hours/asset), feeding the forever-cache. No single model spans the tail.

### 5.4 Sanitization + geometric-normalize boundary (hard rule)
Any LLM/VLM SVG (rung 3, some of 4) passes this gate before it touches the engine:
1. **Sanitize:** parse → whitelist elements (`path,circle,rect,ellipse,line,polyline,polygon,g`) →
   strip `script/foreignObject/style url()` → bound the `viewBox`.
2. **Flatten transforms:** bake the full nested `<g transform>` stack into each leaf path's geometry in
   viewBox space (use svgpathtools/svgelements, not hand-rolled matrices). Read visual-bbox-affecting
   style (stroke-width) *before* stripping. "Never coords" means **on-board placement only** — within-asset
   geometry is authoritative here.
3. **Flatten to polylines:** convert `<path>`/curves to polylines at a fixed tolerance; split each
   `<path>` per `M`-subpath (atomic, orderable).
4. **Classify per-asset** (not globally): outline-native → stroke-only; fill-bearing silhouette →
   fill-with-outline; `evenodd` holes → stroke the outer contour, treat inner subpaths as cutouts.
5. **Compute Extent + per-polyline length *after* flattening.** This is what `measure` returns.

---

## 6. The generator subsystem (rungs 3–5)

### 6.1 Live generator (rung 3) — frontier-LLM-SVG
On a cache miss for a simple named subject:
- **Never block Positioning.** `measure()` returns the rung-6 reserved Extent immediately; `paint()`
  emits the labeled box now; the LLM call fires **async**; the generated drawable **hot-swaps** in on
  return (placeholder-then-swap). The seconds-scale API latency thus never violates the streaming promise.
- **Quality gate** (the operational meaning of "low quality → fall through"): a cheap structural filter
  — path count in range, ink-coverage bounds, ink-bbox fills the viewBox. Failing → keep the rung-6 box.
- **Provisional vs permanent cache:** a live generation serves the **current session** (provisional);
  it is **promoted to the permanent forever-cache only after the offline gate** (§6.2). One
  well-formed-but-wrong SVG must not persist forever. A **negative cache** records rung-6 fall-throughs
  so we don't re-pay the round-trip every request.
- **Cost policy:** rung 3 (paid frontier API) is behind an explicit opt-in; the **default live tier is
  free-local** (rungs 0–2 + rung-6 backstop), optionally a free-local rung-3a (gemma3/qwen, already wired).

### 6.2 Offline asset-generation pipeline (rungs 4–5) — a batch Workflow
Latency-irrelevant. Input = a **missing-concept queue** (benchmark failures + logged live cache-misses).
Per concept: route by subject type (icon/diagram → StarVector or Mermaid; no-photo sketch → DiffSketcher
or LLM-SVG; photographic → paid raster → diffvg/LIVE) → **validate** (well-formed, stroke-only-able,
path-count/quality gate, sane Extent, renders) → **order subpaths** for natural draw-on (enclosing-area
descending, then top-left — cheap, deterministic, latency-irrelevant) → **cache permanently** as
flattened polylines + Extent. Each generator is license-cleared (RESEARCH §6) and **gated on a local
latency benchmark** before adoption (StarVector latency is unverified). Generator racing for the Pareto
table uses a fixed seed, several samples/concept, CI on pass-rate, and two-run stability before adoption.

---

## 7. The benchmark harness (the ruler — built alongside Positioning)

Machine-computable, invariant-based, **output-derived** (no check reads engine-internal state).

- **Corpus** — fixed, versioned, difficulty-graded. **Inputs are structured Beats** (decided);
  interpretation (English→Beats) is the Story engine's separate, later benchmark; author so an English
  layer can compile to the *same* Beats. **Difficulty is computable** (features: #Things, #relations,
  has-conflict), not author-labelled. **L3 must include ≥1 conflicting/over-constrained case per relation
  kind.** Keep a held-out slice; **every layout bug mints a frozen case** at its computed level; log
  per-level case counts per corpus version.
- **Invariants** (all recomputed from output): **coverage** (every named entity drawn; logged drops
  distinguish design from bug), **overlap** (standalone AABB on rendered bbox, must be 0), **on-board**
  (rendered bbox), **relation-fidelity** (geometric predicate on final Placements, post-VPSC),
  **extent-honesty** (render each drawable headless → true ink bbox → `|measured−rendered|/rendered ≤ ε`,
  **ε = 0.10** to start).
- **Two scoreboards, never mixed** — accuracy first (freeze the bar, clear it), then speed.
- **Deterministic-first floor** — run the corpus through rungs 0–2, 6 only. The rung-6 box "never fails"
  the five invariants, so the **needs-generator set is defined on the rung-hit axis**: concepts that
  resolve *only to rung 6* = a coverage/sizing miss (the floor *sizes* generator need; it cannot *grade*
  recognizability — that's the deferred S4 LLM-judge).
- **Per-engine isolation** — Positioning bench (synthetic Things+Relations), measure bench (extent
  honesty), integration bench (the corpus). A regression points at one engine.

---

## 8. Cross-cutting

- **Cache** — key = `(normalized_concept, geometry_attrs)`; value = record
  `{polylines, extent, rung, generator_id, sanitizer_version, quality_score, created_at}`. `paint_attrs`
  (color/label) applied at paint, never in the key. **Provisional (session)** vs **permanent (promoted
  after offline gate)**. Invalidation = generator/sanitizer version or quality bump → lazy re-gen.
  Negative cache for rung-6 fall-throughs. Extends `backend/assets/`.
- **Licenses** — ship-clear: kiwisolver (BSD-3), QuickDraw (CC-BY-4.0, attribute Google), DiffSketcher
  (MIT), diffvg/LIVE (Apache-2.0), Mermaid (MIT), frontier-LLM SVG output (unencumbered). Verify before
  shipping: OmniSVG/DeTikZify/CLLMs weights. Hard-reject: CLIPasso, SDXL-Turbo, FLUX-dev.
- **Observability** — the telemetry/run-log wraps the pipeline: **rung-hit distribution** (the real
  hotpath signal now — where the deterministic core falls through), per-Thing **drop-reason**, generator
  latency/$, and the invariant scores per run.

---

## 9. Phased build plan (gates map to the success ladder)

Each phase ships independently and is gated by an output-derived benchmark number.

- **Phase 1 — Positioning + the ruler.** kiwisolver mapping (§4, incl. §4.4 procedure + §4.8 determinism
  contract) + the benchmark harness (§7) together, so Positioning is measured from day one.
  **Gate:** on a synthetic L1–L3 suite — overlap==0 (recomputed on output), on-board==100%,
  relation-fidelity==100%, flow reading-order holds, incremental==batch, and the over-fill case proves
  drop-fallback. *Maps toward S1-coherent.* **Pre-req: task V0 (§10) validates the Relation set first.**
- **Phase 2 — Drawing measure/paint, deterministic rungs (0–2, 6) + route/connectors.** measure→paint,
  length-reveal of flattened polylines, §5.4 geometric-normalize, the `route` phase. **Gate:** integration
  corpus L1–L3 passes all invariants deterministic-only; **extent-honesty `|measured−rendered|/rendered ≤ 0.10`**;
  connectors route correctly between placed endpoints.
- **Phase 3 — Live generator (rung 3) + sanitization + quality gate.** frontier-LLM-SVG with
  placeholder-then-swap and provisional cache. **Gate:** the **rung-hit distribution on L4 shifts off
  rung-6 toward rungs 0–5**, with the Pareto table (sampled, CI) recorded; the sanitizer rejects malformed SVG.
- **Phase 4 — Offline asset-gen pipeline (rungs 4–5).** Batch Workflow + validate + subpath-order + promote
  to permanent cache; local latency benchmark of StarVector/DiffSketcher. **Gate:** N hard concepts cached
  as clean vector; rung-hit distribution shifts further toward 0–2.
- **Phase 5 — Story emits Beats; wire end-to-end.** Replace the stub Story; full topic → board.
  **Gate:** end-to-end on the topic suite, invariants hold. *S1 across the suite.*
- **Phase 6 — Latency (S2 → S3).** Only now: re-introduce streaming/cadence work (F-section tricks).
  **Gate:** the PAPER SLOs, then the snappy bar.

---

## 10. Open questions & pre-Phase-1 tasks

- **V0 (do before freezing §2's Relation set, gates Phase 1).** Hand-compile 20–30 real English teaching
  topics down to Beats, *allowing new relations*; the set that emerges is the frozen vocabulary, and seeds
  the corpus. (The corpus can't demand a relation it can't express, and Story runs last — so validate now.
  Surfaces whether `align`/`stack`/`inside`/`contains`/`distribute` are needed beyond §2.)
- **Q1 — Corpus input format: DECIDED, structured Beats** (interpretation benchmarked separately, later).
- **Q2 — Stroke-only generation quality** — how often frontier-LLM-SVG yields a *recognizable* line-art
  asset vs needing fill/hybrid. Measure on L4 with the §6.2 perceptual-delta check; recognizability scoring
  is an offline-only VLM/CLIP judge, quarantined off the hot path.
- **Q3 — StarVector/DiffSketcher local latency & build health** — unverified; gate Phase 4 on a local benchmark.
