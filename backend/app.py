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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from assets import catalog
from lesson import stream_lesson
from planner import _chat, ollama_available, pick_model, plan
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
def warmup_model():
    """Load the model into memory now (keep_alive=30m), not on the first
    lesson — at local speeds a cold load adds many seconds to first paint."""
    def _warm():
        try:
            if ollama_available() and (m := pick_model()):
                _chat(m, [{"role": "user", "content": "ok"}], num_predict=1)
        except Exception:
            pass  # warming is best-effort; lessons still work cold
    threading.Thread(target=_warm, daemon=True).start()


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


@app.websocket("/ws/lesson")
async def lesson_ws(ws: WebSocket):
    """Live lesson: client sends {"text": topic}; we stream lesson events.

    stream_lesson is a blocking generator (Ollama calls take seconds-minutes),
    so it runs on a worker thread feeding an async queue. The board starts
    drawing segment 1 while segment 2 is still being planned.
    """
    await ws.accept()
    try:
        req = json.loads(await ws.receive_text())
        topic = (req.get("text") or "").strip()
        if not topic:
            await ws.send_json({"type": "error", "error": "empty topic"})
            return

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def produce():
            try:
                for event in stream_lesson(topic):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "error", "error": f"{e}\n{traceback.format_exc()}"})
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=produce, daemon=True).start()
        while (event := await queue.get()) is not None:
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass  # client left mid-lesson; the worker thread drains harmlessly


@app.get("/")
def index():
    return FileResponse(BOARD / "index.html")


app.mount("/media", StaticFiles(directory=MEDIA), name="media")
app.mount("/board", StaticFiles(directory=BOARD), name="board")
