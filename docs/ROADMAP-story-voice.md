# Story + Voice + Timeline — Roadmap

The plan for the next big push: **Story Generation (the complete workflow)** and **Voice
syncing + presentation**. Grounded in [NOTEBOOK.md](../NOTEBOOK.md) (why) and the ecosystem
research below. Companion to [ARCHITECTURE.md](ARCHITECTURE.md) (the measure→position→route→paint
engines) — this doc adds the **time/choreography/voice** layer on top of them.

Status: **design — no implementation yet** · 2026-06-18 · decisions §0 locked with Lalit.

---

## 0. Decisions locked

| Decision | Choice | Why |
|---|---|---|
| **Voice provider** | **Free-local audio-gen default (HeadTTS-w/-Kokoro, *validate first*) + Web Speech bootstrap-only + `VOICE_PROVIDER` knob** | "Free now, better later." A *local* free path can still reach the lip-sync bar. The clean "audio + phoneme + Oculus-viseme timings in one call" is specifically **HeadTTS** (which wraps a timestamped Kokoro ONNX) — Kokoro core/other wrappers vary, so **validate the exact provider before Phase 5** (§V0) and keep a phoneme→viseme fallback. ElevenLabs/Azure = a one-line paid swap later. Mirrors `STORY_PROVIDER` local-first (NOTEBOOK M2). |
| **Target surface** | **Live streaming board** | The product per [CLAUDE.md](../CLAUDE.md). Offline mp4 falls out of the same IR later. |
| **Lip-sync fidelity** | **Viseme lip-sync, 5–6 mouth shapes** | Reads as real speech; the rig is ~80% there (NOTEBOOK research). Requires the local Kokoro path (Web Speech can't deliver it). |
| **Story validity** | **Typed structured decoding** — Ollama-native JSON-schema `format` first; Outlines/Instructor as escalation | Fixes under-produced/malformed story at the source: `minItems` forces min scene/narration counts (NOTEBOOK K7). Ollama-native = zero new dep on the models.py surface; Outlines only if native is too weak (it needs a non-Ollama serving path that would fork the single provider surface, M1). |
| **Rig model** | **DragonBones-style (MIT)** — bones/slots/attachments/pose/clip/mouthTrack | Same data model as Spine, license-clean: DragonBonesJS is MIT; Spine runtimes need a paid seat. We re-implement the *concepts* in character.py — we don't vendor either runtime (NOTEBOOK J5). |

---

## 1. The core idea — narration is the master clock

The current stream is a **queue**: `say` blocks all drawing, drawing blocks the next draw, there
is no shared time. We move to a **timeline** with parallel tracks (draw / speech / character /
camera). But the sharper framing that unifies *both* work items:

> **Narration is the master clock. A concept is revealed when it is spoken. A named MARKER is the
> seam between words and pixels.**

This is the third application of the repo's founding move (NOTEBOOK **B4/H3**: *take geometry out
of the LLM* → deterministic Drawing + Positioning). Apply it again to **time**:

- The **LLM writes the SCRIPT** — narration words + which concepts exist + how they relate + the
  arc/emotion. That is all it is good at (NOTEBOOK K7/M5/M9).
- A **deterministic CHOREOGRAPHER** aligns visuals to words: reveal `vapor` when the narration says
  "vapor", point the host at it, move the camera, stagger the rays. No model — same spirit as
  kiwisolver positioning. **This is the new "take the LLM out of choreography" engine.**
- The **VOICE layer** resolves marker *times* (live word-boundaries, or pre-generated audio
  timestamps) and drives the mouth from a viseme track.

The mechanism is proven by **Motion Canvas**: a marker is just `{name, targetTime_seconds}`, and
audio + every track anchor to it *by name*. It degrades perfectly to our live-streaming case —
a marker resolves **live** (when the word is spoken) *or* **ahead of time** (from audio timestamps).

---

## 2. Where we are (current state)

We are closer than it looks — three pieces already exist:

- **[plan.py](../backend/engine/plan.py)** — a real direction grammar
  (`LessonPlan→ScenePlan→Shot→Action`), a closed motion verb vocabulary
  (enter/exit/rise/fall/flow/pulse/point/look/…), emotion/purpose per scene. But shots are consumed
  as a **sequential queue**, and narration (`Shot.say`) is **not bound to visuals with time**.
- **[character.py](../backend/engine/character.py)** — a Spine-shaped rig: `pose_library.json` =
  setup-poses, `interpolate()`/`perform()`/`clip_drawables()` = a keyframe engine, look-at-target,
  idle-life. **Gap: the mouth is frozen per-expression** — no mouth *slot*, no viseme track.
- The **board flipbook** ([board.js `playClip`](../frontend/src/lib/board.js), `op.frames`/`op.fps`).
  But the main `play()` loop is `await`-per-event — **`say` blocks drawing**; no master clock.

Hard limits today (confirmed in code):
- `/api/engine/lesson` **materializes all events into a list** — it is not actually streamed
  ([stream.py](../backend/engine/stream.py)).
- Voice = `speechSynthesis` only. **Cannot capture its audio** (so no Rhubarb on it); word-boundary
  events are **unreliable off desktop-Chrome/Safari + local voices**; `elapsedTime` units differ per
  browser. **Zero sync** between speech and drawing ([board/engine.js `speak()`](../board/engine.js)).
- Narration is a flat `list[str]`; `say_dwell` is one global multiplier. No per-event duration, no
  marker, no parallelism.

---

## 3. The Timeline IR (the spine)

One scene = parallel **tracks** whose events anchor to **markers** (narration boundaries) + relative
offsets, on a master clock that is *either* live TTS *or* a pre-gen audio file.

```jsonc
{
  "version": 1,
  "scene": "evaporation",
  "audio": { "src": "vo/scene1.mp3", "offset": 0.0 },   // Path A only; absent for live TTS
  "markers": [                                            // the VO seam — names + (resolved) times
    { "name": "m:vapor", "t": 2.10 },                    // t filled by the voice layer (or live)
    { "name": "m:cloud", "t": 5.40 }
  ],
  "tracks": {
    "speech":    [ { "say": "Water turns to vapor and rises.", "at": 0,
                     "marks": { "vapor": "m:vapor" } } ],         // word→marker bindings
    "draw":      [ { "op": "draw", "target": "vapor", "at": "m:vapor",      "dur": 0.8, "ease": "power2.out" },
                   { "op": "draw", "target": "cloud", "at": "m:cloud+=0.2", "dur": 0.6 },
                   { "op": "connector", "from": "vapor", "to": "cloud", "at": "m:cloud+=0.4" } ],
    "character": [ { "op": "point", "actor": "host", "target": "vapor", "at": "m:vapor" },
                   { "track": "mouth", "cues": [ /* viseme stream — §5 */ ] } ],
    "camera":    [ { "prop": "focus", "to": "cloud", "at": "m:cloud", "ms": 700 } ]
  }
}
```

Design rules (locked from the research):

- **Seconds, one clock.** `<` = previous start, `>` = previous end (GSAP convention; documented so
  we never trip the anime.js inversion). `at` accepts absolute (`3`), relative (`+=0.5`/`-=0.5`),
  **marker names** (`m:vapor+=0.2`), and **entity ids** (`vapor>`), so timelines are order-independent.
- **Easing = a closed string enum** (`linear`/`power2.out`/`back.out`/`stepped`/…) compiled to bezier
  under the hood — never raw bezier handles (Lottie's worst ergonomic). Unknown easing → drop to linear.
- **`draw: 0..1` is a first-class property** mapped to `stroke-dashoffset` over the path length the
  Drawing engine already measures (extent-honesty, NOTEBOOK B7). (Promotes Lottie's trim-path idea.)
- **Universal animated-property wrapper** (Lottie's `{a,k}`, JSON-idiomatic): `{ "v": x }` = static,
  `{ "k": [ {t,v,ease} ] }` = animated. One sampler for the whole system.
- **Drop-don't-repair survives**: every event/keyframe/marker parses independently; a bad one is
  dropped, never patched (house rule).
- **Block layer for the planner** (`chain`/`all`/`sequence`/`stagger`, from Motion Canvas + GSAP) so
  the choreographer emits *structure* ("stagger these 3 rays while the host talks") without computing
  absolute times. The `at` layer handles precise overlaps.

**This generalizes the current stream; it is not a renderer rewrite.** Today's
`start/say/draw/connector/clear/done` flatten into `speech`/`draw` tracks; `clear` becomes a scene
boundary (a master-timeline cut).

---

## 4. Story generation — the complete workflow

Unify on the **directed plan** ([plan.py](../backend/engine/plan.py)) as the canonical IR; keep flat
Beats as the degenerate `lift_beats` case (already true, NOTEBOOK N1). Split into a **script** stage
(LLM) and a **choreograph** stage (deterministic):

```
request ─▶ Director (DirectorSpec) ─▶ SCRIPT  (LLM: narration + concepts + relations + arc/emotion)
                                         │
                                         ▼
                                    CHOREOGRAPH  (deterministic: anchor reveals/points/camera to markers)
                                         │
                                         ▼
                          measure → position → route → paint   (the §ARCHITECTURE engines, unchanged)
                                         │
                                         ▼
                                   TIMELINE IR (§3)  ─▶ stream ─▶ board
```

- **Script stage (LLM, local-first, the only model call).** Emits narration **with inline concept
  references** — e.g. `"Water turns to [vapor] and forms [clouds]."` — plus the concept/relation/
  arc/emotion metadata plan.py already wants. Force validity with **typed structured decoding**
  (Ollama-native JSON-schema `format`; Outlines/Instructor only if needed) — `minItems` on
  scenes/narration so the model can't under-produce — backed by `sanitize_beats`-style defensive
  drop-don't-repair parsing (NOTEBOOK K7/M5). The **bring-your-own-IR endpoint**
  (`POST /api/engine/animate`, NOTEBOOK M9) stays the quality escape hatch for a strong external model.
- **Choreograph stage (new, deterministic).** Turns inline references into markers; anchors each
  concept's reveal to the marker that mentions it; makes the host `look`/`point` at the narrated
  concept (we already compute `turn` toward a target in plan.py); assigns camera focus; applies the
  emotion pacing. **Machine-benchmarkable like positioning** — see §7 gates.
- **Director extensions.** Add timeline knobs to `DirectorSpec`: marker density (how finely narration
  segments), lip-sync on/off, per-scene tempo — alongside the existing energy/draw_speed/say_dwell.

Payoff: the workflow finally closes **with timing** — topic → script → choreographed, voiced
timeline → board — with provenance visible in Studio (extends NOTEBOOK K8/N3 honesty instrumentation).

**Sequencing (important):** the *minimal* **Script V0** — the schema above + fixing the current
"stops after 1–2 lines" truncation — ships **first** (§7 Phase 1), because story is the weakest link
today *and* the choreographer depends on its `[concept]` markers / concepts / relations. The heavier
**hardening** (provider provenance, BYO-IR polish, local-model robustness, Studio debugging) is an
**ongoing parallel track**, not an end-phase. Don't let voice/timeline work outrun Script V0.

---

## 5. Voice + lip-sync — two paths, one contract

**One event contract, two voice paths**, both emitting the same `marker`/`word`/`mouth` events on one
clock, so the board has a single code path.

### Path A — free-local audio-gen (the default)
**HeadTTS (wrapping a timestamped Kokoro-82M ONNX)** — local, $0, Kokoro is Apache-2.0. HeadTTS is the
provider that claims **audio + phoneme timestamps + Oculus visemes in one response**; *Kokoro core and
other wrappers vary* (the Python `KPipeline` gives token start/end times but not necessarily visemes,
and JS/ONNX paths often approximate). **So §V0 validates the exact local provider first**, and the
contract degrades through a fallback chain rather than assuming visemes exist:

1. provider returns **visemes** → map → mouth poses (best);
2. provider returns **phonemes + times** → phoneme→viseme map → poses;
3. provider returns **word times only** → distribute estimated visemes per word window (vowel-weighted);
4. (bring-your-own audio) run a forced aligner (WhisperX) for word times, then (3).

Server pre-resolves marker times, ships `audio + timeline`, board plays against `audio.currentTime`.
Works on **every** browser/OS, consistent voice. Live-board latency is hidden by the plan-ahead model
(generate scene 1's audio, play it while generating scene 2; Kokoro-82M is small/CPU-fast — confirm in §V0).

### Path B — Web Speech (zero-install BOOTSTRAP ONLY — never the trusted sync path)
`speechSynthesis` gated to `localService===true` voices. `phonemize.js` (text→ARPAbet→viseme) places
mouth cues inside each word's `onboundary` window, vowel-weighted + smoothed + ~60 ms min-hold.
Normalize `elapsedTime` units per browser; degrade to a time-estimated flutter where boundaries don't
fire (Linux/Android/iOS). **It cannot do trustworthy sync** (no audio capture, non-portable boundaries,
per-browser unit drift) — it exists to prove the rig + scheduler with zero install and to run a no-setup
demo. Real sync is always Path A. **Do not let Path B creep into being the product path.**

### Later — paid upgrade (one-line swap)
`VOICE_PROVIDER = webspeech | kokoro | headtts | elevenlabs | azure`. ElevenLabs (`with-timestamps`,
per-character) and Azure (viseme IDs 0–21) plug into the *same* marker/mouth contract.

### The mouth-slot rig change (the one real gap)
Make the **mouth a SLOT** (DragonBones-style, MIT — see §11): `build()` emits the mouth as a separate
addressable element plus the *set* of mouth-shape attachments (rest / closed / narrow / mid-open /
wide-open / round). The body keeps playing its server-rendered gesture flipbook; the **mouth is a small
client-swappable layer** driven by the viseme track (or live amplitude — Rive's 1D-blend idea). Avoids
exploding the flipbook frame count; works for both voice paths.

### Character rig spec (DragonBones-style — MIT, re-implemented in `character.py`)
Six elements, mapping the DragonBones data model onto what we already have:

| Element | What | Status |
|---|---|---|
| **bones** | 2-segment limb hierarchy + the head group | ✅ in `character.py` |
| **poses** | named static bone maps (setup-poses) | ✅ `pose_library.json` |
| **clips** | keyframed bone tracks over time + easing | ✅ `perform()`/`interpolate()` |
| **slots** | z-ordered draw slots naming *which* attachment shows (the indirection) | **NEW** |
| **attachments** | the swappable shapes a slot can show; mouth: rest/closed/narrow/mid/wide/round | **NEW** |
| **mouthTrack** | stepped `[{start,end,pose}]` viseme timeline driving the mouth slot | **NEW** (the lip-sync seam) |

Licensing: follow **DragonBonesJS (MIT)**; treat Spine as conceptual confirmation only — **don't vendor
Spine runtimes** (the Spine Runtimes License requires a paid seat). Concepts aren't licensable, but the
MIT reference keeps us clean (NOTEBOOK J5).

**Viseme → 5–6 poses** (collapse the standard sets):

| Pose | Rhubarb (A–X) | Oculus viseme | ARPAbet |
|---|---|---|---|
| rest / closed | X, A | sil, PP | (silence), P B M |
| narrow / teeth | B, G | FF, SS, CH, DD, kk, nn | F V, S Z, CH SH, T D, K G, N L |
| mid-open | C | E, I | EH AE, IH IY |
| wide-open | D | aa | AA AO |
| round / pucker | E, F | O, U | OW, UW UH W |

### Mouth-cue track shape
```jsonc
{ "track": "mouth", "cues": [
  { "start": 1.20, "end": 1.27, "pose": "wide" },
  { "start": 1.27, "end": 1.45, "pose": "narrow" }
] }
```

---

## 6. Presentation — the board scheduler

Replace the `await`-queue [`play()`](../board/engine.js) with a **master-clock scheduler** that
resolves markers and runs tracks in parallel. The visible product wins:

- **Draw while talking** — parallel `draw`+`speech` tracks kill the "say a sentence, *then* draw" stutter.
- **Karaoke captions** — highlight each word as it is spoken (word markers).
- **Host points/looks at the concept as it narrates it**, and the **mouth moves with speech**.
- **Camera moves anchored to narration beats** (staging — bands/host/backdrop — already done, M10).

**Phase 2 (the scheduler) keeps the current materialized JSON** — `/api/engine/lesson` still returns the
whole timeline as one list; the scheduler is proven against that first. **Streaming is deferred** to its
own late phase (§7 Phase 7): only *after* the scheduler works do we switch `/lesson` to **stream
scene-timelines**
(SSE/WS) so the client schedules each scene against the live/audio clock as later scenes are still being
planned (the PAPER "plan-ahead-while-playing" property). Streaming is an optimization on top of a working
contract, never a prerequisite.

---

## 7. Phased plan (foundation-first, machine-gated — NOTEBOOK E1/C1)

Each phase ships independently behind an output-derived gate. **Pre-tasks** M0 (timeline corpus, §10)
and V0 (voice validation, §10) gate the IR freeze and the voice phase respectively.

1. **Script V0 + marker vocabulary (fix the weakest link FIRST).** Story generation is the current
   *visible* failure — cartoon lessons stop after 1–2 lines — and the choreographer can't run without
   it, so this comes early, not at the end. *Start by root-causing the truncation* (a `sanitize_beats`
   concept cap? stray `clear` beats wiping the board? the LLM under-producing?). Then define the minimal
   **Script IR**: `scenes`, `narration` with inline `[concept]` markers, `concepts`, `relations`,
   `emotion`. It ships **standalone into the existing render path** (markers stripped for display until
   the choreographer exists), immediately fixing the visible bug, and is the input the choreographer
   consumes. Generate it with **typed structured decoding** — Ollama-native JSON-schema `format` first
   (zero new dep; `minItems` enforces min scene/narration counts so the model can't under-produce),
   escalating to Outlines/Instructor only if the native constraint is too weak. **✓ Truncation fix
   landed + verified (2026-06-18):** diagnosis found BOTH paths truncated — the template `_story_plan`
   was a hollow 1-line-per-scene stub, and qwen2.5:7b under-produced (7 beats → 2 concepts) despite
   `OllamaStory` already passing `BEAT_SCHEMA` to `format`. Fix = a per-lesson `_beat_schema(spec)` that
   adds **`minItems`** (story=12/learn=10/draw=5/explain=4) + a richer `_story_plan` arc. **Result:
   minItems-through-Ollama CONFIRMED working** (qwen 7→13 beats, 2→4 coherent concepts; template story
   3→6 narration lines). The roadmap's "is Ollama-native enough vs Outlines?" unknown is answered: yes,
   for count. (`sanitize_beats` caps were NOT the cause — pure under-production.) *Gate: lessons produce
   N coherent scenes (no 1–2-line truncation) ✓; every narration `[concept]` resolves to a declared
   concept (next: the `[concept]` schema); schema validates with defensive drop-don't-repair parsing ✓.*
2. **Events → timeline adapter + scheduler (anti-rewrite).** Define the §3 contract; replace the board's
   `await`-queue with a master-clock scheduler that resolves markers. **Deliverable: an `events →
   timeline` adapter** that compiles today's `plan.py` stream into a *degenerate* timeline (one marker
   per `say`, sequential) — the existing product flows through the new scheduler with **no story/engine
   changes**, on the current **materialized JSON** (no streaming yet). *Gate (tolerance, NOT
   pixel-identical — exact bytes are too brittle for animated timing): **same final frame**, **same event
   order**, **same marker-resolved schedule**, **sampled keyframes within tolerance**. If any break, the
   adapter has become a rewrite — stop and fix it.* **✓ 2a done (2026-06-18):** `backend/engine/timeline.py`
   = the Timeline IR (`TLEntry`/`Timeline`, tracks + markers) + `from_events` adapter (encodes the queue's
   await semantics as per-entry `blocking`) + `resolve_schedule` (mirrors the board cursor). Anti-rewrite
   **tolerance gate green** — the scheduled degenerate timeline reproduces an *independently re-derived*
   queue schedule across 4 modes × 2 styles (355 tests, backend-only, zero product change). **Next: 2b —
   the frontend master-clock scheduler** (rewrite `play()` in both renderers) — needs in-browser check.
3. **Deterministic choreographer.** Consumes Script V0; `choreograph()` anchors reveals/points/camera to
   the `[concept]` markers. *Gate (machine-computable): **coverage** — every shown concept anchored to a
   marker that names it; **causality** — no event fires before its marker; **cadence** — draw density
   respects the PAPER saturation bound per marker.*
4. **Voice bootstrap — Web Speech + mouth slot.** Add the mouth slot + attachments to the rig; drive it
   with a crude `phonemize`/amplitude estimate. Proves the rig + scheduler with **zero install**. *Gate:
   mouth swaps on speech; markers fire within tolerance on desktop Chrome/Safari; degrades without
   crashing elsewhere.*
5. **Voice quality — free-local audio-gen (HeadTTS-validated, the default).** *Pre-req §V0.* Wire the §5
   fallback chain; server generates audio + (viseme|phoneme|word) timings; pre-resolve markers; ship
   `audio + timeline`; play against `audio.currentTime`. `VOICE_PROVIDER` knob (default local; paid cloud
   opt-in only). *Gate: viseme lip-sync aligns with audio (rasterize-and-look + cue-vs-audio offset);
   plays on all browsers; voice consistent.*
6. **Character + camera choreography.** Host points/looks at the narrated concept; camera anchored to
   beats; mouth synced; gestures (clips) anchored to markers. *Gate: causality invariants + L6.*
7. **Streaming scene-timelines (deferred optimization).** Only now switch `/api/engine/lesson` to stream
   timelines (SSE/WS) so later scenes plan while earlier ones play; the client schedules each scene
   against the live/audio clock. *Gate: PAPER SLOs (TTFA, no-stall) with playback matching the
   materialized path within the Phase-2 tolerances.*

**Ongoing — Story hardening (a parallel track, not a final gate).** Provider provenance, BYO-IR polish,
local-model robustness, and Studio debugging land incrementally alongside Phases 3–7 as the script path
matures — *not* deferred to the end. The visible story weakness is fixed by Script V0 up front; this is
the long-tail robustness work.

(Offline mp4 via [renderer.py](../backend/renderer.py) falls out of the same IR using the Motion-Canvas
`offset → ffmpeg adelay` mux recipe — a later optional lane.)

---

## 8. Licensing (verify before shipping)

- **Clean / ship:** Kokoro-82M (Apache-2.0), HeadTTS (check repo license at adoption), Rhubarb (MIT),
  `phonemize` JS, CMUdict (public domain), GSAP (now 100% free incl. all plugins, Apr 2025).
- **Caveat:** **Piper is GPL-3.0** — prefer Kokoro (Apache-2.0) as the default local TTS to avoid the
  copyleft question. ElevenLabs/Azure are paid cloud (opt-in only, never a silent default — NOTEBOOK M2).

---

## 9. Gotchas (verified in research — carry forward)

- **You cannot capture audio from Web Speech API** (open since `WICG/speech-api#69`, 2019) → no Rhubarb
  on browser TTS; viseme lip-sync needs the local-gen path.
- **Web Speech word boundaries are not portable** — only desktop Chrome/Safari-mac + `localService`
  voices; absent on Linux/Android/iOS. Gate on `voice.localService === true`.
- **`SpeechSynthesisEvent.elapsedTime` units differ per browser** (Chrome ms vs Edge seconds) —
  detect/normalize.
- **Rhubarb's B shape also covers the "EE" vowel** (not consonants-only) — map accordingly.
- **WhisperX drifts on long single utterances** — chunk to sentence length if ever used (only needed
  for bring-your-own audio; Kokoro/HeadTTS give timestamps natively, so no aligner required).

---

## 10. Open questions / pre-tasks

- **M0 (informs Script V0's marker convention + gates the timeline-IR freeze, Phase 2).** Hand-author
  the timeline for 10–15 real narrated topics (across modes), *allowing new track/marker forms*; the
  vocabulary that emerges is what we freeze, and it seeds the choreographer benchmark. (Mirrors
  ARCHITECTURE §10 V0 for relations.)
- **V0 — voice provider validation (gates Phase 5).** Empirically confirm what the chosen *local* TTS
  returns: run HeadTTS-with-Kokoro locally and check it actually emits audio + phoneme timestamps +
  Oculus visemes (the claim is HeadTTS-specific; Kokoro core/other wrappers vary). Record which fallback
  rung (§5) we land on, and per-scene generation latency on CPU (confirms the plan-ahead model hides it
  for the live board). Don't commit Phase 4 to a provider until this passes.
- **Q1 — marker granularity.** Per-keyword (precise, more markers) vs per-phrase (coarser, simpler)?
  Decide on the M0 corpus; expose as a Director knob.
- **Q2 — mouth as server-frames vs client-swap.** Confirm the client-swap layer (not server flipbook)
  for the mouth, so lip-sync works for both voice paths without frame-count blowup.

---

## 11. Reference systems — borrow the ideas, not the engines

The decision across the board: **upgrade our engine with proven ideas; do not replace it.** The
synthesized method = *our engine + Motion Canvas timeline ideas + Outlines/Ollama-schema story validation
+ DragonBones-style rig slots + HeadTTS voice timings.*

| System | License | Verdict | What we take |
|---|---|---|---|
| **Motion Canvas** | MIT | Borrow ideas | Timeline + `{name,targetTime}` markers, generator-style sequencing, audio-synced animation, and a **preview/debug** surface — a timeline inspector in Studio (scrub, see markers/tracks; fits K8 observability). Not the tool. |
| **HeadTTS** (Kokoro) | verify at adoption | Serious candidate — **validate locally (§V0)** | audio + phoneme timestamps + Oculus visemes in one local call. The voice/lip-sync default if §V0 passes. |
| **Outlines / Instructor** (+ Ollama-native schema) | Apache-2.0 / MIT | Adopt the *mechanism* | Typed structured decoding for Story V0. **Ollama-native `format` first** (on-surface, zero dep); Outlines only if native is too weak (needs a non-Ollama serving path). |
| **DragonBones** (DragonBonesJS) | **MIT** | Borrow data model | bones/slots/attachments/pose/clip/mouthTrack (§5). The license-clean Spine alternative. |
| **Spine** | Spine Runtimes License (paid seat) | Concept reference only | Confirms the same model — **don't vendor its runtimes**. |
| **AnimatedDrawings** (Meta) | MIT | **Already mined** (NOTEBOOK C1) | pose/skeleton-normalization priors + motion clips — feeds the Character Engine; never the whole renderer. |
| **Inochi2D / Live2D** | BSD-2 / proprietary | Future | mesh/parameter puppet model for expressive heads (soft face turns, eyes, hair) — later, likely overkill now. |
| **ToonCrafter** | Apache-2.0 (weights: verify) | Offline/research | cartoon keyframe interpolation for *offline polish*, not the live path. |
| **LiveSVG** | research paper | Future idea | editable-SVG-from-diffusion target — research, not a tool yet. |

---

## 12. Build log + diagnosis (autonomous run, 2026-06-18)

Built and committed on `cartoon` (newest first):

```
54094d2 feat(models): VOICE_PROVIDER config surface — free-local-first voice (5a)
01a3dfa feat(board): viseme lip-sync — host mouth moves with speech (4b)
14c59ef feat(character): mouth-slot viseme rig for lip-sync (4a)
de594d9 feat(studio): scheduler mirror — Studio plays the choreographed timeline (2b, L9)
797bbce feat(board): master-clock scheduler plays the choreographed timeline (2b)
699ccf1 feat(engine): deterministic choreographer — draw-while-talking (3)
7fcff01 feat(engine): Timeline IR + events->timeline adapter (2a)
ff323bb feat(story): Script V0 — minItems floor + [concept] narration markers (1)
d7f8b0c docs(story-voice): roadmap + notebook learnings (O1-O7)
```

**Verified (machine):** backend `376 tests` green + ruff clean; Studio `vite build` green; `board/engine.js`
Biome-clean; and an **end-to-end smoke test through real Ollama** — `stream.timeline_lesson("photosynthesis")`
yields a choreographed timeline: concept draws anchored to `m:sun/m:leaf/m:water/m:soil`, host `point`s at
each, and the host op carries all 6 viseme mouths.

**NOT verified (needs a browser — diagnose here):** the frontend *runtime*. Everything visual now flows
through the new `playTimeline` scheduler in BOTH `board/engine.js` (route `/`) and `frontend/src/lib/board.js`
(Studio). To diagnose: `make dev` → http://127.0.0.1:8000/ , pick cartoon, type a topic, Teach (Ollama running
for real `[concept]` markers). **Expect:** template lessons play as before (anti-rewrite); marker lessons reveal
each concept *as its word is spoken*, the host points at it, and its mouth moves during narration.

**Per-phase risk to check if something's off:**
- *Scheduler (2b):* if the board is blank/stuck, suspect `playTimeline` — the spine is `at===""` entries with
  self-correcting awaits; anchored entries fire via `setTimeout` during their say. `/api/engine/timeline`
  returns the timeline; `/api/engine/lesson` (events) is still there to A/B against.
- *Draw-while-talking (3):* timing uses the say's *estimated* duration × `char_start/text_len` (open-loop) — if
  Web-Speech TTS is much longer/shorter than the estimate, draws bunch early or lag. Phase-5 word boundaries fix it.
- *Lip-sync (4b):* mouth is an overlay `<g class="mouth-slot">` on the host group, swapped from `op.mouths`;
  visemes are *char-estimated* (coarse by design). If the mouth is mispositioned, check the paint transform of
  `op.mouths` vs the host body. If absent, the host op lacked `mouths` (only cinematic cartoon hosts get them).
- *Two renderers (L9):* `board/engine.js` (clear 800 + post-say dwell) and Studio `board.js` (clear 750, no
  dwell, fixed say-estimate, abort signal) intentionally differ — verify BOTH.

**Since first log — also built & committed:**
- *Phase 6 — camera-follows-concept* (`944cc81`): choreograph emits a gentle, cinematic-gated camera focus on
  each narrated concept, anchored to its marker (the camera pans to follow the words). Backend-tested. *Motion
  risk to eyeball: may feel busy — if so, tune the zoom or gate harder.*
- *Phase 5 — word-boundary timing* (`aa92462`): `speak()` forwards `onboundary`; a concept reveals the instant
  its word is spoken (closed-loop), estimate as fallback + final flush. **Removes the open-loop debt** for the
  free Web-Speech path. Both renderers; build/Biome green. (Mouth visemes stay estimate-based — sub-word.)

**Remaining (only these — one blocked, one correctly deferred):**
- *5b voice quality (BLOCKED on a model install):* local Kokoro/HeadTTS audio-gen → real audio file + word/viseme
  timestamps → resolve marker `t` + drive mouths precisely. The whole surface is ready (`VOICE_PROVIDER=kokoro|
  headtts`, `resolve_voice()`, the mouth slot, the marker `t` field) — it just needs the model installed + a small
  server step to generate the audio and fill marker times. Not done autonomously (heavy dep, unverifiable here).
- *7 streaming (DEFERRED by the roadmap's own rule):* per-scene timelines over SSE. It's an optimization on top of
  a *working, verified* scheduler — which isn't browser-verified yet — and the latency cost is *planning*, not
  delivery. Build it after the scheduler is confirmed and once per-scene planning exists.
