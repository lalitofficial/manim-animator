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
