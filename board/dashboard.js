// Engine test/check dashboard. Pulls real in-process check reports from the
// backend (/api/checks/*) and renders status. Faithful by construction: every
// number comes straight from the engine's output-derived invariants, and the
// overall pill is recomputed from EVERY gate (positioning, drawing, lesson, suite).

const $ = (id) => document.getElementById(id);

// Tri-state per gate: true = pass, false = fail, null = not run / unknown.
const status = { positioning: null, drawing: null, lesson: null, suite: null };

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function setPill(el, state, labelPass, labelFail) {
  if (state === null) {
    el.className = 'pill muted';
    el.textContent = '…';
    return;
  }
  el.className = `pill ${state ? 'pass' : 'fail'}`;
  el.textContent = state ? labelPass || 'PASS' : labelFail || 'FAIL';
}

function refreshOverall() {
  const el = $('overall');
  const known = Object.values(status).filter((v) => v !== null);
  if (known.some((v) => v === false)) {
    el.className = 'pill fail';
    el.textContent = 'GATES FAILING';
  } else if (known.length === 0) {
    el.className = 'pill muted';
    el.textContent = '…';
  } else {
    el.className = 'pill pass';
    el.textContent = `GATES PASS · suite ${status.suite === null ? 'not run' : 'pass'}`;
  }
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return res.json();
}

function rowCells(values) {
  return values.map((v) => `<td class="num">${esc(v)}</td>`).join('');
}

function statusPill(pass) {
  return `<span class="pill ${pass ? 'pass' : 'fail'}">${pass ? 'PASS' : 'FAIL'}</span>`;
}

function renderHealth(h) {
  const rows = [
    ['Python', h.python],
    ['Story provider', h.story_provider],
    ['SVG provider', h.svg_provider],
    ['Corpus cases', h.corpus_cases],
    ['Drawing scenes', h.drawing_scenes],
    ['Board', `${h.board.w} × ${h.board.h}`],
  ];
  $('health').innerHTML = rows
    .map(([k, v]) => `<div class="k">${esc(k)}</div><div>${esc(v)}</div>`)
    .join('');
}

function renderSpeed(s) {
  const scaling = s.positioning_scaling
    .map(
      (r) =>
        `<tr><td>N=${r.n}</td><td class="num">${r.ms} ms</td><td class="num">${r.placed} placed · ${r.dropped} dropped</td></tr>`,
    )
    .join('');
  $('speed').innerHTML = `
    <div class="big">${s.ms_per_lesson} ms</div>
    <div class="sub">per lesson (offline, ${s.lessons_measured} measured)</div>
    <table style="margin-top:10px">
      <thead><tr><th>positioning</th><th>time</th><th></th></tr></thead>
      <tbody>${scaling}</tbody>
    </table>`;
}

function gatePill(el, report) {
  const passing = report.cases ? report.cases : report.scenes;
  const k = passing.filter((c) => c.pass).length;
  setPill(el, report.pass, `PASS · ${k}/${passing.length}`, `FAIL · ${k}/${passing.length}`);
}

function renderPositioning(p) {
  gatePill($('pos-pill'), p);
  const head =
    '<tr><th>case</th><th>lvl</th><th>status</th><th>placed</th><th>drops</th><th>overlap</th><th>off</th><th>rows</th></tr>';
  const body = p.cases
    .map(
      (c) =>
        `<tr><td>${esc(c.name)}</td><td>${esc(c.level)}</td><td>${statusPill(c.pass)}</td>${rowCells(
          [`${c.placed}/${c.total}`, c.drops, c.overlap, c.off_board, c.rows],
        )}</tr>`,
    )
    .join('');
  $('positioning').innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderDrawing(d) {
  gatePill($('draw-pill'), d);
  const head =
    '<tr><th>scene</th><th>status</th><th>placed</th><th>drops</th><th>conn</th><th>overlap</th><th>extent-err</th></tr>';
  const body = d.scenes
    .map(
      (s) =>
        `<tr><td>${esc(s.name)}</td><td>${statusPill(s.pass)}</td>${rowCells([
          `${s.placed}/${s.total}`,
          s.drops,
          s.connectors,
          s.overlap,
          s.extent_error,
        ])}</tr>`,
    )
    .join('');
  $('drawing').innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

async function loadAll() {
  const btn = $('rerun');
  btn.disabled = true;
  setPill($('overall'), null);
  $('overall').textContent = 'running…';
  try {
    const data = await getJSON('/api/checks/all');
    renderHealth(data.health);
    renderSpeed(data.speed);
    renderPositioning(data.positioning);
    renderDrawing(data.drawing);
    status.positioning = data.positioning.pass;
    status.drawing = data.drawing.pass;
  } catch (err) {
    // Don't leave last run's green pills standing on an error (review B4).
    status.positioning = null;
    status.drawing = null;
    setPill($('pos-pill'), null);
    setPill($('draw-pill'), null);
    $('overall').className = 'pill fail';
    $('overall').textContent = `error: ${err}`;
    btn.disabled = false;
    return;
  }
  refreshOverall();
  btn.disabled = false;
}

async function renderLesson() {
  const topic = $('topic').value.trim() || 'the water cycle';
  const btn = $('render');
  btn.disabled = true;
  $('lesson-stats').textContent = 'rendering…';
  try {
    const l = await getJSON(`/api/checks/lesson?topic=${encodeURIComponent(topic)}`);
    status.lesson = l.pass;
    $('lesson-svg').innerHTML = l.svg;
    const rungs = Object.entries(l.rung_hits)
      .map(([k, v]) => `rung ${k}×${v}`)
      .join(', ');
    let label = 'PASS';
    if (!l.pass) {
      const reasons = [];
      if (l.overlap > 0) reasons.push(`overlap ${l.overlap}`);
      if (l.off_board && l.off_board.length) reasons.push(`off-board ${l.off_board.join(',')}`);
      if (l.relation_violations.length) reasons.push(l.relation_violations.join('; '));
      if (l.extent_error > 0.1) reasons.push(`extent-err ${l.extent_error}`);
      label = `FAIL (${reasons.join(' · ') || 'invariant failed — see stats'})`;
    }
    $('lesson-stats').innerHTML =
      `<b>${esc(label)}</b> · ${l.beats} beats · placed ${l.placed}/${l.total} · drops ${l.drops} · overlap ${l.overlap} · ${esc(rungs)}`;
    $('lesson-narration').innerHTML = l.narration.map((n) => `<li>${esc(n)}</li>`).join('');
  } catch (err) {
    status.lesson = null;
    $('lesson-stats').textContent = `error: ${err}`;
  }
  refreshOverall();
  btn.disabled = false;
}

async function runSuite() {
  const btn = $('run-suite');
  btn.disabled = true;
  setPill($('suite-pill'), null);
  $('suite-pill').textContent = 'running…';
  $('suite-summary').textContent = 'pytest is starting (imports manim, ~a few seconds)…';
  try {
    const r = await getJSON('/api/checks/suite');
    status.suite = r.ok;
    setPill($('suite-pill'), r.ok);
    $('suite-summary').textContent = `${r.summary || r.error || ''} · ${r.duration_ms} ms`;
    const tail = $('suite-tail');
    tail.textContent = r.tail || r.error || '';
    tail.hidden = !tail.textContent;
  } catch (err) {
    status.suite = null;
    $('suite-pill').className = 'pill fail';
    $('suite-pill').textContent = 'error';
    $('suite-summary').textContent = `${err}`;
  }
  refreshOverall();
  btn.disabled = false;
}

$('rerun').addEventListener('click', loadAll);
$('render').addEventListener('click', renderLesson);
$('run-suite').addEventListener('click', runSuite);
$('topic').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    renderLesson();
  }
});

loadAll();
renderLesson();
