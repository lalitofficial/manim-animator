"""Server-side TTS — render lesson narration to a REAL audio track.

Exported video is silent because the board narrates with browser Web Speech, which a
headless recorder can't capture. This module synthesizes the narration into a WAV the
recorder can mux onto the video. Pluggable like the SVG/story providers: macOS `say` is
the zero-install local provider (verifiable on a dev Mac); Piper (portable) and cloud are
future opt-ins behind VOICE_PROVIDER. Returns None when no provider is available, so the
caller degrades cleanly to silence (never a hard failure).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def available(provider: str) -> bool:
    """True if `provider` can synthesize on this machine."""
    if provider == "say":  # macOS native
        return bool(shutil.which("say") and shutil.which("afconvert"))
    return False


def synthesize(text: str, provider: str = "say") -> bytes | None:
    """Narration text → WAV bytes, or None (empty text / provider unavailable / failure)."""
    text = (text or "").strip()
    if not text or not available(provider):
        return None
    if provider == "say":
        return _say_wav(text)
    return None


def _say_wav(text: str) -> bytes | None:
    """macOS `say` → AIFF → `afconvert` → 16-bit PCM WAV (both tools ship with macOS)."""
    try:
        with tempfile.TemporaryDirectory() as d:
            aiff, wav = Path(d) / "n.aiff", Path(d) / "n.wav"
            subprocess.run(["say", "-o", str(aiff), text], check=True, timeout=180)
            subprocess.run(
                ["afconvert", "-f", "WAVE", "-d", "LEI16@22050", str(aiff), str(wav)],
                check=True,
                timeout=60,
            )
            return wav.read_bytes()
    except Exception:  # noqa: BLE001 - any failure degrades to silence, never crashes the lesson
        return None


def narration(events) -> str:
    """The full spoken narration of a lesson, in order: each `say` event's text, joined.
    Inline [concept] mark brackets are stripped so the speech reads naturally."""
    lines = []
    for e in events:
        if isinstance(e, dict) and e.get("type") == "say" and e.get("text"):
            lines.append(re.sub(r"[\[\]]", "", str(e["text"])).strip())
    return " ".join(line for line in lines if line).strip()
