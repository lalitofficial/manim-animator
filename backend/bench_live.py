"""Live-lesson benchmark: runs stream_lesson and simulates the consumer.

Implements the two-channel playback model from PAPER.md §4:

  visual channel  plays add/play/clear actions FIFO with their durations
  audio  channel  speaks "say" texts at SPEECH_CPS chars/sec, chained

An interval is *perceived idle* when an action's arrival time A_j exceeds
the moment both channels fell silent — i.e. the audience saw and heard
nothing while the model was still generating. This is the metric the
saturation theorem (Thm 1) and speech-credit lemma (§4.3) bound.

Usage:  python bench_live.py "topic" ["topic" ...]
Prints per-lesson: TTFA, action count, generation-gap percentiles,
perceived idle (count, total, ratio), and a verdict against the SLOs.
"""

from __future__ import annotations

import sys
import time

from actions import approx_extent
from ir import SceneObject
from lesson import stream_lesson

SPEECH_CPS = 15.0  # browser TTS, chars/sec (measured ballpark)
CLEAR_DUR = 0.6
SLO_TTFA = 20.0  # s, cold-call allowance for first LLM content
SLO_IDLE_RATIO = 0.05  # ≤5% of the lesson silent+still
SLO_GAP_P50 = 1.5  # s, median generation cadence


def bench(topic: str) -> dict:
    t0 = time.time()
    visual_t = 0.0  # when the visual channel falls silent
    audio_t = 0.0  # when the audio channel falls silent
    idle_mark = 0.0  # end of the last counted idle (interval union)
    arrivals: list[float] = []
    idles: list[tuple[float, float]] = []  # (start, length)
    first_llm = None
    n_actions = n_says = 0
    # Readability replica: final board boxes, rebuilt from the action stream.
    # Only text-vs-text overlap counts: overprinted labels are the
    # readability catastrophe; a thin diagonal arrow's mostly-empty bbox
    # crossing a label is not.
    board: dict[str, tuple] = {}  # id -> (is_text, cx, cy, w, h)
    max_text_overlap = 0.0  # worst board state seen

    def text_overlap() -> float:
        items = [b for b in board.values() if b[0]]
        area = 0.0
        for i, (_, xa, ya, wa, ha) in enumerate(items):
            for _, xb, yb, wb, hb in items[i + 1 :]:
                ix = min(xa + wa / 2, xb + wb / 2) - max(xa - wa / 2, xb - wb / 2)
                iy = min(ya + ha / 2, yb + hb / 2) - max(ya - ha / 2, yb - hb / 2)
                if ix > 0 and iy > 0:
                    area += ix * iy
        return area

    for ev in stream_lesson(topic):
        if ev["type"] != "action":
            continue
        if ev["kind"] == "add":
            o = SceneObject.model_validate(ev["object"])
            w, h = approx_extent(o)
            board[o.id] = (o.type in ("text", "mathtex"), o.position[0], o.position[1], w, h)
            max_text_overlap = max(max_text_overlap, text_overlap())
        elif ev["kind"] == "play":
            s = ev["step"]
            if s["animation"] == "fadeout":
                board.pop(s.get("target"), None)
            elif s["animation"] == "move" and s.get("target") in board and s.get("to"):
                t, _, _, w, h = board[s["target"]]
                board[s["target"]] = (t, s["to"][0], s["to"][1], w, h)
                max_text_overlap = max(max_text_overlap, text_overlap())
        elif ev["kind"] == "clear":
            board.clear()
        a = time.time() - t0
        if ev.get("seg", 0) >= 1:
            arrivals.append(a)
            if first_llm is None:
                first_llm = a
        n_actions += 1

        # Idle = time when neither channel is active, counted as an interval
        # *union* (several arrivals in one silent stretch share it).
        start = max(visual_t, audio_t, idle_mark)
        if ev.get("seg", 0) >= 1 and a > start + 1e-9:
            idles.append((start, a - start))
            idle_mark = a

        kind = ev["kind"]
        if kind == "say":
            n_says += 1
            audio_t = max(a, audio_t) + len(ev.get("text", "")) / SPEECH_CPS
        elif kind == "play":
            # Elastic playback (board.js _paceFactor): stretch when the
            # visual backlog is thin, compress when fat.
            backlog = max(0.0, visual_t - a)
            pace = 1.8 if backlog < 2 else 1.25 if backlog < 5 else 0.8 if backlog > 12 else 1.0
            d = float(ev["step"].get("duration") or 1.0) * pace
            visual_t = max(a, visual_t) + d
        elif kind == "clear":
            visual_t = max(a, visual_t) + CLEAR_DUR
        # "add" is instantaneous (objects appear via play)

    span = max(visual_t, audio_t, arrivals[-1] if arrivals else 0.0)
    gaps = sorted(b - a for a, b in zip(arrivals, arrivals[1:], strict=False))
    pct = lambda q: gaps[min(len(gaps) - 1, int(q * len(gaps)))] if gaps else 0.0
    idle_total = sum(l for _, l in idles)
    res = {
        "topic": topic,
        "ttfa": first_llm or 0.0,
        "actions": n_actions,
        "says": n_says,
        "gap_p50": pct(0.5),
        "gap_p95": pct(0.95),
        "gap_max": gaps[-1] if gaps else 0.0,
        "idle_n": len(idles),
        "idle_total": idle_total,
        "idle_ratio": idle_total / span if span else 0.0,
        "span": span,
        "idles": idles,
        "text_overlap": max_text_overlap,
    }
    return res


def report(r: dict) -> None:
    ok = lambda b: "PASS" if b else "FAIL"
    print(f"\n=== {r['topic']} ===")
    print(
        f"  first LLM action      {r['ttfa']:6.1f}s   [{ok(r['ttfa'] <= SLO_TTFA)} ≤{SLO_TTFA:.0f}s]"
    )
    print(f"  actions / says        {r['actions']} / {r['says']}")
    print(
        f"  generation gap p50    {r['gap_p50']:6.2f}s   [{ok(r['gap_p50'] <= SLO_GAP_P50)} ≤{SLO_GAP_P50}s]"
    )
    print(f"  generation gap p95    {r['gap_p95']:6.2f}s")
    print(f"  generation gap max    {r['gap_max']:6.2f}s")
    print(
        f"  perceived idle        {r['idle_n']} events, {r['idle_total']:.1f}s "
        f"of {r['span']:.1f}s = {100 * r['idle_ratio']:.1f}%   "
        f"[{ok(r['idle_ratio'] <= SLO_IDLE_RATIO)} ≤{100 * SLO_IDLE_RATIO:.0f}%]"
    )
    for start, length in r["idles"]:
        if length > 1.0:
            print(f"    idle {length:5.1f}s at t={start:.1f}s")
    # Idle-cover pulses fire every 2.5s while the board is idle, so the
    # longest truly *motionless* stretch is min(idle, 2.5s) by construction.
    worst = max((l for _, l in r["idles"]), default=0.0)
    print(f"  longest idle event    {worst:6.2f}s (motionless ≤2.5s with idle-cover pulses)")
    print(
        f"  worst text overlap    {r['text_overlap']:6.2f} sq.units   "
        f"[{ok(r['text_overlap'] <= 0.5)} ≤0.5]"
    )


if __name__ == "__main__":
    topics = sys.argv[1:] or ["why the sky is blue"]
    for t in topics:
        report(bench(t))
