#!/usr/bin/env python
"""Export a lesson to a finished MP4 — clean board video + a real narration audio track.

The product export path (distinct from the QA recorder): it films the chrome-free board
(`?clean=1`) so the video is the lesson, not the app UI, and muxes the server-side TTS
(`/api/engine/audio`) so the video has sound (browser Web Speech can't be captured).

Needs a running server (`make dev`) + ffmpeg + a Chrome (uses Playwright's system-Chrome).
Run via:  uv run --with playwright python scripts/export_lesson.py "the water cycle"
"""

from __future__ import annotations

import argparse
import glob
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("topic")
    ap.add_argument("--mode", default="learn")
    ap.add_argument("--style", default="cartoon")
    ap.add_argument("--audience", default="general")
    ap.add_argument("--out", default="build/export/lesson.mp4")
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--max-seconds", type=int, default=120)
    a = ap.parse_args()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    controls = f"style={a.style}&mode={a.mode}&audience={a.audience}&topic={quote(a.topic)}"
    board_url = f"{a.base}/engine?clean=1&{controls}"

    with tempfile.TemporaryDirectory() as d:
        vid_dir = Path(d) / "vid"
        vid_dir.mkdir()
        size = {"width": 1280, "height": 720}
        print(f"Recording {board_url} …", flush=True)
        with sync_playwright() as p:
            br = p.chromium.launch(channel="chrome", headless=True)
            ctx = br.new_context(
                viewport=size, record_video_dir=str(vid_dir), record_video_size=size
            )
            pg = ctx.new_page()
            pg.goto(board_url, wait_until="domcontentloaded")
            waited = 0
            while waited < a.max_seconds * 1000:  # stop when the lesson signals done (caption ✓)
                pg.wait_for_timeout(500)
                waited += 500
                cap = pg.evaluate("(document.getElementById('caption')||{}).textContent || ''")
                if "✓" in cap:
                    break
            pg.wait_for_timeout(700)
            ctx.close()  # finalizes the .webm
            br.close()

        webms = sorted(glob.glob(str(vid_dir / "*.webm")))
        if not webms:
            print("ERROR: no video was recorded", file=sys.stderr)
            sys.exit(1)
        webm = webms[0]

        audio = Path(d) / "narration.wav"
        try:
            urllib.request.urlretrieve(f"{a.base}/api/engine/audio?{controls}", audio)
            has_audio = audio.exists() and audio.stat().st_size > 1024
        except Exception as e:  # noqa: BLE001 - no server TTS -> silent video, still a valid export
            print(f"(no audio track: {e})", flush=True)
            has_audio = False

        cmd = ["ffmpeg", "-y", "-v", "error", "-i", webm]
        if has_audio:
            cmd += ["-i", str(audio)]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
        if has_audio:
            cmd += ["-c:a", "aac", "-shortest"]
        cmd.append(str(out))
        subprocess.run(cmd, check=True)

    print(f"DONE -> {out}  (audio: {'yes' if has_audio else 'no'})")


if __name__ == "__main__":
    main()
