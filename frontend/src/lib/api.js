async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || `${r.status} ${r.statusText}`);
  }
  return r.json();
}

function qs(params) {
  return new URLSearchParams(
    Object.entries(params).filter(([, v]) => v != null && v !== ''),
  ).toString();
}

export const getStatus = () => getJSON('/api/engine/status');

export const getLesson = (params) => getJSON(`/api/engine/lesson?${qs(params)}`);

// The CHOREOGRAPHED timeline for the master-clock scheduler (Phase 2b) — draw-while-talking.
export const getTimeline = (params) => getJSON(`/api/engine/timeline?${qs(params)}`);

// Bring-your-own-story: animate a pasted storyboard (no model call).
export const animate = (body) => postJSON('/api/engine/animate', body);

// The prompt to hand a strong external model so its storyboard animates well here.
export const getScriptPrompt = (params) => getJSON(`/api/engine/script-prompt?${qs(params)}`);

async function getText(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.text();
}

// ---- Asset Studio: assets as first-class bundled, gated resources ---------- //
export const A = '/api/asset-studio';

export const assetCatalog = (params) => getJSON(`${A}/catalog?${qs(params)}`);
export const assetBundles = () => getJSON(`${A}/bundles`);
export const toggleBundle = (id, enabled) => postJSON(`${A}/bundles/toggle`, { id, enabled });
export const assetCoverage = () => getJSON(`${A}/coverage`);
export const assetFamilies = () => getJSON(`${A}/families`);

export const previewUrl = (concept, style = 'cartoon') =>
  `${A}/preview?${qs({ concept, style })}`;
export const previewSvg = (concept, style = 'cartoon') => getText(previewUrl(concept, style));

export const variantPreviewSvg = (family, params) =>
  getText(`${A}/variant/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ family, params }),
  });
export const variantGate = (family, params) => postJSON(`${A}/variant/gate`, { family, params });
export const variantSave = (body) => postJSON(`${A}/variant/save`, body);

// Promote imported candidates to engine-drawable (or demote).
export const publishAssets = (concepts) => postJSON(`${A}/publish`, { concepts });
export const publishAll = () => postJSON(`${A}/publish`, { all: true });
export const unpublishAssets = (concepts) => postJSON(`${A}/unpublish`, { concepts });

// ---- Excalidraw import candidates (MIT, references not trusted runtime) ----- //
export const excalIndex = (refresh = false) =>
  getJSON(`${A}/excalidraw/index?${qs({ refresh })}`);
export const excalImport = (body) => postJSON(`${A}/excalidraw/import`, body);
export const excalImportLibrary = (path) => postJSON(`${A}/excalidraw/import-library`, { path });
export const excalSync = (limit = 0) => postJSON(`${A}/excalidraw/sync?${qs({ limit })}`, {});
export const excalSyncStatus = () => getJSON(`${A}/excalidraw/sync-status`);
export const excalAuthors = (refresh = false) =>
  getJSON(`${A}/excalidraw/authors?${qs({ refresh })}`);
export const excalFiles = (authorPath) =>
  getJSON(`${A}/excalidraw/files?${qs({ author_path: authorPath })}`);
export const excalLibrary = (path) => getJSON(`${A}/excalidraw/library?${qs({ path })}`);
export const excalItem = (path, index) => getJSON(`${A}/excalidraw/item?${qs({ path, index })}`);
