"""FastAPI backend: text -> IR -> pixels, two ways.

Video (Phase 1):
  POST /api/animate   {text}  -> {job_id}
  GET  /api/jobs/{id}         -> {status, video_url, scene}
  GET  /media/...             -> rendered mp4 (static)

Live board (Phase 2):
  WS   /ws/lesson    send {"text": topic} -> receive a stream of lesson events
                     (lesson outline, then one segment of IR at a time) that
                     board/board.js draws live while later segments still plan.

  GET  /                      -> the board UI
  GET  /board/...             -> board JS/static
"""

from __future__ import annotations

import asyncio
import json
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import sketches
from assets import catalog
from lesson import pick_lesson_model, stream_lesson
from planner import _chat, ollama_available, plan
from renderer import render

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"
BOARD = ROOT / "board"
MEDIA.mkdir(exist_ok=True)

app = FastAPI(title="Manim Animator")

# In-memory job store. Fine for a single-process thin slice; swap for Redis/db
# when you need persistence or multiple workers.
JOBS: dict[str, dict] = {}


class AnimateRequest(BaseModel):
    text: str


@app.on_event("startup")
def announce_brain():
    """Print the RESOLVED model config at boot, so a polluted env (e.g. a stray
    STORY_PROVIDER=gemini exported in the shell) is obvious immediately instead of
    silently steering the brain to paid cloud."""
    from engine import models

    cfg = models.describe()
    s = cfg["story"]
    src = "← env STORY_PROVIDER" if s["requested"] not in ("auto",) else "(local-first default)"
    print(f"\n  🧠 brain   : {s['provider']} · {s['model'] or '—'}   {src}")
    print(f"  ✏️  drawing : {cfg['svg']['provider']}")
    print(f"  🤖 ollama  : {'up' if cfg['ollama_reachable'] else 'down'} {cfg['ollama_models']}")
    for w in cfg["warnings"]:
        print(f"  ⚠️  {w}")
    if s["provider"] == "gemini":
        print(
            "  ⚠️  Using PAID cloud. To go local: `unset STORY_PROVIDER GEMINI_API_KEY` then restart."
        )
    print()


@app.on_event("startup")
def warmup_model():
    """Load the model into memory now (keep_alive=30m), not on the first
    lesson — at local speeds a cold load adds many seconds to first paint.
    Also pre-fetch a starter set of human-stroke sketches (one-time, ~KBs)."""

    def _warm():
        try:
            if ollama_available() and (m := pick_lesson_model()):
                _chat(m, [{"role": "user", "content": "ok"}], num_predict=1)
        except Exception:
            pass  # warming is best-effort; lessons still work cold

    threading.Thread(target=_warm, daemon=True).start()
    sketches.warm()


@app.get("/api/sketch/{name}")
def sketch(name: str):
    """A human-drawn stroke sequence (QuickDraw) for `name`, board units."""
    s = sketches.get_sketch(name)
    if not s:
        raise HTTPException(status_code=404, detail="no sketch")
    return s


def _run_job(job_id: str, text: str):
    job = JOBS[job_id]
    try:
        job["status"] = "planning"
        scene = plan(text)
        job["scene"] = scene.model_dump()

        job["status"] = "rendering"
        mp4 = render(scene, MEDIA)
        # Expose path relative to MEDIA via the /media mount.
        job["video_url"] = f"/media/{mp4.relative_to(MEDIA).as_posix()}"
        job["status"] = "done"
    except Exception as e:  # surface the failure to the board
        job["status"] = "error"
        job["error"] = f"{e}\n{traceback.format_exc()}"


@app.post("/api/animate")
def animate(req: AnimateRequest):
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "queued", "text": req.text}
    threading.Thread(target=_run_job, args=(job_id, req.text), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    return JOBS.get(job_id, {"status": "not_found"})


@app.get("/api/assets")
def assets():
    """The asset catalog the planner can draw from (for the board to display)."""
    return {"catalog": catalog()}


@app.get("/api/modes")
def modes():
    """Available session modes (the framework's registry, for the UI)."""
    from modes import mode_list

    return {"modes": mode_list()}


@app.websocket("/ws/lesson")
async def lesson_ws(ws: WebSocket):
    """Live lesson: client sends {"text": topic}; we stream lesson events.

    stream_lesson is a blocking generator (Ollama calls take seconds-minutes),
    so it runs on a worker thread feeding an async queue. The board starts
    drawing segment 1 while segment 2 is still being planned.
    """
    await ws.accept()
    try:
        try:
            req = json.loads(await ws.receive_text())
        except (json.JSONDecodeError, ValueError):
            await ws.send_json({"type": "error", "error": "malformed request (expected JSON)"})
            return
        topic = (req.get("text") or "").strip()
        mode = (req.get("mode") or "learn").strip()
        if not topic:
            await ws.send_json({"type": "error", "error": "empty topic"})
            return

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce():
            try:
                for event in stream_lesson(topic, mode=mode):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait, {"type": "error", "error": f"{e}\n{traceback.format_exc()}"}
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=produce, daemon=True).start()
        while (event := await queue.get()) is not None:
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass  # client left mid-lesson; the worker thread drains harmlessly


@app.get("/api/engine/modes")
def engine_modes():
    """Lesson modes the v3 board offers (learn / story / draw / explain)."""
    from engine.director import MODES

    return {"modes": list(MODES)}


@app.get("/api/engine/status")
def engine_status():
    """The resolved model config (local-first), so 'what's actually running' is
    visible instead of guessable. The single source of truth is engine.models."""
    import sketches
    from engine import models

    d = models.describe()
    return {
        # Flat keys the board/Studio read directly.
        "story_provider": d["story"]["provider"],
        "story_model": d["story"]["model"],
        "svg_provider": d["svg"]["provider"],
        "voice_provider": d["voice"]["provider"],
        "ollama_reachable": d["ollama_reachable"],
        "ollama_models": d["ollama_models"],
        "gemini_key_set": d["gemini_key_set"],
        "quickdraw_cached": len(sketches.cached_names()),
        "warnings": d["warnings"],
        # The full per-job resolution (provider/model/requested/note).
        "models": d,
    }


@app.get("/api/engine/director")
def engine_director(
    topic: str = "the water cycle",
    mode: str = "learn",
    audience: str | None = None,
    depth: str | None = None,
    tone: str | None = None,
    energy: str | None = None,
    density: str | None = None,
    style: str | None = None,
):
    """Preview the DirectorSpec the policy layer derives for a request."""
    from engine.director import direct, to_dict

    spec = direct(
        topic,
        mode=mode,
        audience=audience,
        depth=depth,
        tone=tone,
        energy=energy,
        density=density,
        style=style,
    )
    return to_dict(spec)


@app.get("/api/engine/lesson")
def engine_lesson(
    topic: str = "the water cycle",
    mode: str = "learn",
    audience: str | None = None,
    depth: str | None = None,
    tone: str | None = None,
    energy: str | None = None,
    density: str | None = None,
    style: str | None = None,
):
    """Director -> Story -> engines: the ordered event stream for the board.

    Hermetic by default (heuristic Director + template Story + parametric/fixture
    Drawing); set STORY_PROVIDER / ENGINE_SVG_PROVIDER for real models.
    """
    from engine.director import direct, to_dict
    from engine.stream import stream_lesson

    spec = direct(
        topic,
        mode=mode,
        audience=audience,
        depth=depth,
        tone=tone,
        energy=energy,
        density=density,
        style=style,
    )
    return {"topic": topic, "spec": to_dict(spec), "events": list(stream_lesson(topic, spec=spec))}


@app.get("/api/engine/timeline")
def engine_timeline(
    topic: str = "the water cycle",
    mode: str = "learn",
    audience: str | None = None,
    depth: str | None = None,
    tone: str | None = None,
    energy: str | None = None,
    density: str | None = None,
    style: str | None = None,
):
    """Director -> Story -> engines -> CHOREOGRAPHED Timeline (Phase 2b/3): the board scheduler's
    input. Same hermetic defaults as /lesson; concept draws are anchored to narration markers so
    the picture reveals as it is spoken (a no-op, == /lesson playback, when there are no markers)."""
    from engine.director import direct, to_dict
    from engine.stream import timeline_lesson

    spec = direct(
        topic,
        mode=mode,
        audience=audience,
        depth=depth,
        tone=tone,
        energy=energy,
        density=density,
        style=style,
    )
    return {"topic": topic, "spec": to_dict(spec), "timeline": timeline_lesson(topic, spec=spec)}


@app.get("/api/engine/script-prompt")
def engine_script_prompt(
    topic: str = "the water cycle",
    mode: str = "learn",
    audience: str | None = None,
    style: str | None = None,
    depth: str | None = None,
    tone: str | None = None,
    fmt: str = "plan",
):
    """The prompt to paste into a STRONG model (GPT-4/Claude). `fmt=plan` (default) asks
    for a directed STORYBOARD (scenes/shots/actions — a film); `fmt=beats` for the simple
    flat format. Both embed our drawable vocabulary so concepts render as icons, not boxes."""
    from engine import story
    from engine.director import direct

    spec = direct(topic, mode=mode, audience=audience, style=style, depth=depth, tone=tone)
    return {"prompt": story.script_prompt(spec, fmt=fmt), "fmt": fmt}


class ScriptRequest(BaseModel):
    """A bring-your-own story: paste the JSON a stronger model wrote; we animate it."""

    script: str  # the pasted JSON ({"beats":[...]} or a bare [...]), tolerant of ``` fences
    topic: str = ""
    mode: str = "learn"
    audience: str | None = None
    style: str | None = "cartoon"
    depth: str | None = None
    tone: str | None = None
    energy: str | None = None
    density: str | None = None


def _extract_json(text: str):
    """Tolerantly pull a JSON value out of pasted text (strip ``` fences / prose)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if t.count("```") >= 2 else t.strip("`")
        t = t[4:] if t.lstrip().lower().startswith("json") else t
    a, b = t.find("{"), t.rfind("}")
    c, d = t.find("["), t.rfind("]")
    # prefer the object form {"beats":[...]} if present, else a bare array
    if a != -1 and b > a and (c == -1 or a < c):
        return json.loads(t[a : b + 1])
    if c != -1 and d > c:
        return json.loads(t[c : d + 1])
    return json.loads(t)


@app.post("/api/engine/animate")
def engine_animate(req: ScriptRequest):
    """Animate a pasted storyboard (bring-your-own-story). The engine sanitizes
    (drop-don't-repair), composes, and returns the event stream — no model call."""
    from engine import plan as planmod
    from engine import story
    from engine.director import direct, to_dict
    from engine.stream import stream_lesson

    try:
        data = _extract_json(req.script)
    except Exception as e:  # noqa: BLE001 - surface the parse error to the user
        raise HTTPException(status_code=400, detail=f"Couldn't parse JSON: {e}") from None
    spec = direct(
        req.topic or "lesson",
        mode=req.mode,
        audience=req.audience,
        style=req.style,
        depth=req.depth,
        tone=req.tone,
        energy=req.energy,
        density=req.density,
    )
    # A directed LessonPlan (scenes/shots/actions) compiles through the new pipeline;
    # a flat {"beats":[...]} falls back to the Beat path. Both reach the same renderer.
    lp = planmod.parse_plan(data, title=req.topic or None, style=req.style)
    if lp is not None:
        events = list(planmod.compile_plan(lp, spec))
    else:
        beats = story.parse_beats(data)
        if not beats:
            raise HTTPException(
                status_code=400,
                detail='No valid story. Expected {"beats":[...]} or {"scenes":[...]}.',
            )
        events = list(stream_lesson(req.topic, spec=spec, beats=beats))
    return {"topic": req.topic, "spec": to_dict(spec), "events": events}


# --- v3 engine testing/checking dashboard ---------------------------------- #
@app.get("/dashboard")
def dashboard_view():
    return FileResponse(BOARD / "dashboard.html")


@app.get("/api/checks/all")
def checks_all():
    from engine.checks import full_report

    return full_report()


@app.get("/api/checks/positioning")
def checks_positioning():
    from engine.checks import positioning_report

    return positioning_report()


@app.get("/api/checks/drawing")
def checks_drawing(svg: bool = False):
    from engine.checks import drawing_report

    return drawing_report(include_svg=svg)


@app.get("/api/checks/speed")
def checks_speed():
    from engine.checks import speed_report

    return speed_report()


@app.get("/api/checks/lesson")
def checks_lesson(topic: str = "the water cycle", mode: str = "learn"):
    from engine.checks import lesson_report

    return lesson_report(topic, mode)


@app.get("/api/checks/suite")
def checks_suite():
    from engine.checks import run_suite

    return run_suite()


STUDIO = ROOT / "frontend" / "dist"  # the Svelte Studio (built with `make ui-build`)


@app.get("/")
def index():
    """The product: the Svelte Studio (built) — falls back to the vanilla board if
    the UI hasn't been built yet."""
    if STUDIO.exists():
        return RedirectResponse("/studio/")
    return FileResponse(BOARD / "engine.html")


@app.get("/engine")
def engine_view():
    """The vanilla-JS board (the Studio's fallback / a lighter view)."""
    return FileResponse(BOARD / "engine.html")


@app.get("/legacy")
def legacy_board():
    """The previous v2 action/planner board — demoted, kept for reference."""
    return FileResponse(BOARD / "index.html")


app.mount("/media", StaticFiles(directory=MEDIA), name="media")
app.mount("/board", StaticFiles(directory=BOARD), name="board")
if STUDIO.exists():
    app.mount("/studio", StaticFiles(directory=STUDIO, html=True), name="studio")
