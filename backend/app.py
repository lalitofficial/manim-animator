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
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response
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
    if s["provider"] in ("gemini", "vertex"):
        print(
            "  ⚠️  Using cloud model. To go local: `unset STORY_PROVIDER GEMINI_API_KEY` then restart."
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
        "vertex_project": d["vertex_project"],
        "vertex_location": d["vertex_location"],
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


@app.get("/api/engine/classify")
def engine_classify(topic: str = "photosynthesis", request: str | None = None):
    """Preview the Director's SUBJECT classification of a topic: domain + confidence +
    recommended presentation format, plus the raw per-domain cue scores. The internal
    'thought engine' decision, made observable (docs/PLAN-director-domains-and-liveliness.md)."""
    from engine import semantics
    from engine.director import direct

    spec = direct(topic, request=request)
    m = semantics.classify(topic)
    return {
        "topic": topic,
        "domain": spec.domain,
        "confidence": spec.domain_confidence,
        "fmt": spec.fmt,
        "mode": spec.mode,
        "scores": {k: v for k, v in m.scores.items() if v > 0},  # only domains that matched
    }


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


class StoryStudioRequest(BaseModel):
    """Text-only story lab input. Separate from the visual/cartoon engine."""

    prompt: str
    arc: str = "explainer"
    audience: str = "general"
    tone: str = "warm"
    length: str = "short"
    provider: str = "auto"


class StoryStudioSaveRequest(BaseModel):
    package: dict[str, Any]
    rating: int | None = None
    note: str = ""


class AnimateStoryRequest(BaseModel):
    """Stage 2 of the cartoon workflow: animate an APPROVED Story-Studio package."""

    package: dict[str, Any]
    style: str = "cartoon"


class BundleToggleRequest(BaseModel):
    id: str
    enabled: bool


class VariantRequest(BaseModel):
    """A family-variant preview/gate request from the Asset Studio."""

    family: str
    params: dict[str, Any] = {}


class SaveVariantRequest(BaseModel):
    """Publish an APPROVED family variant into the override layer."""

    concept: str
    family: str
    params: dict[str, Any] = {}
    bundle: str = ""
    approved: bool = False
    license: str = "studio"


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


# --- Story Studio: text-first story-writing feedback loop ------------------- #
@app.get("/story-studio")
def story_studio_view():
    """A separate text-only studio for improving story generation before animation."""
    return FileResponse(BOARD / "story_studio.html")


@app.post("/api/story-studio/generate")
def story_studio_generate(req: StoryStudioRequest):
    from engine import story_studio

    package = story_studio.generate(
        story_studio.StoryStudioRequest(
            prompt=req.prompt,
            arc=req.arc,
            audience=req.audience,
            tone=req.tone,
            length=req.length,
            provider=req.provider,
        )
    )
    return package.to_dict()


@app.get("/api/story-studio/examples")
def story_studio_examples():
    from engine import story_studio

    return {"examples": story_studio.examples()}


@app.post("/api/story-studio/save")
def story_studio_save(req: StoryStudioSaveRequest):
    from engine import story_studio

    return story_studio.save_feedback(req.package, req.rating, req.note)


@app.post("/api/story-studio/animate")
def story_studio_animate(req: AnimateStoryRequest):
    """Stage 2 of the cartoon workflow: animate an APPROVED Story-Studio story. Bridges the
    StoryPackage -> a multi-scene LessonPlan and compiles a CHOREOGRAPHED Timeline the board
    scheduler plays as a full-length cartoon. No model call — the story is already written."""
    from engine.stream import timeline_from_package

    return {"timeline": timeline_from_package(req.package, req.style)}


# --- Asset Studio: assets as first-class, bundled, gated engine resources --- #
@app.get("/asset-studio")
def asset_studio_view():
    """The Asset Studio: catalog, bundles, coverage, and the family-variant creator."""
    return FileResponse(BOARD / "asset_studio.html")


@app.get("/api/asset-studio/catalog")
def asset_studio_catalog(
    q: str = "",
    bundle: str = "",
    kind: str = "",
    style: str = "",
    status: str = "",
    offset: int = 0,
    limit: int = 120,
):
    from engine import asset_registry, asset_studio

    page = asset_studio.catalog(
        q=q, bundle=bundle, kind=kind, style=style, status=status, offset=offset, limit=limit
    )
    return {**page, "stats": asset_registry.stats()}


@app.get("/api/asset-studio/preview")
def asset_studio_preview(concept: str, style: str = "cartoon"):
    """Render an existing concept to a standalone SVG preview."""
    from engine import asset_studio

    return Response(asset_studio.preview(concept, style), media_type="image/svg+xml")


@app.get("/api/asset-studio/bundles")
def asset_studio_bundles():
    from engine import bundles

    return {
        "bundles": [b.to_dict() for b in bundles.all_bundles()],
        "any_disabled": bundles.any_disabled(),
        "resolve_order": bundles.resolve_order(),
    }


@app.post("/api/asset-studio/bundles/toggle")
def asset_studio_toggle_bundle(req: BundleToggleRequest):
    from engine import asset_registry, bundles

    result = bundles.set_enabled(req.id, req.enabled)
    asset_registry.refresh()
    return result


@app.get("/api/asset-studio/coverage")
def asset_studio_coverage():
    from engine import coverage

    return coverage.analyze()


@app.get("/api/asset-studio/families")
def asset_studio_families():
    from engine import asset_studio

    return {"families": asset_studio.families_schema()}


@app.post("/api/asset-studio/variant/preview")
def asset_studio_variant_preview(req: VariantRequest):
    from engine import asset_studio

    try:
        svg = asset_studio.preview_variant(req.family, req.params)
    except Exception as e:  # noqa: BLE001 - surface bad params to the Studio, don't 500
        raise HTTPException(status_code=400, detail=str(e)) from e
    return Response(svg, media_type="image/svg+xml")


@app.post("/api/asset-studio/variant/gate")
def asset_studio_variant_gate(req: VariantRequest):
    from engine import asset_studio

    return asset_studio.gate_variant(req.family, req.params)


@app.post("/api/asset-studio/variant/save")
def asset_studio_variant_save(req: SaveVariantRequest):
    from engine import asset_studio

    return asset_studio.save_variant(
        req.concept,
        req.family,
        req.params,
        bundle=req.bundle,
        approved=req.approved,
        license=req.license,
    )


@app.get("/api/asset-studio/excalidraw/authors")
def asset_studio_excalidraw_authors(refresh: bool = False):
    """Contributor folders from excalidraw-libraries/libraries/. One cached GitHub request."""
    from engine import excalidraw_libraries

    try:
        return excalidraw_libraries.authors(refresh=refresh)
    except Exception as e:  # noqa: BLE001 - surface import-source failures to the Studio
        raise HTTPException(status_code=502, detail=str(e)) from e


@app.get("/api/asset-studio/excalidraw/files")
def asset_studio_excalidraw_files(author_path: str):
    """`.excalidrawlib` files inside one contributor folder."""
    from engine import excalidraw_libraries

    try:
        return excalidraw_libraries.files(author_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/asset-studio/excalidraw/library")
def asset_studio_excalidraw_library(path: str):
    """Summary of one `.excalidrawlib` pack: item counts, element types, bboxes."""
    from engine import excalidraw_libraries

    try:
        return excalidraw_libraries.load(path).to_dict()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/asset-studio/excalidraw/item")
def asset_studio_excalidraw_item(path: str, index: int = 0):
    """One Excalidraw library item plus an approximate SVG preview."""
    from engine import excalidraw_libraries

    try:
        return excalidraw_libraries.item(path, index)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/api/asset-studio/excalidraw/index")
def asset_studio_excalidraw_index(refresh: bool = False):
    """The WHOLE catalog: every published library (Azure/AWS/GCP/clouds/…) with preview
    image + item names, from the repo-root libraries.json. One cached request."""
    from engine import excalidraw_libraries

    try:
        return excalidraw_libraries.index(refresh=refresh)
    except Exception as e:  # noqa: BLE001 - surface import-source failures to the Studio
        raise HTTPException(status_code=502, detail=str(e)) from e


class ExcalImportRequest(BaseModel):
    path: str
    index: int = 0
    concept: str = ""


@app.post("/api/asset-studio/excalidraw/import")
def asset_studio_excalidraw_import(req: ExcalImportRequest):
    """Crop/normalize one library item (and its whole set) to board-unit candidate strokes."""
    from engine import asset_registry, excalidraw_libraries

    try:
        result = excalidraw_libraries.import_item(req.path, req.index, req.concept)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    asset_registry.refresh()
    return result


class PublishRequest(BaseModel):
    """Promote imported candidates to engine-drawable (or demote)."""

    concepts: list[str] = []
    all: bool = False


@app.post("/api/asset-studio/publish")
def asset_studio_publish(req: PublishRequest):
    """Publish candidates so the engine can DRAW them (a low resolution rung that fills
    gaps without shadowing cartoon assets). `all` publishes every renderable candidate."""
    from engine import asset_registry, candidates_store

    n = candidates_store.publish_all() if req.all else candidates_store.publish(req.concepts)
    asset_registry.refresh()
    return {"ok": True, "published": n, "total_published": candidates_store.stats()["published"]}


@app.post("/api/asset-studio/unpublish")
def asset_studio_unpublish(req: PublishRequest):
    from engine import asset_registry, candidates_store

    if req.all:
        candidates_store.unpublish_all()
        n = 0
    else:
        n = candidates_store.unpublish(req.concepts)
    asset_registry.refresh()
    return {"ok": True, "unpublished": n, "total_published": candidates_store.stats()["published"]}


class ExcalLibraryRequest(BaseModel):
    path: str


@app.post("/api/asset-studio/excalidraw/import-library")
def asset_studio_excalidraw_import_library(req: ExcalLibraryRequest):
    """Import a WHOLE set: every item parsed from coordinates into candidate strokes."""
    from engine import asset_registry, excalidraw_libraries

    try:
        result = excalidraw_libraries.import_library(req.path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    asset_registry.refresh()
    return result


# Background full-sync state (single-process; fine for a local Studio).
_EXCAL_SYNC: dict[str, Any] = {"running": False, "done": 0, "total": 0, "name": "", "result": None}


@app.post("/api/asset-studio/excalidraw/sync")
def asset_studio_excalidraw_sync(limit: int = 0):
    """Kick off a background sync of ALL Excalidraw libraries → candidate packs. Poll
    /sync-status for progress. (For large/full syncs, `make sync-excalidraw` is also fine.)"""
    from engine import asset_registry, excalidraw_libraries

    if _EXCAL_SYNC["running"]:
        return {"ok": False, "error": "a sync is already running", **_EXCAL_SYNC}

    def _progress(done: int, total: int, name: str):
        _EXCAL_SYNC.update(done=done, total=total, name=name)

    def _run():
        _EXCAL_SYNC.update(running=True, done=0, total=0, name="", result=None)
        try:
            res = excalidraw_libraries.sync_all(
                progress=_progress, limit=(limit or None), refresh=True
            )
            asset_registry.refresh()
            _EXCAL_SYNC["result"] = res
        except Exception as e:  # noqa: BLE001
            _EXCAL_SYNC["result"] = {"ok": False, "error": str(e)}
        finally:
            _EXCAL_SYNC["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "started": True}


@app.get("/api/asset-studio/excalidraw/sync-status")
def asset_studio_excalidraw_sync_status():
    from engine import candidates_store

    return {**_EXCAL_SYNC, "store": candidates_store.stats()}


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
