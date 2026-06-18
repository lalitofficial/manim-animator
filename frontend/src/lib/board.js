// The board animation engine for the Studio. Plays an engine event stream onto an
// <svg>: whiteboard = mono stroke-on reveal; cartoon = a colored scene backdrop +
// filled shapes that ink their outline then flood their fill, z-ordered, with
// entrance + ambient motion and a camera that pans/zooms to follow the lesson.
// Style is carried by the `start` event; cancellation is clean (abort signal).

const SVG_NS = 'http://www.w3.org/2000/svg';
const PX = 64; // px per board unit
const DRAW_SPEED = 520; // px/sec pen reveal
const SPEECH_CPS = 14;

class Aborted extends Error {}

function sleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Aborted());
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new Aborted());
    });
  });
}

export function clearBoard(svg) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const defs = document.createElementNS(SVG_NS, 'defs');
  svg.appendChild(defs);
  return defs;
}

function speak(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));
}

function makeToPx(halfW, halfH) {
  return (x, y) => [(x + halfW) * PX, (halfH - y) * PX];
}

// SVG paints in document order; honor op.z by inserting before the first element
// with a higher z. Background 0 < things 1 < connectors 2 < presenter 3.
function insertByZ(svg, defs, el, z) {
  el.dataset.z = String(z);
  let ref = null;
  for (const child of svg.children) {
    if (child === defs) continue;
    const cz = child.dataset?.z !== undefined ? Number(child.dataset.z) : 1;
    if (cz > z) {
      ref = child;
      break;
    }
  }
  svg.insertBefore(el, ref);
}

function drawBackground(svg, defs, ev, halfW, halfH) {
  const rect = document.createElementNS(SVG_NS, 'rect');
  rect.setAttribute('x', '0');
  rect.setAttribute('y', '0');
  rect.setAttribute('width', `${halfW * 2 * PX}`);
  rect.setAttribute('height', `${halfH * 2 * PX}`);
  if (ev.gradient) {
    const id = `bg${defs.childElementCount}`;
    const grad = document.createElementNS(SVG_NS, 'linearGradient');
    grad.setAttribute('id', id);
    grad.setAttribute('x1', '0');
    grad.setAttribute('y1', '0');
    grad.setAttribute('x2', '0');
    grad.setAttribute('y2', '1');
    for (const [off, col] of [['0%', ev.gradient.top], ['100%', ev.gradient.bottom]]) {
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
  insertByZ(svg, defs, rect, 0);
  if (ev.ground) {
    // The horizon band — props stand ON it (the scene has a ground, not floating space).
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
    insertByZ(svg, defs, g2, 0); // same layer, after the sky -> sits on top of it
    requestAnimationFrame(() => {
      g2.style.opacity = '1';
    });
  }
  requestAnimationFrame(() => {
    rect.style.opacity = '1';
  });
}

function strokeEl(stroke, opColor, cartoon) {
  const pts = stroke.points.map(stroke._toPx);
  const filled = stroke.closed && stroke.fill && cartoon;
  const line = stroke.color || opColor;
  if (stroke.closed && pts.length) pts.push(pts[0]); // close any closed outline
  const el = document.createElementNS(SVG_NS, filled ? 'polygon' : 'polyline');
  el.setAttribute('points', pts.map(([px, py]) => `${px},${py}`).join(' '));
  el.setAttribute('stroke', line);
  el.setAttribute('stroke-width', filled ? '2.6' : '2.4');
  el.setAttribute('stroke-linecap', 'round');
  el.setAttribute('stroke-linejoin', 'round');
  if (filled) {
    el.setAttribute('fill', stroke.fill);
    el.style.fillOpacity = '0';
  } else {
    el.setAttribute('fill', 'none');
  }
  return { el, filled };
}

async function drawOp(svg, defs, op, toPx, pacing, cartoon, signal) {
  // Re-drawing an existing id REPLACES it (e.g. a character re-posing to point).
  const prev = svg.querySelector(`[data-opid="${window.CSS && CSS.escape ? CSS.escape(op.id) : op.id}"]`);
  if (prev) prev.remove();
  const g = document.createElementNS(SVG_NS, 'g');
  insertByZ(svg, defs, g, op.z == null ? 1 : op.z);
  g.dataset.opid = op.id; // so Action verbs can find this actor later
  const opColor = op.color; // placeholders are now designed concept cards, not dimmed boxes
  const entrance = cartoon ? op.entrance || 'draw' : 'draw';
  let maxMs = 220;

  const els = [];
  for (const stroke of op.strokes) {
    stroke._toPx = ([x, y]) => toPx(x, y);
    const { el, filled } = strokeEl(stroke, opColor, cartoon);
    g.appendChild(el);
    els.push({ el, filled });
  }

  if (entrance === 'draw') {
    for (const { el, filled } of els) {
      const len = el.getTotalLength();
      const ms = Math.max(160, (len / (DRAW_SPEED * pacing.draw_speed)) * 1000);
      maxMs = Math.max(maxMs, ms);
      el.style.strokeDasharray = `${len}`;
      el.style.strokeDashoffset = `${len}`;
      el.getBoundingClientRect();
      el.style.transition = `stroke-dashoffset ${ms}ms ease-in-out${filled ? `, fill-opacity ${ms}ms ease-in ${ms * 0.35}ms` : ''}`;
      el.style.strokeDashoffset = '0';
      if (filled) el.style.fillOpacity = '1';
    }
  } else {
    maxMs = 520;
    for (const { el, filled } of els) if (filled) el.style.fillOpacity = '1';
    const [cx, cy] = toPx(op.label_pos ? op.label_pos[0] : 0, op.label_pos ? op.label_pos[1] : 0);
    g.style.transformOrigin = `${cx}px ${cy}px`;
    g.style.transition = 'transform 520ms cubic-bezier(.34,1.56,.64,1), opacity 360ms ease-out';
    g.style.opacity = '0';
    if (entrance === 'pop') g.style.transform = 'scale(0.5)';
    else if (entrance === 'rise') g.style.transform = 'translateY(26px)';
    g.getBoundingClientRect();
    requestAnimationFrame(() => {
      g.style.opacity = '1';
      g.style.transform = 'none';
    });
  }

  if (op.label && op.label_pos) {
    const [lx, ly] = toPx(op.label_pos[0], op.label_pos[1]);
    const text = document.createElementNS(SVG_NS, 'text');
    text.setAttribute('x', `${lx}`);
    text.setAttribute('y', `${ly + 5}`);
    text.setAttribute('fill', opColor);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('font-size', '15');
    text.setAttribute('font-weight', cartoon ? '700' : '400');
    text.setAttribute('font-family', 'ui-sans-serif, system-ui, sans-serif');
    text.style.opacity = '0';
    text.style.transition = 'opacity 280ms ease-in';
    text.textContent = op.label;
    g.appendChild(text);
    requestAnimationFrame(() => {
      text.style.opacity = '1';
    });
  }

  if (cartoon && op.ambient) {
    const ambDur = { float: 4, rise: 3.4, fall: 3.4, flow: 2.4, glow: 2, bob: 2.6, sway: 2.8 };
    g.style.animation = `amb-${op.ambient} ${ambDur[op.ambient] || 2.6}s ease-in-out infinite`;
  }
  // Character motion: flip through server-rendered pose frames (a mined gesture clip).
  // The limbs change shape frame-to-frame; the CSS ambient (bob) rides on top.
  if (cartoon && op.frames && op.frames.length > 1) {
    playClip(els, op, toPx, signal, maxMs);
  }
  await sleep(maxMs, signal);
}

// Flip a group's strokes through pre-rendered pose frames — real limb motion (the rig
// ACTS). Frame i, stroke j updates element j's points. A one-shot gesture then chains into
// the looping idle-life (op.idle) so the character keeps breathing instead of freezing.
function playClip(els, op, toPx, signal, startDelay) {
  const toFrames = (frames) =>
    frames.map((fr) =>
      fr.map((s) => {
        const pts = s.points.map(([x, y]) => toPx(x, y).join(','));
        if (s.closed && pts.length) pts.push(pts[0]);
        return pts.join(' ');
      }),
    );
  const main = toFrames(op.frames);
  const idle = op.idle ? toFrames(op.idle) : null;
  const fps = op.fps || 14;
  let seq = main;
  let looping = !!op.loop;
  let fi = 0;
  const tick = () => {
    if (signal && signal.aborted) return;
    if (!els[0] || !els[0].el.isConnected) return; // group removed (re-pose / new lesson) — stop
    const fr = seq[fi];
    for (let j = 0; j < els.length; j++)
      if (fr[j] !== undefined) els[j].el.setAttribute('points', fr[j]);
    fi += 1;
    if (fi >= seq.length) {
      if (looping) fi = 0;
      else if (idle && seq === main) {
        seq = idle;
        fi = 0;
        looping = true;
      } else return; // hold the final pose
    }
    setTimeout(() => requestAnimationFrame(tick), 1000 / fps);
  };
  setTimeout(() => requestAnimationFrame(tick), startDelay); // start after the entrance settles
}

// Smooth viewBox pan/zoom (camera). Non-blocking: a newer camera move supersedes
// an in-flight one via the seq token. `cam` is {x,y,w,h} board units (center+size).
function animateCamera(svg, cam, ms, halfW, halfH, isCurrent) {
  const target = [
    (cam.x - cam.w / 2 + halfW) * PX,
    (halfH - (cam.y + cam.h / 2)) * PX,
    cam.w * PX,
    cam.h * PX,
  ];
  const cur = (svg.getAttribute('viewBox') || target.join(' ')).split(/\s+/).map(Number);
  if (!ms || ms <= 0) {
    svg.setAttribute('viewBox', target.join(' '));
    return;
  }
  const start = performance.now();
  function frame(now) {
    if (!isCurrent()) return;
    const t = Math.min(1, (now - start) / ms);
    const e = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2; // easeInOutQuad
    svg.setAttribute('viewBox', cur.map((c, i) => c + (target[i] - c) * e).join(' '));
    if (t < 1) requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// Semantic Action verbs -> a transform animation on the actor's group. One impl per
// verb, applicable to ANY actor (the motion language). `persist` keeps the end state.
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
function applyAction(svg, ev) {
  const sel = window.CSS && CSS.escape ? CSS.escape(ev.id) : ev.id;
  const g = svg.querySelector(`[data-opid="${sel}"]`);
  const spec = ACTION_ANIM[ev.verb];
  if (!g || !spec) return;
  const [name, persist] = spec;
  const ambient = g.style.animation; // bob/float to restore after a one-shot emphasis
  g.style.transformBox = 'fill-box';
  g.style.transformOrigin = 'center';
  g.style.animation = `${name} ${ev.ms || 800}ms ease-in-out ${persist ? 'forwards' : ''}`;
  if (!persist) {
    setTimeout(() => {
      g.style.animation = ambient;
    }, (ev.ms || 800) + 30);
  }
}

// Play the events. `onEvent(ev)` lets the UI update live. Throws Aborted on signal.
export async function play(svg, events, onEvent, signal) {
  let pacing = { draw_speed: 1, say_dwell: 1 };
  let toPx = makeToPx(7, 4);
  let halfW = 7;
  let halfH = 4;
  let cartoon = false;
  let defs = clearBoard(svg);
  let camSeq = 0;

  for (const ev of events) {
    if (signal?.aborted) throw new Aborted();
    onEvent?.(ev);
    if (ev.type === 'start') {
      pacing = ev.pacing || pacing;
      halfW = ev.board.w / 2;
      halfH = ev.board.h / 2;
      toPx = makeToPx(halfW, halfH);
      cartoon = ev.style === 'cartoon';
      svg.style.background = cartoon ? '#eaf3fb' : '';
      svg.setAttribute('viewBox', `0 0 ${ev.board.w * PX} ${ev.board.h * PX}`);
      defs = clearBoard(svg);
      camSeq++;
    } else if (ev.type === 'background') {
      drawBackground(svg, defs, ev, halfW, halfH);
    } else if (ev.type === 'camera') {
      camSeq++;
      const my = camSeq;
      animateCamera(svg, ev, ev.ms, halfW, halfH, () => my === camSeq && !signal?.aborted);
    } else if (ev.type === 'say') {
      speak(ev.text);
      await sleep(Math.min(1500, Math.max(600, (ev.text.length / SPEECH_CPS) * 1000)) * pacing.say_dwell, signal);
    } else if (ev.type === 'action') {
      applyAction(svg, ev);
    } else if (ev.type === 'hold') {
      await sleep(ev.ms || 0, signal); // a beat/pause between shots (pacing)
    } else if (ev.type === 'draw' || ev.type === 'connector') {
      await drawOp(svg, defs, ev.op, toPx, pacing, cartoon, signal);
    } else if (ev.type === 'clear') {
      await sleep(750, signal);
      defs = clearBoard(svg);
      camSeq++;
    }
  }
}

// The master-clock SCHEDULER (Phase 2b): play a choreographed Timeline (timeline.to_dict).
// The SPINE (entries with at==="" — say + sequential draws) plays exactly like play() above, so a
// degenerate (un-choreographed) timeline is identical to today. A choreographed entry (at==="m:x")
// fires DURING its owning say at the spoken word's proportional moment — draw-while-talking.
export async function playTimeline(svg, timeline, onEvent, signal) {
  let pacing = { draw_speed: 1, say_dwell: 1 };
  let toPx = makeToPx(7, 4);
  let halfW = 7;
  let halfH = 4;
  let cartoon = false;
  let defs = clearBoard(svg);
  let camSeq = 0;

  const meta = timeline.meta || {};
  onEvent?.({ type: 'start', ...meta });
  if (meta.board) {
    pacing = meta.pacing || pacing;
    halfW = meta.board.w / 2;
    halfH = meta.board.h / 2;
    toPx = makeToPx(halfW, halfH);
    cartoon = meta.style === 'cartoon';
    svg.style.background = cartoon ? '#eaf3fb' : '';
    svg.setAttribute('viewBox', `0 0 ${meta.board.w * PX} ${meta.board.h * PX}`);
    defs = clearBoard(svg);
    camSeq++;
  }

  const sayMs = (text) =>
    Math.min(1500, Math.max(600, (text.length / SPEECH_CPS) * 1000)) * pacing.say_dwell;

  // Fire-and-continue for camera/action; returns a Promise for the blocking draw/connector/clear.
  const dispatch = (ev) => {
    onEvent?.(ev);
    if (ev.type === 'background') {
      drawBackground(svg, defs, ev, halfW, halfH);
      return null;
    }
    if (ev.type === 'camera') {
      camSeq++;
      const my = camSeq;
      animateCamera(svg, ev, ev.ms, halfW, halfH, () => my === camSeq && !signal?.aborted);
      return null;
    }
    if (ev.type === 'action') {
      applyAction(svg, ev);
      return null;
    }
    if (ev.type === 'draw' || ev.type === 'connector') {
      return drawOp(svg, defs, ev.op, toPx, pacing, cartoon, signal);
    }
    if (ev.type === 'clear') {
      return (async () => {
        await sleep(750, signal);
        defs = clearBoard(svg);
        camSeq++;
      })();
    }
    return null;
  };

  const markByName = {};
  for (const m of timeline.markers || []) {
    markByName[m.name] = m;
  }
  const anchoredBySay = {};
  for (const e of timeline.entries || []) {
    const m = e.at ? markByName[e.at] : null;
    if (m && m.entry) {
      if (!anchoredBySay[m.entry]) {
        anchoredBySay[m.entry] = [];
      }
      anchoredBySay[m.entry].push({ e, m });
    }
  }

  for (const e of timeline.entries || []) {
    if (signal?.aborted) throw new Aborted();
    if (e.at) {
      continue; // anchored entries are fired by their owning say
    }
    const ev = { type: e.kind, ...e.payload };
    if (e.kind === 'say') {
      onEvent?.(ev);
      speak(ev.text || '');
      const durMs = sayMs(ev.text || '');
      const tlen = Math.max(1, (ev.text || '').length);
      for (const { e: ae, m } of anchoredBySay[e.id] || []) {
        const at = Math.round(Math.min(0.92, (m.char_start || 0) / tlen) * durMs);
        setTimeout(() => {
          if (!signal?.aborted) dispatch({ type: ae.kind, ...ae.payload });
        }, at);
      }
      await sleep(durMs, signal);
    } else {
      const p = dispatch(ev);
      if (p) await p;
    }
  }
  onEvent?.({ type: 'done', summary: meta.done });
}

export { Aborted };
