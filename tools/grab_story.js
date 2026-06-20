// FAST end-to-end check of the TWO-STAGE product flow: Story Studio generate (template, instant)
// -> Approve & Animate -> the board plays the bridged cartoon. Grabs small COMPRESSED JPEG frames.
//   NODE_PATH=/tmp/pptr/node_modules node tools/grab_story.js \
//     --url http://127.0.0.1:8010 --prompt "how rain forms" --dir /tmp/ef/rain --n 14
const puppeteer = require('puppeteer-core');
const fs = require('node:fs');
const CHROME =
  process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const arg = (n, d) => {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 ? process.argv[i + 1] : d;
};
const URL = arg('url', 'http://127.0.0.1:8010');
const prompt = arg('prompt', 'how rain forms');
const arc = arg('arc', 'explainer');
const dir = arg('dir', '/tmp/ef/story');
const nFrames = parseInt(arg('n', '14'), 10);
const gap = parseInt(arg('gap', '1300'), 10);
const quality = parseInt(arg('quality', '38'), 10);
const scale = parseFloat(arg('scale', '0.7'));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(dir, { recursive: true });
  const b = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--mute-audio'],
  });
  const p = await b.newPage();
  await p.setViewport({ width: 960, height: 620, deviceScaleFactor: scale });
  // --- Stage 1: generate a story (template = instant + hermetic) ---
  await p.goto(URL + '/story-studio', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await sleep(400);
  await p.evaluate(
    (pr, a) => {
      const set = (id, v) => {
        const el = document.getElementById(id);
        if (el) {
          el.value = v;
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      };
      set('prompt', pr);
      set('providerSelect', 'template');
      set('arc', a);
    },
    prompt,
    arc,
  );
  await p.click('#generate');
  // wait until the package rendered (the Animate button enables)
  let t0 = Date.now();
  while (await p.evaluate(() => document.getElementById('animate').disabled)) {
    if (Date.now() - t0 > 30000) throw new Error('generate never enabled Animate');
    await sleep(300);
  }
  // --- Stage 2: Approve & Animate -> navigates to /engine and plays the bridged cartoon ---
  await Promise.all([
    p.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 30000 }),
    p.click('#animate'),
  ]);
  await sleep(600); // engine.js wires + playPendingStoryTimeline() kicks off
  const boardEls = () =>
    p.evaluate(() => {
      const s = document.getElementById('board');
      return s ? s.querySelectorAll('path,polyline,circle,rect,g,image,text').length : 0;
    });
  t0 = Date.now();
  while ((await boardEls()) < 8) {
    if (Date.now() - t0 > 20000) break;
    await sleep(300);
  }
  await sleep(400);
  const clip = await p.evaluate(() => {
    const s = document.getElementById('board');
    const r = s.getBoundingClientRect();
    return { x: Math.max(0, ~~r.x), y: Math.max(0, ~~r.y), width: ~~r.width, height: ~~r.height };
  });
  const grabbed = [];
  for (let i = 0; i < nFrames; i++) {
    const f = `${dir}/f${String(i).padStart(2, '0')}.jpg`;
    await p.screenshot({ path: f, type: 'jpeg', quality, clip });
    grabbed.push(f);
    await sleep(gap);
  }
  console.log('GRABBED ' + grabbed.length + ' -> ' + dir);
  await b.close();
})().catch((e) => {
  console.error('ERR', e);
  process.exit(1);
});
