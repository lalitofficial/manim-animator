// v3 engine board: fetch the lesson event stream and animate it. Whiteboard =
// mono stroke-on reveal (unchanged). Cartoon = a colored scene backdrop + filled
// shapes that ink their outline then flood their fill, with entrance + ambient
// motion. Style is carried per-stream by the `start` event (palette.py).

const SVG_NS = 'http://www.w3.org/2000/svg';
const PX = 65.7; // pixels per board unit (920 / 14)
const DRAW_SPEED = 520; // px per second for the pen reveal
const SPEECH_CPS = 14; // chars/sec, for pacing narration
const VOICE_TIMEOUT_PAD = 1800; // safety if a browser never fires speech end

const board = document.getElementById('board');
const caption = document.getElementById('caption');
const provenance = document.getElementById('provenance');
const statusBar = document.getElementById('status');
const topicInput = document.getElementById('topic');
const goButton = document.getElementById('go');

let halfW = 7;
let halfH = 4;
let mode = 'learn';
let audience = 'general';
let style = 'cartoon'; // the board defaults to the cartoon look (the product)
let pacing = { draw_speed: 1, say_dwell: 1 };
let defs = null; // shared <defs> for gradients
let gradSeq = 0;
let voices = [];
let selectedVoice = null;
let voicePromise = null;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function toPx(x, y) {
  return [(x + halfW) * PX, (halfH - y) * PX];
}

function clearBoard() {
  while (board.firstChild) {
    board.removeChild(board.firstChild);
  }
  defs = document.createElementNS(SVG_NS, 'defs');
  board.appendChild(defs);
}

// SVG paints in document order, so honor op.z: insert each layer before the first
// existing element with a higher z. Equal z keeps stream-arrival order (stable).
// Contract: background 0 < things 1 < connectors 2 < presenter 3.
function insertByZ(el, z) {
  el.dataset.z = String(z);
  let ref = null;
  for (const child of board.children) {
    if (child === defs) {
      continue;
    }
    const cz = child.dataset && child.dataset.z !== undefined ? Number(child.dataset.z) : 1;
    if (cz > z) {
      ref = child;
      break;
    }
  }
  board.insertBefore(el, ref);
}

function estimateSpeechMs(text, profile = voiceProfile()) {
  const cps = SPEECH_CPS * Math.max(0.65, profile.rate || 1);
  return Math.min(14000, Math.max(900, (text.length / cps) * 1000 * pacing.say_dwell));
}

function loadVoices() {
  if (!('speechSynthesis' in window)) {
    return Promise.resolve([]);
  }
  if (voicePromise) {
    return voicePromise;
  }
  voicePromise = new Promise((resolve) => {
    const done = () => {
      voices = window.speechSynthesis.getVoices() || [];
      if (voices.length) {
        resolve(voices);
      }
    };
    done();
    if (!voices.length) {
      window.speechSynthesis.onvoiceschanged = done;
      setTimeout(() => resolve(window.speechSynthesis.getVoices() || []), 800);
    }
  });
  return voicePromise;
}

function scoreVoice(v) {
  const name = `${v.name} ${v.voiceURI}`.toLowerCase();
  let score = 0;
  if (/en[-_]/i.test(v.lang)) score += 30;
  if (v.lang && v.lang.toLowerCase().startsWith('en-us')) score += 8;
  if (v.localService === false) score += 14; // Chrome/Edge cloud/natural voices are usually better.
  if (/natural|neural|premium|enhanced|online/.test(name)) score += 28;
  if (/google|microsoft|apple/.test(name)) score += 14;
  if (/ava|samantha|zoe|jenny|aria|guy|brian|emma|sonia|libby/.test(name)) score += 12;
  if (/compact|novelty|robot|whisper|zarvox|fred|bad news|bells/.test(name)) score -= 40;
  return score;
}

async function chooseVoice() {
  await loadVoices();
  const list = window.speechSynthesis.getVoices() || voices;
  if (!list.length) {
    selectedVoice = null;
    return null;
  }
  selectedVoice = [...list].sort((a, b) => scoreVoice(b) - scoreVoice(a))[0];
  return selectedVoice;
}

function voiceProfile() {
  if (style === 'cartoon' || audience === 'child') {
    return { rate: 0.9, pitch: 1.12, volume: 1 };
  }
  if (mode === 'story') {
    return { rate: 0.88, pitch: 1.02, volume: 1 };
  }
  if (audience === 'expert') {
    return { rate: 0.98, pitch: 0.96, volume: 1 };
  }
  if (mode === 'explain') {
    return { rate: 0.96, pitch: 1.0, volume: 1 };
  }
  return { rate: 0.94, pitch: 1.0, volume: 1 };
}

async function speak(text) {
  if (!('speechSynthesis' in window) || !text) {
    await sleep(estimateSpeechMs(text));
    return;
  }
  const profile = voiceProfile();
  const voice = selectedVoice || (await chooseVoice());
  await new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    if (voice) {
      u.voice = voice;
      u.lang = voice.lang;
    } else {
      u.lang = 'en-US';
    }
    u.rate = profile.rate;
    u.pitch = profile.pitch;
    u.volume = profile.volume;
    let finished = false;
    const finish = () => {
      if (finished) {
        return;
      }
      finished = true;
      resolve();
    };
    u.onend = finish;
    u.onerror = finish;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    setTimeout(finish, estimateSpeechMs(text, profile) + VOICE_TIMEOUT_PAD);
  });
  await sleep(style === 'cartoon' ? 180 : 90);
}

// A full-board scene backdrop (cartoon only): a vertical 2-stop gradient rect
// behind everything. Drawn instantly — the scene is the stage, not a "drawing".
function drawBackground(ev) {
  const rect = document.createElementNS(SVG_NS, 'rect');
  rect.setAttribute('x', '0');
  rect.setAttribute('y', '0');
  rect.setAttribute('width', `${halfW * 2 * PX}`);
  rect.setAttribute('height', `${halfH * 2 * PX}`);
  if (ev.gradient) {
    const id = `bg${gradSeq++}`;
    const grad = document.createElementNS(SVG_NS, 'linearGradient');
    grad.setAttribute('id', id);
    grad.setAttribute('x1', '0');
    grad.setAttribute('y1', '0');
    grad.setAttribute('x2', '0');
    grad.setAttribute('y2', '1');
    for (const [off, col] of [
      ['0%', ev.gradient.top],
      ['100%', ev.gradient.bottom],
    ]) {
      const stop = document.createElementNS(SVG_NS, 'stop');
      stop.setAttribute('offset', off);
      stop.setAttribute('stop-color', col);
      grad.appendChild(stop);
    }
    defs.appendChild(grad);
    rect.setAttribute('fill', `url(#${id})`);
  } else {
    rect.setAttribute('fill', ev.fill || '#eaf3fb');
  }
  rect.style.opacity = '0';
  rect.style.transition = 'opacity 500ms ease-in';
  insertByZ(rect, 0); // the backdrop sits behind every later stroke
  requestAnimationFrame(() => {
    rect.style.opacity = '1';
  });
  if (ev.ground) {
    // The horizon band — props stand ON it (a scene with ground, not floating space).
    const boardH = halfH * 2 * PX;
    const gh = boardH * ev.ground.frac;
    const g2 = document.createElementNS(SVG_NS, 'rect');
    g2.setAttribute('x', '0');
    g2.setAttribute('y', `${boardH - gh}`);
    g2.setAttribute('width', `${halfW * 2 * PX}`);
    g2.setAttribute('height', `${gh}`);
    g2.setAttribute('fill', ev.ground.fill);
    g2.style.opacity = '0';
    g2.style.transition = 'opacity 500ms ease-in';
    insertByZ(g2, 0);
    requestAnimationFrame(() => {
      g2.style.opacity = '1';
    });
  }
}

// Build one SVG element for a stroke: a filled <polygon> (closed + has fill) or a
// stroke-only <polyline>. Returns {el, len, filled}.
function strokeEl(stroke, opColor) {
  const pts = stroke.points.map(([x, y]) => toPx(x, y));
  const filled = stroke.closed && stroke.fill && style === 'cartoon';
  const line = stroke.color || opColor;
  // Close the loop for ANY closed stroke (filled or not) so the outline's last
  // edge connects back — a closed-but-unfilled shape must still be a closed outline.
  if (stroke.closed && pts.length) {
    pts.push(pts[0]);
  }
  const el = document.createElementNS(SVG_NS, filled ? 'polygon' : 'polyline');
  el.setAttribute('points', pts.map(([px, py]) => `${px},${py}`).join(' '));
  el.setAttribute('stroke', line);
  el.setAttribute('stroke-width', filled ? '2.6' : '2.4');
  el.setAttribute('stroke-linecap', 'round');
  el.setAttribute('stroke-linejoin', 'round');
  if (filled) {
    el.setAttribute('fill', stroke.fill);
    el.style.fillOpacity = '0'; // flood the color in as the outline inks
  } else {
    el.setAttribute('fill', 'none');
  }
  return { el, filled };
}

async function drawOp(op) {
  // Re-drawing an existing id REPLACES it (e.g. a character re-posing to point).
  const prev = board.querySelector(
    `[data-opid="${window.CSS && CSS.escape ? CSS.escape(op.id) : op.id}"]`,
  );
  if (prev) {
    prev.remove();
  }
  const group = document.createElementNS(SVG_NS, 'g');
  insertByZ(group, op.z == null ? 1 : op.z); // presenter (z=3) paints above things/connectors
  group.dataset.opid = op.id; // so Action verbs can find this actor later
  // Placeholders are now designed concept cards (palette-tinted), not dimmed boxes;
  // honesty stays in the provenance panel (the source breakdown still counts them).
  const opColor = op.color;
  const entrance = style === 'cartoon' ? op.entrance || 'draw' : 'draw';
  let maxMs = 250;

  const reveals = [];
  for (const stroke of op.strokes) {
    const { el, filled } = strokeEl(stroke, opColor);
    group.appendChild(el);
    reveals.push({ el, filled });
  }

  if (entrance === 'draw') {
    for (const { el, filled } of reveals) {
      const len = el.getTotalLength();
      const ms = Math.max(180, (len / (DRAW_SPEED * pacing.draw_speed)) * 1000);
      maxMs = Math.max(maxMs, ms);
      el.style.strokeDasharray = `${len}`;
      el.style.strokeDashoffset = `${len}`;
      el.getBoundingClientRect(); // force layout
      el.style.transition = `stroke-dashoffset ${ms}ms ease-in-out${filled ? `, fill-opacity ${ms}ms ease-in ${ms * 0.35}ms` : ''}`;
      el.style.strokeDashoffset = '0';
      if (filled) {
        el.style.fillOpacity = '1';
      }
    }
  } else {
    // pop / rise / fade: appear as a unit (no pen reveal) — good for characters/props.
    maxMs = 520;
    for (const { el, filled } of reveals) {
      if (filled) {
        el.style.fillOpacity = '1';
      }
    }
    const [cx, cy] = toPx(op.label_pos ? op.label_pos[0] : 0, op.label_pos ? op.label_pos[1] : 0);
    group.style.transformOrigin = `${cx}px ${cy}px`;
    group.style.transition = 'transform 520ms cubic-bezier(.34,1.56,.64,1), opacity 360ms ease-out';
    group.style.opacity = '0';
    if (entrance === 'pop') {
      group.style.transform = 'scale(0.5)';
    } else if (entrance === 'rise') {
      group.style.transform = 'translateY(26px)';
    }
    group.getBoundingClientRect();
    requestAnimationFrame(() => {
      group.style.opacity = '1';
      group.style.transform = 'none';
    });
  }

  if (op.label && op.label_pos) {
    const [lx, ly] = toPx(op.label_pos[0], op.label_pos[1]);
    const text = document.createElementNS(SVG_NS, 'text');
    text.setAttribute('x', `${lx}`);
    text.setAttribute('y', `${ly + 5}`);
    text.setAttribute('fill', opColor);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '16');
    text.setAttribute('font-weight', style === 'cartoon' ? '700' : '400');
    text.setAttribute('font-family', 'sans-serif');
    text.style.opacity = '0';
    text.style.transition = 'opacity 300ms ease-in';
    text.textContent = op.label;
    group.appendChild(text);
    requestAnimationFrame(() => {
      text.style.opacity = '1';
    });
  }

  // Ambient idle motion (cartoon): a gentle, infinite life-in-the-frame loop.
  if (style === 'cartoon' && op.ambient) {
    group.style.animation = `amb-${op.ambient} ${op.ambient === 'float' ? 4 : 2.6}s ease-in-out infinite`;
  }

  await sleep(maxMs);
}

// Smooth viewBox pan/zoom. Non-blocking — a newer move supersedes via camSeq.
let camSeq = 0;
function animateCamera(cam, ms) {
  camSeq++;
  const my = camSeq;
  const target = [
    (cam.x - cam.w / 2 + halfW) * PX,
    (halfH - (cam.y + cam.h / 2)) * PX,
    cam.w * PX,
    cam.h * PX,
  ];
  const cur = (board.getAttribute('viewBox') || target.join(' ')).split(/\s+/).map(Number);
  if (!ms || ms <= 0) {
    board.setAttribute('viewBox', target.join(' '));
    return;
  }
  const start = performance.now();
  function frame(now) {
    if (my !== camSeq) {
      return;
    }
    const t = Math.min(1, (now - start) / ms);
    const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
    board.setAttribute('viewBox', cur.map((c, i) => c + (target[i] - c) * e).join(' '));
    if (t < 1) {
      requestAnimationFrame(frame);
    }
  }
  requestAnimationFrame(frame);
}

// Semantic Action verbs -> a transform animation on the actor's group (the motion language).
const ACTION_ANIM = {
  pulse: ['act-pulse', false],
  emphasize: ['act-pulse', false],
  point: ['act-point', false],
  look: ['act-point', false],
  wobble: ['act-wobble', false],
  flow: ['act-wobble', false],
  fall: ['act-fall', false],
  rise: ['act-rise', true],
  exit: ['act-exit', true],
  grow: ['act-grow', true],
  shrink: ['act-shrink', true],
};
function applyAction(ev) {
  const sel = window.CSS && CSS.escape ? CSS.escape(ev.id) : ev.id;
  const g = board.querySelector(`[data-opid="${sel}"]`);
  const spec = ACTION_ANIM[ev.verb];
  if (!g || !spec) {
    return;
  }
  const [name, persist] = spec;
  const ambient = g.style.animation;
  g.style.transformBox = 'fill-box';
  g.style.transformOrigin = 'center';
  g.style.animation = `${name} ${ev.ms || 800}ms ease-in-out ${persist ? 'forwards' : ''}`;
  if (!persist) {
    setTimeout(
      () => {
        g.style.animation = ambient;
      },
      (ev.ms || 800) + 30,
    );
  }
}

async function play(events) {
  for (const ev of events) {
    if (ev.type === 'start') {
      halfW = ev.board.w / 2;
      halfH = ev.board.h / 2;
      pacing = ev.pacing || pacing;
      style = ev.style || style;
      board.classList.toggle('cartoon', style === 'cartoon');
      showProvenance(ev.story);
      board.setAttribute('viewBox', `0 0 ${ev.board.w * PX} ${ev.board.h * PX}`);
      camSeq++;
      clearBoard();
    } else if (ev.type === 'background') {
      drawBackground(ev);
    } else if (ev.type === 'camera') {
      animateCamera(ev, ev.ms);
    } else if (ev.type === 'say') {
      caption.textContent = ev.text;
      await speak(ev.text);
    } else if (ev.type === 'action') {
      applyAction(ev);
    } else if (ev.type === 'hold') {
      await sleep(ev.ms || 0);
    } else if (ev.type === 'draw' || ev.type === 'connector') {
      await drawOp(ev.op);
    } else if (ev.type === 'clear') {
      await sleep(800);
      camSeq++;
      clearBoard();
    } else if (ev.type === 'done') {
      caption.textContent += '  ✓';
      showSummary(ev.summary);
    }
  }
}

function showProvenance(s) {
  if (!s) {
    return;
  }
  if (s.fallback) {
    provenance.innerHTML = `⚠ <b>${s.requested}</b> failed — fell back to template. <i>${s.reason || ''}</i>`;
  } else if (s.used === 'template') {
    provenance.innerHTML =
      '⚠ Offline <b>template</b> story. Start Ollama (local, free) — it auto-uses your installed model for real lessons.';
  } else {
    provenance.innerHTML = `✓ Story by <b>${s.used}</b>`;
  }
}

function showSummary(s) {
  if (!s) {
    return;
  }
  const ph = s.placeholders
    ? ` · <b style="color:#e3a008">${s.placeholders} placeholder box${s.placeholders > 1 ? 'es' : ''}</b>`
    : '';
  const dr = s.dropped ? ` · ${s.dropped} dropped` : '';
  provenance.innerHTML += ` — ${s.real_drawings} real drawing${s.real_drawings === 1 ? '' : 's'}${ph}${dr}`;
}

async function loadStatus() {
  try {
    const s = await (await fetch('/api/engine/status')).json();
    const brain = s.story_model ? `${s.story_provider} · ${s.story_model}` : s.story_provider;
    const tags = [
      `<span class="tag ${s.story_provider === 'template' ? 'warn' : 'ok'}">brain: ${brain}</span>`,
      `<span class="tag ${s.ollama_reachable ? 'ok' : 'warn'}">ollama: ${s.ollama_reachable ? 'up' : 'down'}</span>`,
      `<span class="tag">drawing: ${s.svg_provider}</span>`,
      `<span class="tag">quickdraw: ${s.quickdraw_cached}</span>`,
    ];
    for (const w of s.warnings) {
      tags.push(`<span class="tag warn">⚠ ${w}</span>`);
    }
    statusBar.innerHTML = tags.join('');
  } catch (_e) {
    statusBar.innerHTML = '<span class="tag warn">status unavailable</span>';
  }
}

async function teach() {
  const topic = topicInput.value.trim() || 'the water cycle';
  goButton.disabled = true;
  caption.textContent = 'Planning…';
  try {
    const res = await fetch(
      `/api/engine/lesson?topic=${encodeURIComponent(topic)}&mode=${encodeURIComponent(mode)}&audience=${encodeURIComponent(audience)}&style=${encodeURIComponent(style)}`,
    );
    const data = await res.json();
    await play(data.events);
  } catch (err) {
    caption.textContent = `Error: ${err}`;
  } finally {
    goButton.disabled = false;
  }
}

function wireChips(attr, set) {
  for (const chip of document.querySelectorAll(`[data-${attr}]`)) {
    chip.addEventListener('click', () => {
      for (const c of document.querySelectorAll(`[data-${attr}]`)) {
        c.classList.toggle('active', c === chip);
      }
      set(chip.dataset[attr]);
      teach();
    });
  }
}

wireChips('mode', (v) => {
  mode = v;
});
wireChips('aud', (v) => {
  audience = v;
});
wireChips('style', (v) => {
  style = v;
});

goButton.addEventListener('click', teach);
topicInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    teach();
  }
});

loadStatus();
