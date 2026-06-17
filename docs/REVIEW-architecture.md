# Adversarial Design Review — ARCHITECTURE.md (2026-06-17)

Multi-agent review: 6 critic lenses → 44 findings → 28 verified real → prioritized fixes.
**Verdict: fundamentally sound, zero true blockers.** The recurring root cause: the doc stated
invariants ("overlap==0 by construction", "deterministic", "extent-honest", "relation-fidelity")
as *properties of a mechanism* but never specified the **independent, output-derived check** that
makes them testable — and an invariant you can't independently check is one a broken-but-stable
engine passes green. All fixes are doc-level; all land before the phase that depends on them.
The hardened spec is ARCHITECTURE.md v2; this file is the audit trail.

## A. Phase-1 pre-conditions (the ruler must be right before we build it)
- **A1. "overlap==0 by construction" → recomputed on output.** VPSC is a *bounded iterative*
  projection (today's `actions.py` literally `for _ in range(10)` then returns the capped, possibly
  overlapping result). Fix: recompute overlap from final Placements via a standalone AABB routine
  sharing no code with the solver; guarantee overlap==0 via **convergence-or-drop** (if a sweep
  fails to reduce overlap, drop the lowest-priority Thing); make hitting the cap a logged FAIL.
- **A2. Pin the determinism contract.** Cassowary resolves equal-strength conflicts by *add-order*;
  the doc never fixed ordering. Fix: §4.8 — sort Things by id, canonical relation order, sorted
  VPSC pair-visit + axis tie-break, **ban `set` in layout-affecting iteration**, pin kiwisolver
  version. Test = shuffle independent Beats → byte-identical Placements.
- **A3. Wire extent-honesty to a renderer; forbid bench self-certification.** Computing overlap from
  the *measured* Extent (as `bench_live.py` does from `approx_extent`) lets a measure that lies low
  show overlap==0 while real ink overflows. Fix: render headless → true ink bbox → `|measured−rendered|/rendered ≤ ε`
  (name ε); integration-bench overlap/on-board computed from the **rendered** bbox.

## B. Majors (by engine/phase)
- **B1. Connector ordering hole.** `measure→position→paint` can't express "arrow from A to B" — no
  Extent before placement. Fix: add a `Connector` Thing (bypasses measure & VPSC), a `connect(A,B)`
  Relation, and a **route** phase: `measure→position→route→paint`. (Today's `edge_points()` already does this post-layout; the new contract dropped it.)
- **B2. VPSC must be terminating + board-aware.** Include on-board walls in the separation (a naive
  push lands a box off-frame), alternate deterministic x/y sweeps (kill the axis-flip limit cycle),
  monotone overlap decrease or stop-and-drop.
- **B3. Flow placement isn't a Cassowary objective.** "minimize y then x (weak)" doesn't exist;
  untethered Things snap to one corner → VPSC scatters a blob that passes every gate. Fix: port
  `_flow_spot` as an explicit deterministic first-free-slot pre-pass *outside* the solver; add an L1
  case where ≥6 untethered Things must land in distinct reading-order rows.
- **B4. Tighten the relation→constraint table.** `near` (non-linear norm → weak soft eq below the
  side inequality), `between` (relaxable along the B–C line, not hard-midpoint), `on` (sequence
  offset, not identical x → overlap), `group_with` (define as row/column block).
- **B5. Streaming vs determinism.** kiwisolver edit-variables can't be `required` and incremental
  edit-suggest ≠ batch solve. Fix: freeze placed Things with `required` equalities (existing boxes
  never move); edit-vars only for transient near/flow; assert incremental==batch byte-for-byte.
- **B6. Drop-don't-repair must handle *collective* overflow + a drop order**, and coverage may be
  <100% by design (every drop logged, distinguishable from a bug).
- **B7–B9. The "geometry under-specified at the SVG boundary" cluster.** board.js has no
  dasharray/`<path>` — it's a canvas length-fraction renderer (`partialPolyline`); flatten SVG
  `<path>`→polylines at the sanitization boundary; flatten the transform stack into leaf geometry;
  classify stroke-only vs fill-with-outline **per-asset**; compute Extent/length *after* flattening.
- **B10. Live recognizability gate + provisional/permanent cache.** Rung-3 output currently writes
  straight to the forever-cache — one well-formed-but-wrong SVG persists. Add a structural quality
  filter; serve provisional (session) cache; promote to permanent only after the offline gate.
- **B11. Cache key = record, not bare tuple.** Normalize concept; split attrs into geometry-affecting
  (in key) vs paint-time (color/label, applied at paint); value carries generator_id + sanitizer_version
  + quality_score for invalidation; negative cache for rung-6 fall-through.
- **B12–B13. Benchmark governance.** Computable difficulty grading (features, not author labels);
  L3 must include conflicting/over-constrained cases; regression mints a frozen case. The
  "needs-generator set" must key off the **rung-hit axis** (concepts resolving only to rung-6 =
  coverage miss), not the invariants (rung-6 box passes all five).
- **B14. Validate the relation vocabulary before freezing it** (hand-compile 20–30 real topics to
  Beats, allowing new relations; seed the corpus from that). The corpus can't demand a relation it
  can't express, and Story (which would reveal gaps) runs last.

## D. Highest-leverage edits (all applied in v2)
1. §4.8 Determinism contract (A2, C4).
2. §4.4 terminating/board-aware/drop-backed + §4.7 overlap recomputed-on-output (A1, B2, B6).
3. §5.4 geometric-normalize pass + board-mechanism wording (B7, B8, B9, C5, C9).
4. Operational extent-honesty + no bench self-certification (A3, C2).
5. `Connector` Thing + `route` phase (B1, C1).

## E. Risks consciously accepted
- Self-intersecting paths under length-reveal (cosmetic pen-crossing, monotonic by arc length).
- Live-API latency vs PAPER saturation theorem — *not a contradiction*: streaming/cadence is Phase 6,
  rung-3 ships Phase 3, the two-scoreboard rule keeps block-time out of pass-rate. Only debt = the
  one-sentence cache-miss policy (added).
- StarVector/DiffSketcher build-health/latency — correctly deferred + gated to a Phase-4 local benchmark.
- "100% on L1–L3" authored by the grading team — residual after B12's computable grading; full
  third-party corpus needs Story (Phase 5), premature now.
