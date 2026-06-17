/* Asset library for the live board — the JS twin of backend/assets.py.
 *
 * Each factory returns a display list of primitives in Manim units
 * (origin at the asset's center, +y up) that board.js knows how to draw
 * and progressively reveal. Keep names/aliases in sync with assets.py so
 * the same planner output renders on both the mp4 and the live board.
 *
 * Primitive shapes:
 *   {k:'circle', x,y,r, stroke?, fill?, lw?}
 *   {k:'rect',   x,y,w,h, stroke?, fill?, lw?}        (x,y = center)
 *   {k:'line',   x1,y1,x2,y2, stroke, lw?}
 *   {k:'poly',   pts:[[x,y],...], stroke?, fill?, lw?, closed?}
 *   {k:'text',   x,y, text, size, color}              (size = manim font_size)
 *   {k:'dot',    x,y,r, fill}
 */

const BoardAssets = (() => {
  const FACTORIES = {};
  const ALIASES = {};

  function register(name, aliases, fn) {
    FACTORIES[name] = fn;
    for (const a of aliases) ALIASES[a] = name;
  }

  // Rig-backed: board.js poses and animates it (walk/dance/wave verbs).
  register(
    'stick_figure',
    [
      'man',
      'person',
      'human',
      'boy',
      'girl',
      'woman',
      'people',
      'student',
      'teacher',
      'figure',
      'stickman',
      'stick_man',
      'walker',
      'dancer',
      'kid',
      'child',
    ],
    ({ color = '#E6EDF3' } = {}) => [{ k: 'rig', stroke: color }],
  );

  // Parametric globe: "spin" drifts its meridians — a real rotation, not a
  // rolling circle.
  register('globe', ['earth', 'planet', 'world'], ({ color = '#58A6FF', r = 1.1 } = {}) => [
    { k: 'globe', r, stroke: color },
  ]);

  register(
    'road',
    ['street', 'path', 'highway', 'ground', 'floor'],
    ({ color = '#30363D', width = 14.0, height = 1.6 } = {}) => {
      width = Math.max(Number(width) || 14, 8); // clamp: a road reads frame-wide
      const prims = [{ k: 'rect', x: 0, y: 0, w: width, h: height, fill: color }];
      for (let x = -width / 2 + 0.7; x < width / 2 - 0.5; x += 1.4) {
        prims.push({
          k: 'line',
          x1: x - 0.35,
          y1: 0,
          x2: x + 0.35,
          y2: 0,
          stroke: '#E3B341',
          lw: 6,
        });
      }
      return prims;
    },
  );

  register('car', ['vehicle', 'automobile'], ({ color = '#58A6FF' } = {}) => [
    { k: 'rect', x: 0, y: 0, w: 2.2, h: 0.6, fill: color },
    { k: 'rect', x: -0.1, y: 0.5, w: 1.1, h: 0.5, fill: color },
    { k: 'circle', x: -0.6, y: -0.35, r: 0.28, fill: '#0E1116', stroke: '#8B949E', lw: 3 },
    { k: 'circle', x: 0.6, y: -0.35, r: 0.28, fill: '#0E1116', stroke: '#8B949E', lw: 3 },
  ]);

  register('tree', ['plant'], ({ color = '#3FB950' } = {}) => [
    { k: 'rect', x: 0, y: -0.5, w: 0.35, h: 1.0, fill: '#8B5A2B' },
    { k: 'circle', x: 0, y: 0.5, r: 0.8, fill: color },
  ]);

  register('house', ['home'], ({ color = '#D29922' } = {}) => [
    { k: 'rect', x: 0, y: -0.2, w: 1.6, h: 1.6, fill: color },
    {
      k: 'poly',
      pts: [
        [-1.0, 0.6],
        [1.0, 0.6],
        [0, 1.5],
      ],
      fill: '#B62324',
      closed: true,
    },
    { k: 'rect', x: 0, y: -0.6, w: 0.4, h: 0.7, fill: '#3A2410' },
  ]);

  register('sun', [], ({ color = '#F2CC60' } = {}) => {
    const prims = [{ k: 'circle', x: 0, y: 0, r: 0.6, fill: color }];
    for (let i = 0; i < 8; i++) {
      const a = (i * Math.PI) / 4,
        c = Math.cos(a),
        s = Math.sin(a);
      prims.push({
        k: 'line',
        x1: c * 0.8,
        y1: s * 0.8,
        x2: c * 1.2,
        y2: s * 1.2,
        stroke: color,
        lw: 5,
      });
    }
    return prims;
  });

  register('cloud', [], ({ color = '#C9D1D9' } = {}) => [
    { k: 'circle', x: -0.6, y: 0, r: 0.5, fill: color },
    { k: 'circle', x: 0, y: 0, r: 0.65, fill: color },
    { k: 'circle', x: 0.6, y: 0, r: 0.5, fill: color },
  ]);

  register('mountain', ['hill'], ({ color = '#6E7681' } = {}) => [
    {
      k: 'poly',
      pts: [
        [-1.5, -0.8],
        [1.5, -0.8],
        [0, 1.2],
      ],
      fill: color,
      closed: true,
    },
  ]);

  register('building', ['tower', 'skyscraper'], ({ color = '#484F58' } = {}) => {
    const prims = [{ k: 'rect', x: 0, y: 0, w: 1.4, h: 3.0, fill: color }];
    for (let row = 0; row < 5; row++)
      for (let col = 0; col < 2; col++)
        prims.push({
          k: 'rect',
          x: -0.35 + col * 0.7,
          y: 1.0 - row * 0.5,
          w: 0.3,
          h: 0.3,
          fill: '#F2CC60',
        });
    return prims;
  });

  register('book', [], ({ color = '#A371F7' } = {}) => [
    { k: 'rect', x: 0, y: 0, w: 1.4, h: 1.8, fill: color },
    { k: 'line', x1: -0.6, y1: 0.9, x2: -0.6, y2: -0.9, stroke: '#0E1116', lw: 4 },
  ]);

  register('bulb', ['lightbulb', 'idea'], ({ color = '#F2CC60' } = {}) => [
    { k: 'circle', x: 0, y: 0, r: 0.55, fill: color },
    { k: 'rect', x: 0, y: -0.7, w: 0.4, h: 0.35, fill: '#8B949E' },
  ]);

  register('dot_label', ['marker'], ({ color = '#58A6FF' } = {}) => [
    { k: 'dot', x: 0, y: 0, r: 0.12, fill: color },
  ]);

  function norm(name) {
    return String(name || '')
      .trim()
      .toLowerCase()
      .replace(/[\s-]+/g, '_');
  }

  /* Labeled fallback box — an unknown asset is visible, never an exception
   * (same contract as assets.py `_fallback`). */
  function fallback(name) {
    return [
      { k: 'rect', x: 0, y: 0, w: 2.6, h: 1.2, stroke: '#8B949E', lw: 3 },
      { k: 'text', x: 0, y: 0, text: name || 'asset', size: 22, color: '#8B949E' },
    ];
  }

  function build(name, params) {
    const canonical = ALIASES[norm(name)] || norm(name);
    const fn = FACTORIES[canonical];
    if (!fn) return fallback(name);
    try {
      return fn(params || {});
    } catch (e) {
      return fallback(name);
    }
  }

  function has(name) {
    return !!FACTORIES[ALIASES[norm(name)] || norm(name)];
  }

  return { build, has, names: () => Object.keys(FACTORIES) };
})();
