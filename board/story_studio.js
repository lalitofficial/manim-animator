const $ = (id) => document.getElementById(id);
let lastPackage = null;
let examples = [];

function payload() {
  return {
    prompt: $('prompt').value.trim(),
    arc: $('arc').value,
    audience: $('audience').value,
    tone: $('tone').value,
    length: $('length').value,
    provider: $('providerSelect').value,
  };
}

function scoreClass(v) {
  if (v >= 4) return '#3fb950';
  if (v >= 3) return '#d29922';
  return '#f85149';
}

function render(data) {
  lastPackage = data;
  $('title').textContent = data.title || 'Untitled';
  $('logline').textContent = data.logline || '';
  const arc = data.character_arc || {};
  $('story').textContent = data.story || '';
  $('promise').textContent = data.promise || '';
  $('characterArc').innerHTML = [
    ['Protagonist', arc.protagonist],
    ['Want', arc.want],
    ['Need', arc.need],
    ['Obstacle', arc.obstacle],
    ['Stakes', arc.stakes],
    ['Revelation', arc.revelation],
  ]
    .filter(([, v]) => v)
    .map(
      ([k, v]) =>
        `<div class="score"><span>${escapeHtml(k)}</span><span>${escapeHtml(v)}</span></div>`,
    )
    .join('');

  const p = data.provider || {};
  $('providerInfo').innerHTML = [
    `<span class="pill">${p.provider || 'unknown'}</span>`,
    p.model ? ` ${p.model}` : '',
    p.reason ? `<div class="muted">${p.reason}</div>` : '',
  ].join('');
  $('warnings').innerHTML = (data.warnings || []).map((w) => `<p>${escapeHtml(w)}</p>`).join('');

  $('scores').innerHTML = Object.entries(data.scores || {})
    .map(
      ([k, v]) =>
        `<div class="score"><span>${escapeHtml(k)}</span><b style="color:${scoreClass(v)}">${v}/5</b></div>`,
    )
    .join('');

  $('critique').innerHTML = (data.critique || []).map((c) => `<li>${escapeHtml(c)}</li>`).join('');

  $('scenes').innerHTML = (data.scenes || [])
    .map(
      (s) => `<div class="scene">
        <h3>${escapeHtml(s.title || 'Scene')}</h3>
        <div class="muted">${escapeHtml(s.purpose || '')} · ${escapeHtml(s.emotion || '')}</div>
        <p><b>Focus:</b> ${escapeHtml(s.focus || '')}</p>
        <p>${escapeHtml(s.beat || '')}</p>
        <p><b>Direction:</b> ${escapeHtml(s.direction || '')}</p>
        <p><b>Goal:</b> ${escapeHtml(s.goal || '')}</p>
        <p><b>Conflict:</b> ${escapeHtml(s.conflict || '')}</p>
        <p><b>Turn:</b> ${escapeHtml(s.turn || '')}</p>
        <p><b>Reaction:</b> ${escapeHtml(s.reaction || '')}</p>
        <p><b>Decision:</b> ${escapeHtml(s.decision || '')}</p>
      </div>`,
    )
    .join('');
  $('save').disabled = false;
  $('saveStatus').textContent = '';
}

function escapeHtml(s) {
  return String(s || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

async function generate() {
  const button = $('generate');
  button.disabled = true;
  button.textContent = 'Generating...';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45000);
  try {
    const res = await fetch('/api/story-studio/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload()),
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    render(await res.json());
  } catch (err) {
    $('title').textContent = 'Error';
    $('logline').textContent =
      err && err.name === 'AbortError'
        ? 'Story generation timed out. Try provider=template, or use a smaller local model.'
        : String(err);
  } finally {
    clearTimeout(timer);
    button.disabled = false;
    button.textContent = 'Generate';
  }
}

async function saveFeedback() {
  if (!lastPackage) return;
  const button = $('save');
  button.disabled = true;
  button.textContent = 'Saving...';
  $('saveStatus').textContent = '';
  try {
    const res = await fetch('/api/story-studio/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        package: lastPackage,
        rating: $('rating').value ? Number($('rating').value) : null,
        note: $('note').value,
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    $('saveStatus').textContent = `Saved to ${data.path}`;
  } catch (err) {
    $('saveStatus').textContent = `Save failed: ${err}`;
  } finally {
    button.disabled = false;
    button.textContent = 'Save Feedback';
  }
}

async function loadExamples() {
  try {
    const res = await fetch('/api/story-studio/examples');
    examples = (await res.json()).examples || [];
    $('exampleSelect').innerHTML =
      '<option value="">custom prompt</option>' +
      examples
        .map(
          (e) =>
            `<option value="${escapeHtml(e.id)}">${escapeHtml(e.id.replaceAll('_', ' '))}</option>`,
        )
        .join('');
  } catch (_err) {
    examples = [];
  }
}

function applyExample(id) {
  const ex = examples.find((e) => e.id === id);
  if (!ex) return;
  $('prompt').value = ex.prompt || '';
  $('arc').value = ex.arc || 'explainer';
  $('audience').value = ex.audience || 'general';
  $('tone').value = ex.tone || 'warm';
  $('providerSelect').value = 'template';
}

$('generate').addEventListener('click', generate);
$('save').addEventListener('click', saveFeedback);
$('exampleSelect').addEventListener('change', (ev) => applyExample(ev.target.value));
loadExamples();
