# Cartoon direction (branch: `cartoon`)

The vision: from a monochrome whiteboard teacher → **animated cartoon lessons for kids**,
eventually cartoon *stories*. Decided (2026-06-17): **cheap / mostly-local**, new branch.

## The honest target: flat-color VECTOR cartoon (not painterly)
Cheap + local + consistent rules out per-frame diffusion (Veo/Sora) as the live renderer —
it's expensive, offline, and uncontrollable for accurate teaching. The reachable, *genuinely
good* cartoon style is **flat-design vector** — colorful fills, layers, gradients, simple
characters and scenes. **Kurzgesagt is the proof**: a beloved educational cartoon made of flat
vector shapes. That look is **compositional and deterministic** — exactly our engine.

The painterly/glowing look (the reference screenshot) needs illustration/diffusion. That's a
*later, offline asset-generation* lane (generate-then-cache styled assets), never the live renderer
— same conclusion as `RESEARCH-generative-drawing.md`, now applied to cartoons.

## The brain transfers; only the renderer changes
Director → Story → **Beats** → placement is renderer-agnostic. The Beat contract stays; we add a
**cartoon renderer** behind it. Nothing from the vector engine is thrown away — it *is* the lesson brain.

## What flat-vector cartoon needs (the build, cheap/local)
1. **Color + fill** (this increment) — drawables carry per-part fill/stroke color; the renderer fills
   closed shapes. (Today: stroke-only/monochrome.)
2. **Gradients + layering** — SVG gradients (cheap), z-ordered parts → depth/richness.
3. **A character system** — a parameterized, *reusable* cartoon presenter (head/body/limbs/face,
   poses, expressions). Consistency is free because it's the same rigged asset (the Animaker model).
4. **Scenes / backgrounds** — full-color backdrops as a background layer (classroom, space, underwater…)
   — cf. afk_teacher's `backgrounds/`.
5. **Richer motion** — beyond draw-on: gesture, bob, pose change, camera pan/zoom, object entrances
   (cf. afk_teacher's `actions/` motion templates).
6. **Offline styled-asset generation (later)** — local/open image models generate colored cartoon
   props/characters in a consistent style, cached + reused. The painterly tail. Never live.

## Style modes
The same recipe renders in a **style**: `whiteboard` (mono strokes, what we have) or `cartoon`
(filled, colored, gradients). Style is a render-time concern, not a per-asset fork — so the
whiteboard product stays intact while cartoon grows alongside.

## Sequence
color/fill → a few colored assets + a scene → a parameterized character → motion → (later) offline
styled-asset gen. Each step ships on this branch, gated by the same green test suite.

## Built so far (2026-06-17)
The flat-vector cartoon vertical slice is in and green — `whiteboard` stays byte-identical, `cartoon`
grows alongside (style is a paint-time decision, never a per-asset fork):

1. **Color + fill ✓** — `palette.py` is the render-time STYLE layer. `paint(thing, p, d, style)` applies
   it: cartoon fills closed shapes + outlines them (concept→color map + authored recipe hex); whiteboard
   STRIPS all color so the mono board is unchanged. Core icon recipes (sun/tree/house/…) carry authored
   per-part hex. The live board (`board/engine.js`) now renders filled `<polygon>`s that ink their
   outline then flood their fill; `svg.py` exports the same.
2. **Gradients + layering ✓** — scene backdrops are vertical 2-stop SVG gradients; `DrawOp.z` orders
   background(0) < things(1) < connectors(2) < presenter(3).
3. **Character system ✓** — `character.py`: one reusable rig, head/hair/face/torso/2 arms/2 legs, with
   **5 poses** (idle/point/wave/think/present) × **4 expressions** (neutral/happy/surprised/curious) ×
   themes (teal/coral/violet). Resolves through the Drawing ladder as `source=character` (pose+expression
   in the cache key → consistency for free). The Story injects a presenter that hosts cartoon lessons.
4. **Scenes / backgrounds ✓** — `palette.scene_for(topic)` routes a topic to a backdrop
   (space/underwater/forest/classroom/sky/…); the stream emits a `background` event (cartoon only).
5. **Richer motion ✓** — `entrance` (draw|pop|rise|fade) + `ambient` (bob|float|sway) ride on each
   DrawOp (cartoon derives tasteful defaults by concept; explicit beat hints win). **Camera pan/zoom ✓**:
   the stream emits `camera` events (focus rect, clamped on-board) that the renderer animates via smooth
   viewBox interpolation — the camera follows the pen to each concept then pulls back to reveal the whole
   board. Gated by `DirectorSpec.cinematic` (cartoon + non-calm energy); calm = classic static wide.
6. **Offline styled-asset gen** — still the later painterly tail (Phase 4), unchanged.

**Studio integration ✓** — cartoon is wired into the Svelte Studio (`frontend/`, the product UI), not just
the vanilla fallback board. `frontend/src/lib/board.js` has full parity (fills, gradient backdrop, z-order,
entrance/ambient motion, camera viewBox animation) + a **style chip** (cartoon/whiteboard) in `App.svelte`,
`style` threaded through `api.js`, and the spec panel shows style + a 🎥 when cinematic. Ambient `@keyframes`
live in the global `app.css` (Svelte scopes component keyframes — they must be global for the JS-set
`animation` to resolve). `make ui-build` then `make dev` → http://127.0.0.1:8000/ . The vanilla
`board/engine.js` mirrors the same cartoon+camera rendering (the fallback when the Studio isn't built).

**Recipe coverage:** `cartoon_recipes.json` now holds ~98 colored teaching icons (mass-authored by a
workflow, each render-validated): animals, nature, space, body, objects, food, transport, math + the
original science/civics set.

**Colored icon coverage:** `cartoon_recipes.json` holds colored recipes that OVERRIDE the mono
`icon_recipes.json` (precedence: hand-built core > cartoon_recipes > icon_recipes). 16 high-value
teaching nouns added so far (heart/brain/rocket/atom/fish/bird/volcano/gear/clock/magnet/leaf/eye/
lightbulb/book/battery/earth). Add more there — validate they render before committing.

Verify: `make bench-draw` writes `build/engine/cartoon_demo.svg`; the Director maps `audience=child`
→ cartoon, and the board has a cartoon/whiteboard style chip. Tests: `tests/test_style.py`,
`tests/test_character.py` (+ existing suite stays green — whiteboard untouched). An adversarial
multi-agent review hardened the slice (closed-edge render regression, z-layer wiring, dark-scene label
contrast, warm default fill) — see NOTEBOOK §L7.

**Next highest-leverage:** a real `STORY_PROVIDER` so concepts are concrete drawable nouns (then the
~98-icon colored ladder lights up instead of placeholder cards — this is now the single biggest visible
win), per-scene camera choreography in story mode, prop/scenery sets per backdrop, and the offline
styled-asset gen tail (Phase 4).
