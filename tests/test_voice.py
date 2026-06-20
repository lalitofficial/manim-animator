"""Server-side TTS — narration extraction + the /api/engine/audio endpoint.

Hermetic: audio synthesis is monkeypatched, so macOS `say` is never invoked in CI.
"""

from __future__ import annotations

from engine import voice


def test_narration_joins_say_events_and_strips_marks():
    events = [
        {"type": "start"},
        {"type": "say", "text": "The [sun] warms the [water]."},
        {"type": "draw", "op": {}},
        {"type": "say", "text": "Then it rains."},
    ]
    assert voice.narration(events) == "The sun warms the water. Then it rains."


def test_synthesize_degrades_cleanly():
    assert voice.synthesize("", "say") is None  # empty text → nothing
    assert voice.synthesize("hello", "bogus") is None  # unknown provider → nothing
    assert voice.available("bogus") is False


def test_audio_endpoint_returns_wav(client, monkeypatch):
    from engine import voice as v

    monkeypatch.setattr(v, "available", lambda p: True)
    monkeypatch.setattr(v, "synthesize", lambda text, provider="say": b"RIFFfake")
    r = client.get("/api/engine/audio", params={"topic": "the water cycle"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content == b"RIFFfake"


def test_audio_endpoint_501_without_server_tts(client, monkeypatch):
    from engine import voice as v

    monkeypatch.setattr(v, "available", lambda p: False)
    r = client.get("/api/engine/audio", params={"topic": "x", "text": "hi"})
    assert r.status_code == 501
