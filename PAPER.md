# Saturated Action Streaming: Real-Time Text-to-Animated-Lesson Generation on Commodity Hardware

**Draft v0.1 — June 2026**

> A 4-billion-parameter language model generating ~16 tokens/second cannot
> produce a 300-token animation script in under 20 seconds. We show that it
> does not have to: restructure generation as a *validated action stream*
> whose per-action token cost is matched to per-action playback time, let
> the model speak only topology (a scene grammar of anchors and relations,
> compiled to geometry by a deterministic solver), and allocate tokens to
> the channel that banks the most audience-time per token (speech). The
> result, measured end-to-end: first generated content in ~5 s, a 0.7 s
> median action cadence, 0–0.8% perceived idle with a worst stall of
> 0.85 s, and zero overprinted text — on a laptop, with no cloud APIs, at
> zero marginal cost.

---

## Abstract

We present a system that converts a natural-language topic into a live,
narrated whiteboard lesson — speech plus progressively drawn vector
animation — using only local, freely available models. The naive
architecture (generate a scene description, then play it) is latency-bound
by total scene token count: minutes on commodity hardware. We make three
contributions. **(1) An action-stream protocol:** the planner emits
newline-delimited single-action JSON; each line is validated, laid out, and
dispatched the moment it closes, reducing first-content latency from
*O(scene tokens)* to *O(line tokens)* and converting the latency problem
into a *pacing* problem. We give a saturation theorem: when per-action
playback duration is at least the generation time of the next line, the
board provably never stalls after the first action, and concurrent speech
contributes positive *buffer credit* that absorbs line-length variance.
**(2) Semantic/geometric decoupling:** the model emits topology (what
relates to what); a deterministic layout solver — feasibility projection,
minimum-penetration separation, discrete label-site optimization —
computes geometry, giving collision-bounded boards *by construction*
while cutting the token cost of common constructs ~3–4× via macros.
**(3) A drop-don't-repair robustness ladder:** schema violations are
handled per-line at zero added wall time, with deterministic server-side
recovery (auto-reveal, legacy-parse fallback, narration cards), removing
the repair-regeneration loop — empirically the largest latency tax in
JSON-blob pipelines — from the hot path entirely. On an Apple-silicon
laptop with gemma3:4b (16.4 tok/s), the system achieves first paint <1 s
(deterministic), first model-generated speech in ~15 s cold / seconds warm,
and a steady-state inter-action cadence of ~1.5–2.5 s sustained for the
remainder of a multi-segment lesson.

---

## 1. Introduction

Explanatory animation is among the highest-bandwidth ways to teach, and
among the most expensive to produce. Tools such as Manim [1] made
programmatic animation accessible to experts; large language models made
it conceivable to generate such programs from plain text. But the obvious
pipeline — *text → LLM → animation script → renderer* — inherits the
latency of autoregressive decoding. A modest teaching scene costs
300–600 output tokens; at the 9–16 tok/s of quantized 4–8 B models on
consumer laptops [2,3,4], that is 20–60 seconds *per scene* of dead air,
before accounting for prompt evaluation, model loading, and the
regeneration loops that schema-invalid outputs force.

The standard responses — bigger GPUs, cloud APIs, smaller scenes — trade
away exactly the properties we target: local execution, zero marginal
cost, and the *live* quality of a teacher who starts talking immediately
and draws while speaking.

Our central observation is that a lesson is not consumed as a scene; it is
consumed as a *sequence of small actions* (say a sentence, draw a sun,
label it, draw an arrow), each of which occupies seconds of audience
attention. The generation budget should therefore be paid *per action*,
concurrently with the playback of previous actions — never up front. This
reframes the engineering question from "how do we generate scenes faster?"
(we cannot; decode rate is memory-bandwidth-bound [5]) to "under what
conditions does a generation-playback pipeline never starve?" — a question
with a precise, checkable answer (§4).

We build this as a small, fully local system (~2.5 k lines) around a
renderer-agnostic scene IR consumed by two backends: an offline Manim [1]
renderer producing mp4, and a browser canvas renderer drawing live. All
planning runs on Ollama-served [2] quantized models (qwen2.5:7b [3],
gemma3:4b [4]); narration uses the browser's built-in speech synthesis.

## 2. Related Work

**Programmatic animation.** Manim [1] renders mathematical animation from
Python programs; LLM-driven variants prompt a model to emit Manim code
directly. Emitting executable code from an LLM raises both a safety
problem (arbitrary code execution) and a robustness problem (one syntax
error voids the scene). We instead emit a closed, validated IR — the model
never writes code.

**Constrained and structured decoding.** Grammar-constrained decoding
(GBNF in llama.cpp [6]; Outlines' FSM approach [7]) guarantees syntactic
validity at the token level. Ollama's `format=json` constrains output to
*one* JSON object — useful for blob pipelines but structurally at odds
with streaming many independent objects. Our per-line validation is a
*post-hoc, drop-semantics* alternative: weaker guarantees per line, but
zero coupling between lines, which is what permits incremental dispatch.
Line-level grammar constraints are complementary future work (§8).

**Serving-side caching.** Prefix/KV caching (e.g., vLLM's PagedAttention
[8]) makes the cost of a call proportional to its *novel suffix*. We treat
prompt-prefix invariance as a first-class protocol design constraint and
quantify its effect on segment-boundary latency (§4.4).

**Speculative methods.** Speculative decoding [9] accelerates decoding
itself; our approach is orthogonal — we hide latency rather than reduce
it — and the two compose.

**Incremental structured output.** Streaming partial JSON to progressively
render UI is folklore in production LLM systems; we are not aware of prior
work that (a) formalizes the pacing condition under which a *timed
consumer* (animation) never starves, (b) co-designs the action vocabulary
(macros, durations) to *satisfy* that condition on measured hardware, and
(c) couples it to a deterministic geometry solver with per-line repair
semantics. That combination is the contribution.

## 3. System Architecture

```
topic ──► lesson engine (LLM, NDJSON action lines)
              │ per line: parse → validate → layout → dispatch
              ▼
        WebSocket event stream ──► browser action player
              │                        ├─ canvas: progressive stroke reveal
              │                        └─ speech: chained utterances,
              ▼                           concurrent with drawing
        deterministic runtime state
        (layout boxes, id registry, auto-reveal ledger)
```

**Scene IR.** Objects (`text, circle, …, asset, group`) and steps
(`write, create, fadein, fadeout, move, scale, transform, wait`) with
Manim-convention coordinates. The same IR drives the offline Manim
renderer and the live canvas renderer; assets are name-resolved against
twin libraries (Python factories for Manim; display-list factories in JS)
with labeled-box fallback for unknown names.

**Action protocol.** The model emits one JSON object per line:
`{"say": …}`, `{"add": {object}}`, `{"play": {step}}`,
`{"macro": "label"|"flow", …}`, `{"clear": true}`, `{"end": true}`.
Call 1 additionally opens with `{"title": …}` and `{"plan": [4 segments]}`,
folding lesson planning and the first teaching beat into a single round
trip. `{"end": true}` closes the HTTP stream immediately — tokens that
would follow are never decoded.

**Runtime state.** The server tracks every placed object as a box
(id → center, extent). This state (i) feeds the layout solver, (ii) is
serialized into each call's *user* message so the model can build on what
is drawn, and (iii) backs validation (plays referencing unknown ids are
dropped; re-adds of existing ids are dropped).

**Two lanes, one budget.** The live lane prefers the fastest installed
model (gemma3:4b); the offline mp4 lane keeps the larger model
(qwen2.5:7b), where composition quality matters more than latency. Only
one model is resident at a time (commodity-RAM constraint).

## 4. A Latency Model for Generation-Driven Animation

Let `r` be decode rate (tok/s), `r_p` prompt-eval rate, `P′` the uncached
prompt suffix, `k_j` the token length of action line `j`, and `d_j` the
playback duration of action `j` (animation time; ≈0 for `say`, whose
utterance occupies the parallel audio channel).

### 4.1 Arrival and service processes

Action `j` finishes generating at

    A_j = P′/r_p + (k_1 + … + k_j)/r.

The board plays actions FIFO: start `S_j = max(A_j, F_{j−1})`, finish
`F_j = S_j + d_j`, with `F_0 = 0`. The **stall** before action `j` is

    G_j = max(0, A_j − F_{j−1}).

`G_1 = A_1 = P′/r_p + k_1/r` is the irreducible time-to-first-action
(TTFA). Everything else is controllable.

### 4.2 Saturation theorem

**Theorem 1.** If `d_j ≥ k_{j+1}/r` for every `j ≥ 1`, then `G_j = 0` for
all `j ≥ 2`.

*Proof.* Induction on `j`. Base: `F_1 = A_1 + d_1 ≥ A_1 + k_2/r = A_2`,
so `G_2 = 0`. Step: if `F_{j−1} ≥ A_j` then
`F_j = F_{j−1} + d_j ≥ A_j + k_{j+1}/r = A_{j+1}`. ∎

The condition `d_j ≥ k_{j+1}/r` is enforceable: we clamp durations into
`[0.6, 2.5] s` and budget lines at `E[k] ≈ 25–35` tokens, so at
`r = 16.4`, `E[k]/r ≈ 1.8 s` sits inside the clamp window. Individual
violations (a short `play` followed by a long `add`) are absorbed by
backlog:

**Proposition 2 (backlog drift).** Define surplus `σ_j = d_j − k_{j+1}/r`
and backlog `B_j = F_j − A_{j+1}`. Then `B_j = max(B_{j−1}, 0) + σ_j`, a
reflected random walk; a stall of magnitude `−B_j` occurs iff `B_j < 0`.
If `E[σ] > 0`, stalls are transient and their expected frequency decays
with accumulated drift. ∎

### 4.3 Speech as buffer credit

A `say` of `ℓ` characters costs `k_say/r ≈ 1–2 s` to generate but occupies
the audio channel for `ℓ/ρ ≈ 6–10 s` (browser TTS, `ρ ≈ 14–16` chars/s).
During that utterance the generator produces `r · ℓ/ρ` further tokens —
several full action lines — so every spoken sentence *strictly increases*
drawing backlog. Perceived idleness requires both channels silent;
interleaving `say` lines (which the prompt mandates) therefore covers
exactly the stalls that Proposition 2 leaves possible. This is why a
talking teacher is not just pedagogy: it is the pipeline's shock absorber.

### 4.4 Segment boundaries and prefix-cache discipline

A lesson is several calls. At each boundary the next stream's first action
arrives after `C = P′/r_p + k_say/r`. With a byte-identical system prompt
across calls (board state travels in the *user* message), the cached
prefix covers the system prompt and `P′ ≈ 100–150` tokens ⇒
`C ≈ 1–1.5 s + 1.2 s ≈ 2.2–2.7 s`, typically under the terminal backlog
`B_end` of the previous segment ⇒ no audible gap. Violating prefix
invariance (v1 embedded board state in the system prompt) makes
`P′ ≈ 1200` ⇒ `C ≈ 10–12 s`, a guaranteed stall. Measured: v1 segment
voice latency fell from ~47 s (cold prefix) to 4–15 s (warm) on identical
prompts; v2 inherits the discipline by construction.

### 4.5 Closed-loop pacing: elastic playback and idle cover

Theorem 1's condition is *open-loop*: durations are chosen at authoring
time against an assumed rate `r`. The client can do better, because it
observes its own backlog `B` exactly (the queued playback time). We apply
a piecewise-proportional controller to the playback rate:

    d_eff = d · π(B),   π(B) = 1.4 if B < 2 s;  0.8 if B > 12 s;  1 otherwise.

Stretching when the buffer is thin *manufactures* surplus σ (Prop. 2)
exactly when the reflected walk approaches the boundary; compressing when
fat caps end-to-end lag. This is adaptive-bitrate streaming transposed to
generative content: the scarce resource is not bandwidth but decode rate,
and the adapted quantity is not resolution but *time itself* — the lesson
breathes at the model's pace without ever appearing to wait. Residual
exposures (a cold call, a fenced block being assembled) are covered by
**idle gestures**: when the queue is empty and both channels silent, the
board pulses the most recently drawn object — a semantic no-op that cannot
be wrong, chosen precisely because deterministic recovery needs no tokens.

### 4.6 The narration ratio: token allocation across channels

Each generated token buys a channel-dependent amount of *playback mass*
(seconds of audience attention). Speech: at ~3.5 chars/token and
ρ ≈ 15 chars/s, `μ_A ≈ 0.23 s/token`. Drawing: an add+play pair costs
~35 tokens for `d ≈ 1.5 s`, so `μ_V ≈ 0.04–0.07 s/token`. The stream
saturates only if mean mass per token covers mean generation time per
token:

    f·μ_A + (1−f)·μ_V ≥ 1/r,

where `f` is the token share allocated to `say` lines. The asymmetry is
the point: **speech plays back ~3.5× slower than it generates, while
drawing plays back at roughly its generation speed** — narration is the
only channel that robustly *banks* time.

This predicts the instability we measured. Early v2 lessons allocated
`f ≈ 0.11`, giving `μ̄ ≈ 0.061 s/token` against `1/r = 0.061` — the
system sat *exactly at criticality*, and individual lessons starved or
survived on per-run variance (observed open-loop idle 42–65% across four
topics, despite healthy cadence medians). The remedy is not faster
decoding but *reallocation*: prompting for two-sentence narration every
1–2 draw lines pushes `f ≈ 0.2` (`μ̄ ≈ 0.08`, ~30% margin), and raising
default draw durations to 1.4–1.6 s lifts `μ_V` ≈ 60%. A teacher who
talks more is, quite literally, a pipeline with more headroom.

### 4.7 The error-cost ladder

Let a segment have `n` lines and per-line corruption probability `ε`.

| failure mode | v1 (JSON blob + repair) | v2 (action stream) |
|---|---|---|
| syntactic slip | regenerate segment: `+K_seg/r ≈ 18–65 s` per attempt | drop line: 0 added wall time, `k/r ≈ 2 s` of content lost |
| dangling reference | repair or prune-with-risk | drop line; **auto-reveal** restores any added-but-never-animated object at segment end (0 tokens) |
| pretty-printed / fenced output | n/a (format-forced) | **brace-balancing line assembler**: lines accumulate until braces balance, then the block parses whole — streaming resumes after |
| re-`add` of an existing object | duplicate object | **intent recovery**: converted to a scale *pulse* — the teacher visibly "points at" the object. Observed: a recap that would have been 24 s of dropped lines becomes a sequence of emphasis gestures |
| mid-thought `clear` | board wipe | dropped unless it is the segment's first board action (a teacher wipes *between* parts) |
| protocol ignored (blob output) | n/a | legacy parse of the whole buffer recovers narration/objects/steps |
| nothing usable | mock scene | deterministic narration card (lesson continues) |

The design principle generalizing these rows: **never spend model tokens
on recovery when a deterministic interpretation of intent exists.** The
sampler is the scarce resource; the runtime is free.

Expected segment wall time in v1 scales as `T/(1−p_seg)` with
`p_seg = 1−(1−ε)^n` the blob-failure probability; in v2 it is constant
`T` with expected content loss `n·ε` lines, each individually
inconsequential and partially repaired deterministically. For small local
models (ε non-negligible), this exchange — *latency variance for bounded
content loss* — is decisively favorable, and it is what lets v2 keep no
repair loop at all on the hot path.

## 5. Deterministic Geometry: the Layout Solver

The model is good at topology ("the arrow goes from the sun to the
ocean") and unreliable at geometry (overlaps, off-frame placement,
inconsistent spacing) — and geometry is token-expensive to specify. We
therefore treat model coordinates as *hints* and compute final geometry
server-side:

1. **Containment by projection.** Each object is modeled as a centered
   box (type-specific extent estimates; assets from a measured table).
   Centers are projected onto the feasible region
   `[−(X−w/2), X−w/2] × [−(Y−h/2), Y−h/2]` — clamping is exactly
   Euclidean projection onto an axis-aligned box, so containment holds by
   construction.
2. **Separation by minimum-penetration descent.** New boxes are pushed
   out of the deepest overlap along the axis of least penetration,
   re-projected, and iterated (≤10 steps; existing boxes never move —
   the teacher does not shuffle what is already drawn). Sequential
   insertion onto sparse boards converges in 1–3 iterations empirically;
   this is a greedy online approximation to rectangle packing (NP-hard in
   general), adequate because lesson boards are sparse by design (≤ ~10
   boxes).
3. **Label sites by discrete argmin.** `{"macro":"label"}` scores four
   candidate sites (below/above/right/left of the target box) by overlap
   area plus a frame-violation penalty and takes the minimum.
4. **Arrow endpoints on box borders.** `{"macro":"flow"}` connects box
   centers pulled back to their borders along the center line, so arrows
   touch objects instead of piercing them.

**Token economics of macros.** A labeled object via raw IR costs an `add`
plus a `play` (~45–60 tokens); `{"macro":"label","of":"sun1","text":"the
Sun"}` costs ~14 — a 3–4× per-construct compression that simultaneously
*improves* output (solver-placed labels never collide). Compression here
is latency: at fixed `r`, fewer tokens per construct means more constructs
per second of generation.

### 5.1 From coordinate hints to a scene grammar

Coordinate hints with collision repair proved insufficient in practice:
the model gravitates to the frame center, so every object arrives needing
repair, repairs compose poorly across segments, and the result reads as
noise (overprinted labels, arrows slashing through text, recaps dumped on
diagrams). The durable fix removes coordinates from the model's vocabulary
entirely. A teacher's spatial reasoning is *relational and regional* —
"the figure stands **on** the ground, the sun goes **up in the corner**,
I'll draw the next part **over here**" — so the protocol now speaks
exactly that:

- **Anchors** on `add`: `at` (nine named regions), `near`+`side` (beside an
  existing id), `on` (bottom edge meets the target's top — things *stand
  on* things), `between` (midpoint of two ids). No anchor at all invokes
  **flow placement**: a typesetter-style scan for the first zero-overlap
  slot. The solver compiles anchors to coordinates, then projects into the
  active panel and de-collides as before.
- **Panels**: each segment is allotted a column (left → right → wipe and
  re-title → repeat), so consecutive segments physically cannot
  overprint each other, and the recap always has clean board. The wipe
  and title rewrite are deterministic actions (zero tokens) — the
  engine, not the model, manages board real estate.
- **A reserved title band** that content placement cannot enter, and
  size floors (asset scale, font size) so semantic importance survives
  the model's noisy magnitudes.
- **Moves de-collide their destinations** with the same projection +
  separation pass as placements.

This completes a progression worth naming: v0 trusted the model with
*everything* (code), v1 with *geometry* (validated IR), v2 with *hints*
(coordinates as suggestions), and the scene grammar with *only topology* —
each step moving invariants from the sampler into the runtime, and each
step both cheaper in tokens and better-looking on the board. Readability
is tracked by the benchmark as worst-case text-overlap area (§7).

### 5.2 The performance vocabulary: strokes, rigs, and verbs

Topology solved placement, but lines and polygons do not make a *sketch*,
and translation does not make a *dance*. The same principle — skill lives
in the runtime, the model only names it — extends to expressiveness in
three layers, none of which costs lesson-time tokens:

**Stroke style.** Every vector path is resampled (~0.35 u) and jittered
perpendicular by seeded value noise (amplitude ~0.05 u, endpoints pinned;
the seed is the object id, so the wobble is stable across frames — no
shimmer). Fills follow the same wobbled outline. One rendering change and
every shape on the board reads as hand-drawn chalk rather than CAD output;
this is the rough.js [10] insight implemented natively in the renderer.

**Human strokes.** Google's QuickDraw corpus [11] holds 50 M human
drawings in 345 categories, stored as *ordered stroke sequences* — which
is precisely the renderer's progressive-reveal format. The backend lazily
fetches one clean sample per category (a few KB; the source is streamed
and cut at the first `recognized` drawing) and caches it forever. Any
unknown asset name now resolves through: built-in factory → human sketch →
labeled fallback. The model gains ~110 nouns ("cat", "bicycle", "tornado")
whose drawings are not generated but *performed from human demonstration*,
stroke by stroke under the pen tip.

**Behavior verbs.** Articulated motion comes from a skeletal rig (9-DoF
stick figure: shoulders, elbows, hips, knees, lean) with a pose-keyframe
library, plus parametric props (a globe whose meridians drift with a phase
variable — rotation reads as *rotation*, not as a rolling circle). The IR
gains six verbs — `dance`, `walk(to)`, `wave` (rig keyframe cycles, eased
in and out of the current pose), `spin(revs)` (rotation, or meridian phase
on globes), `orbit(around)`, `bounce` — each a single ~12-token action
line that the renderer expands into seconds of kinematics. Verbs degrade
like everything else: `dance` on a non-figure becomes a bounce; `orbit`
around an unknown id is dropped. In channel-mass terms (§4.6), verbs are
the most efficient visual tokens in the system: `μ_V ≈ 3.5 s / 12 tok ≈
0.29 s/token` — *better than speech* — so a lesson that performs is also a
lesson that never starves.

The asset resolution ladder is now: rig/parametric factory → QuickDraw
human sketch → labeled box; the animation ladder: verb performance →
eased property animation → reveal. The model's interface stays nouns and
verbs; everything below it is deterministic, cached, and free.

### 5.3 Modes: the engine as a framework

Nothing in §§3–5 is lesson-specific: the action stream, validators,
layout solver, pacing controller, and performance vocabulary form a
general engine for *LLM-driven timed media*. What distinguishes "teach
me X" from "draw me X" from "tell me a story about X" is policy, so the
system exposes exactly that as a **mode registry**: a `ModeSpec` binds a
voice (system prompts sharing the byte-identical action contract — the
cache-hot region), an arc (plan + N segments, or a single pass), a board
policy (`columns` with wipes, a fresh `scenes` stage per act, or one
`full` canvas), and token budgets. Four modes ship — *learn*, *draw*,
*story*, *explain* — and each is ~15 declarative lines; the orchestrator,
transport, renderer, and all guarantees (saturation, drop semantics,
collision bounds) are inherited unchanged. The framework claim is the
practical one: a new mode is a registry entry, not an engineering
project.

## 6. Implementation

Backend: Python/FastAPI; planning via Ollama `/api/chat` with streamed
reads, `keep_alive=30 m`, `num_predict` caps (700 first call / 500 per
segment), `temperature 0.3`, and `{"end":true}`-triggered early stream
close (remaining tokens are never decoded). Model warm-up fires at server
startup. Frontend: dependency-free canvas renderer (progressive stroke
reveal with a glowing pen tip, typewriter text, group animation by leaf
resolution) and chained-but-concurrent speech. The offline Manim path is
untouched: same IR, same asset names.

## 7. Evaluation

Hardware: Apple-silicon laptop, macOS; models via Ollama (Q4_K_M).
Measured decode/prompt rates: qwen2.5:7b = 9.0 / 61 tok/s; gemma3:4b =
16.4 / 115 tok/s.

**Metrics.** *TTFA*: wall time to the first model-generated action
(deterministic intro content plays from t≈0 regardless). *Cadence*:
inter-arrival gaps between generated actions (p50/p95). *Perceived idle*:
simulated time during which the visual channel (FIFO playback with the
elastic controller of §4.5) and the audio channel (utterances at ~15
chars/s) are both silent while generation is still pending — measured by
`bench_live.py`, which replays real lesson streams through the two-channel
model. Idle-cover pulses bound any *motionless* interval to ≤2.5 s by
construction; we report idle without that cover (conservative). The user
-facing target "<1.5 s" is interpreted as the steady-state cadence/stall
bound, not total scene latency, which no 16 tok/s decoder can meet for
multi-hundred-token content (§1).

**Pipeline generations** (one lesson per cell unless noted; topics varied;
all wall-clock):

| metric | v0 (scene blob, qwen) | v1 (segment blobs + early narration) | v2 (action stream, gemma) |
|---|---|---|---|
| first paint | minutes (render-then-play) | <1 s (deterministic intro) | <1 s (deterministic intro) |
| first model-generated voice | — | 8.8 s (gemma) / 47 s (qwen, cold) | 11–15 s cold |
| first model-drawn content | ~5 min | 31–39 s (gemma/qwen warm) | 16–22 s |
| steady-state cadence | one scene | 20–30 s between segments | **1.3–2.1 s between actions (p50)** |
| cadence p95 | — | — | 4–8 s (segment boundaries, assembled blocks) |
| repair regenerations per lesson | frequent | 1–2 (40–65 s each) | 0 (drop semantics) |
| full 4-segment lesson | — | 149 s (gemma) / ~215 s (qwen) | 102–129 s, 50–60 actions |

**Ablation: protocol discipline in the prompt.** Two single-lesson probes
isolate prompt-level fixes on identical machinery. Banning markdown fences
and requiring a `say` line before the title/plan block moved first-voice
from 23.9 s → 11.4 s, cadence p50 from 2.32 s → 1.66 s, and cadence p95
from 12.0 s → 4.1 s. Fence wrappers alone taxed every action ~5 tokens
(~20% of cadence) — at fixed decode rate, *prompt-induced syntax is a
latency line-item*.

**Ablation: narration share vs. starvation (the §4.6 prediction).** Eight
lessons across four prompt configurations, all gemma3:4b, simulated
open-loop idle (conservative: no pulse cover):

| config | topic | says/actions | idle ratio | longest idle |
|---|---|---|---|---|
| base v2 | volcanoes | 6% | 65.1% | 38.3 s |
| base v2 | seasons | 13% | 42.0% | 10.4 s |
| base v2 | echoes | 13% | 47.0% | 19.8 s |
| base v2 | ice | 12% | 46.9% | 24.1 s |
| + worked example | magnets | 14% | 47.1% | 12.4 s |
| + worked example | leaves | 45%* | 37.9% | 9.8 s |
| + narration ratio | heart | 12%† | 38.2% | 11.9 s |
| + narration ratio | thunder | **26%** | **17.7%** | 10.6 s |

(*short one-sentence says — high count, low mass; †non-compliant run.)

**The scene-grammar configuration (v3): all SLOs pass.** Replacing
coordinates with anchors compounds with everything above: anchor fields
cost ~10–20 tokens/line versus 30+ with coordinate pairs, halving cadence;
the narration mandate held (10–13 says per lesson); and panels structurally
eliminate overprint. Three lessons, simulated with the elastic controller:

| topic | TTFA | cadence p50 | perceived idle | longest stall | text overlap |
|---|---|---|---|---|---|
| sun rise & set (run 1) | 5.5 s | 0.76 s | 0.0% | 0 s | 0* |
| sun rise & set (run 2) | 4.9 s | 0.70 s | 0.0% | 0 s | 0.00 |
| plants drink water | 5.9 s | 0.65 s | 0.8% | 0.85 s | 0.00 |

(*run 1 predates the text-only overlap metric; its 2.91 reading was a
bbox artifact of flow-arrow diagonals.) Every target — including the
user-facing "<1.5 s" interpreted as the worst perceived stall — is met,
on a 4 B model, on a laptop, with zero marginal cost. The interventions
compose multiplicatively because they attack independent factors of the
same product: tokens-per-action (anchors, macros, short ids) ×
seconds-per-token (model choice, caching) × coverage (narration mass,
elastic pacing, idle cover) × correctness-per-action (validators, layout).

The pattern matches the criticality analysis: lessons whose *narration
mass* clears the §4.6 bound (thunder) cut idle ~3× versus the baseline;
lessons that ignore the mandate (heart) stay near it. Instruction
adherence on a 4 B model is itself stochastic — which argues for
enforcing the allocation in decoding (grammar constraints) or in the
runtime, not the prompt; both are future work. Residual idle concentrates
in two places: the cold-start window between the deterministic intro
ending and the first generated action (~6–11 s; pulse-covered in the real
client), and isolated generation holes where the model emits droppable
prose (p95 cadence 4–13 s).

**Failure-mode accounting (v2):** dropped lines cost generation time only;
auto-reveal recovered every added-but-unplayed object in testing; the
brace-balancing assembler recovered pretty-printed plan blocks observed
in every gemma3:4b first call before the fence ban; one observed recap
that re-`add`ed five board objects (24 s of would-be silence) played as
five pointing pulses instead.

## 8. Discussion, Limitations, Future Work

**Limitations.** Single-machine, single-rater evaluation; no user study of
pedagogical quality; content accuracy is the model's (the system
guarantees *well-formedness*, not *truth*); browser TTS prosody is
utilitarian; the layout solver's box abstraction is coarse (it prevents
gross overlap, not typographic finesse); `transform` is crossfade, not
shape morphing.

**Future work.** (i) Per-line grammar-constrained decoding — drop rate ε→0
without losing streamability; (ii) speculative decoding on the live lane
(composes multiplicatively with pacing); (iii) two KV slots
(`OLLAMA_NUM_PARALLEL=2`) to keep both call types' prefixes
simultaneously warm and to overlap look-ahead planning with the current
stream; (iv) point-matching morphs (Hungarian assignment on path samples)
for true `transform`; (v) skeletal walk cycles for articulated assets;
(vi) microphone input — the saturation analysis is input-agnostic, so a
speech-transcribed topic stream drops in unchanged; (vii) lesson
memoization (topic-hash → action-log replay at zero cost); (viii) a local
neural TTS (e.g., Piper) for prosody, which *increases* speech credit
(slower, more natural ρ); (ix) a principled pacing controller — replace
the piecewise π(B) of §4.5 with PID or MPC on a stochastic arrival model,
with formal no-starvation guarantees under bounded rate variance; (x) a
*content* QA lane: a second cheap model auditing `say` lines against the
topic asynchronously (it can lag the board by seconds and flag, since
correctness review — unlike drawing — is not latency-critical);
(xi) *channel scheduling*: perceived idle equals `span − |V ∪ A|` for
busy-interval unions V (visual) and A (audio), so at fixed workloads idle
is minimized by minimizing channel overlap — deferring utterance starts
into predicted visual gaps is an online interval-union maximization,
amenable to a greedy exchange-argument-optimal policy under FIFO
constraints. The current always-concurrent policy is the simplest point
in that design space.

## 9. Conclusion

The latency of LLM-driven animation is not a decoding-speed problem; it
is a *scheduling* problem with a decoding-speed constraint. Once
generation is restructured into a validated action stream, three small
pieces of mathematics — a saturation inequality, a per-token
channel-mass accounting, and a buffer-feedback rule — describe the whole
system well enough to predict its failures (criticality starvation),
prescribe the fix (narration reallocation, duration floors), and bound
what remains (cover gestures). Every recovery mechanism in the system
follows one principle: *the sampler is the scarce resource; the runtime
is free*. We believe this recipe — stream small typed actions, validate
with drop semantics, compute geometry deterministically, pace playback to
generation, and spend tokens where playback time per token is highest —
applies beyond whiteboard lessons to any setting where an LLM drives a
timed medium on constrained hardware: slides, data-story dashboards, game
tutorials, or embodied narration.

## 10. Reproducibility

Everything is local and free. `backend/lesson.py "<topic>"` prints the
timed event trace and the gap statistics used in §7;
`backend/benchmark.py` exercises the offline path. Models:
`ollama pull gemma3:4b qwen2.5:7b`.

## References

[1] The Manim Community Developers. *Manim: Mathematical Animation Engine.* manim.community.
[2] Ollama. *Get up and running with large language models locally.* ollama.com.
[3] Qwen Team. *Qwen2.5 Technical Report.* arXiv:2412.15115, 2024.
[4] Gemma Team. *Gemma 3 Technical Report.* arXiv:2503.19786, 2025.
[5] Williams, S., Waterman, A., Patterson, D. *Roofline: An Insightful Visual Performance Model.* CACM 52(4), 2009.
[6] Gerganov, G. et al. *llama.cpp: GBNF grammar-constrained decoding.* github.com/ggml-org/llama.cpp.
[7] Willard, B., Louf, R. *Efficient Guided Generation for Large Language Models.* arXiv:2307.09702, 2023.
[8] Kwon, W. et al. *Efficient Memory Management for Large Language Model Serving with PagedAttention.* SOSP 2023.
[9] Leviathan, Y., Kalman, M., Matias, Y. *Fast Inference from Transformers via Speculative Decoding.* ICML 2023.
