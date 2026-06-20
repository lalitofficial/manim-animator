// FAST visual feedback loop: drive a lesson and grab a few COMPRESSED, board-only JPEG frames.
// Much faster than recording a full real-time video — for iterating on how the cartoon LOOKS.
//   node tools/grab_frames.js --url http://127.0.0.1:8001 --topic "how a volcano erupts" \
//        --mode story --style cartoon --dir /tmp/frames --n 6
const puppeteer = require('puppeteer-core');
const fs = require('node:fs');
const CHROME =
  process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const arg = (n, d) => {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 ? process.argv[i + 1] : d;
};
const URL = arg('url', 'http://127.0.0.1:8001');
const topic = arg('topic', 'how a volcano erupts');
const mode = arg('mode', 'story');
const style = arg('style', 'cartoon');
const dir = arg('dir', '/tmp/frames');
const nFrames = parseInt(arg('n', '6'), 10);
const gap = parseInt(arg('gap', '2500'), 10);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  fs.mkdirSync(dir, { recursive: true });
  const b = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--mute-audio'],
  });
  const p = await b.newPage();
  await p.setViewport({ width: 1280, height: 860, deviceScaleFactor: 1 });
  await p.goto(URL + '/studio/', { waitUntil: 'networkidle2', timeout: 30000 });
  const chip = async (t) => {
    for (const e of await p.$$('button.chip')) {
      if ((await p.evaluate((x) => x.textContent.trim(), e)) === t) return e.click();
    }
  };
  await chip(style);
  await chip(mode);
  // Set the topic ROBUSTLY: set value + dispatch input (so Svelte's bind:value updates `topic`),
  // then ENTER fires go() with it. (Typing + clicking Teach was unreliable — the button is
  // disabled while a chip-triggered DEFAULT lesson plays, so the default topic got captured.)
  const inp = await p.$('input[placeholder="Type a topic…"]');
  await inp.focus();
  await p.evaluate((t) => {
    const el = document.querySelector('input[placeholder="Type a topic…"]');
    el.value = t;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, topic);
  await p.keyboard.press('Enter');
  const boardEls = () =>
    p.evaluate(() => {
      const s = document.querySelector('.board-wrap svg');
      return s ? s.querySelectorAll('path,polyline,circle,rect,g,image,text').length : 0;
    });
  // The NEW (topic) lesson only takes over once its LLM fetch returns: its start event CLEARS the
  // board, then it refills. The OLD chip-triggered default lesson lingers during the (slow, ~10-40s)
  // fetch — waiting for "has content" alone captured THAT. So wait for a CLEAR, then a REFILL.
  const baseline = await boardEls();
  const clearTo = Math.max(2, Math.floor(baseline * 0.3));
  let t0 = Date.now();
  while ((await boardEls()) > clearTo) {
    if (Date.now() - t0 > 90000) break; // a cloud Gemini fetch can take tens of seconds
    await sleep(400);
  }
  t0 = Date.now();
  while ((await boardEls()) <= 6) {
    if (Date.now() - t0 > 40000) break;
    await sleep(400);
  }
  await sleep(900); // settle into the new lesson
  const clip = await p.evaluate(() => {
    const s = document.querySelector('.board-wrap svg');
    const r = s.getBoundingClientRect();
    return { x: ~~r.x, y: ~~r.y, width: ~~r.width, height: ~~r.height };
  });
  const grabbed = [];
  for (let i = 0; i < nFrames; i++) {
    const f = `${dir}/f${String(i).padStart(2, '0')}.jpg`;
    await p.screenshot({ path: f, type: 'jpeg', quality: 55, clip });
    grabbed.push(f);
    await sleep(gap);
  }
  console.log('GRABBED ' + grabbed.join(' '));
  await b.close();
})().catch((e) => {
  console.error('ERR', e);
  process.exit(1);
});
