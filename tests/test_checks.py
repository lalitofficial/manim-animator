"""Tests for the dashboard's check layer (engine.checks) + the /api/checks routes.

The dashboard reports test/check status, so its OWN correctness matters: a report
that shows green while something is red is the failure mode we built the whole
ruler to avoid (§K1/§K2). These tests verify the reports reflect real invariants
and that a forced failure actually flips the report to fail.
"""

from __future__ import annotations

from engine import checks


def test_health_reports_providers_and_counts():
    h = checks.health()
    assert h["corpus_cases"] >= 9
    assert h["drawing_scenes"] >= 5
    assert "story_provider" in h and "svg_provider" in h


def test_positioning_report_passes_and_is_per_case():
    rep = checks.positioning_report()
    assert rep["pass"] is True
    assert len(rep["cases"]) >= 9
    for c in rep["cases"]:
        assert {"name", "level", "pass", "overlap", "drops"} <= c.keys()
        assert c["pass"] is True


def test_drawing_report_passes_with_extent_honesty():
    rep = checks.drawing_report()
    assert rep["pass"] is True
    assert all(s["extent_error"] <= 0.10 for s in rep["scenes"])


def test_speed_report_has_numbers():
    rep = checks.speed_report()
    assert rep["ms_per_lesson"] > 0
    assert len(rep["positioning_scaling"]) == 3


def test_lesson_report_renders_and_carries_svg():
    rep = checks.lesson_report("the water cycle")
    assert rep["pass"] is True
    assert rep["narration"] and rep["beats"] > 0
    assert rep["svg"].startswith("<svg")


def test_full_report_aggregates_all_sections():
    rep = checks.full_report()
    assert set(rep) == {"pass", "health", "positioning", "drawing", "speed"}
    assert rep["pass"] is True
    assert rep["pass"] == (rep["positioning"]["pass"] and rep["drawing"]["pass"])


def test_report_is_faithful_flips_on_a_real_failure(monkeypatch):
    """If an invariant actually fails, the report must say FAIL — not green."""
    import engine.invariants as inv

    monkeypatch.setattr(inv, "overlap_area", lambda placements: 99.0)  # force overlap
    rep = checks.positioning_report()
    assert rep["pass"] is False
    assert any(c["pass"] is False for c in rep["cases"])


def test_dropping_everything_flips_to_fail(monkeypatch):
    """The coverage false-green (review A1): if placement drops all Things, the
    report must FAIL even though an empty board is vacuously overlap-free."""
    monkeypatch.setattr(
        checks,
        "place",
        lambda things, board: ([], [{"id": t.id, "reason": "forced"} for t in things]),
    )
    rep = checks.positioning_report()
    assert rep["pass"] is False
    assert all(c["pass"] is False for c in rep["cases"])


def test_run_suite_surfaces_a_failing_pytest(monkeypatch):
    class FakeProc:
        returncode = 1
        stdout = "tests/x.py F\n=== 1 failed, 2 passed in 0.1s ==="
        stderr = ""

    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: FakeProc())
    r = checks.run_suite()
    assert r["ok"] is False
    assert "failed" in r["summary"] and r["tail"]


# --- HTTP surface (uses the hermetic client fixture from conftest) --------- #
def test_checks_all_endpoint(client):
    r = client.get("/api/checks/all")
    assert r.status_code == 200
    body = r.json()
    assert body["positioning"]["pass"] and body["drawing"]["pass"]


def test_dashboard_view_serves(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert b"TEST" in r.content


def test_checks_lesson_endpoint(client):
    r = client.get("/api/checks/lesson", params={"topic": "binary search"})
    assert r.status_code == 200
    assert r.json()["svg"].startswith("<svg")
