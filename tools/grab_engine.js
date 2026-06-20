// FAST motion/staging check: drive the VANILLA /engine board (no build step) and grab small,
// heavily COMPRESSED JPEG frames timed across the lesson. Built for quick visual iteration —
// the cartoon's MOTION + STAGING read with any content, so template provider = instant.
//   NODE_PATH=/tmp/pptr/node_modules node tools/grab_engine.js \
//     --url http://127.0.0.1:8010 --topic "the water cycle" --mode story --dir /tmp/ef/water --n 12
const puppeteer = require('puppeteer-core');
const fs = require('node:fs');
const CHROME =
  process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const arg = (n, d) => {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 ? process.argv[i + 1] : d;
};
const URL = arg('url', 'http://127.0.0.1:8010');
const topic = arg('topic', 'the water cycle');
const mode = arg('mode', 'story');
const style = arg('style', 'cartoon');
const dir = arg('dir', '/tmp/ef/run');
const nFrames = parseInt(arg('n', '12'), 10);
const gap = parseInt(arg('gap', '1500'), 10);
const quality = parseInt(arg('quality', '38'), 10); // low quality = small files, fast to read
const scale = parseFloat(arg('scale', '0.7')); // downscale: a quick check needs no full res
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
  await p.goto(URL + '/engine', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await sleep(500); // let engine.js wire up the controls
  const clickData = async (attr, val) => {
    const el = await p.$(`[data-${attr}="${val}"]`);
    if (el) await el.click();
  };
  // Set the topic FIRST — the chips' teach() reads the live #topic value when clicked.
  await p.evaluate((t) => {
    const el = document.getElementById('topic');
    el.value = t;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, topic);
  await clickData('style', style);
  await clickData('mode', mode); // this teach() runs MY topic, in story mode, cartoon style
  const boardEls = () =>
    p.evaluate(() => {
      const s = document.getElementById('board');
      return s ? s.querySelectorAll('path,polyline,circle,rect,g,image,text').length : 0;
    });
  // template = instant; just wait until the first subjects have drawn.
  let t0 = Date.now();
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
