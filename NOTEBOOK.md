# Learning Notebook

A shared, running log of **why we do things the way we do** — for both Lalit and Claude.
Read it at the start of a work session; append to it whenever a principle becomes clear.

**How to use this notebook**
- One learning = one small idea: a principle in a sentence, then *why* in a sentence or two.
- Capture the **thought process**, not just the conclusion — the "why" is the reusable part.
- Be honest: if a learning is proven wrong later, strike it and note what replaced it.
- Keep sections logical, not chronological. Newest insight can go to the top of its section.
- **Keep it current:** end every substantial work session by appending what we learned.
  This notebook holds the *earlier* learnings (mined from the code, PAPER.md, and past
  sessions — sections H & I) **and** every *new* one going forward. Nothing should be lost
  to a closed chat. (CLAUDE.md tells future sessions to read + append here.)

Status: living doc · started 2026-06-17

---

## A. The big picture — why we're restructuring

**A1. Stop building "lesson generation" as one thing.**
A monolith can't be optimised, tested, or reasoned about part-by-part. When a lesson
looks wrong, you can't tell which part failed. Split it into independent engines and
each becomes measurable and improvable on its own.

**A2. "Not realtime yet" is fine — it works.**
Correctness of the foundation matters more than speed right now. A correct slow engine
can be sped up; a fast wrong engine is just wrong faster. Speed is a later, separate
problem.

## B. The three engines (the decomposition)

**B1. Three engines: Drawing, Positioning, Story.**
- *Drawing* = "draw whatever we name" (a thing → strokes/pixels).
- *Positioning* = "where does each thing go" (things → collision-free coordinates).
- *Story* = "what to show and say, in what order" (topic → ordered beats + narration).

Why: clean seams give independent optimisation, independent tests, and parallel execution.

**B2. Build bottom-up, run top-down.**
Build order: Drawing → Positioning → Story (can't place what you can't size; can't
sequence what you can't place). Run order: Story → Positioning → Drawing.
Why: the dependency points one way at build time and the other at runtime — don't confuse them.

**B3. It's the browser pipeline: measure → layout → paint.**
Drawing has TWO phases: *measure* (how big is this thing?) before layout, and *paint*
(render it here) after. Positioning sits in the middle — it needs a thing's **size** but
not its pixels. (Mental map: Story = HTML, Drawing = box-model + paint, Positioning = CSS layout.)

**B4. THE KEY MOVE: take the LLM out of Drawing and Positioning.**
Drawing (catalog lookup + parametric shapes + cached strokes) and Positioning (a
constraint solver) can be **deterministic**. Only Story needs a big model.
Why: today the model invents story AND picks shapes AND computes coordinates in one
token stream — slow, and it hallucinates geometry. Move geometry to deterministic engines
→ far fewer tokens, zero overlap / off-board errors, perfect layouts, and the model only
does what it's actually good at (story).

**B5. The Story↔Positioning seam needs a small relational vocabulary.**
Story must not emit coordinates, but it must express spatial *intent* ("cause on the left,
effect on the right"). A short list of relations: `left-of`, `right-of`, `above`, `below`,
`in-panel`, `emphasize`, `group-with`.
Why: too thin → dumb layouts; too rich → you've reinvented coordinates inside the LLM.
Getting this list right is the crux of the whole design.

**B6. Drawing needs a fallback ladder for the long tail.**
`exact asset → parametric shape → named sketch → labeled box`. Never fail; just degrade.
Why: "draw whatever we write" is unbounded — the engine must always return *something*
with an honest size.

**B7. Extent honesty is non-negotiable.**
Every drawable (including fallbacks) must report a size close to what it actually renders.
Why: layout quality is capped by measurement accuracy. A lie in "measure" becomes an
overlap in "layout".

**B8. A generative visual LANGUAGE, not a catalog. (Lalit, 2026-06-17.)**
*The fastest system isn't the one with the fastest image generator — it's the one that rarely
needs generation.* Most teaching concepts decompose into **primitives → composed icons**
(sun = circle + rays; cloud = blobs; person = head + limbs; molecule = atoms + bonds). So the
Drawing ladder is: primitive → **composed icon (the language)** → catalog (QuickDraw) → generated
SVG → box. Composition is deterministic, free, instant, infinitely combinable, and *style-consistent*
— so it's the PRIMARY path; catalog and generation are the rare fallback. Recipes are **declarative
data** (parts + transforms), not code → safe, validatable, and mass-authorable by a workflow against
a frozen primitive API. *Generalises B6: don't just fall back to a catalog/generator — compose.*
Tag every drawable with its `source` (primitive/icon/sketch/generated/box) so you can SEE how little
generation you actually need (ties to K8 observability).

## C. Benchmarking & metrics

**C1. Benchmarks must be machine-computable — humans can't test everything.**
We will run hundreds of cases on every change. If scoring needs a human, we'll test 5
cases and fool ourselves. Machine scoring is what makes "tune until the number goes up" possible.

**C2. Score invariants, not reference pictures.**
Coverage (everything named got drawn), no-overlap, on-board (no clipping),
relation-fidelity (stated relations hold), extent-honesty.
Why: most of these are *self-evident from the output* — overlap and clipping need no
"correct answer" to compare against. Only coverage/relations need the input tagged with
expected entities, and we write those tags ourselves. So we can machine-test the
foundation **without anyone hand-drawing ground truth**.

**C3. Accuracy and Speed are two separate scoreboards — never mix them.**
Order: freeze the accuracy target → clear it → *then* race for speed.
Why: if speed numbers leak into accuracy work, you optimise the wrong thing.

**C4. The corpus is a fixed, versioned, difficulty-graded yardstick.**
`L1 primitives → L2 compositions → L3 spatial intent → L4 long tail`. Same suite every run.
Why: a frozen suite makes progress legible ("L1–L3 at 100%, L4 climbing") and stops us
cherry-picking demos.

**C5. Bench each engine in isolation — mock the boundaries.**
Positioning: feed synthetic things + relations, check no-overlap / on-board / relations
(no drawing, no model). Drawing.measure: render, then compare bbox. Integration: the corpus.
Why: a regression should point at ONE engine, not a blur of three.

**C6. Benchmark the deterministic core to death first; quarantine model-in-loop.**
Deterministic = reproducible, so a diff is a real regression. A model in the loop is noisy
→ needs multiple samples + tolerance → keep it off the critical path.

## D. Models, speed & cost

**D1. "Do we need Gemini?" is a benchmark OUTPUT, not an input.**
Run the corpus deterministic-only → that's the floor (free, instant). The failures define
the "needs interpretation" set. Only there, race models (qwen / gemma / Gemini Flash / Pro)
and read off a Pareto table: `accuracy-lift × latency × $`.
Why: don't pick a model by vibe. Measure that you need it for (say) 20% of cases — the L4
tail — and nothing else, then pay only for that.

**D2. Paid APIs are now allowed (reverses the old free-local-only rule).**
Why: Gemini-as-the-interpretation-fallback lets the deterministic core stay the fast/free
path and buys accuracy only where it's actually needed.

## E. How we work (process)

**E1. Foundation before story.**
Drawing + Positioning must be proven-correct before we tune Story.
Why: you can't debug the story if the layer under it is unreliable — you'd never know
whose fault a bad lesson is.

**E2. Keep this notebook.**
Append small learnings (principle + why) as they crystallise; both of us read it at session start.
Why: the *thought process* is the reusable asset; conclusions without the why rot.

**E3. Define success as suite-based gates that map to a logged number.**
Why: a success criterion you can't compute from the benchmark output is a wish, not a stage.

## F. Reference — how the *current* realtime trick works (kept, even though de-prioritised)

- **F1.** Deterministic intro paints in <1s with zero tokens → hides model cold-start.
- **F2.** Stream line-by-line: each closed NDJSON line becomes a board action immediately —
  don't wait for the full response.
- **F3.** Early stop on `{"end":true}` → unspent tokens never decode.
- **F4.** Byte-identical system prompts → Ollama KV prefix-cache re-evals ~100 tokens, not thousands.
- **F5.** Browser plays two channels (visual + audio) with elastic pacing so neither goes silent.

Why keep this: when we *do* return to latency, these are the levers — and the new
architecture (cheap story beats expanded by deterministic engines) makes all of them easier.

## G. Open decisions (decide next)

**G1. Corpus input format — DECIDED: structured Beats.** The foundation corpus tests
Positioning + Drawing only; interpretation (English→Beats) is the Story engine's separate,
later benchmark. Author the corpus so an English layer can later compile to the *same* Beats —
no lock-in. *Why: isolate one engine's correctness at a time (E1/C5).*

**G2. The relational vocabulary.** Lock the 6–8 spatial relations (see B5).

**G3. Sim vs client truth (later, for latency).** Grade on the bench_live consumer
simulation, or have board.js beacon real timings back?

---

## H. Earlier learnings — design principles proven in v1/v2 (carried forward)

These were learned building the current system. The new direction (sections A–E) isn't a
U-turn — several of these are its seeds.

**H1. The IR is the spine — the model emits validated *data*, never code.**
The planner produces JSON only (no Manim code, no `exec`). Why: you can swap renderers,
validate, and test without trusting model output to be safe or runnable. *This is the
original seed of the new direction — skill/geometry lives below the model, not inside it.*

**H2. Drop-don't-repair beats repair loops.**
A malformed or overflowing line is dropped for free, not patched. Why: repair loops burn
tokens + latency and can cascade; dropping keeps the stream alive and the system simple.
Generalises to: **prefer cheap rejection over expensive correction.**

**H3. No coordinates — the model speaks anchors, the solver computes geometry.**
`at / near / on / between` → a layout solver compiles real positions. Why: LLM-authored
coordinates are token-heavy and error-prone; anchors roughly halve tokens and the solver
*guarantees* valid placement. *This already proves B4 in miniature — keep pushing geometry
out of the model.*

**H4. The drawing skill lives in the runtime, not the model.**
Performance vocabulary — seeded stroke wobble, verbs (walk/spin/dance/orbit), human
QuickDraw sketches — is *performed by the engine* when the model merely names it. Why:
expressiveness at ~0 lesson tokens; the model says *what*, never *how*. *Direct ancestor of
the Drawing-engine idea (B1/B4).*

**H5. Fallback ladders everywhere — never crash, always degrade.**
Unknown asset → factory shape → human sketch → labeled box; Ollama down → mock lesson; bad
object/step → skipped, not fatal. Why: a teaching tool must always show *something*. (B6 is
this principle applied to one engine.)

**H6. Behaviour as data, not code (the modes registry).**
A new mode = one `ModeSpec` entry (voice + arc + panel policy + budgets), zero engine
changes. Why: adding capability shouldn't touch the engine — the same instinct that makes
separating the three engines worthwhile.

**H7. Latency has a theory, not just vibes (PAPER.md).**
The saturation theorem (action density `dⱼ ≥ kⱼ₊₁/r` ⇒ no stalls after action 1) and the
speech-credit lemma (narration buys runway) give the *minimum* cadence and explain why
audio masks gaps. Why: reason about and **measure** latency (`bench_live.py`) — don't guess.

## I. Earlier learnings — tooling & environment (repo setup, 2026-06-17)

**I1. One source of truth for deps: `pyproject.toml` + `uv.lock`.**
uv manages the env; `requirements.txt` is *generated*, never hand-edited. Why: reproducible
installs, and no drift between local / CI / hooks.

**I2. `biome.json` must be STRICT JSON.**
A single `//` comment silently voids the entire linter rules block — no error, it just
stops applying. Why: a lint config that mysteriously "does nothing" usually has a comment in it.

**I3. Pyright stays advisory on Manim-facing code.**
Manim's loose typing throws ~16 false positives; type-checking is non-blocking until the
code is annotated. Why: don't let a noisy gate block real work — make it advisory, tighten later.

**I4. Hooks use the project's own tool versions (`uv run`), not pinned copies.**
Why: pre-commit and `make lint` must never disagree about formatting.

**I5. Tests are hermetic — they run the mock/fallback paths, no Ollama/network.**
Why: those fallback paths are exactly what CI and a fresh machine exercise, so they're worth
guarding hardest.

## J. Learnings from the external research (2026-06-17 — full report: docs/RESEARCH-generative-drawing.md)

**J1. The famous diffusion models output flat raster — we reject them.**
SD/SDXL/SD3.5/FLUX, all distillation (LCM/Turbo/Lightning/Hyper-SD), all conditioning
(ControlNet/T2I-Adapter), StreamDiffusion → a pixel grid with no path/stroke/layer. Using
them means vectorizing after the fact (lossy, slow, non-deterministic). *Our editable/streaming
design is vindicated, not challenged — the popular high-fidelity models are exactly what we are NOT.*

**J2. The real vector generators are autoregressive LLM/VLM SVG-*code*, not diffusion.**
StarVector, OmniSVG, and frontier-LLM-writes-SVG actually run and emit composable SVG.
Diffusion's one vector branch (SVGFusion) is the right idea but shipped no code/weights. So the
Drawing engine's generative tiers are built around **SVG-code-in → parse → measure → paint**.

**J3. Positioning = adopt kiwisolver (Cassowary), reject learned layout.**
Anchors map to linear constraints; sub-ms incremental re-solve; editable coords by construction;
BSD-3. Learned layout (LayoutGPT/DM/LaySPA) is *strictly weaker* — LaySPA still loses to solvers
on overlap (0.0257 vs 0.0024). This is independent proof of B4/H3: **the model never emits coordinates.**

**J4. The long tail is a LADDER tiered by subject type, not one model.** Each rung license-cleared
+ vector-native: frontier-LLM-SVG (live, simple subjects) → StarVector (offline icons/diagrams) →
DiffSketcher (offline no-photo strokes) → diffvg/LIVE + paid-raster (photographic) →
QuickDraw/parametric/labeled-box backstop. The *ladder is the architecture* (extends B6/H5).

**J5. License landmines are real — check before shipping.** Non-commercial: SDXL-Turbo, FLUX-dev,
CLIPasso (+ viral ShareAlike), CLLMs weights (Vicuna-tainted), DeTikZify weights (Llama license).
Clean: kiwisolver (BSD-3), Mermaid (MIT), DiffSketcher (MIT), diffvg/LIVE (Apache-2.0), QuickDraw
(CC-BY-4.0, attribute Google), frontier-LLM SVG *output* (unencumbered).

**J6. Sanitization boundary: the LLM proposes *what* to draw, the solver decides *where*.**
LLM-emitted SVG is non-deterministic → validate well-formed XML, bound the viewBox, strip scripts,
and pass only *intrinsic shapes* to the measure phase. Never let a model emit final coordinates.

**J7. SVG→stroke-order — DECIDED: constrain the generator, don't build a traversal engine.**
LLM/VLM SVG defaults to filled paths, not pen order. Instead of writing a geometry→stroke-order
engine, **prompt/normalize generators to stroke-only line-art** (`<path fill="none" stroke=.../>`)
and animate draw-on with the standard `stroke-dasharray`/`stroke-dashoffset` trick (works in both
board.js and Manim `Create`). Fills, when needed, fade in *after* their outline draws (hybrid).
*Principle: **push complexity into the contract/prompt, not a post-processor** — same instinct as
deterministic engines. The geometry-ordering pass is a deferred YAGNI.* (Credit: Lalit.)

**J9. The full engine design now lives in docs/ARCHITECTURE.md** — contracts, the rung ladder,
kiwisolver Positioning (first build), the offline asset-gen pipeline, the benchmark gates, and a
6-phase plan. Read it before building.

**J8. Don't optimise STORY decode speed yet.** Narration tokens aren't the bottleneck (PAPER math).
CLLMs / EAGLE-3 speculative decoding wait until STORY decode is a *measured* bottleneck.

## K. Learnings from the adversarial architecture review (docs/REVIEW-architecture.md)

**K1. "By construction" is a smell — every invariant needs an independent, output-derived check.**
The review's recurring finding: we asserted overlap/determinism/extent-honesty/relation-fidelity as
*properties of a mechanism* but never said how to recompute them from the output. *An invariant you
can't independently recompute is one a broken-but-stable engine passes green.* Now every gate recomputes
from the rendered output, sharing no code with the engine it grades (overlap via a standalone AABB
routine on rendered bboxes, never the solver's own box cache).

**K2. Don't let the benchmark self-certify off the same function it grades.** Today's `bench_live.py`
computes overlap from `approx_extent` — the same sizing it places with. A measure that lies low then
shows overlap==0 while ink overflows. Grade extent-honesty against a *headless render*; compute
overlap/on-board from the *rendered* bbox, not the measured Extent.

**K3. The connector ordering hole.** `measure→position→paint` can't express "arrow from A to B" — an
edge has no size before its endpoints are placed. Fix: a `Connector` Thing that bypasses measure/VPSC +
a **route** phase after positioning. *General lesson: placement-dependent geometry needs a stage after
placement; not everything fits "size it, then place it."*

**K4. Flow placement is not a solver objective.** "minimize y then x" doesn't exist in Cassowary —
untethered things pile in one corner and the overlap-remover scatters them into a blob that passes every
gate. Free-space packing is a deterministic pre-pass *outside* the solver. *Lesson: know what your solver
genuinely can't express; don't paper over it with a soft constraint that silently no-ops.*

**K5. Verify library claims against the actual library.** Reviewers empirically found kiwisolver
edit-variables can't be `required` and incremental edit-suggest ≠ batch solve — so "sub-ms incremental
re-solve" needed a freeze-placed-Things rule to stay deterministic. Adversarial review caught what a
read-through wouldn't.

**K7. Proved Story with a real model (qwen2.5:7b) — content is good, JSON is the weak point.**
Across 3 topics: the model named genuinely teachable, *drawable* concepts (leaf/sunlight/chlorophyll/
CO₂; bill/gavel/senate) with clean referential integrity, and **the engine pipeline handled real
Beats perfectly — invariants passed, zero overlap/drops.** BUT **JSON reliability was 2/3** — one
topic returned a malformed array (beat split into string fragments even with `format:"json"`) that
crashed the parser. *Lesson: an LLM that emits a content structure WILL malform it ~1/3 of the time;
you need (a) defensive parsing that salvages valid items, and (b) constrained/validated generation
(Ollama JSON-schema `format`, or Outlines/Instructor) — not just `format:"json"`.* Also found:
**drawing coverage 0–20%** — the model names more concepts than our 32 cached QuickDraw sketches
cover (and compound names like `carbon_dioxide` don't match) → warm more QuickDraw + handle compounds.

**K8. No silent fallbacks — make provider status visible (faithfulness, for the PRODUCT).**
The system silently degraded in 3 places: no model → generic template story; LLM fails → template;
concept not drawable → placeholder box. Mechanically it "works," but the user can't tell real from
fallback — so it reads as a working product when it's a placeholder demo. *Same principle as K1/K2,
one layer out:* surface (a) which provider is configured AND reachable (`/api/engine/status`), (b)
per-lesson provenance — was the real model used or did it fall back, and *why* (story `plan()` returns
a StoryResult; LLM providers stopped falling back internally so the decision is recorded), and (c)
real-vs-placeholder per drawing (DrawOp carries `rung`; the board dims placeholder boxes + shows a
count). *Lesson: a demo that silently degrades is dishonest about its own status — instrument the
fallbacks so "it works" can't hide "it fell back."*

**K6. The false-green trap recurses — even the dashboard that checks for it had it.** Our test/check
dashboard's `pass` was vacuously true on empty output: drop *every* Thing and overlap/off-board/
relation are all trivially clean → GREEN. A "pass" that holds on zero output is the K1 trap one level
up. Fix: bake a **coverage floor** into the ruler itself (`not (total>0 and drawn==0)`) so no gate can
forget it, and make every rollup *server-authoritative* (compute overall from ALL sub-gates, not a
client subset). *Lesson: whenever you add a status/aggregation layer, re-ask "what does green mean on
empty/partial input?" — and gate coverage, not just correctness.*

---

## The success ladder (for reference; gates must map to a logged number — see E3)

| Rung | Name | Exit gate |
|---|---|---|
| S0 | Runs | Offline fallback + ≥1 real lesson end-to-end, 0 crashes |
| S1 | Coherent | Valid actions, `text_overlap ≤ 0.5`, every `play` targets a real object |
| S2 | Live | PAPER SLOs: `TTFA ≤ 20s`, `idle ≤ 5%`, `gap_p50 ≤ 1.5s` across the suite |
| S3 | Snappy | Tighter: `TTFA ≤ 8s`, `idle ≤ 2%` on the 10-topic suite |
| S4 | Good teaching | Pedagogical rubric pass (needs an LLM judge — deferred) |
| S5 | Production | Concurrency, persistence, graceful degradation under load |

Current focus: get the **Drawing + Positioning** engines to high accuracy on the corpus
(L1→L4) first; latency rungs (S2/S3) come after the foundation is trustworthy.

---

## L. Cartoon (branch `cartoon`) — flat-vector style as a PAINT-TIME layer

**L1. Style is a render decision, not an asset fork.** The honest, cheap, local cartoon target is
flat-design VECTOR (Kurzgesagt), not per-frame diffusion. So the engine brain (Director→Story→Beats→
measure→position→route) is unchanged; only `paint()` gained a `style`. `measure()` stays
color-INDEPENDENT (geometry caches by concept+geometry_attrs); color is applied at paint by `palette.py`.
*Lesson: when a new look must coexist with the old, put the variation at the LAST stage that can express
it (paint), keep everything upstream shared, and the old product stays byte-identical for free.*

**L2. Whiteboard must STRIP, not just "skip".** Recipes carry authored cartoon hex (a multi-part tree
needs brown trunk + green foliage — one concept→color tint can't express that). So whiteboard can't merely
"not add color"; it must actively strip fill+stroke to stay mono. Style is the single source of color:
cartoon adds, whiteboard removes. *Lesson: if you let assets carry optional styling data, every consumer
that wants the un-styled view must explicitly neutralize it — "default off" in the data ≠ "off" downstream.*

**L3. Paint hints can't ride the geometry cache key.** `entrance`/`ambient`/`z`/`color` are paint-time,
but Beats only carry one `geometry` dict (which becomes the Drawing cache key). Mixing them in would make
two identical shapes with different motion miss the cache. Fix: split `geometry` into geometry_attrs vs
paint_attrs when building the Thing (stream + compile_beats). *Lesson: the §2 geometry/paint split is a
real invariant — honor it at every Beat→Thing boundary, not just inside paint().*

**L4. A parameterized rig buys consistency for free (the Animaker model).** One `character.py` rig
(head/hair/face/torso/arms/legs) with pose+expression+theme params is the SAME asset everywhere — so a
lesson's host is automatically consistent across poses. Pose/expression live in geometry_attrs → each
variant caches separately, zero generation. *Lesson: for a recurring entity, a rigged parametric asset
beats N drawn variants on both consistency and cost — and it composes from the primitives you already have.*

**L5. Motion defaults belong in the palette, overridable by the story.** Cartoon derives tasteful idle
motion from the concept (characters bob/rise, sky props float) so the frame has life with zero authoring;
an explicit beat hint always wins. *Lesson: give "good by default, controllable when needed" — a concept→
behavior table plus an override beats either pure-manual or pure-magic.*

**L6. Verify a renderer by rendering, not by asserting.** Tests lock the contracts (whiteboard strips,
cartoon fills, pose caches), but the real check was rasterizing `build/engine/*.svg` via `qlmanage` and
LOOKING — that's how the spindly stick-`person` (→ motivated the rig) and the readable scene were caught.
*Lesson: machine invariants gate correctness; an eyeball on the pixels gates whether it's actually good.*

**L7. A from-scratch rewrite silently drops invariants the original quietly held — adversarial review on the DIFF caught it.** Rewriting `board/engine.js` for fills, I changed "close the loop when `closed`" to "close the loop when `filled`" — so every WHITEBOARD closed primitive (circle/square/triangle) lost its closing edge. Tests stayed green (they assert wire shape, not pixels); the multi-agent review found it by tracing the data path and noticing svg.py/geometry.py close unconditionally while engine.js didn't. Same pass found the z-layer system was fully built in Python (DrawOp.z, serialize) yet INERT at the renderer (the presenter never painted on top). *Lesson: when you rewrite a renderer, the old one encoded invariants you didn't re-derive; diff the behavior, not just the code — and an adversarial reviewer that reads ALL the sibling paths (svg vs board) catches the inconsistency a single-file read never would.* Also confirmed L6: rasterize-and-look is what surfaced the warm-default fix (blue-on-blue) and the dark-scene invisible labels — both invisible to the test suite.

**L8. Camera as ENGINE-EMITTED data, animated by the renderer — not renderer magic.** Pan/zoom is a
`{type:"camera", x,y,w,h,ms}` event the stream emits (focus rect clamped on-board) and the board animates
by interpolating the SVG `viewBox` over `ms` (easeInOutQuad, rAF, non-blocking with a seq token so a newer
move supersedes an in-flight one). Keeping the camera in the IR makes it deterministic + testable (assert
the focus rects stay on-board, assert a full-board pull-back ends the run) instead of an opaque renderer
behavior. Gated by a derived `DirectorSpec.cinematic` (cartoon + non-calm) so it's a policy knob, not hard-
coded. *Lesson: "motion" that the engine can describe as data (where to look, for how long) belongs in the
event stream — the renderer just plays it; then it's reproducible and the whole pipeline stays the spine.*

**L9. Two renderers will silently diverge — and Svelte scopes your keyframes.** The product board is the
Svelte Studio (`frontend/src/lib/board.js`); `board/engine.js` is the fallback. Both had the SAME pre-cartoon
gaps, so every cartoon feature (fills, gradient backdrop, z-order, motion, camera) had to land in BOTH or the
real UI shows none of it — the integration, not the engine work, is what makes it a product. Gotcha: Svelte
RENAMES `@keyframes` defined in a component `<style>`, so a JS-set `element.style.animation = "amb-bob ..."`
silently finds nothing — the ambient keyframes must live in the GLOBAL `app.css`. *Lesson: when a feature
lives behind a build step + a second renderer, "done in the engine" isn't "done in the product"; wire the
product surface and watch for framework-scoping that breaks string-referenced CSS.*

---

## M. Model/provider selection — one local-first surface (`engine/models.py`)

**M1. Scattered provider config reads as "wrong default" even when the default is right.** The engine had
provider/model logic in 4 modules (story, generators, app-status, checks), each reading env independently;
the v3 default was `template` (generic) while the v1 lanes already auto-picked local Ollama. A user with
Ollama running saw generic lessons + UI strings dangling "gemini" and concluded it "defaults to gemini" —
it never did. *Lesson: when "what model am I using?" can't be answered from ONE place, users (rightly)
distrust it; centralize resolution into a single surface with a `describe()` the product shows verbatim.*

**M2. Local-first means the DEFAULT probes local, never reaches for paid.** `STORY_PROVIDER=auto` (new
default) uses local Ollama with the best installed model when it's running, else the deterministic template;
cloud (gemini) runs ONLY when explicitly named AND keyed. A key being present is NOT consent to spend it —
`auto` never selects cloud. Drawing-gen defaults `off` (the 98-recipe ladder covers ~98%; LLM-SVG is slow +
unreliable). *Lesson: a free/private product must make the zero-config path the local one and treat any paid
call as explicit opt-in — and SAY so when it downgrades (gemini-without-key → template, with a warning).*

**M3. Auto-pick by family, best-first, so installing a better model upgrades you for free.** `pick_model`
matches a preference list by family prefix (`qwen3` covers `qwen3:4b`/`:8b`), so `ollama pull qwen3:4b`
auto-selects it with no config change. Brain preference leads with Qwen because the brain emits schema-
constrained Beat JSON and Qwen is the most reliable at structured output for its size (NOTEBOOK K7). *Lesson:
encode model choice as a ranked capability preference over installed models, not a hardcoded name that breaks
when it isn't pulled.*

**M4. A smart default needs a hermetic guard or the test suite hits the dev's Ollama.** Switching the default
from `template` to `auto` made the suite probe local Ollama (network, non-deterministic, and *slower* — a 2s
status probe per run). Fix: an autouse conftest fixture forces `template`/`fixture` + monkeypatches the single
`ollama_tags` probe to "unreachable" for every test; resolution tests re-set what they need. *Lesson: every
"auto-detect" default must have one probe seam the test harness can pin — centralize the probe so hermeticity
is one monkeypatch, not N.*

**M5. "Quality is bad" was the brain's STRUCTURE, not its content or the renderer.** A real qwen2.5:7b
water-cycle lesson named great drawable concepts (cloud/rain/river/sun) — but emitted 6 `clear` beats in
LEARN mode (the live board wiped itself every 1-2 concepts) and 11 concepts for a 3-concept spec (cramped,
3 dropped). The engine faithfully rendered the mess. Fix = **drop-don't-repair at the Story layer**
(`sanitize_beats`): strip clears outside story mode, cap concepts per mode, null relations to unshown ids,
drop dangling connect edges — plus a prompt that forbids clears in learn and demands concrete drawable
nouns + valid ids. Result: 0 clears, 5 clean concepts, real edges. *Lesson: when an LLM feeds a renderer,
the renderer's faithfulness AMPLIFIES structural garbage — sanitize the model's plan with the same
drop-don't-repair rigor you apply to positioning/actions; don't trust it and don't try to "fix" it.*

**M6. Coverage lives or dies on normalization — LLMs name plurals.** The brain says "raindrops"/"clouds"/
"trees"; the recipe ladder keyed on singulars → labeled boxes (looks broken). Adding article+plural variants
to `icons.compose` (try `the clouds`→`cloud`, `trees`→`tree`/`tre`, first match wins) jumped real-icon
coverage on a real lesson from ~50% to ~100%. *Lesson: the gap between "we have a recipe" and "the lesson
uses it" is entirely concept normalization — spend there before authoring more assets.*

**M7. Cartoon needs a COMPOSED frame, not free-space packing.** The Phase-1 positioner packs Things into
reading-order free space + honors relations — correct for a whiteboard concept map, but fed an LLM's
scattered absolute regions it spreads elements thin and arrows sprawl diagonally across the board (the real
"quality is bad"). Fix: a separate cartoon layout (`layout.compose_cartoon`) — title across the top, the
reusable host beside the board, concepts in a CENTERED, evenly-spaced grid sized to fill the stage. Concepts
land in emission order, so the sequence the Story connects (c0→c1→c2) sits adjacent and arrows stay short.
It's a render-time STRATEGY (whiteboard keeps `place()`), deterministic, and never overlaps by construction.
*Lesson: "good teaching layout" (relations + flow) and "good cartoon staging" (a balanced, intentional frame)
are different objectives — don't overload one positioner; pick the layout strategy by style.*

**M8. Pre-place the whole segment, then reveal — the freeze-placed rule was about NOT reshuffling mid-draw,
not about placing one-at-a-time.** The live stream used an incremental Placer (a relic of the streaming-LLM
design); but beats now arrive as a complete plan, so I batch-place each scene-segment (compose_cartoon for
cartoon, place() for whiteboard — which is internally incremental-in-order, so the batch is byte-identical)
and then stream the reveals + camera from the fixed placements. The composition is balanced before the first
stroke; nothing reshuffles while drawing. *Lesson: revisit "incremental because streaming" assumptions when
the upstream stops streaming — batch-then-reveal gives global composition AND keeps the no-reshuffle promise.*

**M9. Bring-your-own-story: open the IR to the user (the cleanest quality lever).** A small local model
(qwen2.5:7b) writes mediocre lessons; but the engine's thesis is "IR → pixels", so the highest-leverage fix
isn't a better local model — it's letting the user supply the IR directly. `POST /api/engine/animate` takes a
pasted storyboard JSON (a strong external model writes it from `GET /api/engine/script-prompt`, which embeds
the Beat format + our DRAWABLE VOCABULARY so concepts hit the icon ladder, not boxes), runs the same
sanitize → compose → stream, and animates it with zero model call. Key tweak: the model path caps concepts
tightly (tame over-production) but the BYO path trusts the author up to the board cap (`sanitize_beats(...,
max_concepts=8)`). Result on a hand-written water cycle: 6 concepts, ALL real icons, 0 boxes — vs qwen's 2
things + a box. *Lesson: when your generator is the weak link, don't only improve the generator — expose the
contract so a better generator (or a human) can drive it. The IR is the product surface, not just an internal seam.*

**M10. "Cartoon is film" → STAGE the scene, don't pack a diagram; "icons ≠ drawing".** Two product truths
the user crystallized: (1) whiteboard = a line diagram (Lucide icons fit — a coverage *floor*, not the
soul); (2) cartoon = film, a story well presented. So cartoon must not free-space-pack concepts (that's a
diagram) — it STAGES them: `layout.compose_cartoon` places props in semantic vertical BANDS (sky up:
sun/cloud/bird; ground down: tree/house/river; rest mid), the host stands on a HORIZON ground-band
(palette `ground` in the backdrop), title across the top; abstract topics degrade to a centered grid. The
catalog rung became style-aware: whiteboard resolves a long-tail concept to a Lucide line icon, cartoon
skips it (a UI icon breaks a film) and uses the designed concept card. One render flipped the whole feel —
a water cycle went from a scattered concept-map to a scene with a sky, a horizon, and characters standing on
grass. *Lesson: the SAME content (Beats) reads as "diagram" or "film" purely by the staging policy — layout
is the difference between a concept map and a cartoon, far more than asset richness. Pick the staging by
mode, and keep catalog/icons as the floor, never the soul.*

---

## N. The cartoon DIRECTION pipeline — the grammar between Beats and pixels (engine/plan.py)

**N1. The renderer was done; the DIRECTOR wasn't.** Flat Beats (show/connect/say/clear) can only express a
concept map — fine for whiteboard, vague for film. The missing layer is a DIRECTION GRAMMAR:
`DirectorSpec → LessonPlan → ScenePlan → Shot → Action → [compile] → timed events → renderer`. Built in
`plan.py`: a Scene has a SETTING (where) + CAST (who); a Shot has FRAMING (camera) + ACTIONS (semantic verbs
on actors, with timing) + NARRATION. `compile_plan` reuses everything below it (measure, compose_cartoon
staging, camera, paint) — the plan owns intent, the engine owns geometry/timing/framing. `lift_beats` lifts
old Beats into a single-scene plan so nothing forks; `parse_plan` lets the bring-your-own lane author full
directed storyboards (the `animate` endpoint accepts `{scenes:[...]}` OR `{beats:[...]}`). *Lesson: when
output is "vague visuals," the fix is rarely the renderer — it's giving the renderer SPECIFIC intent via a
richer IR. Build the grammar, keep the old IR as a degenerate case, compile both to one renderer.*

**N2. Animation as a CLOSED verb vocabulary, not per-object keyframes (the motion language).** `VERBS` =
{enter,exit,rise,fall,flow,pulse,emphasize,grow,shrink,point,look,transform,connect,wobble} — each one
implemented ONCE as a transform the renderer applies to ANY actor (found by `data-opid`), parameterized by
duration. An Action references actors by id (`point(guide,sun)`), so it works wherever they're staged; the
plan says WHAT, the renderer's CSS keyframes own HOW. Unknown verbs are dropped at parse (closed set). *Lesson:
same "language not catalog" principle as drawing, applied to motion — reuse is structural (one `pulse`, infinite
uses), and a closed vocabulary keeps the LLM's choices renderable.*

**N3. The plan makes failure visible.** `compile_plan`'s `done` summary reports scenes, shots, real drawings,
placeholders, and by_source — so "looked like it worked" can't hide "creatively it was all boxes." The
provenance is `plan` (vs template/ollama), so you always know which path drew the lesson. *(Maps to the user's
gap #12 — quality gates over silent fallback, the §K8 principle one layer up.)*

**N4. Semantic SCALE is a role, not a size — and the planning layer must assign it, or "beats
leak through."** The renderer became cartoon-capable, but the *content* layer wasn't acting like a
director: a droplet beside a cloud got the same size as the cloud, so the frame read as a diagram of
equal nodes, not a film with a subject. Fix is a `role` on every Entity (hero/main/prop/particle/
setting) → `_ROLE_SIZE` base scale, and a layout that uses ONE common scale per band so RELATIVE sizes
survive (`f = min(slot/max_w, band_h/max_h)`, not per-item normalize — that flattens hierarchy back).
The subtle part: *templates* set roles explicitly, but LLM/BYO content arrives as flat Beats with no
roles, so it degraded to a uniform row — the "beats leak through" symptom. `lift_beats` now INFERS
roles (particle-lexicon → particle; title-subject or most-connected prop → the lone hero; rest → prop)
so beat content gets the same hierarchy a template does. Cartoon only — whiteboard stays a uniform
diagram (roles off). *Lesson: a capability in the renderer isn't a capability of the product until the
planning layer reliably USES it. "Consistently acting like a director" means the degenerate input path
(flat beats) must be lifted to the same intent the rich path authors — infer the missing intent, don't
just pass it through.*

**N5. In a film, the relationship is shown, not labeled.** Cartoon drops connector text labels
(`label=None` in `compile_plan` when style==cartoon) — narration + the host pointing + explanatory
motion carry "evaporates"/"falls as," not a diagram edge-tag. And motion is EXPLANATORY by concept,
auto-assigned (`palette.ambient_for`): vapor rises, rain falls, river flows, sun glows, cloud floats —
the animation teaches the mechanism instead of being generic idle bob. *Lesson: every label or generic
wiggle you can replace with a staged/animated equivalent moves the frame from diagram toward film. The
whiteboard keeps labels (it IS a diagram); the style axis decides.*

**N6. Direction has a FELT layer: scene purpose (why) + emotion (how it should feel).** A
real director gives every scene a job and a mood, and an arc across scenes. `ScenePlan` now
carries `purpose` (introduce/explain/contrast/build/resolve) and `emotion` (calm/curious/
wonder/tense/joyful) — both CLOSED sets. Emotion carries the visible weight on THREE channels:
the host's FACE (`_EMOTION_FACE` → rig expression), the post-shot PACING (`_EMOTION_PACE` →
tension cuts at 0.5×, wonder lingers at 1.5×), and the backdrop WARMTH (`palette.apply_mood`
blends the sky toward warm gold / cool blue). Purpose sets the host's body language (pose).
Story mode is authored as an ARC (curious→tense→joyful), not N flat scenes; `lift_beats` gives
beat content a gentle default arc (curious open, joyful close) so even LLM/BYO content feels
directed. *Lesson: "acting like a director" isn't only WHAT is on screen (staging/hierarchy) —
it's how it FEELS. The same frame with a neutral face + quick cut + cool sky reads as tension;
with a smile + lingering hold + warm sky it reads as joy. Encode feeling as data, render it on
multiple cheap channels at once.*

**N7. The hero must be a DRAWABLE subject, tested the way the style will draw it.** The story/
draw templates used the raw topic string as the hero concept ("a brave little seed" → a labeled
box). `story._subject(topic, style)` now extracts the most drawable noun by probing `measure(...,
style)` and taking the last word whose `source != "box"`. Critically it is STYLE-AWARE: cartoon
skips the catalog rung, so 'mars' boxes in cartoon and 'a rocket to mars' correctly picks
'rocket' (a recipe) — testing drawability with the wrong rung set (e.g. catalog.lookup) lies.
A recipe-subject topic now compiles with ZERO hero boxes (volcano/heart/moon draw for real).
*Lesson: when you need "will this render?", ask the ACTUAL renderer in the ACTUAL style, not a
proxy. Honest remaining gap: cartoon coverage is recipe-limited by design (catalog excluded as
too diagram-like) — topics whose subject has no recipe (seed) still box. The real #7 fix is
broader cartoon coverage (more recipes, or catalog-as-colored-fallback) — a design call.*

**B9. Scale the visual LANGUAGE with parametric FAMILIES, not more one-off recipes.** A hand
recipe (icons.py) is one composition; a FAMILY (`families.py`) is a *generator* — `quadruped(body,
ear, tail, horns…)` emits cat/dog/cow/lion/fox/panda/zebra from parameters, every one a fully
composed, multi-color, FILLED cartoon. Coverage then grows as a one-LINE data table (`"cat": ("quad",
{...})`), not fresh geometry per concept — ~11 families took the deterministic corpus from ~60 → 277
concepts, and the path to thousands is mechanical data entry the families make safe (the "a workflow
can mass-author them" promise, finally true). *Why this over "color the catalog as a fallback":* Lucide/
Tabler are STROKE-only line icons — flood-filling them yields colored outlines, not filled cartoon
shapes, which is exactly why cartoon skips the catalog. Real cartoon needs COMPOSED, multi-region,
multi-color drawables; families are the only thing that gives that AND scales. *Precedence lesson:
COLOR before coverage* — the mono `icon_recipes.json` had to be pulled OUT of `ICON_RECIPES` into a
separate lowest-priority dict, because an uncolored mono "cat" was silently beating the colored family
"cat" (same key, wrong winner). Order: hand core → cartoon_recipes.json → families → mono. *Honest
limit:* 277 ≠ 2k; families are the engine, the long tail is still data-entry (rare concepts like
`pineapple` still box). Bespoke hand recipes always override a family for concepts that deserve art.

**C1. Character LIFE from mined data — the rig acts, driven by 178k real childlike drawings.**
Workstream A of docs/ROADMAP-assets.md, built end-to-end. Meta's Amateur Drawings dataset (MIT, COCO
17-keypoint, ~288MB annotations, gitignored) → `tools/ad_mine.py` canonicalizes each figure to our
rig frame (y-up, upright-rotated about hip-mid, torso-normalized) and emits DERIVED measurements:
`character_proportions.json` (median limb ratios — the classic childlike BIG HEAD = 0.94× torso) and
`pose_library.json` (median limb-ANGLES per named pose, extracted by semantic filter: cheer = both
wrists above shoulders, walk = ankles apart, wave/point mirrored to one canonical side). The rig
(`character.py`) became DATA-DRIVEN: poses are 2-segment limb specs `[a1,l1,a2,l2]` (shoulder→elbow→
hand, hip→knee→foot — the dataset's exact skeleton), so mined angles drop straight in. `interpolate()`
tweens (shortest-arc on angles), `perform(clip)` expands a keyframe path into frames, `clip_drawables()`
renders them at a CONSISTENT scale (body fixed, limbs move). The Director picks a clip from EMOTION
(joyful→cheer, curious→wave); `compile_plan` renders placed frames onto the host op; `board.js`
flipbooks them. *Lessons:* (1) **mine DERIVED priors, render in your OWN style** — we never touch their
ARAP mesh or their images, just the joint statistics, so zero style risk + MIT-clean + the raw data
stays out of git (only ~measurements commit). (2) **A rig that's already angle-based makes external pose
data a drop-in** — the hard part was the 2-segment refactor + canonicalization math, not the rendering.
(3) **Semantic filters beat blind clustering for NAMED poses** — "both wrists up = cheer" gives a
directly-usable, Director-addressable gesture; mirror asymmetric ones (wave/point) before averaging or
they wash out to the mean. The cartoon is now a film with a presenter that gestures in time, not a bob.

**B10. Verify-before-scaling killed the BioIcons ingest; composed science FAMILIES won.** Workstream
B's plan was a normalization gateway ingesting BioIcons (2,836 CC0/CC-BY/MIT science SVGs). Before
building it, I rendered a 16-icon sample through a colored svgnorm — and the sample exposed three
fatal frictions the roadmap had assumed away: (1) full-canvas BACKGROUND rects (the cells rendered as
black squares), (2) shapes that SPILL off-canvas because they rely on CLIP-PATHS that flattening drops
(a viewBox Sutherland-Hodgman clip fixed some but MANGLED even-odd/holed shapes into black staircases),
and (3) specialized FILENAMES (`MII_Oocyte`, `1cell_pn4_zygote`) that don't match the common nouns
lessons use. ~half the icons need real clip/hole/even-odd geometry work for an uncertain yield. So I
PIVOTED: ~9 science generators in `families.py` (cell/atom/virus/dna/neuron/vessel/bulb/magnet/organ)
→ ~50 concepts (cell types, coronavirus, double helix, beaker/flask, lungs/brain/bone…), every one a
clean, consistent, FILLED composition named with the noun a lesson says. A "the cell" scene now
compiles with **0 boxes**. *Lessons:* (1) the §"verify visually" rule applies to INGEST too — render a
sample of any external asset source before building the pipeline; the cheap 16-icon render saved hours
of building a gateway whose source didn't fit. (2) **Composed > ingested for a controlled style** — the
SAME reason cartoon skips the line-icon catalog (B9) applies to messy illustration SVGs: you can't
reliably normalize arbitrary art into ONE style, but a family generator IS one style by construction,
and you own the naming. BioIcons-clean-subset harvest (strict reject-don't-clip gate) remains a
documented long-tail option, not the primary path.

**C2. A character GRAMMAR (cast), not a sticker pack — learn the modular model, don't ingest the
art.** Asked to add character assets (Open Peeps, Humaaans, CC0 modular vector chars), the §B10 rule
applied straight across: each source is a DIFFERENT style (Open Peeps = sketchy, Humaaans = flat-
geometric), so ingesting their art fragments the look. But their GRAMMAR — a character = modular parts
(skin + hair + outfit + accessories + pose + emotion) — is our rig's model. So we extended OUR rig
(`character.py`) into a modular CAST: `ROLES` (teacher/student/scientist/doctor/nurse/farmer/chef/
astronaut/artist/graduate/king/queen/wizard/superhero/police/explorer) = skin index + hair color +
shirt + a tuple of ACCESSORIES (`_ACCESSORIES`: glasses/goggles/straw_hat/chef_hat/crown/wizard_hat/
grad_cap/cap/helmet/coat/stethoscope/beard/cape, layered back/front around the body). `build(...,
character=role)` swaps the costume; the role rides in via the concept (drawing._character passes
`thing.concept`), so a "scientist" entity resolves to source=character with a lab coat — and inherits
the ENTIRE pose/emotion/motion engine for free (a scientist cheers in costume; the clip frames keep the
coat+goggles because clip_drawables threads `character`). 16 distinct characters, ZERO new art, ONE
style. *Lesson: the win isn't "more assets forever" (the user's words) — it's a character grammar
(face/body/pose/emotion/action/entrance/exit). Once the rig is a parametric system, a new character is
a one-line ROLE entry, exactly like a family is a one-line concept entry (B9). Composition is the
through-line: primitives→icons→families→science→cast, every rung the same "generator + data table" shape.*

**C3. The Director CASTS the host; the rig gained head articulation + a bigger clip/role set.**
Extending C2: (1) `character.cast_for(topic)` picks a topic-appropriate host — a farm lesson gets a
farmer, space an astronaut, science a scientist, baking a chef — and `plan._host_entity` sets the host
CONCEPT to that role (id stays "guide" so actions/streaming still address it). Matching is WORD-BOUNDARY
(a keyword is a whole word or stem), because naive substring cast "baking" as a *king* and would cast
"walking"/"thinking" too. (2) **Role names must not shadow object concepts** — the `_character` rung
runs before `_icon`, so a role named "star" hijacked the astronomical *star* (a real generation-test
concept); renamed to "celebrity", and a test now guards that `star` stays an object. (3) The head is now
a tiltable GROUP (skull+hair+face+head-accessories rotate about the neck `_NECK`) keyed by a pose's
`head` field → real nods (`agree` pose, head −17°) and a path to `look`. Clips grew to 9 (+jump/nod/
think), roles to 26 (+cowboy/pirate/businessman/dj/witch/clown/princess/celebrity/knight/grandpa) via 9
new accessories (cowboy_hat/pirate_hat/eyepatch/party_hat/witch_hat/sunglasses/headphones/mustache/tie).
*Lesson: casting is the cheapest way to make a lesson feel authored — the SAME engine, themed by topic,
turns a generic narrator into "a scientist is teaching you about cells." And every parametric system
eventually meets the NAMESPACE problem: a person-role corpus and an object corpus share the concept
namespace, so guard the high-value object nouns (star/sun/…) against accidental role shadowing.*

**C4. Multi-angle + a real pose/motion vocabulary + easing — "even simple art looks good if motion
is staged well."** Four asks, one rig. (1) **Multi-angle**: the head is a tilt+TURN group (turn shifts
face features toward the facing side + pushes the nose to the head edge → a 3/4 read), and a body
`facing` foreshortens the torso+limbs (x-squash + lean) so the whole figure turns, not just the head —
front / 3-4-left / 3-4-right + head-only glances. Full side-profile (single-arm silhouette) is a
DIFFERENT silhouette → documented future, not faked. (2) **Body-part rigging was already true** (2-seg
limbs posed by data); we made the head a separable group and the FACE articulate (turn, blink). (3)
**Pose library** 8→21: explain/surprised/hold/shrug/clap/look_up/look_left/look_right/turn_left/turn_right/
jump/crouch/agree + originals; 18 clips. (4) **Easing** bakes timing into FRAME SPACING (eased `t`
between keyframes) so the board flips at constant rate yet reads as accelerate/decelerate; `ease:back`
overshoots past the target then settles (follow-through), and ANTICIPATION is an authored wind-up
keyframe (jump = idle→crouch→jump→land). *Lessons:* (a) the head being a GROUP (C3) paid compounding
dividends — tilt, turn, blink, and nod all fell out of one pivot+feature-shift seam. (b) **Bake easing
into the data, not the player** — eased frame-spacing + dumb constant-rate playback beats a clever
player, stays deterministic, and needs zero renderer change. (c) Multi-angle in 2D is a feature-shift +
foreshorten CHEAT, not real 3D — and that's the right call for a cartoon (Kurzges.-style turns are cheats
too). The Director now maps emotion→richer clips (curious→explain, wonder→surprised) so the cast acts in
character with timing, not just a bob.

**C5. Full side-profiles (the silhouette cheat) + PER-SCENE casting.** (1) **Side profile**: at
|facing|~1 the rig switches to a true side view — `_face` draws ONE eye + a NOSE wedge poking off the
head's silhouette edge (the single cue that sells a profile), `_limbs` HIDES the far arm, and
`_turn_body` squashes harder (sx~0.54). side_left/side_right/walk_side complete the angle set
front→3/4→side both ways. The nose-off-the-edge is doing almost all the work — a round head reads as
front until one feature breaks its outline. (2) **Per-scene casting**: the host is a neutral
"presenter" that `compile_plan` RECASTS per scene via `character.cast_concept(concept, scene.setting +
narration)` — so a story that walks through settings changes who's on stage (lab→scientist, field→
farmer, kitchen→chef, all verified in one render). It only recasts GENERIC hosts (`NEUTRAL_HOST` =
presenter/guide/narrator/…); a specific role (scientist) or a thing (sun) passes through untouched —
the same namespace-guard discipline as §C3's star. *Lessons:* (a) a 2D "3D turn" is a hierarchy of
cheats — feature-shift (3/4) → break-the-silhouette (profile); pick the cheapest cue that reads. (b)
Casting belongs at COMPILE time over the SCENE, not at host-injection over the lesson — the scene is the
unit that has a setting, so per-scene is the natural granularity and it falls out of one recast pass.

**C6. Acting details — look-at-target + idle-life — and committing the branch.** Two small touches
that buy a lot of "alive": (1) **look-at-target** — `posed(name, **overrides)` lets geometry_attrs
carry head turn/facing/head overrides; `drawing._character` applies them, and `compile_plan`'s
point/look sets `turn = clamp(target.x − host.x)` so the host LOOKS at what it points to (a head turn,
not a stare). (2) **idle-life** — a held pose looked frozen, so an `alive` looping clip does a gentle
weight-shift sway + a periodic blink; still/tense hosts play it instead of a static hold. The blink
needed `interpolate()` to carry the discrete `blink` flag in a SHORT window near the keyframe (t<0.3 /
t>0.7) so it reads as a flick, not a slow fade — discrete state can't lerp, so you gate it on the
interpolation parameter. *Process note:* committed the whole accumulated cartoon branch in 10 logical
commits (chore→build→engine→cartoon→character→director→studio→api→test→docs) + one per increment after.
The pre-commit hooks need `uv` on PATH (`~/.local/bin`) and auto-fix EOF/format, so stage→commit→re-add
→commit is the rhythm. *Lesson: the cheapest acting cues (look where you point, blink when idle) read
as intention and life far out of proportion to their code — polish the SEAMS the eye lands on (face,
gaze, stillness), not the parts it skims.*

---

## O. The next direction — Story + Voice + Timeline (plan, 2026-06-18; full doc: docs/ROADMAP-story-voice.md)

**O1. Narration is the master clock — "take the LLM out of CHOREOGRAPHY" (the third time we run B4).**
The current stream is a QUEUE (say blocks drawing, no shared time); the ecosystem (Motion Canvas /
Theatre.js / GSAP / Lottie / Rive / Spine / Rhubarb) all point to a mini animation TIMELINE: parallel
tracks (draw/speech/character/camera), keyframes, easing, **audio markers**. The unifying insight that
ties Story-gen and Voice-sync into ONE design: *a concept is revealed when it is spoken; a named MARKER
is the seam between words and pixels.* So the LLM writes only the SCRIPT (words + concepts + relations +
arc); a DETERMINISTIC choreographer anchors reveals/points/camera to narration markers; the voice layer
resolves marker TIMES. This is B4/H3 applied a third time — first geometry left the model (Drawing),
then coordinates (Positioning), now TIME (Choreography). *Why: the model is good at words and intent,
bad at timing/geometry; markers are the cheap, testable seam (coverage/causality/cadence are all
machine-computable, like overlap/on-board were for Positioning).* The mechanism is Motion Canvas's
`{name, targetTime}` map, which degrades perfectly to our live board: a marker resolves LIVE (word
boundary) or AHEAD (audio timestamp).

**O2. "Free now, better later" voice = free-LOCAL Kokoro, not browser TTS.** Lalit can't pay for
ElevenLabs yet but chose 5–6-shape viseme lip-sync. Key correction: browser Web Speech CANNOT deliver
that (you can't capture its audio → no Rhubarb; word boundaries are non-portable; elapsedTime units
drift per browser), so the chosen fidelity *requires* a local audio-gen path. **The free-local path is
HeadTTS (wrapping a timestamped Kokoro-82M ONNX), Apache-2.0, $0, Ollama-for-voice** — HeadTTS is what
claims audio+phoneme+viseme timings in one call; *Kokoro core/other wrappers vary, so VALIDATE the exact
provider before committing (roadmap §V0) and keep a phoneme→viseme fallback chain.* So the design is a
`VOICE_PROVIDER` knob (mirrors M2's
`STORY_PROVIDER` local-first): default free-local Kokoro, Web Speech as the zero-install bootstrap,
ElevenLabs/Azure a one-line paid upgrade later. *Lesson: "free" and "paid-quality-later" are a PROVIDER
axis, not a reason to ship the weaker mechanism — pick the free path that can still reach the quality bar
(local-gen), and gate the paid swap behind the same surface as every other provider. Also: Piper is
GPL-3.0 → prefer Apache-2.0 Kokoro to dodge copyleft.*

**O3. We're 80% to a Spine rig and a timeline — the gaps are a mouth SLOT and a master-clock scheduler.**
plan.py already has a direction grammar (scenes/shots/actions + closed verbs + emotion); character.py
already has bone-poses (pose_library.json = Spine setup-poses), interpolate/perform/clip_drawables (a
keyframe engine), look-at-target, idle-life; the board already flipbooks `op.frames`. The two real gaps:
(1) the mouth is frozen per-expression — make it a swappable SLOT (Spine model) rendered as a small
CLIENT-swap layer (not server frames, or lip-sync frames explode), driven by a viseme track; (2) the
board's `play()` is `await`-per-event — replace with a master-clock scheduler that resolves markers and
runs tracks in parallel (draw WHILE talking). *Lesson: before designing a new format, check what the
code already is — our rig was accidentally Spine-shaped and our plan.py was a half-built timeline; the
work is lifting them, not inventing.*

**O4. Sequence by the WEAKEST LINK, not by the architecture diagram (Lalit, 2026-06-18).** The clean
build order (timeline → choreographer → voice → character) buries Story hardening at the end — but story
is *already the visible failure* (cartoon lessons stop after 1–2 lines), and the choreographer can't run
without the script's `[concept]` markers/concepts/relations anyway. So split story: a **minimal Script V0**
ships FIRST (schema + root-causing the truncation), and the heavier hardening (provenance, BYO-IR,
local-model robustness, Studio debug) is an **ongoing parallel track**, not an end-phase. *Lesson: don't
let the lower layers (voice/timeline) outrun the layer that's already broken; order phases so the
currently-visible pain is addressed early, especially when it's also an upstream dependency.* Corollary
on the anti-rewrite gate: **"pixel-identical" is the wrong bar for animated timing** — use a TOLERANCE
gate (same final frame + same event order + same marker-resolved schedule + sampled keyframes within
tolerance). Exact-bytes equality is brittle where the whole point is motion.

**O5. Structured DECODING is the story fix; DragonBones (MIT) is the rig reference (Lalit's survey,
2026-06-18).** Two refinements from a tool survey that both *confirmed* "upgrade, don't replace." (1)
Under-produced/malformed story is best fixed at the SOURCE with **typed structured decoding** (constrain
generation to a JSON schema), not just defensive parsing — `minItems` forces min scene/narration counts
so "stops after 1–2 lines" can't happen *if* the cause is generation. Use **Ollama-native JSON-schema
`format` first** (it's on the models.py surface, zero new dep, and llama.cpp GBNF enforces the grammar
incl. minItems); escalate to **Outlines/Instructor** only if native is too weak — Outlines' logit-masking
needs a non-Ollama serving path, which would fork the single provider surface (M1), so don't reach for it
by default. Caveats: structured decoding guarantees valid+complete STRUCTURE, never good CONTENT, and does
nothing if the truncation is post-processing (a sanitize cap) — so diagnose the cause first (why Script V0
opens with root-causing, not schema work). (2) For the rig, adopt the **DragonBones (DragonBonesJS, MIT)**
data model — bones/slots/attachments/pose/clip/mouthTrack — NOT Spine: Spine runtimes need a paid seat
(Spine Runtimes License). Re-implement the concepts in character.py (concepts aren't licensable), but cite
the MIT source to stay clean (J5). *Lesson: when borrowing a data model, pick the MIT sibling as the
reference even if the famous one is paid — and prefer the structured-output path already on your provider
surface over a more powerful library that forks it.*

**O6. The [concept]-marker contract — narration binds to the visual, with ZERO schema change
(Script V0 done, 2026-06-18).** Narration carries inline `[concept]` tokens (`say "The [sun] warms the
[ground]."`). Key design wins: (1) markers ride *inside the existing `say` text string*, so `BEAT_SCHEMA`
needed NO change — only `parse_marks(raw)→(clean_text, marks)` extracts them, brackets stripped for TTS,
char-offsets recorded into the CLEAN text (future per-word timing). (2) `Mark`/`Beat.marks`/`Shot.marks`
are additive optional tuples → fully backward-compatible; both renderers ignore the extra `marks` key on
the say event (no divergence — L9). (3) **Resolution is authoritative at ONE place — `compile_plan`,
against the entities actually STAGED** — not at parse time; so capped-out/forward-ref/BYO-plan all resolve
uniformly, and unmatched markers DROP (drop-don't-repair). (4) Markers bind to CONTENT props only — the
title (`kind=text`) and host (`kind=character`) are excluded, or a `[text]`/`[guide]` would falsely bind
to scaffolding. *Lesson: when adding a cross-cutting annotation, hide it INSIDE an existing string field
(zero schema/contract churn), record structured data alongside, and resolve at the single point that has
the final truth (staged entities), not where it's first seen.* Two process notes: a design Workflow
with a deeply-NESTED StructuredOutput schema sent the synthesizer agent into a 40-min validation-retry
runaway — **keep workflow output schemas FLAT** (the review workflow's flat schema ran clean in ~5 min);
and when a delegated step hangs, kill it and proceed on your own context rather than block.

**O7. The Timeline IR — encode the QUEUE'S await-semantics as data; a marker is a CLOCK POINT, not a
char-range (Phase 2a, 2026-06-18).** `backend/engine/timeline.py` adds the Timeline IR (parallel tracks +
markers) and `from_events`, the ANTI-REWRITE adapter that compiles today's linear event stream into a
degenerate timeline. The load-bearing trick: encode the board's exact await behavior as a per-entry
**`blocking` flag** (say/draw/connector/hold/clear block the cursor; camera/action/background don't), so
`resolve_schedule` reproduces the current queue cursor to the millisecond — then the SAME IR generalizes
to the parallel, marker-anchored timelines the choreographer will emit. The gate is §K1 applied to
playback: an **independent** re-derivation of the old queue schedule straight from raw events, compared to
the timeline's resolved schedule (not the engine's own numbers). *Lessons:* (1) to replace a control-flow
mechanism (an await-queue) without a rewrite, **turn its implicit timing rules into explicit data** — the
new player then reproduces the old by construction and extends past it. (2) **A timeline marker is a
master-clock point `{name, t}`** (Motion Canvas / roadmap §3): adversarial review caught that I'd built
markers carrying only character offsets and NO `t` time slot, so the voice layer would have had nowhere to
write the resolved time and `at:"m:x"` couldn't resolve — fixed before it calcified (`t` seconds, None
until filled; `char_start/char_end` are the separate word-timing offsets). (3) **Name deferred gaps in
the code:** bounded overlap isn't expressible yet — documented in `resolve_schedule` as the Phase-3
`at`-grammar extension, not silently missing. *The two renderers still diverge (board/engine.js clear=800
+ post-say dwell; Studio board.js clear=750, no dwell) — Phase 2b must unify them on this one IR (L9).*

**O8. The voice/lip-sync half — built ADDITIVELY because the frontend can't be machine-verified here
(autonomous run, 2026-06-18).** Phases 2b–5a shipped end-to-end: the master-clock scheduler (`playTimeline`
in both renderers), the choreographer wired in (`stream.timeline_lesson`), the **mouth-slot viseme rig**
(`character.mouth_shapes` → painted onto the host op as `op.mouths`), **char-estimated Web-Speech lip-sync**
(the bootstrap — no audio to align to), and the **`VOICE_PROVIDER`** surface (free-local-first, like
`STORY_PROVIDER`). End-to-end smoke through real Ollama produced the intended structure (concept draws
anchored to their word's marker, host points, 6 visemes). *Process lessons under "build all phases, no
verification loop":* (1) **make every unverifiable-frontend change ADDITIVE + reversible** — `play()` stayed
as a shared `dispatch()`, the mouth is an OVERLAY on the resting face (not a rewrite of `_face`), `op.mouths`
is an optional key — so a runtime bug is isolated and the old path A/B-able. (2) **Compile is the cheap
machine gate when runtime isn't reachable** — `vite build` + Biome caught the JS errors I couldn't catch by
running; lean on them. (3) **Push the intelligence backend (testable), keep the frontend a thin player** —
the scheduler/choreographer/markers are Python-tested; the board just resolves anchors + swaps a mouth, so
most of the risk surface IS verified. (4) **Open-loop timing is the known debt** — draw-while-talking + the
mouth ride the say's *estimated* duration (Web Speech gives no real timing); precise alignment is the
deferred Phase-5 local-TTS word-boundary work, not a bug. Diagnosis guide: roadmap §12.

**O9. The camera is a SHOT GRAMMAR, not a box-zoom — and the engine already had the staging, just
not the direction (2026-06-18).** First step of the "diagram-animator → cartoon" pivot. *Researched the
craft before coding* — of five strands, only **film direction** (Katz, *Film Directing Shot by Shot*;
Glebas, *Directing the Story*) and **AnimatedDrawings** survived 3-vote adversarial verification; Disney's
12 principles, McCloud's panel transitions, and the story-spine got NO primary citations, so they're
DIRECTION not fact (re-source before they drive architecture). Katz's verified rules are small + deterministic:
**shot SIZE = emotional distance** (a close-up is intimacy, NOT a crop of the prop); **cut to compare two
POVs / move to intensify one**; the 180° line is a half-plane test. Applied to `compile_plan`: replaced
"focus-or-full" (a fixed 1.7× the prop's *own* width) with a framing→board-fraction ladder (`_FRAMING_SCALE`
establishing=1.0 / medium=0.6 / close=0.4) + `_camera_shot` that **hard-cuts (ms=0) to a new focus subject
and pushes-in (ms>0) on the same one**, plus `_effective_framing` that INFERS a framing+focus for
beat-derived shots (which all default to `wide`) so real Ollama lessons get varied shot sizes instead of flat
full frames. *Why it was cheap:* the screenplay grammar (`Shot.framing` wide|medium|close, `ScenePlan`,
`VERBS`, emotion/purpose) ALREADY existed — the gap was the compiler, not missing structure. Two gotchas
banked: **(a) a deep-research agent FABRICATED a repo quote** — it echoed my own brief's phrase ("the compiler
flattens the screenplay into a concept-map") back and attributed it to plan.py's docstring; `grep` finds it
nowhere. Always verify a load-bearing repo quote against the actual file. **(b) There are now TWO camera
subsystems** — `compile_plan` shot-framing (this change) AND `choreograph._follow_cameras` (concept-follow on
the timeline path); both feed the live board and will FIGHT until unified. Next step (#1b): make the
shot-grammar the camera authority and demote concept-follow to "a medium on the spoken concept."
