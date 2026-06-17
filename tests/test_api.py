"""HTTP surface: the read-only routes must serve without Ollama or rendering."""

from __future__ import annotations


def test_index_serves_board(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"<" in r.content  # the board HTML


def test_modes_registry(client):
    r = client.get("/api/modes")
    assert r.status_code == 200
    body = r.json()
    assert "modes" in body
    assert isinstance(body["modes"], list)
    assert body["modes"], "at least the default 'learn' mode should be registered"


def test_asset_catalog(client):
    r = client.get("/api/assets")
    assert r.status_code == 200
    assert "catalog" in r.json()


def test_unknown_job_is_not_found(client):
    r = client.get("/api/jobs/doesnotexist")
    assert r.status_code == 200
    assert r.json()["status"] == "not_found"


def test_index_serves_a_board(client):
    # `/` is the built Studio (redirects to /studio/) or the vanilla board fallback.
    r = client.get("/")  # client follows redirects
    assert r.status_code == 200
    assert b'id="app"' in r.content or b"data-mode" in r.content


def test_engine_board_has_mode_chips(client):
    r = client.get("/engine")
    assert r.status_code == 200
    assert b"data-mode" in r.content  # the vanilla board's mode chips


def test_legacy_board_still_served(client):
    r = client.get("/legacy")
    assert r.status_code == 200
    assert b"<" in r.content


def test_engine_modes_endpoint(client):
    r = client.get("/api/engine/modes")
    assert r.status_code == 200
    assert set(r.json()["modes"]) == {"learn", "story", "draw", "explain"}


def test_engine_lesson_honors_mode(client):
    r = client.get("/api/engine/lesson", params={"topic": "the water cycle", "mode": "story"})
    assert r.status_code == 200
    body = r.json()
    events = body["events"]
    assert events[0]["type"] == "start" and events[0]["mode"] == "story"
    assert any(e["type"] == "clear" for e in events)  # story mode has scene breaks
    assert body["spec"]["mode"] == "story"  # the Director spec is surfaced


def test_engine_director_endpoint(client):
    r = client.get("/api/engine/director", params={"topic": "x", "audience": "child"})
    assert r.status_code == 200
    spec = r.json()
    assert spec["audience"] == "child" and "concept_count" in spec


def test_engine_status_reports_providers(client):
    r = client.get("/api/engine/status")
    assert r.status_code == 200
    body = r.json()
    assert {"story_provider", "svg_provider", "ollama_reachable", "warnings"} <= body.keys()
    # Default config is template/fixture — that must surface as a warning, not silence.
    assert any("template" in w.lower() for w in body["warnings"])


def test_engine_lesson_honors_audience_pacing(client):
    r = client.get("/api/engine/lesson", params={"topic": "x", "audience": "child"})
    spec = r.json()["spec"]
    assert spec["audience"] == "child" and spec["energy"] == "lively"  # kid -> lively pacing


def test_engine_script_prompt(client):
    # default = a directed STORYBOARD (scenes/shots/actions — a film)
    r = client.get("/api/engine/script-prompt", params={"topic": "the water cycle"})
    assert r.status_code == 200
    p = r.json()["prompt"]
    assert '"scenes"' in p and "water cycle" in p and "drawable" in p.lower()
    # fmt=beats gives the simpler flat format
    rb = client.get("/api/engine/script-prompt", params={"topic": "x", "fmt": "beats"})
    assert '"beats"' in rb.json()["prompt"]


def test_engine_animate_pasted_story(client):
    """Bring-your-own-story: a pasted storyboard animates with no model call."""
    script = (
        '{"beats":['
        '{"kind":"show","entity":"sun","concept":"sun","relation":{"at":"top_left"}},'
        '{"kind":"say","text":"The sun shines."},'
        '{"kind":"show","entity":"cloud","concept":"cloud","relation":{"right_of":"sun"}},'
        '{"kind":"connect","src":"sun","dst":"cloud","label":"warms"}]}'
    )
    r = client.post(
        "/api/engine/animate",
        json={"script": script, "topic": "the water cycle", "style": "cartoon"},
    )
    assert r.status_code == 200
    evs = r.json()["events"]
    assert evs[0]["type"] == "start" and evs[0]["story"]["used"] == "script"
    drawn = {e["op"]["id"] for e in evs if e["type"] == "draw"}
    assert {"sun", "cloud"} <= drawn  # the pasted concepts drew (no model involved)

    # tolerant of markdown ``` fences a model often adds
    r2 = client.post("/api/engine/animate", json={"script": f"```json\n{script}\n```"})
    assert r2.status_code == 200


def test_engine_animate_rejects_unparseable(client):
    r = client.post("/api/engine/animate", json={"script": "this is not json"})
    assert r.status_code == 400
