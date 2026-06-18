// Record the Studio board playing a lesson to a video file (headless Chrome screencast).
//
// The cartoon lesson is the v3 timeline played on the SVG board, so a faithful video = recording
// the board playback. This drives the Studio headlessly (set mode/style, type topic, Teach), waits
// for drawing to start, screencasts just the board region to an mp4, and stops when playback ends.
//
// v1 limitations (documented): recording is REAL-TIME (a 1-min lesson takes ~1 min), and the video
// is SILENT — Web Speech audio cannot be captured (WICG/speech-api#69); narration audio needs the
// local-TTS path (Kokoro) muxed in later. On-screen captions carry the narration for now.
//
//   node tools/record_lesson.js --url http://127.0.0.1:8001 --topic "the water cycle" \
//        --mode story --style cartoon --out build/lesson.mp4
// Needs puppeteer-core on NODE_PATH and ffmpeg on PATH.

const puppeteer = require('puppeteer-core');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');

const CHROME =
  process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const arg = (name, def) => {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 ? process.argv[i + 1] : def;
};
const URL_BASE = arg('url', 'http://127.0.0.1:8001');
const topic = arg('topic', 'the water cycle');
const mode = arg('mode', 'story');
const style = arg('style', 'cartoon');
const out = arg('out', 'build/lesson.mp4');
const maxMs = parseInt(arg('max', '360000'), 10); // hard cap on recording length
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--mute-audio', '--force-device-scale-factor=1'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 920, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message));

  await page.goto(URL_BASE + '/studio/', { waitUntil: 'networkidle2', timeout: 30000 });

  const clickChip = async (text) => {
    for (const el of await page.$$('button.chip')) {
      if ((await page.evaluate((e) => e.textContent.trim(), el)) === text) {
        await el.click();
        return true;
      }
    }
    return false;
  };
  await clickChip(style);
  await clickChip(mode);
  // Set the topic ROBUSTLY (set value + dispatch input so Svelte's bind:value updates), then ENTER
  // fires go() — the Teach button is disabled while a chip-triggered DEFAULT lesson plays, so
  // clicking it silently captured the default topic instead of ours.
  const inp = await page.$('input[placeholder="Type a topic…"]');
  await inp.focus();
  await page.evaluate((t) => {
    const el = document.querySelector('input[placeholder="Type a topic…"]');
    el.value = t;
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }, topic);
  await page.keyboard.press('Enter');
  await sleep(900); // let the abort+restart settle so we record THIS topic

  // Wait until the board actually STARTS drawing (skip the "Planning…" generation wait so the
  // video doesn't open on a blank board).
  const boardEls = () =>
    page.evaluate(() => {
      const s = document.querySelector('.board-wrap svg');
      return s ? s.querySelectorAll('path,polyline,circle,rect,g,image,text').length : 0;
    });
  const t0 = Date.now();
  while ((await boardEls()) <= 4) {
    if (Date.now() - t0 > 150000) {
      console.error('lesson never started drawing');
      break;
    }
    await sleep(400);
  }

  // Crop to the board + CAPTION region (.board-wrap holds the svg AND the caption line), so the
  // recorded video shows the narration too — the truest record of the actual output.
  const crop = await page.evaluate(() => {
    const s = document.querySelector('.board-wrap');
    if (!s) return null;
    const r = s.getBoundingClientRect();
    const even = (n) => Math.max(2, Math.round(n / 2) * 2); // ffmpeg wants even dimensions
    return { x: Math.round(r.x), y: Math.round(r.y), width: even(r.width), height: even(r.height) };
  });

  const tmp = out.replace(/\.(mp4|webm)$/i, '') + '.rec.webm';
  let recorder;
  try {
    recorder = await page.screencast({ path: tmp, crop: crop || undefined });
  } catch (e) {
    console.error('crop screencast failed, recording full viewport:', e.message);
    recorder = await page.screencast({ path: tmp });
  }

  // Record until the lesson finishes (Teach button stops showing "Teaching…") or the cap.
  const recStart = Date.now();
  const stillPlaying = async () =>
    (await page.$$eval('button.primary', (els) => els.map((e) => e.textContent.trim()))).includes(
      'Teaching…'
    );
  await sleep(1500);
  while (await stillPlaying()) {
    if (Date.now() - recStart > maxMs) break;
    await sleep(800);
  }
  await sleep(1500); // a short tail so the final frame lands
  await recorder.stop();
  await browser.close();

  // Puppeteer screencast writes VP9/webm; transcode to a universal H.264 mp4 (+faststart).
  execFileSync(
    'ffmpeg',
    ['-y', '-v', 'error', '-i', tmp, '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out],
    { stdio: 'inherit' }
  );
  fs.unlinkSync(tmp);
  const secs = Math.round((Date.now() - recStart) / 1000);
  console.log(`RECORDED ${out} (~${secs}s) errors: ${errors.length ? errors.join('; ') : '(none)'}`);
})().catch((e) => {
  console.error('REC ERROR', e);
  process.exit(1);
});
