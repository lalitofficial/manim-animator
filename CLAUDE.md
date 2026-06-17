# CLAUDE.md

Guidance for AI coding agents (and humans) working in this repo. Keep it current.

## What this is

Text → IR → pixels, two ways from the **same IR**:

1. **Offline video** — `POST /api/animate` plans an IR, renders an mp4 with Manim.
2. **Live teaching board** — `WS /ws/lesson` streams a lesson as NDJSON board
   *actions* that `board/board.js` draws in real time while later segments are
   still being planned.

The planner is a **local Ollama model** (free, no API key, private). When Ollama
is unreachable, both lanes fall back to deterministic mock output — that is the
path the test suite and CI exercise.

## Architecture — the IR is the spine

The planner never writes Manim code; it emits IR, and the runtime owns drawing.

| File | Role |
| --- | --- |
| `backend/ir.py` | The IR schema (`Scene`, `Step`, `SceneObject`) — the contract every other module speaks. |
| `backend/planner.py` | Text → IR for the **offline mp4 lane**: two-stage plan + repair loop + Ollama plumbing. Falls back to `plan_mock`. |
| `backend/renderer.py` | IR → Manim → mp4. **The only Manim-aware file** — keep Manim imports out of everything else. |
| `backend/lesson.py` | Streams a live lesson (outline, then one segment of actions at a time). Falls back to `mock_lesson`. |
| `backend/actions.py` | The live-board action model + `BoardLayout` solver. **Drop-don't-repair**: bad/overflowing actions are dropped, never patched. |
| `backend/modes.py` | Session modes (learn/draw/…) as `ModeSpec` data. Adding a mode = adding one entry, no engine changes. |
| `backend/assets.py` | Asset catalog the planner may draw from (`/api/assets`). |
| `backend/sketches.py` | Human-stroke sketches (QuickDraw), fetched once and cached under `backend/assets/` (gitignored). |
| `backend/app.py` | FastAPI app: REST + the lesson WebSocket. In-memory job store. |
| `board/` | Vanilla-JS front end: `board.js` (renderer/loop), `assets.js`, `index.html`. No build step. |

`PAPER.md` has the latency math behind the streaming design; `README.md` is the
user-facing intro.

## Commands (use the Makefile — `make help` lists all)

| Task | Command |
| --- | --- |
| Install/sync env (runtime + dev) | `make setup` |
| Run API + board (autoreload) | `make dev` → http://127.0.0.1:8000 |
| Lint Python | `make lint` |
| Auto-fix + format Python | `make fix` |
| Type check | `make typecheck` |
| Tests | `make test` |
| Front-end lint/format | `make web` / `make web-fix` |
| Everything CI runs | `make check` |
| Live-board latency bench | `make bench T="why the sky is blue"` |
| Positioning benchmark (Phase-1 gate) | `make bench-pos` |
| Studio UI (Svelte) dev server | `make ui` (Vite :5173, proxies /api) |
| Build the Studio → served at `/` | `make ui-build` |
| Re-lock deps + refresh requirements.txt | `make lock` |

**The Studio (`frontend/`, Vite + Svelte) is the product UI.** One robust surface: the animated
board + full Director controls (mode/audience/depth/tone/energy) + live observability (provider
status, story provenance, **source breakdown** primitive/icon/sketch/generated/box, the DirectorSpec).
Builds to `frontend/dist` (gitignored), served at `/` (redirects to `/studio/`); falls back to the
vanilla `board/engine.html` if not built. `make ui` for live dev. The old `/dashboard` (gates/speed/
suite QA) and `/legacy` (v2 board) remain. Build it: `make ui-build`, then `make dev`.

**Engine rebuild (`backend/engine/`, see docs/ARCHITECTURE.md).** The 3-engine rebuild
(Drawing/Positioning/Story) lives here, separate from the v1/v2 flat modules. **Phases 1–2
built & green:**
- P1 Positioning: `contracts.py` (frozen seams), `positioning.py` (kiwisolver + deterministic
  flow/separation + drop-don't-repair), `invariants.py` (output-derived ruler — recompute every
  invariant from the Placements, never solver state), `corpus.py`, `bench.py` (`make bench-pos`).
- P2 Drawing: `geometry.py` (stroke gen), `drawing.py` (measure/paint over the ladder, memoized,
  color=paint-time), `route.py` (connectors attach post-placement), `scene.py`
  (measure→position→route→paint pipeline), `svg.py` (visual export). `make bench-draw` writes SVGs.
  - **Ladder (a visual LANGUAGE, not a catalog — NOTEBOOK B8):** parametric primitive (circle/
    square/rect/triangle/blob/wave/arc) + text · **composed ICON** (`icons.py` — declarative recipes:
    sun=circle+rays, person=head+limbs; `set_compose`) · **parametric FAMILIES** (`families.py` — a
    family is a *generator* of composed colored cartoons: `quadruped(body,ear,tail,…)` → cat/dog/cow/
    lion from params; ~11 families × a one-line concept table = the scalable colored-cartoon corpus,
    so coverage grows by DATA not geometry — NOTEBOOK B9) · **Tabler catalog** (`catalog.py` — MIT
    stroke-only line icons vendored in `backend/engine/assets/tabler/`, ~92 now, alias index built
    from each icon's `tags:`; flattened via svgnorm; `set_catalog_lookup`; expand with `make
    vendor-icons`) · QuickDraw (`sketches.py get_cached`; `set_sketch_lookup`) · LLM-SVG (off by
    default) · labeled-box backstop. **Composition (recipes + families) is the PRIMARY deterministic
    path** (~277 composed concepts now, zero generation); cartoon SKIPS the stroke-only catalog (it
    reads as a diagram, not a cartoon) and relies on composition. `icons.compose` precedence: hand
    core → `cartoon_recipes.json` → families → mono `icon_recipes.json` (COLOR before coverage — a
    colored family beats an uncolored mono recipe). Every drawable carries a `source` (primitive/icon/
    catalog/sketch/generated/box) surfaced in the stream + Studio so you see how little generation is needed.

- P3 Generative rung: `svgnorm.py` (sanitize + geometric-normalize boundary — reject
  scripts/external refs, flatten transforms via svgelements `reify`, curves→polylines, normalize
  to a board-unit box, quality-gate), `generators.py` (pluggable `SvgProvider`: `FixtureProvider`
  default/tested, `OllamaProvider`/`GeminiProvider` behind `ENGINE_SVG_PROVIDER`). `drawing.measure`
  now has **rung 3** with a negative cache + **placeholder-then-swap** (`generate=False` returns the
  backstop instantly; `pregenerate()` warms; next render swaps). Fixtures: `backend/engine/fixtures/svg/`.

- P5 Story + end-to-end: `story.py` (`tell(topic,mode)→[Beat]`; deterministic `TemplateStory`
  default, `OllamaStory`/`GeminiStory` behind `STORY_PROVIDER`; `parse_beats()` for LLM JSON),
  `compile_beats()` in `scene.py` (Beats → Scene + narration), `runtime.py` (`lesson(topic)` =
  tell→compile→render). `make lesson T="..."` writes `build/engine/lesson.svg`. **The product loop is
  closed: topic → board, output-verified.**

- P6 Live board (end-to-end, **the product**): `serialize.py` (DrawOp→JSON), `positioning.Placer`
  (incremental freeze-placed streaming), `stream.py` (`stream_lesson()` yields ordered
  `start/say/draw/connector/clear/done` events), `board/engine.{html,js}` (SVG `stroke-dasharray`
  draw-on + TTS + **mode chips**). **THE v3 board is the default route `/`**; `/legacy` is the old v2
  action/planner board (demoted, kept). `GET /api/engine/lesson?topic=&mode=` streams events;
  `GET /api/engine/modes` lists modes.
  - **Modes** (`story.py` MODE_NAMES, mode-aware `tell()` + LLM prompt): `learn` (concept map),
    `story` (3 scenes separated by `clear` beats → the board wipes between scenes), `draw` (one
    central illustration), `explain` (terse cause→effect). Offline templates are structurally distinct
    per mode; real per-topic content needs `STORY_PROVIDER=ollama|gemini`.
  - **One board, one engine, one workflow:** topic + mode → `stream_lesson` → animated `/`. The v2
    board/planner/video stack is no longer on the default path.
  - **Run `make dev` → http://127.0.0.1:8000/** , pick a mode/audience chip, type a topic, Teach.

- **Director (policy layer, `director.py`) — above the engines.** `direct(topic, mode, request,
  **controls) → DirectorSpec` (typed: mode/depth/audience/tone/density/energy/scene_count) +
  derived knobs (`concept_count`, `draw_speed`, `say_dwell`). Deterministic + hermetic (heuristic
  cue-parsing + audience profiles; explicit controls win); LLM refinement is a future slot.
  **Pipeline: request → DirectorSpec → Story(Beats) → engines** — the spec parameterizes the Story
  prompt + deterministic engine knobs, NOT extra LLM planning stages (density→concept count,
  energy→board pacing via the stream `start` event, scene_count→story segments).
  `GET /api/engine/director?...` previews the spec; `/api/engine/lesson` returns it. Board has
  mode + audience chips. Tests: `tests/test_director.py`.

Tests: `tests/test_{positioning,drawing,generation,story,stream}.py` + engine routes in `test_api.py`
(77 total). Extent-honesty is checked from the painted ink, not the measured Extent (the §A3/§K2
anti-self-certification rule). Every rung is hermetic by default (fixture/template providers); real
models only run when `STORY_PROVIDER` / `ENGINE_SVG_PROVIDER` = `ollama|gemini`. **All 6 phases done;
the topic→Beats→measure→position→route→paint→stream→board loop is complete.** Remaining: Phase 4
(offline asset-gen → permanent cache) is the one optional enhancement; real-model lessons just need
`STORY_PROVIDER=ollama` + a local model.
(StarVector/DiffSketcher → permanent cache), or **Phase 5** — Story emits Beats, wire end-to-end.

Direct CLIs still work: `cd backend && python planner.py "..."`,
`python lesson.py "..."`, `python renderer.py`.

## Conventions / gotchas

- **Dependencies are managed by `uv`.** `pyproject.toml` is the source of truth;
  `uv.lock` is committed. `requirements.txt` is **generated** (`make lock`) for
  compatibility only — never hand-edit it. Don't `pip install` into `.venv`.
- **Backend modules import each other flat** (`import sketches`, `from assets
  import catalog`) because the app runs with `--app-dir backend`. Tests and tools
  add `backend/` to the path (`pythonpath`, `extraPaths`, `src`). Keep new modules
  in `backend/` and import them the same flat way.
- **Keep Manim confined to `renderer.py`.** Other modules must stay importable
  without rendering.
- **Live board is drop-don't-repair.** Don't add code that "fixes" malformed
  actions — drop them and move on; that is the design.
- **Model/provider config = `backend/engine/models.py` (ONE surface).** Local-first:
  story brain defaults `auto` (local Ollama, auto-picks best installed model; else
  the offline template); drawing-gen defaults `off`; cloud (gemini) is opt-in only and
  NEVER a silent default. `models.describe()` is what the status endpoint + Studio show.
  Don't read `STORY_PROVIDER`/`ENGINE_SVG_PROVIDER` ad-hoc — go through `models.resolve_*`.
- **No network or Ollama in tests.** New tests must hit the mock/fallback paths (see
  `tests/conftest.py` — the autouse `hermetic` fixture forces template/fixture + pins
  the single `models.ollama_tags` probe; startup warmup is also neutralized).
- **Generated artifacts are gitignored**: `media/`, `*.mp4`, `__pycache__/`,
  `backend/assets/`, `.venv/`. Don't commit them.
- **`biome.json` must be strict JSON** (no comments) or Biome silently ignores
  the rules block.
- Config lives in `pyproject.toml` (ruff/pyright/pytest) and `biome.json` (JS/HTML).
  Lint baseline relaxes a few legacy-friendly rules — tighten as code is cleaned.

## Learning notebook — read this, and keep it growing

`NOTEBOOK.md` is the shared log of **why** — the engine-decomposition direction (Drawing /
Positioning / Story), the benchmarking philosophy (machine-computable invariants, accuracy
before speed, benchmark-derives-model), the design principles proven in v1/v2, and hard-won
gotchas.

- **Read it at the start of a session** — it carries the reasoning that the code alone doesn't.
- **Append at the end of any substantial session**: one learning = a principle + the *why*.
  Don't let an insight die in a closed chat. It already holds the *earlier* learnings
  (sections H & I); add every new one going forward.
- Durable items also live in the memory system (see the `engine-decomposition-plan` and
  `how-lalit-wants-to-work` memories).

Current direction: perfect + benchmark the **Drawing + Positioning** engines first
(foundation before story); latency is de-prioritised until the foundation is trustworthy.

## Before you commit

Hooks run ruff + Biome automatically (`make hooks` installs them). For a full
local gate run `make check` — it must be green before pushing (CI runs the same).
