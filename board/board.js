/* Live board engine — the realtime twin of backend/renderer.py.
 *
 * Consumes the same Scene IR (objects + steps), but draws on a <canvas>
 * with progressive "hand-drawn" reveal instead of rendering an mp4.
 * Segments stream in over a websocket and queue up; the board plays one
 * while the planner is still thinking about the next.
 *
 * Mirrored semantics (keep in sync with renderer.py):
 *   - Coordinates are Manim's: origin center, +y up, frame 14.2 x 8 units.
 *   - line/arrow/polygon carry their own absolute coords; everything else
 *     is positioned by `position` (its center).
 *   - Objects appear only when a step animates them in; a step that
 *     references a missing id is skipped, never fatal.
 *   - Groups bundle already-placed members and animate them as a unit.
 */

const FRAME_W = 14.2,
  FRAME_H = 8.0;

/* ----------------------------------------------------------------------- *
 * IR object -> {prims, pos, scale, opacity}
 * Prims are local to the object's center so move/scale are uniform.
 * ----------------------------------------------------------------------- */
function compileObject(o) {
  let prims,
    selfPositioned = false;
  const color = o.color || '#FFFFFF';
  const type = o.type;

  if (type === 'asset') {
    prims = BoardAssets.build(o.asset, o.params);
  } else if (type === 'text' || type === 'mathtex') {
    prims = [
      { k: 'text', x: 0, y: 0, text: o.text || o.tex || '', size: o.font_size || 40, color },
    ];
  } else if (type === 'circle') {
    prims = [{ k: 'circle', x: 0, y: 0, r: o.radius ?? 1, stroke: color, lw: 4 }];
  } else if (type === 'square') {
    prims = [{ k: 'rect', x: 0, y: 0, w: o.width ?? 2, h: o.width ?? 2, stroke: color, lw: 4 }];
  } else if (type === 'rectangle') {
    prims = [{ k: 'rect', x: 0, y: 0, w: o.width ?? 2, h: o.height ?? 1, stroke: color, lw: 4 }];
  } else if (type === 'triangle' || type === 'polygon') {
    let pts = (o.points || []).map((p) => [p[0], p[1]]);
    if (pts.length < 3) {
      // manim's default Triangle: circumradius 1, apex up
      pts = [0, 1, 2].map((i) => {
        const a = Math.PI / 2 + (i * 2 * Math.PI) / 3;
        return [Math.cos(a), Math.sin(a)];
      });
    } else {
      selfPositioned = true;
    }
    prims = [{ k: 'poly', pts, stroke: color, lw: 4, closed: true }];
  } else if (type === 'line' || type === 'arrow') {
    const s = o.start || [0, 0],
      e = o.end || [1, 0];
    prims = [
      {
        k: 'line',
        x1: s[0],
        y1: s[1],
        x2: e[0],
        y2: e[1],
        stroke: color,
        lw: 4,
        arrow: type === 'arrow',
      },
    ];
    selfPositioned = true;
  } else if (type === 'dot') {
    prims = [{ k: 'dot', x: 0, y: 0, r: 0.08, fill: color }];
  } else if (type === 'group') {
    return { id: o.id, group: true, members: o.members || [], scale: o.scale ?? 1 };
  } else {
    prims = BoardAssets.build(type, o.params); // unknown type -> labeled box
  }

  let pos = [o.position?.[0] ?? 0, o.position?.[1] ?? 0];
  if (selfPositioned) {
    // Recenter absolute coords around their bbox center so pos == center
    // and move/scale behave exactly like manim's move_to/scale.
    const c = bboxOfPrims(prims).center;
    prims = translatePrims(prims, -c[0], -c[1]);
    pos = c;
  }
  return {
    id: o.id,
    prims,
    pos,
    scale: o.scale ?? 1,
    opacity: 0,
    reveal: 1,
    rotation: 0,
    phase: 0,
    pose: null,
    color: o.color || '#E6EDF3',
    seed: hashSeed(o.id),
    dynamic: prims.some((p) => p.k === 'rig' || p.k === 'globe' || p.k === 'strokes'),
  };
}

/* ------------------------- geometry helpers --------------------------- */
function primExtent(p) {
  switch (p.k) {
    case 'circle':
      return [p.x - p.r, p.y - p.r, p.x + p.r, p.y + p.r];
    case 'dot':
      return [p.x - p.r, p.y - p.r, p.x + p.r, p.y + p.r];
    case 'rect':
      return [p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2];
    case 'line':
      return [
        Math.min(p.x1, p.x2),
        Math.min(p.y1, p.y2),
        Math.max(p.x1, p.x2),
        Math.max(p.y1, p.y2),
      ];
    case 'poly': {
      const xs = p.pts.map((q) => q[0]),
        ys = p.pts.map((q) => q[1]);
      return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    }
    case 'text': {
      const h = (p.size || 40) / 48,
        w = h * 0.52 * (p.text || '').length;
      return [p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2];
    }
    case 'rig':
      return [-0.75, -1.3, 0.75, 1.25];
    case 'globe':
      return [-(p.r || 1.1), -(p.r || 1.1), p.r || 1.1, p.r || 1.1];
    case 'strokes': {
      let x0 = 1e9,
        y0 = 1e9,
        x1 = -1e9,
        y1 = -1e9;
      for (const s of p.strokes || [])
        for (const q of s) {
          x0 = Math.min(x0, q[0]);
          y0 = Math.min(y0, q[1]);
          x1 = Math.max(x1, q[0]);
          y1 = Math.max(y1, q[1]);
        }
      return x0 > x1 ? [0, 0, 0, 0] : [x0, y0, x1, y1];
    }
  }
  return [p.x || 0, p.y || 0, p.x || 0, p.y || 0];
}

function bboxOfPrims(prims) {
  let x0 = 1e9,
    y0 = 1e9,
    x1 = -1e9,
    y1 = -1e9;
  for (const p of prims) {
    const e = primExtent(p);
    x0 = Math.min(x0, e[0]);
    y0 = Math.min(y0, e[1]);
    x1 = Math.max(x1, e[2]);
    y1 = Math.max(y1, e[3]);
  }
  if (x0 > x1) {
    x0 = y0 = x1 = y1 = 0;
  }
  return { x0, y0, x1, y1, center: [(x0 + x1) / 2, (y0 + y1) / 2] };
}

function translatePrims(prims, dx, dy) {
  return prims.map((p) => {
    const q = { ...p };
    if (q.k === 'line') {
      q.x1 += dx;
      q.y1 += dy;
      q.x2 += dx;
      q.y2 += dy;
    } else if (q.k === 'poly') {
      q.pts = q.pts.map((pt) => [pt[0] + dx, pt[1] + dy]);
    } else {
      q.x += dx;
      q.y += dy;
    }
    return q;
  });
}

function primLength(p) {
  // stroke length, for proportional reveal pacing
  switch (p.k) {
    case 'line':
      return Math.hypot(p.x2 - p.x1, p.y2 - p.y1);
    case 'circle':
      return 2 * Math.PI * p.r;
    case 'rect':
      return 2 * (p.w + p.h);
    case 'poly': {
      let L = 0;
      for (let i = 0; i < p.pts.length; i++) {
        const a = p.pts[i],
          b = p.pts[(i + 1) % p.pts.length];
        if (i === p.pts.length - 1 && !p.closed) break;
        L += Math.hypot(b[0] - a[0], b[1] - a[1]);
      }
      return L;
    }
    case 'text':
      return Math.max(1, (p.text || '').length * 0.3);
    case 'dot':
      return 0.3;
  }
  return 1;
}

const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2);

/* ----------------------------------------------------------------------- *
 * Hand-drawn stroke machinery — what makes the board feel sketched.
 * Stable per-object noise (no shimmer): same seed -> same wobble forever.
 * ----------------------------------------------------------------------- */
function hashSeed(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

function noise1(seed, i) {
  const x = Math.sin(seed * 127.1 + i * 311.7) * 43758.5453;
  return x - Math.floor(x) - 0.5;
}

/* Resample a polyline to ~step spacing and jitter perpendicular — the
 * chalk-line wobble. amp in board units. */
function sketchify(pts, seed, amp = 0.05, step = 0.35) {
  if (pts.length < 2) return pts;
  const out = [pts[0].slice()];
  let k = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i],
      [bx, by] = pts[i + 1];
    const L = Math.hypot(bx - ax, by - ay);
    const n = Math.max(1, Math.round(L / step));
    const px = -(by - ay) / (L || 1),
      py = (bx - ax) / (L || 1); // unit normal
    for (let j = 1; j <= n; j++) {
      const t = j / n;
      const w = j === n && i === pts.length - 2 ? 0 : noise1(seed, ++k) * 2 * amp;
      out.push([ax + (bx - ax) * t + px * w, ay + (by - ay) * t + py * w]);
    }
  }
  return out;
}

function circlePts(cx, cy, r, n = 36) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n; // start at top, like a hand
    pts.push([cx + Math.cos(a) * r, cy + Math.sin(a) * r]);
  }
  return pts;
}

/* ----------------------------------------------------------------------- *
 * Skeletal rig — a stick figure that can perform.
 * Pose = [lArm, lElbow, rArm, rElbow, lHip, lKnee, rHip, rKnee, lean]
 * Angles in radians from straight-down, positive toward +x.
 * ----------------------------------------------------------------------- */
const POSES = {
  idle: [0.25, 0.1, -0.25, -0.1, 0.12, 0.0, -0.12, 0.0, 0.0],
  waveA: [0.3, 0.15, 2.7, 0.5, 0.12, 0.0, -0.12, 0.0, 0.0],
  waveB: [0.3, 0.15, 2.7, -0.5, 0.12, 0.0, -0.12, 0.0, 0.0],
  walkA: [-0.45, -0.2, 0.45, 0.35, 0.55, -0.45, -0.4, 0.3, 0.04],
  walkB: [0.45, 0.35, -0.45, -0.2, -0.4, 0.3, 0.55, -0.45, 0.04],
  danceA: [2.3, 0.6, -0.6, -0.4, 0.4, -0.3, -0.15, 0.0, 0.14],
  danceB: [0.6, 0.4, -2.3, -0.6, 0.15, 0.0, -0.4, 0.3, -0.14],
  bow: [0.5, 0.3, -0.5, -0.3, 0.1, 0.0, -0.1, 0.0, 0.65],
};

function lerpPose(a, b, t) {
  return a.map((v, i) => v + (b[i] - v) * t);
}

/* Pose -> drawable prims (local units, pelvis-centered, ~2.4 tall). */
function rigPrims(pose, color) {
  const p = pose || POSES.idle;
  const [la, le, ra, re, lh, lk, rh, rk, lean] = p;
  const dir = (x, y, len, th) => [x + Math.sin(th) * len, y - Math.cos(th) * len];
  const lw = 4;
  const chestX = Math.sin(lean) * 0.55;
  const pelvis = [0, -0.25],
    chest = [chestX, 0.5];
  const headC = [chestX * 1.3, 0.92];
  const sh = [chestX, 0.42];
  const lElb = dir(sh[0], sh[1], 0.42, la),
    lHand = dir(lElb[0], lElb[1], 0.38, la + le);
  const rElb = dir(sh[0], sh[1], 0.42, ra),
    rHand = dir(rElb[0], rElb[1], 0.38, ra + re);
  const lKnee = dir(pelvis[0], pelvis[1], 0.5, lh),
    lFoot = dir(lKnee[0], lKnee[1], 0.5, lh + lk);
  const rKnee = dir(pelvis[0], pelvis[1], 0.5, rh),
    rFoot = dir(rKnee[0], rKnee[1], 0.5, rh + rk);
  return [
    { k: 'circle', x: headC[0], y: headC[1], r: 0.28, stroke: color, lw },
    { k: 'poly', pts: [pelvis, chest], closed: false, stroke: color, lw },
    { k: 'poly', pts: [sh, lElb, lHand], closed: false, stroke: color, lw },
    { k: 'poly', pts: [sh, rElb, rHand], closed: false, stroke: color, lw },
    { k: 'poly', pts: [pelvis, lKnee, lFoot], closed: false, stroke: color, lw },
    { k: 'poly', pts: [pelvis, rKnee, rFoot], closed: false, stroke: color, lw },
  ];
}

/* Globe at rotation phase [0,1): outline + equator + drifting meridians. */
function globePrims(r, phase, color) {
  const prims = [{ k: 'circle', x: 0, y: 0, r, stroke: color, lw: 4 }];
  const eq = [];
  for (let i = 0; i <= 24; i++) {
    const a = Math.PI + (i * Math.PI) / 24; // front half of the equator
    eq.push([r * Math.cos(a), -r * 0.22 * Math.sin(a)]);
  }
  prims.push({ k: 'poly', pts: eq, closed: false, stroke: color, lw: 2.5 });
  for (let m = 0; m < 3; m++) {
    const lon = ((phase + m / 3) % 1) * Math.PI - Math.PI / 2; // visible face
    const rx = r * Math.sin(lon);
    if (Math.abs(rx) < 0.06 * r) continue; // edge-on: invisible
    const pts = [];
    for (let i = 0; i <= 20; i++) {
      const a = -Math.PI / 2 + (i * Math.PI) / 20;
      pts.push([rx * Math.cos(a), r * Math.sin(a) * 0.99]);
    }
    prims.push({ k: 'poly', pts, closed: false, stroke: color, lw: 2.5 });
  }
  return prims;
}

/* ----------------------------------------------------------------------- *
 * The player
 * ----------------------------------------------------------------------- */
class BoardPlayer {
  /**
   * Plays a stream of board *actions* (see backend/actions.py):
   *   {kind:"say"|"add"|"play"|"clear"} and {type:"segment_start"} markers.
   * Speech runs concurrently with drawing — the teacher talks while the
   * hand draws — but consecutive "say"s are chained so they never overlap.
   *
   * @param canvas  the <canvas> to draw on
   * @param opts    { speak(text)->Promise, onSay(text), onSegment(evt), onIdle() }
   */
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.opts = opts;
    this.objects = new Map(); // id -> compiled object (insertion = draw order)
    this.queue = [];
    this.playing = false;
    this.background = '#0E1116';
    this.pen = null; // [x,y] world coords of the drawing tip
    this._speech = Promise.resolve();
    this._raf = null;
    this._startLoop();
    new ResizeObserver(() => this._resize()).observe(canvas.parentElement || canvas);
    this._resize();
  }

  /* ---- public API ---- */
  enqueueAction(evt) {
    this.queue.push(evt);
    if (!this.playing) this._drain();
  }

  reset() {
    this.queue.length = 0;
    this.objects.clear();
    this.pen = null;
    this.playing = false;
    this._speech = Promise.resolve();
  }

  _fetchSketch(name, obj) {
    const key = String(name || '')
      .trim()
      .toLowerCase()
      .replace(/[\s_]+/g, '%20');
    fetch(`/api/sketch/${key}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d && d.strokes && d.strokes.length) {
          obj.prims = [{ k: 'strokes', strokes: d.strokes }];
          obj.dynamic = true;
        }
      })
      .catch(() => {}); // no sketch: the labeled fallback box stays
  }

  /* ---- action playback ---- */
  async _drain() {
    this.playing = true;
    while (true) {
      if (!this.queue.length) {
        await this._speech; // teacher finishes the sentence...
        if (!this.queue.length) break; // ...unless more arrived meanwhile
      }
      const a = this.queue.shift();
      try {
        if (a.type === 'segment_start') {
          this.opts.onSegment?.(a);
        } else if (a.kind === 'say') {
          // Chain speeches (no overlap) but DON'T await: drawing continues
          // underneath the voice, like a real teacher at a board.
          const text = a.text;
          this._speech = this._speech.then(() => {
            this.opts.onSay?.(text);
            return this.opts.speak ? this.opts.speak(text) : Promise.resolve();
          });
        } else if (a.kind === 'add') {
          if (!this.objects.has(a.object.id)) {
            const obj = compileObject(a.object);
            this.objects.set(a.object.id, obj);
            // Unknown asset: try the human-sketch corpus (QuickDraw) — if a
            // real hand drawing exists for this word, swap it in for the
            // labeled fallback box before the reveal step reaches it.
            if (a.object.type === 'asset' && !BoardAssets.has(a.object.asset)) {
              this._fetchSketch(a.object.asset, obj);
            }
          }
        } else if (a.kind === 'play') {
          // Elastic playback: stretch when the buffer is thin (generation
          // barely ahead), compress when fat — adaptive-bitrate streaming,
          // but the rate being adapted is animation time, not bits.
          await this._runStep(a.step, this._paceFactor());
        } else if (a.kind === 'clear') {
          await this._clearBoard();
        }
      } catch (e) {
        /* one bad action never stops the lesson */
      }
    }
    this.playing = false;
    this.opts.onIdle?.();
  }

  /* Pending playback time queued ahead (the backlog B_j of the model). */
  _backlog() {
    let s = 0;
    for (const a of this.queue) {
      if (a.kind === 'play') s += Number(a.step?.duration) || 1;
      else if (a.kind === 'say') s += (a.text || '').length / 15;
    }
    return s;
  }

  _paceFactor() {
    const b = this._backlog();
    if (b < 2) return 1.8; // starving: draw slowly, let the model catch up
    if (b < 5) return 1.25;
    if (b > 12) return 0.8; // fat buffer: tighten up, stay lively
    return 1.0;
  }

  /* Idle-cover: pulse the most recent visible object — a semantic no-op
   * gesture (the teacher "pointing") for moments when the planner is slow. */
  async pulseRecent() {
    if (this.playing || this._pulsing) return;
    const vis = [...this.objects.values()].filter((o) => !o.group && o.opacity > 0.5);
    const o = vis[vis.length - 1];
    if (!o) return;
    this._pulsing = true;
    const s0 = o.scale,
      c = [...o.pos];
    await this._animate(0.5, (t) => {
      o.scale = s0 * (1 + 0.12 * Math.sin(Math.PI * t));
    });
    o.scale = s0;
    o.pos = c;
    this._pulsing = false;
  }

  /* Resolve a step target to the list of leaf objects it animates. */
  _leaves(id) {
    const o = this.objects.get(id);
    if (!o) return [];
    if (!o.group) return [o];
    return o.members.flatMap((m) => this._leaves(m));
  }

  async _runStep(step, pace = 1.0) {
    const d = Math.max((Number(step.duration) || 1) * pace, 0.1);
    if (step.animation === 'wait') return this._wait(d);
    const leaves = this._leaves(step.target);
    if (!leaves.length) return;

    switch (step.animation) {
      case 'write':
      case 'create': {
        // Reveal leaves sequentially, sharing `d` by stroke length.
        const lens = leaves.map((o) => this._expand(o).reduce((s, p) => s + primLength(p), 0) || 1);
        const total = lens.reduce((a, b) => a + b, 0);
        for (let i = 0; i < leaves.length; i++) {
          const o = leaves[i];
          o.opacity = 1;
          o.reveal = 0;
          await this._animate((d * lens[i]) / total, (t) => {
            o.reveal = t;
            this._penAt(o, t);
          });
          o.reveal = 1;
        }
        this.pen = null;
        return;
      }
      case 'fadein':
        return this._animate(d, (t) =>
          leaves.forEach((o) => {
            o.opacity = Math.max(o.opacity, t);
          }),
        );
      case 'fadeout':
        return this._animate(d, (t) =>
          leaves.forEach((o) => {
            o.opacity = Math.min(o.opacity, 1 - t);
          }),
        );
      case 'move': {
        if (!step.to) return;
        leaves.forEach((o) => {
          if (o.opacity === 0) {
            o.opacity = 1;
          }
        }); // manim implicit add
        const c = this._centerOf(leaves);
        const dx = step.to[0] - c[0],
          dy = step.to[1] - c[1];
        const starts = leaves.map((o) => [...o.pos]);
        return this._animate(d, (t) => {
          const e = easeInOut(t);
          leaves.forEach((o, i) => {
            o.pos = [starts[i][0] + dx * e, starts[i][1] + dy * e];
          });
        });
      }
      case 'scale': {
        const f = Number(step.factor) || 1.5;
        leaves.forEach((o) => {
          if (o.opacity === 0) {
            o.opacity = 1;
          }
        });
        const c = this._centerOf(leaves);
        const starts = leaves.map((o) => ({ pos: [...o.pos], scale: o.scale }));
        return this._animate(d, (t) => {
          const k = 1 + (f - 1) * easeInOut(t); // scale about the common center
          leaves.forEach((o, i) => {
            o.scale = starts[i].scale * k;
            o.pos = [c[0] + (starts[i].pos[0] - c[0]) * k, c[1] + (starts[i].pos[1] - c[1]) * k];
          });
        });
      }
      case 'transform': {
        const into = this._leaves(step.into);
        if (!into.length) return;
        return this._animate(d, (t) => {
          leaves.forEach((o) => {
            o.opacity = 1 - t;
          });
          into.forEach((o) => {
            o.opacity = t;
          });
        });
      }

      /* ---- behavior verbs: runtime performances, zero extra tokens ---- */
      case 'spin': {
        leaves.forEach((o) => {
          if (o.opacity === 0) o.opacity = 1;
        });
        const revs = Number(step.revs) || 1;
        const starts = leaves.map((o) => ({
          rot: o.rotation || 0,
          phase: o.phase || 0,
          globe: o.prims.some((p) => p.k === 'globe'),
        }));
        return this._animate(d, (t) => {
          const e = easeInOut(t);
          leaves.forEach((o, i) => {
            // A globe "rotates" by drifting its meridians, not by rolling.
            if (starts[i].globe) o.phase = (starts[i].phase + revs * e) % 1;
            else o.rotation = starts[i].rot + 2 * Math.PI * revs * e;
          });
        });
      }
      case 'orbit': {
        const around = this._leaves(step.around);
        if (!around.length) return;
        leaves.forEach((o) => {
          if (o.opacity === 0) o.opacity = 1;
        });
        const c = this._centerOf(around);
        const revs = Number(step.revs) || 1;
        const starts = leaves.map((o) => {
          const dx = o.pos[0] - c[0],
            dy = o.pos[1] - c[1];
          return { r: Math.hypot(dx, dy) || 1.5, a: Math.atan2(dy, dx) };
        });
        return this._animate(d, (t) => {
          const e = easeInOut(t);
          leaves.forEach((o, i) => {
            const a = starts[i].a + 2 * Math.PI * revs * e;
            o.pos = [c[0] + Math.cos(a) * starts[i].r, c[1] + Math.sin(a) * starts[i].r];
          });
        });
      }
      case 'bounce': {
        leaves.forEach((o) => {
          if (o.opacity === 0) o.opacity = 1;
        });
        const y0s = leaves.map((o) => o.pos[1]);
        const hops = Math.max(2, Math.round(d));
        return this._animate(d, (t) => {
          const off = Math.abs(Math.sin(Math.PI * hops * t)) * 0.4;
          leaves.forEach((o, i) => {
            o.pos = [o.pos[0], y0s[i] + off];
          });
        }).then(() =>
          leaves.forEach((o, i) => {
            o.pos = [o.pos[0], y0s[i]];
          }),
        );
      }
      case 'wave':
      case 'dance':
      case 'walk': {
        leaves.forEach((o) => {
          if (o.opacity === 0) o.opacity = 1;
        });
        const rigs = leaves.filter((o) => o.prims.some((p) => p.k === 'rig'));
        if (!rigs.length) {
          // not a figure: a friendly bounce stands in
          return this._runStep({ ...step, animation: 'bounce' }, 1.0);
        }
        const [A, B] =
          step.animation === 'wave'
            ? [POSES.waveA, POSES.waveB]
            : step.animation === 'dance'
              ? [POSES.danceA, POSES.danceB]
              : [POSES.walkA, POSES.walkB];
        const cycles = Math.max(2, Math.round(d * (step.animation === 'walk' ? 1.5 : 1.1)));
        const starts = rigs.map((o) => [...o.pos]);
        const fromPose = rigs.map((o) => o.pose || POSES.idle);
        const to = step.to;
        return this._animate(d, (t) => {
          const ph = (t * cycles) % 1;
          const mix = ph < 0.5 ? ph * 2 : 2 - ph * 2; // keyframe A <-> B
          const blend = Math.min(1, t * 6, (1 - t) * 6); // ease in/out of the act
          rigs.forEach((o, i) => {
            o.pose = lerpPose(fromPose[i], lerpPose(A, B, mix), blend);
            if (to && step.animation === 'walk') {
              o.pos = [
                starts[i][0] + (to[0] - starts[i][0]) * t,
                starts[i][1] + (to[1] - starts[i][1]) * t,
              ];
            } else if (step.animation === 'dance') {
              o.pos = [
                starts[i][0],
                starts[i][1] + Math.abs(Math.sin(Math.PI * t * cycles)) * 0.12,
              ];
            }
          });
        }).then(() =>
          rigs.forEach((o) => {
            o.pose = null;
          }),
        );
      }
    }
  }

  _centerOf(leaves) {
    let x0 = 1e9,
      y0 = 1e9,
      x1 = -1e9,
      y1 = -1e9;
    for (const o of leaves) {
      const b = bboxOfPrims(o.prims);
      x0 = Math.min(x0, o.pos[0] + b.x0 * o.scale);
      y0 = Math.min(y0, o.pos[1] + b.y0 * o.scale);
      x1 = Math.max(x1, o.pos[0] + b.x1 * o.scale);
      y1 = Math.max(y1, o.pos[1] + b.y1 * o.scale);
    }
    return [(x0 + x1) / 2, (y0 + y1) / 2];
  }

  async _clearBoard() {
    const all = [...this.objects.values()].filter((o) => !o.group && o.opacity > 0);
    if (all.length) {
      await this._animate(0.6, (t) =>
        all.forEach((o) => {
          o.opacity = Math.min(o.opacity, 1 - t);
        }),
      );
    }
    this.objects.clear();
  }

  _wait(seconds) {
    return new Promise((r) => setTimeout(r, seconds * 1000));
  }

  _animate(seconds, fn) {
    return new Promise((resolve) => {
      const t0 = performance.now(),
        ms = Math.max(seconds, 0.05) * 1000;
      const tick = (now) => {
        const t = Math.min((now - t0) / ms, 1);
        fn(t);
        if (t < 1) requestAnimationFrame(tick);
        else resolve();
      };
      requestAnimationFrame(tick);
    });
  }

  /* Track the pen tip at reveal fraction t of object o (world coords). */
  _penAt(o, t) {
    const prims = this._expand(o);
    const lens = prims.map(primLength);
    const total = lens.reduce((a, b) => a + b, 0) || 1;
    let acc = 0,
      target = t * total;
    for (let i = 0; i < prims.length; i++) {
      if (acc + lens[i] >= target) {
        const local = this._pointAlong(prims[i], lens[i] ? (target - acc) / lens[i] : 1);
        this.pen = [o.pos[0] + local[0] * o.scale, o.pos[1] + local[1] * o.scale];
        return;
      }
      acc += lens[i];
    }
    this.pen = null;
  }

  _pointAlong(p, t) {
    switch (p.k) {
      case 'line':
        return [p.x1 + (p.x2 - p.x1) * t, p.y1 + (p.y2 - p.y1) * t];
      case 'circle': {
        const a = -Math.PI / 2 + t * 2 * Math.PI; // start at top, like a hand would
        return [p.x + Math.cos(a) * p.r, p.y + Math.sin(a) * p.r];
      }
      case 'rect': {
        const pts = [
          [p.x - p.w / 2, p.y + p.h / 2],
          [p.x + p.w / 2, p.y + p.h / 2],
          [p.x + p.w / 2, p.y - p.h / 2],
          [p.x - p.w / 2, p.y - p.h / 2],
        ];
        return pointAlongPolyline(pts, true, t);
      }
      case 'poly':
        return pointAlongPolyline(p.pts, p.closed !== false, t);
      case 'text': {
        const e = primExtent(p);
        return [e[0] + (e[2] - e[0]) * t, p.y];
      }
      default:
        return [p.x || 0, p.y || 0];
    }
  }

  /* ------------------------------ drawing ------------------------------ */
  _resize() {
    const host = this.canvas.parentElement || document.body;
    const dpr = window.devicePixelRatio || 1;
    let w = host.clientWidth,
      h = host.clientHeight;
    if (!w || !h) return;
    if (w / h > FRAME_W / FRAME_H) w = (h * FRAME_W) / FRAME_H;
    else h = (w * FRAME_H) / FRAME_W;
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
  }

  _startLoop() {
    const loop = () => {
      this._draw();
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  /* world -> pixels */
  _X(x) {
    return this.canvas.width / 2 + x * this._unit();
  }
  _Y(y) {
    return this.canvas.height / 2 - y * this._unit();
  }
  _unit() {
    return this.canvas.width / FRAME_W;
  }

  _draw() {
    const { ctx, canvas } = this;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = this.background;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (const o of this.objects.values()) {
      if (o.group || o.opacity <= 0.003) continue;
      this._drawObject(o);
    }

    if (this.pen) {
      // chalk tip
      const u = this._unit();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(this._X(this.pen[0]), this._Y(this.pen[1]), u * 0.07, 0, 2 * Math.PI);
      ctx.fillStyle = '#FFFFFF';
      ctx.shadowColor = '#FFFFFF';
      ctx.shadowBlur = u * 0.15;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  /* Dynamic prims (rig/globe/strokes) expand to drawable prims each frame —
   * the pose and phase live on the object, so performances animate. */
  _expand(o) {
    if (!o.dynamic) return o.prims;
    const color = o.color || '#E6EDF3';
    return o.prims.flatMap((p) => {
      if (p.k === 'rig') return rigPrims(o.pose, p.stroke || color);
      if (p.k === 'globe') return globePrims(p.r || 1.1, o.phase || 0, p.stroke || color);
      if (p.k === 'strokes') {
        return p.strokes.map((s) => ({
          k: 'poly',
          pts: s,
          closed: false,
          stroke: p.stroke || color,
          lw: p.lw || 3.5,
          raw: true,
        })); // human strokes: no wobble
      }
      return [p];
    });
  }

  _drawObject(o) {
    const prims = this._expand(o);
    const lens = prims.map(primLength);
    const total = lens.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    for (let i = 0; i < prims.length; i++) {
      // Reveal fraction local to this primitive (sequential along the list).
      const start = acc / total,
        end = (acc + lens[i]) / total;
      acc += lens[i];
      let t = 1;
      if (o.reveal < 1) {
        if (o.reveal <= start) continue;
        t = Math.min(1, (o.reveal - start) / Math.max(end - start, 1e-6));
      }
      this._drawPrim(o, prims[i], t, i);
    }
  }

  _drawPrim(o, p, t, idx = 0) {
    const { ctx } = this;
    const u = this._unit();
    const rot = o.rotation || 0;
    const cr = Math.cos(rot),
      sr = Math.sin(rot);
    const W = (x, y) => {
      const rx = x * cr - y * sr,
        ry = x * sr + y * cr;
      return [this._X(o.pos[0] + rx * o.scale), this._Y(o.pos[1] + ry * o.scale)];
    };
    const seed = (o.seed || 0) + idx * 7.77;
    const lw = ((p.lw || 4) * u) / 55;
    ctx.globalAlpha = o.opacity;
    ctx.lineWidth = Math.max(lw, 1);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    switch (p.k) {
      case 'line': {
        let pts = [
          [p.x1, p.y1],
          [p.x2, p.y2],
        ];
        if (!p.raw) pts = sketchify(pts, seed);
        const part = partialPolyline(pts, false, t);
        ctx.strokeStyle = p.stroke || '#FFF';
        ctx.beginPath();
        part.forEach((q, i) => {
          const [x, y] = W(q[0], q[1]);
          i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.stroke();
        if (p.arrow && t > 0.85 && part.length > 1) {
          // head as the shaft finishes
          const [x2, y2] = W(...part[part.length - 1]);
          const [x1, y1] = W(...part[Math.max(0, part.length - 3)]);
          const ang = Math.atan2(y2 - y1, x2 - x1),
            s = u * 0.28;
          ctx.fillStyle = p.stroke || '#FFF';
          ctx.beginPath();
          ctx.moveTo(x2, y2);
          ctx.lineTo(x2 - s * Math.cos(ang - 0.45), y2 - s * Math.sin(ang - 0.45));
          ctx.lineTo(x2 - s * Math.cos(ang + 0.45), y2 - s * Math.sin(ang + 0.45));
          ctx.closePath();
          ctx.fill();
        }
        return;
      }
      case 'circle': {
        let pts = circlePts(p.x, p.y, p.r);
        if (!p.raw) pts = sketchify(pts, seed, 0.04 * Math.max(1, p.r));
        if (p.fill) {
          ctx.beginPath();
          pts.forEach((q, i) => {
            const [x, y] = W(q[0], q[1]);
            i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
          });
          ctx.closePath();
          ctx.fillStyle = p.fill;
          ctx.globalAlpha = o.opacity * t;
          ctx.fill();
          ctx.globalAlpha = o.opacity;
        }
        if (p.stroke) {
          const part = partialPolyline(pts, false, t);
          ctx.strokeStyle = p.stroke;
          ctx.beginPath();
          part.forEach((q, i) => {
            const [x, y] = W(q[0], q[1]);
            i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
          });
          ctx.stroke();
        }
        return;
      }
      case 'dot': {
        const [cx, cy] = W(p.x, p.y);
        ctx.beginPath();
        ctx.arc(cx, cy, p.r * o.scale * u, 0, 2 * Math.PI);
        ctx.fillStyle = p.fill || '#FFF';
        ctx.globalAlpha = o.opacity * t;
        ctx.fill();
        return;
      }
      case 'rect': {
        const pts = [
          [p.x - p.w / 2, p.y + p.h / 2],
          [p.x + p.w / 2, p.y + p.h / 2],
          [p.x + p.w / 2, p.y - p.h / 2],
          [p.x - p.w / 2, p.y - p.h / 2],
        ];
        return this._strokePoly(
          o,
          { pts, closed: true, stroke: p.stroke, fill: p.fill, raw: p.raw },
          t,
          W,
          seed,
        );
      }
      case 'poly':
        return this._strokePoly(o, p, t, W, seed);
      case 'text': {
        const [x, y] = W(p.x, p.y);
        const px = ((p.size || 40) / 48) * u;
        const text = p.text || '';
        const n = Math.ceil(t * text.length);
        ctx.font = `${px}px -apple-system, "Segoe UI", Roboto, sans-serif`;
        ctx.textBaseline = 'middle';
        ctx.fillStyle = p.color || '#FFF';
        // Center the *full* string; reveal a prefix so it types in place.
        const full = ctx.measureText(text).width;
        ctx.fillText(text.slice(0, n), x - full / 2, y);
        return;
      }
    }
  }

  _strokePoly(o, p, t, W, seed = 0) {
    const { ctx } = this;
    const closed = p.closed !== false;
    // Wobble the path once (stable seed): both the fill outline and the
    // stroke follow the same sketched line, like a real chalk shape.
    let path = closed ? [...p.pts, p.pts[0]] : p.pts;
    if (!p.raw) path = sketchify(path, seed);
    if (p.fill) {
      ctx.beginPath();
      path.forEach((q, i) => {
        const [x, y] = W(q[0], q[1]);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.closePath();
      ctx.fillStyle = p.fill;
      ctx.globalAlpha = o.opacity * t; // shade in as it draws
      ctx.fill();
      ctx.globalAlpha = o.opacity;
    }
    if (p.stroke) {
      const pts = partialPolyline(path, false, t);
      if (pts.length > 1) {
        ctx.beginPath();
        pts.forEach((q, i) => {
          const [x, y] = W(q[0], q[1]);
          i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        });
        ctx.strokeStyle = p.stroke;
        ctx.stroke();
      }
    }
  }
}

/* Partial polyline up to fraction t of its total length. */
function partialPolyline(pts, closed, t) {
  const path = closed ? [...pts, pts[0]] : pts;
  if (t >= 1) return path;
  const segs = [];
  let total = 0;
  for (let i = 0; i < path.length - 1; i++) {
    const L = Math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1]);
    segs.push(L);
    total += L;
  }
  let target = t * total,
    out = [path[0]];
  for (let i = 0; i < segs.length; i++) {
    if (target >= segs[i]) {
      out.push(path[i + 1]);
      target -= segs[i];
      continue;
    }
    const f = segs[i] ? target / segs[i] : 0;
    out.push([
      path[i][0] + (path[i + 1][0] - path[i][0]) * f,
      path[i][1] + (path[i + 1][1] - path[i][1]) * f,
    ]);
    break;
  }
  return out;
}

function pointAlongPolyline(pts, closed, t) {
  const partial = partialPolyline(pts, closed, Math.min(t, 0.9999));
  return partial[partial.length - 1];
}
