# Manim Animator

Text → animation engine. A planner turns natural language into a renderer-agnostic
**Scene IR**, and a renderer turns the IR into an animation. Two renderers consume
the same IR: Manim (offline mp4) and a **realtime live teaching board** — type a
topic and a canvas "teacher" draws the lesson segment by segment while narrating
(browser TTS), streaming over a websocket as the planner thinks.

The planner runs on a **local Ollama model** — free, no API key, private.

```
Text ─► Planner (2-stage + repair) ─► Scene IR (JSON) ─► Renderer ─► Animation ─► Board
          │ stage 1: outline                              │  ├─ Manim (offline mp4)
          │ stage 2: outline → IR                         │  └─ JS canvas (realtime, streamed)
          │ repair:  validate → re-prompt on error        │
          └─ asset catalog injected into prompts ◄── assets.py / assets.js
```

**Live board pipeline (v2 — action streaming):** the model emits NDJSON, ONE
action per line (`say` / `add` / `play` / `macro` / `clear` / `end`); the server
validates, *lays out*, and dispatches each action over `/ws/lesson` the moment
its line closes. First-content latency drops from O(segment tokens) to O(line
tokens ≈ 30), and per-action playback (~1–2.5 s) overlaps the generation of the
next line, so the board stays continuously alive. See [PAPER.md](PAPER.md) for
the formal latency model (saturation theorem, speech-credit lemma) and
measurements.

**Latency design** (local models generate 9–16 tok/s, so every token counts):
- a deterministic intro (title + voice) plays in <1 s, zero LLM tokens;
- title + 4-segment plan + the first teaching beat come back in *one* call;
- per-line **drop-don't-repair** error handling: a bad line is skipped free;
  re-adding an existing object becomes a "pulse" (the teacher points at it);
  added-but-never-animated objects get auto-reveal steps; a model that ignores
  NDJSON entirely falls back to whole-buffer parsing, then to a narration card;
- geometry is *computed, not generated*: a layout solver (frame projection,
  min-penetration collision separation, scored label placement) treats model
  coordinates as hints — and `macro` lines compress label/arrow constructs 3–4×;
- system prompts are byte-identical across calls (board state travels in the
  user message) so Ollama's KV prefix cache re-evals only ~100 tokens per call;
- the model is warmed at startup, kept resident (`keep_alive=30m`), outputs are
  capped (`num_predict`), and `{"end":true}` closes the stream early;
- the live lane prefers the fastest installed model (gemma3:4b, ~16 tok/s);
  the offline mp4 lane keeps qwen2.5:7b. Override: `OLLAMA_LESSON_MODEL`;
- **narration is the buffer**: speech plays ~3.5× slower than it generates,
  so `say` tokens bank audience-time. The prompt allocates ~20% of tokens to
  two-sentence narration; the client adds elastic playback (stretch when the
  buffer is thin) and idle-cover pulses (bounded motionless time ≤2.5 s).
  Measure any change with `python backend/bench_live.py "<topic>"`;
- **drawing skill lives in the runtime, not the model**: every stroke gets
  stable hand-drawn wobble (chalk feel); ~110 nouns resolve to *real human
  stroke sequences* from Google QuickDraw (lazily cached, replayed stroke by
  stroke under the pen); and six performance verbs — `dance`, `walk`, `wave`
  (skeletal rig keyframes), `spin` (meridian-drift on globes), `orbit`,
  `bounce` — turn one ~12-token line into seconds of kinematics.

**Session modes** ([backend/modes.py](backend/modes.py)) — the same engine,
parametrized. A mode is a `ModeSpec`: voice (system prompts), arc (plan +
segments vs one pass), board policy (columns / fresh stage per scene / one
canvas), and token budgets. Shipped modes:

| mode | what you get |
|---|---|
| **Learn** | full multi-part lesson with a plan and recap (columns + wipes) |
| **Draw** | one rich narrated illustration on the whole board |
| **Story** | a three-scene performed story — characters walk, dance, wave |
| **Explain** | the 30-second version: one idea, one picture, fastest path |

Adding a mode is one entry in the registry — no engine changes. The UI picks
modes via chips (served from `/api/modes`); CLI: `python lesson.py --mode draw
"a farm in the morning"`.

The IR is the spine of the whole design: the planner never writes Manim code
(safe, no `exec`), and swapping the renderer doesn't touch the planner.

**Assets are the trick for figurative prompts.** Instead of faking a "man" from a
circle, the planner picks from a named [asset library](backend/assets.py)
(`stick_figure`, `road`, `car`, `tree`, `sun`...). Unknown names degrade to a
labeled box — a single bad object never crashes a render. Add a new asset by
writing one factory in `assets.py`, or drop a `.svg` into `backend/assets/svg/`.

## Layout

| File | Role |
|------|------|
| [backend/ir.py](backend/ir.py) | Scene IR schema (Pydantic) — the contract |
| [backend/assets.py](backend/assets.py) | Named composite asset library + SVG drop-in + catalog |
| [backend/planner.py](backend/planner.py) | Text → IR: two-stage + repair loop (offline mp4 lane) + Ollama plumbing |
| [backend/lesson.py](backend/lesson.py) | Topic → *streamed NDJSON action lines* (the live-board engine) |
| [backend/actions.py](backend/actions.py) | Action protocol: line parser/assembler, layout solver, macros |
| [backend/renderer.py](backend/renderer.py) | IR → Manim → mp4 (the only Manim-aware file) |
| [backend/app.py](backend/app.py) | FastAPI: video jobs + `/ws/lesson` websocket stream + static board |
| [backend/bench_live.py](backend/bench_live.py) | Latency benchmark: TTFA, cadence percentiles, perceived-idle simulation |
| [board/index.html](board/index.html) | The board UI: Live Board tab (canvas + narration) and Video tab |
| [board/board.js](board/board.js) | Realtime canvas renderer: action player, progressive reveal, pen tip |
| [board/assets.js](board/assets.js) | JS twin of assets.py: same names/aliases as display-list factories |
| [PAPER.md](PAPER.md) | Research paper draft: latency model, layout solver, evaluation |

## Setup

System deps (macOS): `brew install cairo pango pkg-config ffmpeg`
(LaTeX is only needed for `mathtex` objects: `brew install --cask mactex-no-gui`.)

Python:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Ollama (the free local planner):
```bash
# install from https://ollama.com, then pull a model:
ollama pull qwen2.5:7b    # ~4.7GB, recommended (much better at composition)
ollama serve              # usually runs automatically
```

The planner auto-picks the best installed model (`qwen2.5:7b` → … → `gemma3`);
set `OLLAMA_MODEL` to force one.

## Run

```bash
# optional overrides
export OLLAMA_HOST=http://localhost:11434
export OLLAMA_MODEL=qwen2.5:7b   # else auto-picked

uvicorn app:app --reload --app-dir backend --port 8000
# open http://localhost:8000 — the Live Board tab is the default
```

Type a topic ("why the sky is blue") and hit **Teach it**: the lesson outline
appears in the sidebar, then segments stream in and the board draws them live
with spoken narration (browser TTS — free, offline; toggle with the checkbox).
The **Video** tab is the Phase-1 flow: same prompt, offline Manim mp4.

If Ollama isn't reachable — or every repair attempt fails — the planner falls
back to a deterministic mock, so a job never hard-fails. The first real plan is
slow (model load + LLM calls); subsequent ones are faster while it stays warm.

Smoke-test the planner alone (text → IR JSON):

```bash
cd backend && python planner.py "Explain the Pythagorean theorem"
```

Smoke-test the lesson planner alone (topic → streamed segments, printed):

```bash
cd backend && python lesson.py "the water cycle"
```

Smoke-test the renderer alone (no server, no LLM — exercises assets + fallback):

```bash
cd backend && python renderer.py   # writes an mp4 under ./media
```

Run the verification prompt set (validity + assets used per prompt):

```bash
cd backend && python benchmark.py
```

## Known limits

- **"Walking/driving" is translation, not articulation.** A `stick_figure` slides
  across the road; its legs don't swing yet. The asset keeps its sub-parts, so a
  future `walk` animation can drive them with updaters.
- **Small-model layout is imperfect** — objects can overlap or sit off the road.
  The repair loop fixes *invalid* IR, not *ugly* IR. Better layout heuristics (or
  a stronger model) are the lever here.
- **Live-board text is typewriter, not handwriting**, and `mathtex` renders as
  plain text on the canvas (Manim still typesets it in video mode, given LaTeX).
- **Narration voice quality is whatever the browser ships** (`speechSynthesis`).
  A local neural TTS (e.g. Piper) would be the free upgrade path.

## Roadmap

- **Phase 1 (done):** offline Manim render, polled by a web board.
- **Phase 2 (done):** realtime live teaching board — topic → streamed lesson
  segments over a websocket → JS canvas renderer draws live with narration.
  Same IR, same asset names on both renderers.
- **Next:** articulation (walk cycles), mic input (speech → topic), smarter
  layout, local neural TTS, lesson export (live board → mp4 via the Manim path).
