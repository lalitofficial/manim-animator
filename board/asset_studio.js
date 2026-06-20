const $ = (id) => document.getElementById(id);

let authors = [];
let selectedLibrary = '';

function esc(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function optionList(el, values, label = (v) => v) {
  el.innerHTML = values.map((v) => `<option value="${esc(v)}">${esc(label(v))}</option>`).join('');
}

function renderStats(stats = {}) {
  const cards = [
    ['Assets', stats.total ?? 0],
    ['Candidates', stats.candidates ?? 0],
    ['Colored', stats.by_style?.colored ?? 0],
    ['Families', stats.by_kind?.family ?? 0],
    ['Catalog', stats.by_kind?.catalog ?? 0],
  ];
  $('stats').innerHTML = cards
    .map(([k, v]) => `<div class="stat"><b>${esc(v)}</b><span class="muted">${esc(k)}</span></div>`)
    .join('');
}

async function loadBundles() {
  const data = await getJson('/api/asset-studio/bundles');
  optionList($('bundle'), ['', ...data.bundles.map((b) => b.id)], (v) => v || 'all');
}

async function loadCatalog() {
  const params = new URLSearchParams({
    q: $('q').value.trim(),
    bundle: $('bundle').value,
    kind: $('kind').value,
    style: $('style').value,
    status: $('statusFilter').value,
    limit: '120',
  });
  const data = await getJson(`/api/asset-studio/catalog?${params}`);
  renderStats(data.stats);
  $('catalogMeta').textContent = `${data.total} matched`;
  $('catalog').innerHTML = data.items
    .map(
      (a) => `<div class="row">
        <div>
          <b>${esc(a.concept)}</b>
          <div class="tags">
            <span class="tag">${esc(a.bundle)}</span>
            <span class="tag">${esc(a.kind)}</span>
            <span class="tag">${esc(a.style)}</span>
            <span class="tag">${esc(a.license)}</span>
          </div>
        </div>
        <button class="secondary" data-preview="${esc(a.concept)}">Preview</button>
      </div>`,
    )
    .join('');
  for (const btn of document.querySelectorAll('[data-preview]')) {
    btn.addEventListener('click', () => {
      window.open(`/api/asset-studio/preview?concept=${encodeURIComponent(btn.dataset.preview)}`);
    });
  }
}

async function loadCoverage() {
  const data = await getJson('/api/asset-studio/coverage');
  $('catalogMeta').textContent =
    `coverage ${Math.round(data.composed_rate * 100)}% · fallback ${Math.round(data.fallback_rate * 100)}%`;
  $('catalog').innerHTML = [
    `<div class="row"><div><b>Boxed Concepts</b><div class="muted">${esc(data.boxed.join(', ') || 'none')}</div></div></div>`,
    `<div class="row"><div><b>Source Breakdown</b><div class="muted">${esc(JSON.stringify(data.source_breakdown))}</div></div></div>`,
    `<div class="row"><div><b>Missing Requests</b><div class="muted">${esc(
      data.missing_nouns.map((m) => `${m.concept} (${m.requests})`).join(', ') || 'none logged',
    )}</div></div></div>`,
  ].join('');
}

function renderAuthors() {
  const q = $('authorSearch').value.trim().toLowerCase();
  const visible = authors.filter((a) => !q || a.name.toLowerCase().includes(q));
  $('authors').innerHTML = visible
    .slice(0, 160)
    .map(
      (a) => `<div class="row">
        <div><b>${esc(a.name)}</b><div class="muted">${esc(a.path)}</div></div>
        <button data-author="${esc(a.path)}">Open</button>
      </div>`,
    )
    .join('');
  for (const btn of document.querySelectorAll('[data-author]')) {
    btn.addEventListener('click', () => loadFiles(btn.dataset.author));
  }
}

async function loadAuthors(refresh = false) {
  $('authors').innerHTML = '<div class="muted">Loading authors...</div>';
  const data = await getJson(
    `/api/asset-studio/excalidraw/authors?refresh=${refresh ? 'true' : 'false'}`,
  );
  authors = data.authors || [];
  renderAuthors();
}

async function loadFiles(authorPath) {
  $('files').innerHTML = '<div class="muted">Loading files...</div>';
  $('items').innerHTML = '';
  $('exPreview').innerHTML = '<span class="muted">Select an item</span>';
  const data = await getJson(
    `/api/asset-studio/excalidraw/files?author_path=${encodeURIComponent(authorPath)}`,
  );
  $('files').innerHTML = (data.files || [])
    .map(
      (f) => `<div class="row">
        <div>
          <b>${esc(f.name)}</b>
          <div class="tags"><span class="tag">${esc(f.license)}</span><span class="tag">${esc(f.size)} bytes</span></div>
        </div>
        <button data-lib="${esc(f.path)}">Inspect</button>
      </div>`,
    )
    .join('');
  for (const btn of document.querySelectorAll('[data-lib]')) {
    btn.addEventListener('click', () => loadLibrary(btn.dataset.lib));
  }
}

async function loadLibrary(path) {
  selectedLibrary = path;
  $('items').innerHTML = '<div class="muted">Parsing library...</div>';
  $('exPreview').innerHTML = '<span class="muted">Select an item</span>';
  const data = await getJson(
    `/api/asset-studio/excalidraw/library?path=${encodeURIComponent(path)}`,
  );
  $('items').innerHTML = data.items
    .map(
      (item, i) => `<div class="row">
        <div>
          <b>${esc(item.name)}</b>
          <div class="tags">
            <span class="tag">${esc(item.elements)} elements</span>
            <span class="tag">${esc(Object.keys(item.types || {}).join(', ') || 'unknown')}</span>
            <span class="tag">candidate</span>
          </div>
        </div>
        <button data-item="${i}">Preview</button>
      </div>`,
    )
    .join('');
  for (const btn of document.querySelectorAll('[data-item]')) {
    btn.addEventListener('click', () => loadItem(Number(btn.dataset.item)));
  }
}

async function loadItem(index) {
  if (!selectedLibrary) return;
  $('exPreview').innerHTML = '<span class="muted">Rendering...</span>';
  const data = await getJson(
    `/api/asset-studio/excalidraw/item?path=${encodeURIComponent(selectedLibrary)}&index=${index}`,
  );
  $('exPreview').innerHTML = data.svg || '<span class="muted">No preview</span>';
}

async function init() {
  optionList(
    $('kind'),
    ['', 'override', 'core', 'cartoon', 'family', 'mono', 'catalog', 'candidate'],
    (v) => v || 'all',
  );
  optionList($('style'), ['', 'colored', 'mono', 'line', 'candidate'], (v) => v || 'all');
  optionList($('statusFilter'), ['', 'active', 'shadowed', 'candidate'], (v) => v || 'all');
  await loadBundles();
  await loadCatalog();
}

$('search').addEventListener('click', loadCatalog);
$('coverage').addEventListener('click', loadCoverage);
$('loadAuthors').addEventListener('click', () => loadAuthors(false));
$('authorSearch').addEventListener('input', renderAuthors);
$('q').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') loadCatalog();
});

init().catch((err) => {
  $('catalog').innerHTML = `<div class="muted">${esc(err)}</div>`;
});
