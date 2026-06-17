# Research — Generative Drawing/Layout Landscape → Our Pipeline

Multi-agent survey (2026-06-17): 8 research areas, 16 candidate techniques adversarially
fact-checked for **current metrics, commercial license, and the raster-vs-vector trap**.
Source of truth for "what already exists and how we use it." Companion to [NOTEBOOK.md](../NOTEBOOK.md).

The decisive axis is **output type**: does a technique emit composable/editable/placeable
content for our vector+streaming board, or flat raster that we'd have to vectorize (lossy,
slow, non-deterministic — breaking our core value)?

## 1. Landscape (by verdict)

| Technique | Output | License (commercial) | Verdict |
|---|---|---|---|
| **Cassowary / kiwisolver** (+ CoLa overlap removal) | layout coords | BSD-3 ✅ | **ADOPT — this IS the Positioning engine** |
| **Frontier LLM writes SVG** (Gemini 3 Pro / Claude 4.5) | SVG code | API paid; SVG output unencumbered ✅ | **ADOPT — live long-tail first try** |
| **StarVector 1B/8B** | SVG code | Apache-2.0 ✅ | **PROTOTYPE — offline icon/diagram asset gen** |
| **OmniSVG 3B/4B/8B** | SVG code | base Apache; weights unclear, dataset NC ⚠️ | **PROTOTYPE/WATCH — richer offline SVG** |
| **diffvg** | Bezier vector | Apache-2.0 ✅ | **PROTOTYPE — offline substrate + raster→Bezier fitter** |
| **LIVE** (layer-wise vectorizer) | Bezier vector | Apache-2.0 ✅ | **PROTOTYPE (narrow) — raster→SVG bridge** |
| **DiffSketcher** (text→sketch SDS) | Bezier strokes | MIT ✅ | **PROTOTYPE — offline no-photo long-tail sketch** |
| **SketchRNN + QuickDraw** | strokes (dx,dy,pen) | Apache-2.0 + CC BY 4.0 ✅ | **WATCH — in-vocab stroke variety only** |
| **Mermaid/Graphviz LLM gen** | DSL→SVG | MIT/EPL ✅ | **PROTOTYPE (narrow) — node-edge/flow tier** |
| **DeTikZify / TikZ codegen** | TikZ code | code Apache; **weights Llama license** ⚠️ | **WATCH — offline, needs TikZ→IR + license clear** |
| **SketchKnitter** | strokes | MIT ✅ | **WATCH — ~10 classes, no weights** |
| **CLLMs** (consistency LLM) | faster text | code Apache; **weights NC-tainted** ⚠️ | **WATCH — STORY decode only, not the bottleneck** |
| **CLIPasso** (photo→sketch) | Bezier vector | CC BY-NC-SA ❌ | **REJECT (license) — method reference only** |
| **SVGFusion** | SVG vector | empty repo ❌ | **REJECT (today) — right idea, no code/weights** |
| SD 1.5 / SDXL / SD3.5 / FLUX | raster | mixed (FLUX-dev NC) | **REJECT — flat raster** |
| LCM / Turbo / Lightning / Hyper-SD | raster | mixed (Turbo NC) | **REJECT for live — raster** |
| ControlNet / T2I-Adapter / StreamDiffusion | raster | mixed | **REJECT — raster, heavy, GPU** |
| LayoutGPT / LayoutDM / BLT / LayoutFormer++ | layout boxes | mostly permissive | **REJECT — probabilistic, no collision guarantee** |
| RALF (retrieval layout) | layout | permissive | **WATCH — template-as-soft-preference idea only** |
| AnimateDiff | raster motion | unconfirmed | **REJECT — raster video** |

## 2. The raster-vs-vector reality (straight talk)

The entire diffusion-image branch fails our test, and it's not close. DDPM/LDM, SD1.5/XL/3.5,
FLUX, all distillation (LCM, SD-Turbo, SDXL-Lightning, Hyper-SD), all conditioning (ControlNet,
T2I-Adapter), and real-time systems (StreamDiffusion) emit a **pixel grid decoded by a VAE** —
no path, stroke, or layer. Putting any of it on our board means **vectorizing after the fact**:
lossy, slow, non-deterministic, and it breaks editability. **The famous, high-fidelity models
are exactly what we are NOT.**

Three honest nuances:
- **Diffusion *can* emit geometry — but only when the latent is vector primitives.** SVGFusion
  proves it (FID 4.64 vs SVGDreamer 70.10, layered recolorable paths) — but it shipped **no code
  and no weights**. So the practical winner in vector generation is **not diffusion**; it's
  **autoregressive LLM/VLM SVG-code** (StarVector, OmniSVG, frontier-LLM), which actually runs.
- **Diffusion-on-strokes (SDS) is vector-native but offline-only.** DiffSketcher / diffvg-based
  optimizers produce true editable curves, but minutes-to-hours per asset on a GPU → a
  **pre-bake-and-cache lane**, never live.
- **Diffusion's legit role: a raster *source* vectorized once, offline, for the cache** (FLUX.1-schnell
  Apache → LIVE → cached SVG). But LIVE is tens-of-min-to-hours and over-partitions on anything
  non-trivial. For most of the tail, **a paid Gemini/Claude SVG call or StarVector is cheaper and
  cleaner than diffusion-raster + LIVE.**

**Bottom line:** diffusion is never a live path and never our primary generator. Our
streaming/editable design is *vindicated*, not challenged.

## 3. Pipeline mapping

**Positioning (engine 2)**
- **kiwisolver (Cassowary) — IS the engine. ADOPT.** Anchors (at/near/on/between) → linear
  equality/inequality constraints; soft constraints + priorities = graceful relaxation;
  incremental edit-variables = sub-ms re-solve as actions stream. Editable coords by construction.
  BSD-3, maintained (v1.5.0 Mar 2026), Python-native. Port CoLa's overlap-removal routine for
  non-overlap; do **not** depend on WebCola (unmaintained since ~2019).
- **All learned layout — REJECT for the hot path.** LaySPA (RL-trained) still loses to constraint
  solvers on overlap (0.0257 vs 0.0024). This *validates* "the model never emits coordinates."

**Drawing — live paint**
- **Frontier-LLM-writes-SVG — ADOPT (cheap first try).** Raw SVG markup → parse to primitives for
  measure→paint. No GPU/hosting. The 2024 "weak at positioning" ceiling is partly outdated (Nov 2025
  frontier models handle gradients/positioning). Guardrails: gate to simple named subjects;
  **sanitize** (well-formed XML, bounded viewBox, strip scripts); feed only intrinsic shapes to
  measure — never let it emit final coordinates.
- **SketchRNN — WATCH (low priority).** Archived (repo read-only 2026-01-06), ~100 classes (not 345),
  no vocab gain — only adds *variety* to in-vocab doodles. Not the long-tail answer.

**Drawing — offline asset pre-generation (cache forever)**
- **StarVector 1B/8B — PROTOTYPE (top offline candidate).** Apache-2.0, real SVG, DinoScores
  0.96–0.98 on icons/diagrams/charts. Hard limit (card): "will not work for natural images or
  illustrations" → a **specialized icon/diagram tier**, between exact-asset and QuickDraw. No
  published latency for 8B autoregressive (up to 16k SVG tokens) → **benchmark locally** first.
- **OmniSVG — PROTOTYPE/WATCH.** Released weights (Apache base Qwen2.5-VL-3B), but slow
  (8B ~5.4–98s for 256–4096 tokens) and weight-license "unclear" (dataset CC-BY-NC-SA).
- **DiffSketcher — PROTOTYPE (text→stroke, no photo).** MIT. Draw-on animatable strokes. Offline
  (SDS+diffvg, minutes/prompt, GPU). Real cost: diffvg is a fiddly C++/CMake build + pins an SD
  checkpoint. For the genuinely hard tail, a paid Gemini SVG call may beat maintaining it.
- **diffvg — PROTOTYPE (substrate + fitter).** Apache-2.0; `save_svg()` emits real Bezier/stroke
  SVG. Builds CPU-only when no CUDA. Roles: rendering substrate for optimizers; raster→clean-Bezier
  fitter for the cache.
- **LIVE — PROTOTYPE (narrow raster→SVG bridge).** Apache-2.0. The "we got raster, make it
  composable" converter. Reserve for **simple flat single-subject** assets; gate on path-count/quality.
- **Mermaid/Graphviz codegen — PROTOTYPE (node-edge tier).** Generate DSL → mature deterministic
  layout places nodes → compile-validate → SVG→strokeable paths. MIT, local LLM. These engines own
  their own layout, so it's a self-contained tier our anchor solver does not drive.
- **DeTikZify — WATCH.** Composable TikZ, but MCTS ~10-min/figure, image-conditioned (not text→figure),
  needs TikZ→IR transpile, and **weights carry the Llama license** (not Apache).

**Story (engine 1 / planner)**
- **CLLMs — WATCH (downgraded).** Faster decode, but narration isn't our bottleneck (PAPER math),
  weights are NC-tainted, and it needs a per-base re-distill. Revisit (or EAGLE-3 speculative
  decoding) only if STORY decode becomes a *measured* bottleneck on a self-hosted model.

## 4. Tiered adoption plan

- **ADOPT NOW:** kiwisolver (Positioning); frontier-LLM-writes-SVG (live long-tail first try).
- **PROTOTYPE:** StarVector 1B (offline icons/diagrams); OmniSVG 4B (richer offline SVG);
  DiffSketcher (offline no-photo strokes); diffvg+LIVE (raster→editable bridge);
  Mermaid/Graphviz codegen (node-edge tier).
- **WATCH:** SketchRNN (in-vocab variety); SketchKnitter; DeTikZify (pending TikZ→IR + license);
  SVGFusion (re-check for code drop); RALF (retrieval-template idea); CLLMs/EAGLE-3 (if STORY decode
  becomes a bottleneck).
- **REJECT:** all raster diffusion + distillation + conditioning + video; all learned layout for
  the hot path; CLIPasso (NC + viral ShareAlike); IconShop (no license, monochrome only).

## 5. Highest-leverage opportunities

1. **kiwisolver as the Positioning engine** — highest-confidence win; deterministic, collision-free,
   sub-ms incremental, editable coords by construction. Removes the #1 documented failure of
   LLM-driven systems (layout/overlap; Code2Video & TheoremExplainAgent fail hardest there).
2. **Frontier-LLM-writes-SVG as the live long-tail rung** — lowest-integration editable-vector
   generator; one API call → parseable primitives; collapses a large slice of "named thing, no
   asset" into a cheap composable first try, with parametric→QuickDraw→labeled-box as fallback.
3. **StarVector (offline) as the icon/diagram asset-cache generator** — Apache-2.0, on-domain,
   free-local; also an image→SVG cleaner. Gated on a local latency benchmark + SVG→stroke-IR test.
4. **diffvg/LIVE raster→editable-SVG bridge** — principled escape hatch that keeps "editable forever"
   even for content we got as raster (paid Gemini image / FLUX-schnell). Narrow but principled.
5. **DiffSketcher (offline) for the no-photo text→stroke tail** — MIT, aesthetically closest to a
   whiteboard; fills the gap SketchRNN does *not* (concepts outside QuickDraw's classes).

## 6. Risks, licenses, decisions forced

**Licenses to double-check before shipping:** OmniSVG fine-tuned weights; DeTikZify weights (Llama
license, not Apache); CLLMs weights (Vicuna/ShareGPT NC lineage); CLIPasso (CC-BY-NC-SA, hard reject);
SVGFusion (empty repo). **Clean:** kiwisolver (BSD-3), Mermaid (MIT), DiffSketcher (MIT), diffvg/LIVE
(Apache-2.0), QuickDraw data (CC-BY-4.0, attribute Google), frontier-LLM SVG *output* (unencumbered).

**Measure ourselves (cutoff couldn't confirm):** StarVector/OmniSVG live latency on free-local HW;
**SVG→stroke-order fidelity** (LLM/VLM SVG gives filled paths, not pen order — draw-on animation must
be *derived* from path geometry, unlike QuickDraw which is stroke-native); diffvg/DiffSketcher build
health on target machines; LIVE output-quality gate (over-partitions on non-trivial input).

**Decisions forced:**
1. **Geometry stays deterministic, full stop.** Adopt kiwisolver; never route placement through a
   learned model — not even as a seed.
2. **The generative win is autoregressive SVG *code*, not diffusion.** Architect the Drawing engine's
   generative tiers around *SVG-code-in → parse → measure → paint*; SDS-optimizers + raster-bridge are
   slower offline supplements.
3. **Tier the long tail by subject type, not one model.** No single model spans the tail — the
   *ladder* is the architecture, each rung mapped to a license-cleared, vector-native option.
4. **Don't over-invest in STORY decode speed** — not the bottleneck.
5. **Sanitization boundary between LLM-emitted SVG and the solver.** LLM proposes *what* to draw; the
   solver decides *where*.
