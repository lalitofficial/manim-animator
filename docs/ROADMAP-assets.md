# Asset & Data Roadmap — character life + coverage, without breaking the style

Status: **A DONE** (character life) · **B DONE via pivot** — BioIcons ingest proved too messy (clip-paths/holes/background rects); science delivered as composed FAMILIES instead (NOTEBOOK §B10) · Owner: cartoon branch · Companion to [CARTOON.md](CARTOON.md),
[ARCHITECTURE.md](ARCHITECTURE.md), NOTEBOOK §B8–B9.

This sequences two independent workstreams that extend the engine with external resources:

- **A — Character life:** mine Meta's *Amateur Drawings* annotations → proportion priors + a
  pose library + a rig motion layer, so the presenter and story characters **act** (gesture,
  walk in, react) instead of CSS-bobbing. Driven by the `emotion`/`action` Director we already built.
- **B — Coverage:** a **normalization gateway** that ingests license-clean flat SVG (BioIcons
  science first) into the *one* families ladder, so science lessons stop boxing.

Neither replaces the Director — these are **asset/data layers feeding its decisions**. The
Director still decides what's on screen, where, how big (roles), and how it feels (emotion).

---

## The governing law (read first)

Kurzgesagt's power is **ruthless style consistency**. Every external source resolves into exactly
one bucket, and the bucket is non-negotiable:

| Bucket | What | Ingest path | Style risk |
| --- | --- | --- | --- |
| **1 — DATA** | joints, scene graphs | mine priors → **render in OUR style** | none |
| **2 — flat/stroke SVG** | BioIcons-flat, OpenMoji | `svgnorm` → recolor → families ladder | low *if* style-gated |
| **3 — raster / pre-shaded / gradient** | most Kenney, Twemoji, Noto | **backgrounds only**, never actors | fatal as actors |

**Rule:** a bucket-3 asset may never be a foreground actor. That single mistake turns a film into a
ransom-note collage. Backgrounds (behind composed actors) are the only safe use.

**License law:** vendor only **CC0 / CC-BY / MIT**. Reject **CC-BY-SA** (viral copyleft), **-NC**
(non-commercial), and unknown. Raw datasets stay **out of the repo** (gitignored); we commit only
(a) *derived statistical priors* (proportion ratios, pose angles — measurements, not the copyrighted
images) and (b) normalized recipes from permissive icons, each with attribution in `NOTICE.md`.

---

## Workstream A — Character life (Meta AnimatedDrawings)

**Source:** <https://github.com/facebookresearch/AnimatedDrawings> · code+weights+data **MIT**.
**Dataset:** ~178k amateur/childlike human figures, each annotated with a bounding box, a segmentation
mask, and **16 joint keypoints**. Split: `amateur_drawings_annotations.json` (**~275MB**) vs
`amateur_drawings.tar` (**~50GB images**). **We need only the 275MB annotations** — metadata-first.

**The skeleton (maps ~1:1 onto our rig):**
```
root → hip → torso → neck
torso → {left,right}_shoulder → _elbow → _hand
root  → {left,right}_hip      → _knee  → _foot          (16 joints)
```
Our `character.py` rig is **already angle-based** — `_limb(shoulder, angle_deg, length)` per arm/leg,
with proportions in constants (`_HEAD_R`, `_SHOULDER_X/Y`, `_HIP_X/Y`). So **a mined pose is literally
a table of limb angles**, and proportion priors retune those constants. No new rig architecture — we
feed the one we have. We **do not** adopt their ARAP mesh-deform (that animates raster drawings; we
synthesize vectors).

### Phases

- **A0 · Acquire (manual, gitignored).** Download `amateur_drawings_annotations.json` to
  `backend/engine/assets/animateddrawings/` (gitignored). Document provenance + MIT in `NOTICE.md`.
  *No images.* Acceptance: file present, loader reads it.

- **A1 · Loader + filter** (`tools/ad_mine.py`). Parse the JSON; for each figure normalize the 16
  joints into our root-centered, height-normalized frame. **Filter to clean figures:** all 16 joints
  present, plausible limb ratios, front-facing-ish, not degenerate. Log the keep-rate. Acceptance: a
  validated in-memory table of N≥20k clean poses; schema documented below.

- **A2 · Proportion priors → retune the rig.** Across the clean set compute median limb-length ratios
  (head, neck, torso, upper/lower arm, upper/lower leg) relative to standing height + their spread.
  Emit `backend/engine/character_proportions.json` (a dozen numbers). Update `character.py` constants
  to the childlike-cluster medians. Acceptance: rig renders with data-derived proportions; a
  before/after contact sheet; whiteboard rig unchanged unless we choose to adopt.

- **A3 · Pose library** (`pose_library.json`). Convert each clean figure to **limb angles** in our
  rig's convention (the args `_limb`/`_bent_limb` already take). Canonicalize (mirror so "pointing"
  isn't split L/R; scale-normalize). Cluster (k-means or angular binning) → ~30–60 centroids;
  hand-label clusters → semantic poses (`wave`, `point_l/r`, `cheer`, `walk_a/b`, `hands_hips`,
  `jump`, `sit`, `lean`, `shrug`, `think`, `idle`). Emit a name→joint-angles table. Acceptance: ≥30
  named poses; each renders as a recognizable rig on a contact sheet; `POSES` in `character.py` grows
  from 5 → library size.

- **A4 · Motion layer (deterministic tween).** Extend `character.build(pose)` to accept a library pose
  (angles → limb geometry, generalizing the current 5-pose switch). Add
  `interpolate(pose_a, pose_b, t)` → per-frame rig, and `perform(sequence)` → a keyframed clip
  (e.g. `wave` = idle→arm-up→arm-down×2). This is the engine that makes the rig *move*. Acceptance:
  a multi-frame gesture renders to an SVG/GIF strip; deterministic + hermetic (no dataset at runtime —
  only the committed `pose_library.json`).

- **A5 · Wire to the Director.** Map the layer onto what we already emit:
  `action(point) → point pose hold`, `emotion(joyful) → cheer`, scene-entrance → `walk_in`,
  `emotion(tense) → lean/still`. The stream emits pose keyframes; both renderers
  (`frontend/src/lib/board.js`, `board/engine.js`) interpolate the rig (they already animate
  `viewBox` + ambient — same rAF pattern). Acceptance: a directed lesson shows the host *gesturing in
  time with narration*, mood-appropriate; tests assert the emitted pose sequence per action/emotion.

- **A6 · (future) BVH motion retarget.** Adopt their motion clips (walk/dance/jump BVH) retargeted to
  our 16-joint skeleton → real locomotion. Needs a BVH parser + retarget; bigger; after A5 proves out.

**Pose/proportion priors are DERIVED MEASUREMENTS from MIT data → safe to commit.** The raw 275MB and
the 50GB images never enter the repo or the runtime.

### Schemas (A)

```jsonc
// amateur_drawings_annotations.json  (their format, per drawing — confirm exact keys at A1)
{ "<image_id>": { "bbox": [x,y,w,h],
                  "mask": [[x,y], ...],                 // polygon
                  "joints": { "root":[x,y], "hip":[x,y], "neck":[x,y],
                              "left_shoulder":[x,y], "left_elbow":[x,y], "left_hand":[x,y],
                              "right_shoulder":[x,y], ... } } }

// character_proportions.json  (we emit — A2)
{ "head_r": 0.30, "neck_len": 0.08, "torso_len": 0.40,
  "upper_arm": 0.24, "lower_arm": 0.22, "thigh": 0.26, "shin": 0.24,
  "shoulder_x": 0.26, "hip_x": 0.13, "_spread": { ... } }

// pose_library.json  (we emit — A3; angles in our _limb() convention, degrees)
{ "cheer":      { "l_arm": [250,0.42], "r_arm": [110,0.46], "l_leg": [255,0.44], "r_leg": [285,0.44] },
  "point_r":    { "l_arm": [250,0.42], "r_arm": [35,0.50],  ... },
  "walk_a":     { ... }, "_meta": { "n_figures": 178000, "n_clean": 41230, "clusters": 48 } }
```

---

## Workstream B — Coverage (normalization gateway → BioIcons science)

**Goal:** science lessons (photosynthesis, the cell, DNA, neurons) draw real icons, not boxes. Families
cover everyday concepts; science is the missing domain.

**The gateway is the product**, not any single pack. One pipeline turns *any* license-clean flat SVG
into a families-ladder recipe in our style:

- **B0 · `tools/ingest_svg.py`** — `svg + concept + source + license →` (1) `svgnorm` sanitize
  (reject scripts/external refs), flatten transforms, curves→polylines, normalize to the board box;
  (2) **recolor pass** — assign palette fills to closed regions, palette ink to strokes (drop authored
  gradients); (3) **style gate** — reject too-many-paths / too-detailed / has-gradient / non-flat
  (machine-checkable: path-count, point-count, fill-type); (4) emit a colored recipe (strokes JSON)
  tagged `source` + `license`. Acceptance: a CC-BY SVG in → a normalized, recolored, style-passing
  recipe out, or a logged rejection reason.

- **B1 · License gate + manifest.** `assets_manifest.json` maps each ingested asset → `{source, license,
  url}`; only **CC0/CC-BY/MIT** pass; CC-BY attribution flows to `NOTICE.md`. Acceptance: nothing
  vendors without a manifest entry; a CI check fails on an unlicensed asset.

- **B2 · BioIcons ingest.** <https://bioicons.com> — filter by license (per-icon, **mixed**) + by the
  style gate + by education relevance (cell/organ/molecule/DNA/neuron/lab). Vendor passing ones as
  `science_recipes.json`; merge into `icons.compose` precedence **below families, above mono** (or its
  own "science" rung). Acceptance: photosynthesis/cell/DNA lessons compile with **0 boxes** for the
  science nouns; source=`bioicons` shows in the Studio breakdown.

- **B3 · (optional, gated) OpenMoji-flat** — only if **CC-BY-SA is cleared** for our use; otherwise
  skip. Same gateway. **Twemoji/Noto: skip as actors** (gradient → bucket 3).

---

## Cross-cutting / later tiers (context, not now)

- **Kenney / OpenGameArt (CC0) → a SEPARATE background-layer system**, not the icon ladder. Pre-made
  sky/terrain/water *layers* behind composed actors (bucket 3 is fine *as background*). Future.
- **Visual Genome / Open Images → Director layout priors.** Mine scene graphs ("cloud above mountain",
  "person beside tree") → staging hints for `compose_cartoon`. Our band-staging already approximates
  this; a data-driven refinement is a *later* Director upgrade.
- **AnimeRun / LinkTo-Anime → learned inbetweening.** Far future; only if we want motion smoothing
  beyond deterministic tweening.

---

## Sequencing & recommendation

```
A (character life)  ──A0─A1─A2─A3─A4─A5──▶ presenter & characters ACT     [MIT, zero style risk]
B (coverage)        ──B0─B1─B2────────────▶ science lessons stop boxing    [needs license discipline]
   (independent — can run in parallel; both feed the existing Director)
```

**Recommended order: A first.** It's the unique differentiator (life/motion), MIT-clean end-to-end,
zero style risk (we render our own rig), and it cashes in the `emotion`/`action` Director we just
built. **B second** — high-value science coverage, but it lives or dies on the style gate + license
discipline, so the gateway (B0/B1) must be solid before ingesting anything.

**Deprioritized** (vs the initial stack): generic SVG/Iconify rungs (we already vendor 1,795 Lucide +
277 composed concepts — diminishing returns), and emoji rungs (a *second* style + stickier licenses).
After the families work, the bottleneck isn't more static props — it's **motion (A)** and **one missing
domain (B)**.

## Acceptance posture (project ethos: verify, don't assert)

- **Machine-checkable** where possible: pose-library size, proportion ratios, box-rate on a topic
  corpus, style-gate pass/reject counts, license-manifest completeness.
- **Visual** where pixels matter: contact sheets (poses, ingested icons) + a directed lesson render,
  Read back as PNG (`qlmanage`), per the §"verify visually" rule in the cartoon memory.
- Every rung stays **hermetic** at runtime — derived priors + vendored recipes are committed; raw
  datasets are external acquisition steps, never runtime deps.

## Sources

- AnimatedDrawings — <https://github.com/facebookresearch/AnimatedDrawings> · blog
  <https://ai.meta.com/blog/ai-dataset-animation-drawings/> · paper <https://arxiv.org/pdf/2303.12741>
- BioIcons <https://bioicons.com> · Kenney <https://kenney.nl/assets> · OpenMoji <https://openmoji.org>
- Visual Genome <https://homes.cs.washington.edu/~ranjay/visualgenome/> · AnimeRun
  <https://lisiyao21.github.io/projects/AnimeRun>
