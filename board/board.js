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
"use strict";

const FRAME_W = 14.2, FRAME_H = 8.0;

/* ----------------------------------------------------------------------- *
 * IR object -> {prims, pos, scale, opacity}
 * Prims are local to the object's center so move/scale are uniform.
 * ----------------------------------------------------------------------- */
function compileObject(o) {
  let prims, selfPositioned = false;
  const color = o.color || "#FFFFFF";
  const type = o.type;

  if (type === "asset") {
    prims = BoardAssets.build(o.asset, o.params);
  } else if (type === "text" || type === "mathtex") {
    prims = [{ k: "text", x: 0, y: 0, text: o.text || o.tex || "",
               size: o.font_size || 40, color }];
  } else if (type === "circle") {
    prims = [{ k: "circle", x: 0, y: 0, r: o.radius ?? 1, stroke: color, lw: 4 }];
  } else if (type === "square") {
    prims = [{ k: "rect", x: 0, y: 0, w: o.width ?? 2, h: o.width ?? 2, stroke: color, lw: 4 }];
  } else if (type === "rectangle") {
    prims = [{ k: "rect", x: 0, y: 0, w: o.width ?? 2, h: o.height ?? 1, stroke: color, lw: 4 }];
  } else if (type === "triangle" || type === "polygon") {
    let pts = (o.points || []).map(p => [p[0], p[1]]);
    if (pts.length < 3) {  // manim's default Triangle: circumradius 1, apex up
      pts = [0, 1, 2].map(i => {
        const a = Math.PI / 2 + i * 2 * Math.PI / 3;
        return [Math.cos(a), Math.sin(a)];
      });
    } else {
      selfPositioned = true;
    }
    prims = [{ k: "poly", pts, stroke: color, lw: 4, closed: true }];
  } else if (type === "line" || type === "arrow") {
    const s = o.start || [0, 0], e = o.end || [1, 0];
    prims = [{ k: "line", x1: s[0], y1: s[1], x2: e[0], y2: e[1], stroke: color, lw: 4,
               arrow: type === "arrow" }];
    selfPositioned = true;
  } else if (type === "dot") {
    prims = [{ k: "dot", x: 0, y: 0, r: 0.08, fill: color }];
  } else if (type === "group") {
    return { id: o.id, group: true, members: o.members || [], scale: o.scale ?? 1 };
  } else {
    prims = BoardAssets.build(type, o.params);  // unknown type -> labeled box
  }

  let pos = [o.position?.[0] ?? 0, o.position?.[1] ?? 0];
  if (selfPositioned) {
    // Recenter absolute coords around their bbox center so pos == center
    // and move/scale behave exactly like manim's move_to/scale.
    const c = bboxOfPrims(prims).center;
    prims = translatePrims(prims, -c[0], -c[1]);
    pos = c;
  }
  return { id: o.id, prims, pos, scale: o.scale ?? 1, opacity: 0, reveal: 1 };
}

/* ------------------------- geometry helpers --------------------------- */
function primExtent(p) {
  switch (p.k) {
    case "circle": return [p.x - p.r, p.y - p.r, p.x + p.r, p.y + p.r];
    case "dot":    return [p.x - p.r, p.y - p.r, p.x + p.r, p.y + p.r];
    case "rect":   return [p.x - p.w / 2, p.y - p.h / 2, p.x + p.w / 2, p.y + p.h / 2];
    case "line":   return [Math.min(p.x1, p.x2), Math.min(p.y1, p.y2),
                           Math.max(p.x1, p.x2), Math.max(p.y1, p.y2)];
    case "poly": {
      const xs = p.pts.map(q => q[0]), ys = p.pts.map(q => q[1]);
      return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    }
    case "text": {
      const h = (p.size || 40) / 48, w = h * 0.52 * (p.text || "").length;
      return [p.x - w / 2, p.y - h / 2, p.x + w / 2, p.y + h / 2];
    }
  }
  return [p.x || 0, p.y || 0, p.x || 0, p.y || 0];
}

function bboxOfPrims(prims) {
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for (const p of prims) {
    const e = primExtent(p);
    x0 = Math.min(x0, e[0]); y0 = Math.min(y0, e[1]);
    x1 = Math.max(x1, e[2]); y1 = Math.max(y1, e[3]);
  }
  if (x0 > x1) { x0 = y0 = x1 = y1 = 0; }
  return { x0, y0, x1, y1, center: [(x0 + x1) / 2, (y0 + y1) / 2] };
}

function translatePrims(prims, dx, dy) {
  return prims.map(p => {
    const q = { ...p };
    if (q.k === "line") { q.x1 += dx; q.y1 += dy; q.x2 += dx; q.y2 += dy; }
    else if (q.k === "poly") { q.pts = q.pts.map(pt => [pt[0] + dx, pt[1] + dy]); }
    else { q.x += dx; q.y += dy; }
    return q;
  });
}

function primLength(p) {  // stroke length, for proportional reveal pacing
  switch (p.k) {
    case "line":   return Math.hypot(p.x2 - p.x1, p.y2 - p.y1);
    case "circle": return 2 * Math.PI * p.r;
    case "rect":   return 2 * (p.w + p.h);
    case "poly": {
      let L = 0;
      for (let i = 0; i < p.pts.length; i++) {
        const a = p.pts[i], b = p.pts[(i + 1) % p.pts.length];
        if (i === p.pts.length - 1 && !p.closed) break;
        L += Math.hypot(b[0] - a[0], b[1] - a[1]);
      }
      return L;
    }
    case "text": return Math.max(1, (p.text || "").length * 0.3);
    case "dot":  return 0.3;
  }
  return 1;
}

const easeInOut = t => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

/* ----------------------------------------------------------------------- *
 * The player
 * ----------------------------------------------------------------------- */
class BoardPlayer {
  /**
   * @param canvas  the <canvas> to draw on
   * @param opts    { speak(text)->Promise, onSegment(seg), onIdle() }
   */
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.opts = opts;
    this.objects = new Map();   // id -> compiled object (insertion = draw order)
    this.queue = [];
    this.playing = false;
    this.background = "#0E1116";
    this.pen = null;            // [x,y] world coords of the drawing tip
    this._raf = null;
    this._startLoop();
    new ResizeObserver(() => this._resize()).observe(canvas.parentElement || canvas);
    this._resize();
  }

  /* ---- public API ---- */
  enqueue(segment) {
    this.queue.push(segment);
    if (!this.playing) this._drain();
  }

  reset() {
    this.queue.length = 0;
    this.objects.clear();
    this.pen = null;
    this.playing = false;
  }

  /* ---- segment/step playback ---- */
  async _drain() {
    this.playing = true;
    while (this.queue.length) {
      const seg = this.queue.shift();
      this.opts.onSegment?.(seg);
      // speak() gets the whole segment: narration may already be playing
      // via an early "narration" event — the UI dedupes by segment index.
      const speech = this.opts.speak ? this.opts.speak(seg) : Promise.resolve();
      if (seg.clear) await this._clearBoard();
      for (const o of seg.objects || []) {
        if (!this.objects.has(o.id)) {
          try { this.objects.set(o.id, compileObject(o)); } catch (e) { /* skip bad object */ }
        }
      }
      for (const step of seg.steps || []) {
        try { await this._runStep(step); } catch (e) { /* skip bad step */ }
      }
      await speech;               // teacher finishes the sentence before moving on
      await this._wait(0.4);
    }
    this.playing = false;
    this.opts.onIdle?.();
  }

  /* Resolve a step target to the list of leaf objects it animates. */
  _leaves(id) {
    const o = this.objects.get(id);
    if (!o) return [];
    if (!o.group) return [o];
    return o.members.flatMap(m => this._leaves(m));
  }

  async _runStep(step) {
    const d = Math.max(Number(step.duration) || 1, 0.1);
    if (step.animation === "wait") return this._wait(d);
    const leaves = this._leaves(step.target);
    if (!leaves.length) return;

    switch (step.animation) {
      case "write":
      case "create": {
        // Reveal leaves sequentially, sharing `d` by stroke length.
        const lens = leaves.map(o => o.prims.reduce((s, p) => s + primLength(p), 0) || 1);
        const total = lens.reduce((a, b) => a + b, 0);
        for (let i = 0; i < leaves.length; i++) {
          const o = leaves[i];
          o.opacity = 1; o.reveal = 0;
          await this._animate(d * lens[i] / total, t => { o.reveal = t; this._penAt(o, t); });
          o.reveal = 1;
        }
        this.pen = null;
        return;
      }
      case "fadein":
        return this._animate(d, t => leaves.forEach(o => { o.opacity = Math.max(o.opacity, t); }));
      case "fadeout":
        return this._animate(d, t => leaves.forEach(o => { o.opacity = Math.min(o.opacity, 1 - t); }));
      case "move": {
        if (!step.to) return;
        leaves.forEach(o => { if (o.opacity === 0) { o.opacity = 1; } });  // manim implicit add
        const c = this._centerOf(leaves);
        const dx = step.to[0] - c[0], dy = step.to[1] - c[1];
        const starts = leaves.map(o => [...o.pos]);
        return this._animate(d, t => {
          const e = easeInOut(t);
          leaves.forEach((o, i) => {
            o.pos = [starts[i][0] + dx * e, starts[i][1] + dy * e];
          });
        });
      }
      case "scale": {
        const f = Number(step.factor) || 1.5;
        leaves.forEach(o => { if (o.opacity === 0) { o.opacity = 1; } });
        const c = this._centerOf(leaves);
        const starts = leaves.map(o => ({ pos: [...o.pos], scale: o.scale }));
        return this._animate(d, t => {
          const k = 1 + (f - 1) * easeInOut(t);   // scale about the common center
          leaves.forEach((o, i) => {
            o.scale = starts[i].scale * k;
            o.pos = [c[0] + (starts[i].pos[0] - c[0]) * k,
                     c[1] + (starts[i].pos[1] - c[1]) * k];
          });
        });
      }
      case "transform": {
        const into = this._leaves(step.into);
        if (!into.length) return;
        return this._animate(d, t => {
          leaves.forEach(o => { o.opacity = 1 - t; });
          into.forEach(o => { o.opacity = t; });
        });
      }
    }
  }

  _centerOf(leaves) {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const o of leaves) {
      const b = bboxOfPrims(o.prims);
      x0 = Math.min(x0, o.pos[0] + b.x0 * o.scale); y0 = Math.min(y0, o.pos[1] + b.y0 * o.scale);
      x1 = Math.max(x1, o.pos[0] + b.x1 * o.scale); y1 = Math.max(y1, o.pos[1] + b.y1 * o.scale);
    }
    return [(x0 + x1) / 2, (y0 + y1) / 2];
  }

  async _clearBoard() {
    const all = [...this.objects.values()].filter(o => !o.group && o.opacity > 0);
    if (all.length) {
      await this._animate(0.6, t => all.forEach(o => { o.opacity = Math.min(o.opacity, 1 - t); }));
    }
    this.objects.clear();
  }

  _wait(seconds) { return new Promise(r => setTimeout(r, seconds * 1000)); }

  _animate(seconds, fn) {
    return new Promise(resolve => {
      const t0 = performance.now(), ms = Math.max(seconds, 0.05) * 1000;
      const tick = now => {
        const t = Math.min((now - t0) / ms, 1);
        fn(t);
        if (t < 1) requestAnimationFrame(tick); else resolve();
      };
      requestAnimationFrame(tick);
    });
  }

  /* Track the pen tip at reveal fraction t of object o (world coords). */
  _penAt(o, t) {
    const lens = o.prims.map(primLength);
    const total = lens.reduce((a, b) => a + b, 0) || 1;
    let acc = 0, target = t * total;
    for (let i = 0; i < o.prims.length; i++) {
      if (acc + lens[i] >= target) {
        const local = this._pointAlong(o.prims[i], lens[i] ? (target - acc) / lens[i] : 1);
        this.pen = [o.pos[0] + local[0] * o.scale, o.pos[1] + local[1] * o.scale];
        return;
      }
      acc += lens[i];
    }
    this.pen = null;
  }

  _pointAlong(p, t) {
    switch (p.k) {
      case "line": return [p.x1 + (p.x2 - p.x1) * t, p.y1 + (p.y2 - p.y1) * t];
      case "circle": {
        const a = -Math.PI / 2 + t * 2 * Math.PI;  // start at top, like a hand would
        return [p.x + Math.cos(a) * p.r, p.y + Math.sin(a) * p.r];
      }
      case "rect": {
        const pts = [[p.x - p.w / 2, p.y + p.h / 2], [p.x + p.w / 2, p.y + p.h / 2],
                     [p.x + p.w / 2, p.y - p.h / 2], [p.x - p.w / 2, p.y - p.h / 2]];
        return pointAlongPolyline(pts, true, t);
      }
      case "poly": return pointAlongPolyline(p.pts, p.closed !== false, t);
      case "text": {
        const e = primExtent(p);
        return [e[0] + (e[2] - e[0]) * t, p.y];
      }
      default: return [p.x || 0, p.y || 0];
    }
  }

  /* ------------------------------ drawing ------------------------------ */
  _resize() {
    const host = this.canvas.parentElement || document.body;
    const dpr = window.devicePixelRatio || 1;
    let w = host.clientWidth, h = host.clientHeight;
    if (!w || !h) return;
    if (w / h > FRAME_W / FRAME_H) w = h * FRAME_W / FRAME_H; else h = w * FRAME_H / FRAME_W;
    this.canvas.style.width = w + "px";
    this.canvas.style.height = h + "px";
    this.canvas.width = Math.round(w * dpr);
    this.canvas.height = Math.round(h * dpr);
  }

  _startLoop() {
    const loop = () => { this._draw(); this._raf = requestAnimationFrame(loop); };
    this._raf = requestAnimationFrame(loop);
  }

  /* world -> pixels */
  _X(x) { return this.canvas.width / 2 + x * this._unit(); }
  _Y(y) { return this.canvas.height / 2 - y * this._unit(); }
  _unit() { return this.canvas.width / FRAME_W; }

  _draw() {
    const { ctx, canvas } = this;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = this.background;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (const o of this.objects.values()) {
      if (o.group || o.opacity <= 0.003) continue;
      this._drawObject(o);
    }

    if (this.pen) {  // chalk tip
      const u = this._unit();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(this._X(this.pen[0]), this._Y(this.pen[1]), u * 0.07, 0, 2 * Math.PI);
      ctx.fillStyle = "#FFFFFF";
      ctx.shadowColor = "#FFFFFF"; ctx.shadowBlur = u * 0.15;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  _drawObject(o) {
    const lens = o.prims.map(primLength);
    const total = lens.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    for (let i = 0; i < o.prims.length; i++) {
      // Reveal fraction local to this primitive (sequential along the list).
      const start = acc / total, end = (acc + lens[i]) / total;
      acc += lens[i];
      let t = 1;
      if (o.reveal < 1) {
        if (o.reveal <= start) continue;
        t = Math.min(1, (o.reveal - start) / Math.max(end - start, 1e-6));
      }
      this._drawPrim(o, o.prims[i], t);
    }
  }

  _drawPrim(o, p, t) {
    const { ctx } = this;
    const u = this._unit();
    const W = (x, y) => [this._X(o.pos[0] + x * o.scale), this._Y(o.pos[1] + y * o.scale)];
    const lw = (p.lw || 4) * u / 55;
    ctx.globalAlpha = o.opacity;
    ctx.lineWidth = Math.max(lw, 1);
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    switch (p.k) {
      case "line": {
        const [x1, y1] = W(p.x1, p.y1);
        const [x2r, y2r] = [p.x1 + (p.x2 - p.x1) * t, p.y1 + (p.y2 - p.y1) * t];
        const [x2, y2] = W(x2r, y2r);
        ctx.strokeStyle = p.stroke || "#FFF";
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        if (p.arrow && t > 0.85) {  // head appears as the shaft finishes
          const ang = Math.atan2(y2 - y1, x2 - x1), s = u * 0.28;
          ctx.fillStyle = p.stroke || "#FFF";
          ctx.beginPath();
          ctx.moveTo(x2, y2);
          ctx.lineTo(x2 - s * Math.cos(ang - 0.45), y2 - s * Math.sin(ang - 0.45));
          ctx.lineTo(x2 - s * Math.cos(ang + 0.45), y2 - s * Math.sin(ang + 0.45));
          ctx.closePath(); ctx.fill();
        }
        return;
      }
      case "circle": {
        const [cx, cy] = W(p.x, p.y), r = p.r * o.scale * u;
        ctx.beginPath();
        ctx.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + t * 2 * Math.PI);
        if (p.fill) {
          if (t >= 1) { ctx.closePath(); }
          ctx.fillStyle = p.fill; ctx.globalAlpha = o.opacity * t; ctx.fill();
          ctx.globalAlpha = o.opacity;
        }
        if (p.stroke) { ctx.strokeStyle = p.stroke; ctx.stroke(); }
        return;
      }
      case "dot": {
        const [cx, cy] = W(p.x, p.y);
        ctx.beginPath(); ctx.arc(cx, cy, p.r * o.scale * u, 0, 2 * Math.PI);
        ctx.fillStyle = p.fill || "#FFF"; ctx.globalAlpha = o.opacity * t; ctx.fill();
        return;
      }
      case "rect": {
        const pts = [[p.x - p.w / 2, p.y + p.h / 2], [p.x + p.w / 2, p.y + p.h / 2],
                     [p.x + p.w / 2, p.y - p.h / 2], [p.x - p.w / 2, p.y - p.h / 2]];
        return this._strokePoly(o, { pts, closed: true, stroke: p.stroke, fill: p.fill }, t, W);
      }
      case "poly":
        return this._strokePoly(o, p, t, W);
      case "text": {
        const [x, y] = W(p.x, p.y);
        const px = (p.size || 40) / 48 * u;
        const text = p.text || "";
        const n = Math.ceil(t * text.length);
        ctx.font = `${px}px -apple-system, "Segoe UI", Roboto, sans-serif`;
        ctx.textBaseline = "middle";
        ctx.fillStyle = p.color || "#FFF";
        // Center the *full* string; reveal a prefix so it types in place.
        const full = ctx.measureText(text).width;
        ctx.fillText(text.slice(0, n), x - full / 2, y);
        return;
      }
    }
  }

  _strokePoly(o, p, t, W) {
    const { ctx } = this;
    const closed = p.closed !== false;
    if (p.fill) {
      ctx.beginPath();
      p.pts.forEach((q, i) => {
        const [x, y] = W(q[0], q[1]);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.closePath();
      ctx.fillStyle = p.fill;
      ctx.globalAlpha = o.opacity * t;   // shade in as it draws
      ctx.fill();
      ctx.globalAlpha = o.opacity;
    }
    if (p.stroke) {
      const pts = partialPolyline(p.pts, closed, t);
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
    segs.push(L); total += L;
  }
  let target = t * total, out = [path[0]];
  for (let i = 0; i < segs.length; i++) {
    if (target >= segs[i]) { out.push(path[i + 1]); target -= segs[i]; continue; }
    const f = segs[i] ? target / segs[i] : 0;
    out.push([path[i][0] + (path[i + 1][0] - path[i][0]) * f,
              path[i][1] + (path[i + 1][1] - path[i][1]) * f]);
    break;
  }
  return out;
}

function pointAlongPolyline(pts, closed, t) {
  const partial = partialPolyline(pts, closed, Math.min(t, 0.9999));
  return partial[partial.length - 1];
}
