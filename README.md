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

**Live board pipeline:** `topic → plan+first segment (one LLM call) → per-segment
IR, streamed over /ws/lesson → board.js draws live`. Each call plans just one
teaching beat, so it's faster and more reliable on a 7B model than one giant scene
— and the board plays segment N while segment N+1 is still being planned.

**Latency design** (local 7B models generate ~10 tok/s, so every token counts):
- a deterministic intro segment draws the title and starts the voice in <1s,
  no LLM involved;
- the lesson plan and the first real segment come back in *one* round trip;
- every call streams: the `narration` field is emitted the moment it closes in
  the token stream, so speech starts seconds into a call, not after it;
- the segment system prompt is byte-identical across calls (board state travels
  in the user message), so Ollama's KV prefix cache re-evals only the ~100 new
  tokens per segment;
- the model is warmed at server startup and kept resident (`keep_alive=30m`),
  and outputs are capped (`num_predict`) and budgeted (1-3 sentences, ≤4 objects).

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
| [backend/planner.py](backend/planner.py) | Text → IR: two-stage + repair loop (local Ollama, mock fallback) |
| [backend/lesson.py](backend/lesson.py) | Topic → *streamed* lesson: outline → per-segment IR (the live-board planner) |
| [backend/renderer.py](backend/renderer.py) | IR → Manim → mp4 (the only Manim-aware file) |
| [backend/app.py](backend/app.py) | FastAPI: video jobs + `/ws/lesson` websocket stream + static board |
| [board/index.html](board/index.html) | The board UI: Live Board tab (canvas + narration) and Video tab |
| [board/board.js](board/board.js) | Realtime canvas renderer: IR → progressive hand-drawn reveal, step timeline |
| [board/assets.js](board/assets.js) | JS twin of assets.py: same names/aliases as display-list factories |

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
