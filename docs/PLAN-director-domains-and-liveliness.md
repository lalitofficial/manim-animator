# PLAN — The Director as a content-classifier; per-domain assets; liveliness layers

*Research-backed, repo-grounded plan. Drafted 2026-06-20.*

This answers a strategic question: **what kinds of video do we make, how does the
system internally decide which kind a topic is, and how do we make the output more
"alive"** (kinetic text, sound, motion polish). It pairs an external research survey
(Part A) with a plan that maps onto code that exists today (Part B–D).

> **On the research's confidence.** A 5-angle deep-research pass fetched 26 sources and
> extracted 119 claims. The **6 content-taxonomy claims were adversarially verified**
> (3-0 / 2-0) in the first run; a **second 3-vote verification pass** then hardened the
> remaining 17 asset/tooling/typography claims: **16 confirmed, 1 corrected (Reactome
> categories), 0 refuted, 0 uncertain.** The corrected facts are baked into Part A below,
> and the full verdict-by-verdict appendix is at the end of this doc. Net: the plan rests
> on verified ground; remaining ⚠ tags are gone.

---

## The big decision, framed

Today the engine has *one* implicit classification: a 4-domain keyword matcher
(`cloud-computing / networking / software / weather`) in
[`semantics.py`](../backend/engine/semantics.py), plus a `mode`
(`learn / story / draw / explain`) the user (or a cue) picks. Everything else —
audience, depth, pacing — is policy in [`director.py`](../backend/engine/director.py).

The question "what *type* of video" is really **two orthogonal questions**, and the
research confirms educational-video classification is naturally multi-axis (the arXiv
lecture-style taxonomy uses *human-presence × instructional-media*; Segel & Heer use
*genre × narrative tactics*). So the recommendation is:

> **The Director should classify every topic on two axes — SUBJECT DOMAIN (what it's
> about) and PRESENTATION FORMAT (how to show it) — and a router maps `(domain, format)`
> to a generation strategy (which asset rung / provider / renderer).** This is internal
> and automatic, not a user dropdown — exactly the "thought engine" you described. The
> user can still *override*, but the default is inferred.

This reframes your bullet list as one coherent mechanism:

| Your idea | Where it lands in the two-axis model |
| --- | --- |
| "Cartoon story type" | format = `narrative-story` (existing `story` mode, "subjects ACT") |
| "Learning: technical / bio / maths…" | **domain** axis (bio, math, physics, CS, history, …) |
| "for bio I have this icon lib" | domain=`biology` → asset strategy = Bioicons candidates |
| "for math, manim generation" | domain=`math` → strategy = LaTeX/Manim (see §B6 — *not* naïvely) |
| "thought engine to direct us, internally" | **the two-axis classifier itself** |
| "animated/typographed text when assets are weak" | format/fallback = `kinetic-text` (§B8) |
| "sound effects" | a client-side SFX layer keyed to stream events (§B9) |

---

# PART A — External research (cited)

### A1. There IS a sensible, finite taxonomy a director can classify into ✅ *verified*

- Educational video styles organize cleanly along **two dimensions**: *level of human
  presence* and *type of instructional media* — explicitly framed as a **design space**
  for *choosing* a style, not just describing one. [arXiv:1801.06050]
- A concrete **10-style taxonomy** derived from 105 student videos: Visible Narrator,
  Filmed Reality, Acted Scenes, Integration of Existing Media, **Textual Presentation**,
  **Digital Animation**, Tutorial/Demo, **Blackboard**, Interview, Handmade Animation —
  each with *checkable* visual conventions (Textual Presentation "necessarily prioritizes
  text"; Digital Animation is "useful for showing relationships or abstract concepts";
  Blackboard is hand-drawn step-by-step). [Springer 10.1186/s41239-021-00295-6]
- **Segel & Heer — 7 narrative-visualization genres** (magazine, annotated chart,
  partitioned poster, **flow chart**, **comic strip**, slide show, **video/animation**),
  organized by *genre × visual-narrative tactics (structuring / highlighting / transition
  guidance) × narrative-structure tactics (ordering / interactivity / messaging)*. A
  director can apply these per beat/scene. [Segel & Heer 2010]

**Takeaway:** our `mode` is a coarse version of the *format* axis; the literature says a
richer, finite, checkable format taxonomy is legitimate and decision-useful.

### A2. Domain asset libraries — open / permissive ✅ *verified (2nd pass)*

- **Bioicons** (`github.com/duerrsimon/bioicons`) — free open-source **SVG** scientific
  icons; **2,829 icons across 43 scientific fields** (life sciences, oncology, neuroscience,
  chemistry, animals, plants, lab apparatus). SVG ⇒ scales infinitely ⇒ programmatic-drawing
  friendly. **License is PER-ICON** — the *repo code* is MIT, but each *icon* carries its
  own (CC0, CC-BY 3.0/4.0, CC-BY-SA, MIT, some BSD); the site says "always cite the
  individual icons and their respective license." ⇒ our importer **must capture per-icon
  license** into `candidates_store`'s `license` field, and CC-BY/CC-BY-SA icons need an
  attribution surface.
- **Reactome Icon Library** — free, **Creative Commons** (main project license CC BY 4.0;
  contributed icons inherit it), every icon in **SVG + EMF + PNG**. Categories (corrected
  from the first pass — there is **no "ion channels" category**): *cell element, cell type,
  compound, human tissue, protein, receptor, transporter* (+ arrow), plus a *Therapeutic*
  group in the displayed library. Good for molecular/cell biology.
- **unDraw** — open illustrations, **no attribution required**, commercial + personal,
  primarily **SVG**, single-accent-color recolorable. **Carve-outs that matter to us:**
  no redistributing illustrations *in packs*, no cloning unDraw as a service, and
  **no AI/ML training without written permission**. Good for *general/everyday/economics*
  scenes — but the AI-training restriction means treat it as a *runtime asset library*, not
  training data, and don't bundle-redistribute the raw set.
- General icon sets already in our wheelhouse: **Tabler** (MIT, vendored), **Lucide**
  (ISC), **Iconify** (aggregator), **Noto / OpenMoji** (emoji, Apache/CC-BY). All
  stroke/flat SVG — same normalization path we already use.
- Also worth a look (from the survey's blog sources): **SciDraw**, **Servier Medical
  Art** (CC-BY) for medical; these are heavier illustrations.

**Takeaway:** Bioicons is the right first domain pack *because it's SVG and large*, but
expect a **usable subset**, not all ~2,829 — our normalizer (§B5) rejects gradients /
over-complex paths by design (drop-don't-repair).

### A3. Programmatic math & physics ✅ *verified (2nd pass)*

- **Manim** (3Blue1Brown / ManimCE) is the standard for math animation, and there's
  active **LLM→Manim** research: **Manimator** (arXiv:2507.14306) — *confirmed* two-stage
  pipeline: LLM₁ turns text/PDF into a structured scene description, LLM₂ emits executable
  Manim Python. **Code2Video** (arXiv:2510.01174) — *confirmed* **Planner→Coder→Critic**
  three-agent loop producing **executable code (not pixel-space video synthesis)**, with a
  VLM critic refining spatial layout. *That planner→coder→critic shape is essentially a
  director→renderer→QA loop — a strong template if we later want LLM-authored scenes.*
- **manim-physics** — *confirmed* pip-installable Manim plugin: 2D rigid mechanics,
  electromagnetism, waves.
- **Schemdraw** — *confirmed* Python, fluent (method-chaining) API for **circuit
  schematics**, **exports SVG** (+ PNG/PDF/EPS) ⇒ fits our SVG pipeline directly.
- Data/charts: **matplotlib/plotly** (SVG export) for economics/statistics. The
  **animated-data-video literature** (CHI'25, "Reflecting on Design Paradigms of Animated
  Data Video Tools," 46 tools surveyed) decomposes such videos into four coordinated
  components — *visual, motion, narrative, audio* — a useful checklist for the data-story
  format.

**Critical caveat (engineering judgment, not from the sources):** **Manim is
video-native** — it produces an mp4 timeline, not a single board-drawable SVG, and not an
incremental stroke stream. **Do not shove Manim into the live-board `SvgProvider`.** The
honest split is in §B6: Manim belongs in the **offline video lane** (`renderer.py`, our
only Manim-aware file); the **live board** wants a lightweight **LaTeX→SVG** equation
path + **schemdraw→SVG** for circuits.

### A4. Kinetic typography ✅ *verified (2nd pass)*

- Kinetic typography "attracts attention more rapidly than static text and improves
  comprehension," but the benefit comes mostly from **sequential presentation that mirrors
  the logic of speech** — a "shared thinking process" — *not* from movement per se.
  [Nature s41599-023-01646-6]
- **And the guardrail:** *excessive / inappropriate* kinetic text **harms** learning —
  fatigue and cognitive overload (cognitive-load theory). Same source. ⇒ Use it
  **purposefully** (emphasis, asset-less beats), never everywhere.
- Foundational refs: the CMU kinetic-typography work (Lee/Forlizzi/Hudson) — a model and
  toolkit for expressing emotion/emphasis through text motion.
- Tooling (all mature): **GSAP SplitText** (splits text to lines/words/chars for
  per-unit animation), **SplitType** (open MIT equivalent), **anime.js**, **Lottie**
  (After-Effects JSON), Remotion/Framer for React. For our SVG board the cheapest path is
  *no dependency*: emit a text-animation primitive and animate per-word reveal in
  `engine.js` with CSS/SVG (§B8).

### A5. Sound + motion polish *(background sources; not re-verified — low-risk common knowledge)*

- **CC0 SFX**: **Freesound** has a dedicated CC0 tag/browse; **Pixabay** SFX
  (royalty-free). BBC Sound Effects (free for personal/educational under their licence).
  These give whoosh/pop/click/chime beds with no attribution burden (CC0).
- Sound in motion graphics is a recognized polish layer; the engagement evidence is
  positive but modest — treat SFX as **perceived-quality lift**, subtle, and **mutable**.
- **The 12 principles of animation** (squash & stretch, anticipation, staging, ease
  in/out, follow-through, exaggeration, …) and **camera moves** (pan / zoom / push-in /
  focus) are the standard levers for "alive." Biggest-lift-least-effort: **ease + a slight
  anticipation/overshoot on entrances**, **staggered reveals**, and a **subtle push-in on
  the active concept** — all paint-time/stream-time, *zero new assets*.

**Sources** (primary unless noted): arXiv:1801.06050 · Springer
10.1186/s41239-021-00295-6 · Segel & Heer 2010 (Narrative Visualization) ·
github.com/duerrsimon/bioicons · reactome.org/icon-info · undraw.co ·
arXiv:2507.14306 (Manimator) · arXiv:2510.01174 (Code2Video) ·
github.com/Matheart/manim-physics · pypi.org/project/schemdraw ·
Nature s41599-023-01646-6 (kinetic typography) · CMU kinetic-typography papers ·
gsap.com SplitText · github.com/lukePeavey/SplitType · freesound.org/browse/tags/CC0 ·
Frontiers fpsyg.2024.1335022 (sound) · StudioBinder (12 principles; camera moves; *blog*).

---

# PART B — The plan, mapped onto our code

### B0. The seams already exist (from the repo grounding)

Adding a domain has **four ready-made entry points** — we are not inventing
infrastructure, we're populating it:

1. **Parametric family** — add a generator in
   [`families.py`](../backend/engine/families.py), register in `CONCEPT_FAMILIES`
   (deterministic, the primary path).
2. **Bundle** — add an entry in
   [`bundles.json`](../backend/engine/bundles.json); toggles a whole domain on/off and is
   honored by `drawing.measure()`'s bundle gate.
3. **Importer → candidates → publish** — like
   [`excalidraw_libraries.py`](../backend/engine/excalidraw_libraries.py) →
   [`candidates_store.py`](../backend/engine/candidates_store.py) → Asset Studio gates →
   `asset_overrides.json`. **This is the Bioicons path.**
4. **New `SvgProvider`** — implement the protocol in
   [`generators.py`](../backend/engine/generators.py); output flows through the same
   `svgnorm` security+normalize gate. **This is the math/physics/LaTeX path.**

And the resolution ladder in [`drawing.py`](../backend/engine/drawing.py) stamps a
`source` at each rung (primitive / character / icon / catalog / sketch / published /
generated / box) — already surfaced in the stream + Studio, so coverage stays honest.

### B1. The two-axis classifier (the "thought engine") — **foundation, build first**

Extend the Director so `direct()` produces, in addition to today's spec:

- **`domain`** (already a field) — expand from 4 tech domains to a real taxonomy (§B2).
- **`fmt`** (NEW) — the presentation format (richer than `mode`).
- **`confidence`** (NEW) — drives the fallback posture (low confidence ⇒ lean on safe
  families + kinetic text instead of guessing a wrong domain icon).

Mechanism — **hybrid, hermetic-first** (consistent with "deterministic core, LLM only for
Story", local-first):

1. **Deterministic floor** — extend `semantics.DOMAINS` with `cues` per domain; add a
   `classify(topic, request) -> (domain, fmt, confidence)`. Free, fast, testable, runs in
   CI. This is the default and the test path.
2. **LLM refinement slot** — when `STORY_PROVIDER` is live, fold a
   `{domain, fmt, confidence}` request into the existing Phase-1 story prompt (we already
   send a domain line). The deterministic result is the floor; the model only *raises*
   confidence or disambiguates. Never required.

New seams (from grounding): `DirectorSpec` fields at
[`director.py:33`](../backend/engine/director.py); domain inference at
[`director.py:181`](../backend/engine/director.py); the `DOMAINS` registry at
[`semantics.py:26`](../backend/engine/semantics.py); preview route
`GET /api/engine/director`. Add `GET /api/engine/classify?topic=` to preview
`(domain, fmt, confidence)` for debugging/observability (surface it in the Studio
provenance panel next to the existing source breakdown).

### B2. Recommended taxonomy

**AXIS 1 — Subject domain → drives ASSETS**

| Domain | Asset strategy |
| --- | --- |
| `general` / everyday | existing composition ladder (families + recipes) — *unchanged* |
| `biology` / life-science | **Bioicons** + Reactome candidates (§B5) |
| `chemistry` | Bioicons chem + molecule/atom families |
| `physics` | schemdraw (circuits) · manim-physics (offline) · vector/wave families |
| `math` | LaTeX→SVG (live) · Manim (offline) (§B6) |
| `computing` / technical | existing cloud/network/software + Tabler catalog |
| `earth` / geography / weather | existing weather + map/terrain families |
| `history` / social | narrative-story + timeline + portrait/figure families |
| `economics` / finance / data | data-viz (matplotlib/plotly → SVG) (§B7) |
| `language` / humanities | **kinetic-text-forward** (few concrete assets) |

**AXIS 2 — Presentation format → drives MODE + renderer strategy**

| Format | Relation to today |
| --- | --- |
| `narrative-story` | = `story` mode ("subjects ACT the process") |
| `concept-map` | = `learn` mode |
| `process` / cause→effect | = `explain` mode |
| `single-illustration` | = `draw` mode |
| `equation-walkthrough` | **NEW** — math |
| `schematic` / diagram | **NEW-ish** — systems / physics / circuits |
| `data-story` | **NEW** — charts |
| `kinetic-text` | **NEW** — abstract / emphasis / asset-less fallback |

The **router** maps `(domain, fmt)` → strategy. Default cell is the existing ladder;
special cells light up the new providers. Low confidence ⇒ `general` + `kinetic-text`
posture (never paint a wrong-domain icon).

### B3. Bio first — **highest coverage-per-effort, uses seam #3 only (data, no engine change)**

1. `scripts/sync_bioicons.py` (mirror of `scripts/sync_excalidraw.py`): walk the Bioicons
   `static/icons/**` SVGs, read **per-icon license metadata**, normalize via `svgnorm`,
   `candidates_store.save_pack("bioicons/<domain>", …)` one pack per scientific domain.
2. Review/publish in **Asset Studio**; the existing `gate_variant` license + renderability
   + complexity gates already protect us (expect a subset to pass — that's correct).
3. Add `biology` / `chemistry` **bundles** in `bundles.json`; add `Domain(...)` entries in
   `semantics.py` so a bio topic rewrites plain nouns → published bio icons.
4. **Honesty:** log coverage per domain via existing `coverage.py`; the % that fell to
   `box` is the work queue.

### B4. Kinetic-text backstop — **the asset-less answer; do early, small**

This is the cleanest synthesis of your "animated text when assets are weak" idea: it maps
exactly onto **rung 6**, the labeled-box backstop in
[`drawing.py`](../backend/engine/drawing.py) (`source="box"`, intentionally never cached
so it can be swapped).

- Replace/augment the static labeled box with a **kinetic-text treatment**: a designed
  word/phrase that animates in (per-word reveal, weight/scale emphasis, underline draw-on).
- Add an **emphasis text primitive** the Story can request directly (a `say` beat can flag
  a key phrase to render as kinetic text, not just narrate it).
- Implementation: new `text-anim` event in [`serialize.py`](../backend/engine/serialize.py)
  / [`stream.py`](../backend/engine/stream.py); animate per-word in `board/engine.js` with
  CSS/SVG (`stroke-dasharray` draw-on we already use for strokes; opacity/transform for
  words). **No JS dependency** — GSAP/SplitType are the reference, not a requirement.
- **Guardrail (Nature):** purposeful only — emphasis + fallback beats — capped per scene
  to avoid cognitive overload.

### B5. Math — split the lane honestly

- **Live board:** a **`LatexSvgProvider`** (rung 3) — render LaTeX via MathJax/KaTeX→SVG
  (or matplotlib mathtext→SVG), normalize through `svgnorm`, draw-on like any stroke. Gives
  `equation-walkthrough` without Manim.
- **Offline video lane:** route `domain=math` to native **Manim** scene templates in
  [`renderer.py`](../backend/renderer.py) (MathTex / Transform / Create) parameterized by
  the DirectorSpec. This is where Manim's video nature is an asset, not a mismatch. The
  Manimator/Code2Video two-stage + critic pattern is the model if we later want
  LLM-authored scenes — but **templates first** (deterministic, hermetic, testable).

### B6. Physics & data

- **Circuits:** `SchemdrawProvider` (rung 3) — schemdraw → SVG → board. Deterministic.
- **Mechanics/EM/waves:** offline via **manim-physics**; live via parametric
  **vector/wave/field families** (arrows already exist as connectors).
- **Economics/stats/data-story:** a `ChartProvider` — matplotlib/plotly → SVG → board,
  parameterized by the director (bar/line/flow). Covers the data-viz genre from Segel & Heer.

### B7. Sound effects — **client-side layer keyed to existing events** (you flagged "maybe later")

- Curate a tiny **CC0** pack (Freesound CC0): `draw` whoosh, `appear` pop, `connect`
  click, `clear`/`done` chime. ~6 sounds.
- The stream already emits `draw / connector / say / clear / done` — the board just plays a
  sound on each event type. No engine change beyond a sound map + a mute toggle.
- Keep it **subtle and mutable**; evidence says modest lift, big downside if loud/annoying.

### B8. Motion / camera polish — **paint-time, zero assets, do alongside sound**

- Ease + slight **anticipation/overshoot** on entrances; **staggered** multi-concept
  reveals; a subtle **camera push-in** on the active concept (we already have a `cinematic`
  flag + camera events in `stream.py`). These are the 12-principles levers with the best
  lift-to-effort.

---

# PART C — Phased rollout (sequenced by leverage × dependency)

| Phase | What | Touches | Why here |
| --- | --- | --- | --- |
| **P0** ✅ *built* | Two-axis classifier (`domain`+`fmt`+`confidence`), deterministic floor, `/api/engine/classify`, tests | `director.py`, `semantics.py`, `app.py` | The brain everything routes through |
| **P1** ✅ *importer built* | **Bioicons** importer → candidates → publish; `biology`/`chemistry` domains | `engine/bioicons.py`, `scripts/sync_bioicons.py`, `semantics.py` | Biggest coverage/effort; data-only, existing seams |
| **P2** ✅ *backstop built* | **Kinetic-text** backstop (emphasis primitive deferred) | `contracts.py`, `drawing.py`, `serialize.py`, `engine.js` | Directly fixes "weak-asset" beats; small, high impact |
| **P3** ◑ *diagrams + equations done* | STEM diagram recipes ✅ + **math equations** (matplotlib mathtext) ✅; Manim animation + schemdraw circuits still deferred | `icons.py`, `mathtext.py`, `drawing.py` | Largest lift; needs the classifier first |
| **P4** ✅ *sound built* | **SFX** (procedural Web Audio) + **motion/camera** polish (motion deferred) | `engine.js` | Polish once breadth exists |
| **P5** | LLM-refined classification; multi-label domains; per-domain story framing | `director.py`, `story.py` | Quality ceiling, optional |

**Recommended first cut:** P0 + P1 + P2. That gives you the internal "director decides"
mechanism, a big bio asset win, and a graceful answer for everything we *can't* draw — the
three things that most change the product feel, all on existing seams.

> **P3 build log (2026-06-20).** Shipped the **no-dependency slice** of math/physics:
> **STEM diagram recipes** in [`icons.py`](../backend/engine/icons.py) — `axes` (coordinate plane
> with arrowheads + ticks), `number line` (double-headed, ticked), `sine wave` (over a faint
> baseline) — plus aliases (coordinate plane/cartesian plane → axes; waveform/sinusoid/sound wave →
> sine wave). They resolve via composition (`source="icon"`) and render on both the live board and
> the offline SVG. Visually verified (rasterized each — arrowheads point correctly, ticks even, sine
> clean). **Design correction:** first built as *families*, but `test_families.py` enforces that
> families are FILLED cartoons (line art fails) — so these moved to the **recipe** rung (the home for
> line icons like sun's rays), which is the correct call. 469 tests green.
> - **Math equations — DONE (user approved adding matplotlib).** New deterministic **math rung**
>   in [`drawing.measure`](../backend/engine/drawing.py): an expression concept (`E = mc^2`,
>   `a^2 + b^2 = c^2`, `\frac{1}{2}`) renders via **matplotlib mathtext** ([`mathtext.py`](../backend/engine/mathtext.py)) →
>   SVG → board strokes. Parsed with the **fill-preserving** svgelements path (`bioicons.svg_to_strokes`,
>   which resolves matplotlib's `<use>` glyph refs and keeps fill → SOLID letters); `svgnorm` is
>   *not* used (it rejects `<use>` and strips fill to hollow outlines). The rung is deterministic +
>   always-on (lazy matplotlib import; only fires on expression-like concepts after all other rungs
>   miss), `source="generated"`, rung 3. Visually verified — `E=mc²`, `a²+b²=c²`, `x=½` typeset
>   correctly. 472 tests green.
>   - **Known limit:** glyph counters (holes in a/b/e/o) fill slightly because subpaths render as
>     separate filled polygons (no even-odd hole subtraction) — legible but imperfect; an even-odd
>     glyph fill is the follow-up.
> - **Still deferred (dep/architecture decisions).** **Manim animation** is already a dep but lives
>   in the *offline v1 lane* (`renderer.py`); wiring true animated math into the v3 board/stream lane
>   is real cross-lane work. **schemdraw** circuits would add a dep (now cheap — matplotlib is in).
>   Data-viz **charts** (matplotlib) need the Story to pass data, not just a concept string.
>
> **P4 build log (2026-06-20).** Shipped the **sound layer** in
> [`board/engine.js`](../board/engine.js): a self-contained procedural **Web Audio** `sfx` module
> (no asset files, no licensing, nothing to source/bundle — strictly cleaner than a CC0 pack and
> mutable). Cues are keyed to the existing stream events — pen-scratch on a `draw`, pop on a
> `pop`/`rise` entrance, tick on a `connector`, descending whoosh on `clear`, a 3-note chime on
> `done` — re-poses are skipped so a gesturing character doesn't chatter. The AudioContext is
> created on the Teach gesture (autoplay-safe); a persistent top-right **🔊/🔇 toggle** mutes it
> (localStorage). Verified behaviorally in headless Chrome: AudioContext created, **3 cues fired
> for 3 draw ops**, **0 audio nodes created while muted**, toggle present + functional, board still
> animates, **no JS errors**. *Subjective tuning (does it sound nice) needs ears — my tools can't
> capture audio.*
> - **Deferred — motion/camera polish.** Left untouched on purpose: the cartoon entrances/ambient
>   motion are already deliberately tuned (recent git history), so adding overshoot/anticipation
>   blindly would regress real work. A targeted pass (e.g. camera push-in on the active concept via
>   the existing `cinematic` flag) is the clean follow-up.
> - **Default ON** (subtle, master level 0.18). Mute persists. Off leaves the board byte-identical.
>
> **P2 build log (2026-06-20).** Shipped the **kinetic-text backstop**: a new `text_anim`
> field on `DrawOp` ([`contracts.py`](../backend/engine/contracts.py)) that `paint()` sets to
> `"kinetic"` whenever the resolved `source == "box"` (the labeled-box rung-6 fallback); it
> flows through [`serialize.py`](../backend/engine/serialize.py) to the board. In
> [`board/engine.js`](../board/engine.js), a `"kinetic"` label reveals **word-by-word** (all
> words placed up front at opacity 0 so the centered layout is stable; per-word opacity
> staggered, capped, and the beat's dwell extended to cover it). Sequential reveal is the
> *evidence-backed* kinetic-typography benefit (Nature: it mirrors the logic of speech), so an
> un-drawable concept now lands as attention-holding typography instead of a static box. End-to-end
> verified: a lesson stream emits `text_anim:"kinetic"` for backstop concepts, `""` for real
> drawings. 468 tests green; `make web` clean (engine.js adds zero warnings). **Visually verified**
> by driving the live board in headless Chrome (Playwright, system-Chrome channel) and capturing a
> frame sequence: the word-by-word reveal is confirmed (frame N shows "Why", N+1 shows "Why it
> matters" with "matters" still fading) and the cartoon backstop cards read as intentional cream
> cards with bold text, not blank boxes.
> - **Deferred:** the **Story-requested emphasis primitive** (kinetic text on *any* beat, not just
>   the backstop) — needs `text_anim` in `PAINT_ATTR_KEYS` + a Beat field. The backstop is the
>   high-value case; emphasis-on-demand is a clean follow-up on the same field.
> - **Scope note:** kinetic reveal is a **live-board** effect (`engine.js` over time). The static
>   `svg.py` export (offline still) keeps rendering the label as one `<text>` — correct, since a
>   still frame can't animate. The Manim offline-video lane is untouched.
>
> **P1 build log (2026-06-20).** Shipped: [`engine/bioicons.py`](../backend/engine/bioicons.py) —
> a **color-preserving** SVG→board-stroke importer (parses each icon's per-shape fill/stroke
> via `svgelements`; `svgnorm` is deliberately *not* used — it flattens to monochrome). License
> + category come from the folder path (`static/icons/<license>/<category>/<name>.svg`), author
> from `icons.json`; **each candidate carries its own license + author** (Bioicons is per-icon
> licensed). One candidate pack per category; `import_domain()` restricts to a subject domain.
> CLI: [`scripts/sync_bioicons.py`](../scripts/sync_bioicons.py) (`make sync-bioicons D=biology`)
> shallow-clones the repo then imports. `biology`/`chemistry` domains got `sets` tokens so
> published packs are domain-tagged (`force` stays empty — Bioicons fills *gaps* only, never
> overrides a cartoon recipe/family). 6 hermetic tests (fixture tree → import → per-icon
> license/author → publish → `measure` source=`published`; color preserved; security reject).
> 467 tests green.
> - **Two deliberate deferrals.** (1) **No `biology`/`chemistry` bundle entries** — published
>   candidates *bypass* the bundle gate (and fall to `core`, always-on), so a bundle wouldn't
>   actually gate them; bundles become meaningful once we add bio *families* (parametric), which
>   the gate does cover. (2) **Author is captured but not yet surfaced** — where attribution
>   appears in an animated video (a credits beat? a Studio panel?) is its own design question;
>   the data is stored on every candidate, ready to surface.
> - **Known limit:** `svgelements`' partial CSS-class support means class-filled icons may import
>   colorless (geometry kept); and complex/gradient icons may exceed the point budget and drop
>   (drop-don't-repair). Expect a usable *subset* of the ~2,829, exactly as the research predicted.
>
> **P0 build log (2026-06-20).** Shipped: 9 subject domains added to `semantics.DOMAINS`
> (biology, chemistry, physics, mathematics, astronomy, earth-science, history, economics,
> language) + `classify(topic) → DomainMatch(domain, confidence, scores)`; `infer_domain`
> now delegates to it. `DirectorSpec` gained `domain_confidence` + an advisory `fmt` property
> (`recommend_format(domain, mode)`); `direct()` populates both (explicit domain ⇒ confidence
> 1.0). New `GET /api/engine/classify` preview route. Fixed a **pre-existing** substring bug
> (the `aws` strong-signal fired inside `laws`) — strong cues are now whole-word. 461 tests
> green (ruff + pyright clean). Next: **P1 Bioicons importer**.

---

# PART D — Risks & what NOT to do

- **Don't put Manim in the live `SvgProvider`.** It's video-native; live board wants
  LaTeX→SVG. (§B5)
- **Don't expect all 2,829 Bioicons to import.** `svgnorm` rejects gradients/over-complex
  paths by design; a usable subset is the honest outcome.
- **Licensing is per-asset, and it bites.** Bioicons icons are individually licensed
  (CC0 / CC-BY / CC-BY-SA / MIT / BSD) — capture each into `candidates_store.license` and
  give CC-BY/-SA an attribution surface. **unDraw forbids AI/ML training and pack
  redistribution** — use it as a runtime library, never as training data or a re-shipped
  bundle. (Both confirmed in the 2nd verification pass.)
- **Don't over-use kinetic text.** Nature (verified): excessive motion → cognitive
  overload. Cap it; reserve for emphasis + fallback.
- **Don't make a wrong-domain guess.** Low classifier confidence ⇒ `general` + kinetic-text,
  not a confidently-wrong bio/math icon. (drop-don't-repair, applied to *classification*.)
- **Keep the deterministic floor.** Every new path must work hermetically (template/fixture)
  so CI stays network-free; LLM only ever *raises* quality.

---

# "And more stuff?" — additional high-leverage levers

- **Per-domain palette** (extend the cartoon palette layer) — bio greens/blues, math
  high-contrast ink, history sepia. Cheap identity signal per genre.
- **Narration as master clock** — ties into the existing Story+Voice+Timeline direction
  (`ROADMAP-story-voice.md`): word↔pixel markers so kinetic text + SFX + draw-on all sync
  to speech. The single biggest "feels produced" upgrade.
- **Confidence-driven coverage dashboard** — per-domain `box`-rate from `coverage.py`,
  surfaced in the Studio, as the standing work queue.
- **Transition/intro/outro library** — reusable scene wipes + a branded title/end card;
  large perceived-quality lift, tiny effort.
- **Captions for free** — `say` beats already carry text ⇒ burn-in captions / accessibility
  with near-zero work.
- **Thumbnail generation** — render the hero beat as a still for the offline video.

---

# Part E — Directed-cartoon pivot (creative direction)

*Added 2026-06-20 after a visual review: the output read as "narrated board preview," not a
directed cartoon. Diagnosis grounded in captured frames + two pipeline maps.*

**Diagnosis.** The pipeline already has the directed-film skeleton (`ScenePlan → Shot →
Action`, a `VERBS` motion set, camera framing by `emotion`/`purpose`, a posed presenter rig
with gesture clips + visemes). It's **starved of input**: the story emits thin scenes (one
hero that "acts once," or generic cards), staging is deterministic banding (sparse), motion is
one discrete swap per shot, the presenter gestures once. So the board shows *presenter + one
prop + dead space*.

**Shipped (committed, visually verified via headless-Chrome capture):**
- **Production polish** (`fix(board)`): status no longer stuck on "Planning…" (cleared on
  playback start); transition **washout** fixed (backgrounds draw solid, not fading from the
  pale empty board); **video-grade captions** (engine 24px+shadow, Studio 20px bold).
- **Water-cycle directed exemplar** (`feat(story)`): a hand-authored, single-scene directed
  cartoon — sun + vapor + cloud + rain + mountain, **revealed shot-by-shot**, each **acting**
  (`rise`/`grow`/`fall`), the presenter **pointing** at each step. Proves the directed pipeline
  produces a rich animated scene (9 action events, 13 draws) and is the **reference shape** the
  LLM-story prompt should target. Applies to learn/draw/explain (story mode keeps its arc).

**CRITICAL insight — the Ollama path bypasses the offline exemplar.** With `STORY_PROVIDER`
unset, the default is **auto → local Ollama**, which takes the `plan_lesson` LLM path
(`lift_beats`), *not* `tell_plan`. So the authored exemplar only fires in **template** mode.
For real per-topic richness on a live (Ollama) setup, the motion/staging/presenter choreography
must be added to **`lift_beats`** (the LLM→plan bridge) and the **LLM prompt** must request
multi-entity staged motion + shot direction. That is the next big lever.

**Resolution status (the 13-point critique).** Done: #1 cartoon-feel (exemplar + lift_beats
motion/points + staging), #2 concept animation (nature verbs rise/grow/fall/flow), #3 direction
(shot-by-shot reveal + presenter points + camera), #4 empty scenes (denser staging), #5 hierarchy
(role-scale), #6 passive presenter (points at each concept), #7 washout (solid backgrounds), #8
status (cleared on play), #9 export captures UI (`?clean=1` board-only surface), #10 silent video
(`/api/engine/audio` server TTS — recorder mux is the 1-line last mile), #11 captions (video-grade),
#12 story/visual disconnect (narration paired to the visual it describes — off-by-one fixed). #13
(assets aren't the bottleneck) — addressed by the direction work above. **Remaining:** the recorder
mux line (in your `record_lesson.js` WIP) and lip-sync (mouth↔audio, Phase 4b); the any-topic brain
is config (`STORY_PROVIDER=gemini`), and lift_beats now makes its output a directed cartoon.

**Roadmap (remaining, priority order):**
- **A2 — LLM→visual richness:** give `lift_beats` the same defaults the exemplar shows (each
  shown concept gets a nature motion verb; presenter points at each; reveal shot-by-shot), and
  strengthen the story prompt to emit process motion + staging. *This is what makes the user's
  Ollama lessons rich.*
- **Staging density:** `compose_cartoon` — scale the hero up, cut dead space, real
  foreground/background composition (the board is bottom-heavy with a tall empty sky).
- **Presenter performance:** mid-scene gestures (not one clip per scene), stronger pointing,
  react/nod; lip-sync wired to word boundaries.
- **B — Production audio + clean export:** server-side TTS (Piper/Kokoro recommended, local) →
  `/api/engine/audio` → muxed into the recorder; a clean board-only export surface (the recorder
  currently films the app UI). `models.resolve_voice()` already resolves a provider; there's no
  audio-file endpoint yet.

---

# Part F — Backlog (left off)

*The running list of everything deferred across the session, priority order. Model-agnostic
items (benefit every lesson incl. Gemini) rank above topic-specific or future-research work.*

**Tier 1 — model-agnostic cartoon quality (every lesson benefits; verifiable via capture)**
- [x] **More process exemplars** — water cycle + **day/night** + **photosynthesis** (the last
      mixes icons with kinetic-text gases). Done; capture-verified.
- [x] **Presenter performance depth** — the host's teaching gesture rotates (point/present/explain),
      `point` dominant + head turns to the concept. Done.
- [ ] **Staging composition** — kill the remaining horizontal dead space (props cluster left-of-centre
      when few); spread across the width; scale up when sparse. *(partly inherent to progressive reveal)*
- [ ] **Camera / cinematic build** — more deliberate push-ins + holds; foreground/background depth.

**Tier 2 — production polish**
- [ ] **Export A/V sync** — tighten the ~2.5 s trailing drift (trim/pad to the narration).
- [ ] **Export lip-sync** — sync the presenter's mouth to the *exported* audio (needs word-timed TTS;
      live board already lip-syncs via Web Speech boundaries).
- [ ] **Recorder mux line** — fold the ffmpeg audio mux into `tools/record_lesson.js` (your WIP).

**Tier 3 — assets & domains**
- [x] **Run the real Bioicons sync** — done; **caught + fixed a real bug** (icons nest under an
      author folder, 4 levels). Biology: 442 imported, 237 renderable (~53%), **98% colored**. Author
      now taken from the folder. Packs are gitignored (the user re-runs `make sync-bioicons` locally).
- [ ] **Surface per-icon author/attribution** (CC-BY) in the Studio + a credits beat. *(author is
      now captured from the folder; surfacing it remains)*
- [ ] **Math glyph counters** — even-odd hole subtraction so a/b/e/o aren't filled (needs a hole
      concept in the Stroke/render model — not a quick fix).
- [ ] **schemdraw circuits / data-viz charts** — need the Story to emit structured specs, not just
      a concept string.
- [ ] **`biology`/`chemistry` bundles** — meaningful once there are bio *families* (published
      candidates bypass the bundle gate today).

**Tier 4 — brain & config (mostly the user's action)**
- [ ] **Gemini end-to-end** — verify a real `STORY_PROVIDER=gemini` lesson (needs an API key).
- [ ] **Emphasis-text primitive** — kinetic text on any beat (not just the backstop): add `text_anim`
      to `PAINT_ATTR_KEYS` + a Beat field.

**Tier 5 — tech debt**
- [ ] **pyright advisory** — svgelements `Optional` noise in bioicons/mathtext/svgnorm (non-blocking).
- [ ] **Studio caption** — the BoardPanel.svelte bump needs `make ui-build` to take effect.

---

# Appendix — Hardened verification

Each claim below was independently checked by **three adversarial verifiers** (fetching the
primary source) and aggregated. **16 confirmed, 1 corrected, 0 refuted, 0 uncertain.**

### CONFIRMED (16)

- **Bioicons — overview** ([github](https://github.com/duerrsimon/bioicons)): free
  open-source SVG icons for biology/chemistry illustration (~40+ categories), copy-to-clipboard
  / download into Inkscape/Illustrator; repo *code* MIT, *icons* per-license (mostly CC0/CC-BY).
- **Bioicons — SVG format**: infinitely scalable SVG, vector ⇒ suited to programmatic
  drawing/animation; per-icon license governs attribution.
- **Bioicons — count & domains**: **2,829 icons across 43 scientific fields** ("~44" rounds
  correctly; exact is 43).
- **Bioicons — per-icon licensing**: per-icon, no blanket license — CC0, CC-BY 3.0/4.0,
  CC-BY-SA, MIT, some BSD; "always cite the individual icons and their respective license."
- **Reactome — license**: free, Creative Commons; contributed icons inherit it (page doesn't
  name the CC variant; the project's main license is CC BY 4.0).
- **Reactome — formats**: every element in SVG + EMF + PNG (PNG at 300 DPI, transparent).
- **unDraw — license**: free, commercial + personal, no attribution; carve-outs = no cloning
  as a service, **no pack redistribution**, **no AI/ML training without written permission**.
- **unDraw — SVG**: primarily SVG (on-the-fly recolorable), optimized PNG also.
- **Manimator** ([arXiv:2507.14306](https://arxiv.org/abs/2507.14306)): open-source
  papers/prompts→Manim via two LLM stages (scene description → executable Manim Python).
- **Code2Video** ([arXiv:2510.01174](https://arxiv.org/abs/2510.01174)): executable-code
  (not pixel-space) education videos via Planner → Coder (scope-guided auto-fix) → VLM Critic.
- **manim-physics** ([github](https://github.com/Matheart/manim-physics)): `pip install`
  Manim plugin — 2D rigid mechanics, electromagnetism, waves.
- **Schemdraw** ([pypi](https://pypi.org/project/schemdraw)): Python circuit schematics via
  fluent API, exports SVG (+ PNG/PDF/EPS). *(PyPI 403'd; verified via readthedocs.)*
- **Kinetic typography — benefit** ([Nature](https://www.nature.com/articles/s41599-023-01646-6)):
  faster attention + comprehension; benefit comes from *sequential presentation mirroring the
  logic of speech*, not movement itself.
- **Kinetic typography — overload** (same): excessive/inappropriate use → fatigue + cognitive
  overload (cognitive-load theory).
- **Narrative-viz spectrum** ([Segel & Heer](https://www.researchgate.net/publication/47544586_Narrative_Visualization_Telling_Stories_with_Data)):
  author-driven↔reader-driven continuum; strongly author-driven (linear order, messaging, low
  interactivity) suits guided storytelling. *(Paper centers on data storytelling; teaching-board
  application is a sound inferred extension.)*
- **Data-video components** ([arXiv:2502.04801](https://arxiv.org/pdf/2502.04801)): CHI'25
  "Reflecting on Design Paradigms of Animated Data Video Tools" — visual / motion / narrative /
  audio, across 46 tools.

### CORRECTED (1)

- **Reactome — category set**: gist right (~7 categories) but names were off. Authoritative
  set (from the icon validator) = **cell element, cell type, compound, human tissue, protein,
  receptor, transporter** (+ arrow); displayed library also shows **Therapeutic**. **No "ion
  channels" category** (the first-pass claim invented it and omitted transporter/therapeutic).

### REFUTED / UNCERTAIN (0)

None — every claim resolved with evidence.
