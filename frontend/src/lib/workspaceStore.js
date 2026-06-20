import { derived, get, writable } from 'svelte/store';
import { animate, getScriptPrompt, getStatus, getTimeline } from './api.js';
import { Aborted, play, playTimeline } from './board.js';

export const MODES = ['learn', 'story', 'draw', 'explain'];
export const AUDIENCES = [
  ['child', 'kid'],
  ['general', 'general'],
  ['expert', 'expert'],
];
export const STYLES = [
  ['cartoon', 'cartoon'],
  ['whiteboard', 'whiteboard'],
];
export const DEPTHS = ['brief', 'normal', 'deep'];
export const TONES = ['neutral', 'playful', 'formal'];
export const ENERGIES = ['calm', 'normal', 'lively'];

export const topic = writable('the water cycle');
export const mode = writable('learn');
export const audience = writable('general');
export const style = writable('cartoon');
export const depth = writable('normal');
export const tone = writable('neutral');
export const energy = writable('normal');
export const script = writable('');
// No manual toggle: the input source is inferred — JSON in the box means "animate it".
export const inputMode = derived(script, ($s) => ($s.trim() ? 'script' : 'topic'));

export const status = writable(null);
export const playing = writable(false);
export const error = writable('');
export const caption = writable('');
export const provenance = writable(null);
export const summary = writable(null);
export const spec = writable(null);
export const promptMsg = writable('');
export const runLabel = writable('Idle');
export const hasRun = writable(false);

let svgEl = null;
let controller = null;
let statusLoaded = false;
let promptTimer = null;

export function setBoardElement(el) {
  svgEl = el;
}

export async function refreshStatus(force = false) {
  if (statusLoaded && !force) return;
  try {
    status.set(await getStatus());
    statusLoaded = true;
  } catch (e) {
    error.set(`status: ${e.message}`);
  }
}

function payload() {
  return {
    topic: get(topic),
    mode: get(mode),
    audience: get(audience),
    style: get(style),
    depth: get(depth),
    tone: get(tone),
    energy: get(energy),
  };
}

function resetRunState(label) {
  error.set('');
  caption.set(label);
  provenance.set(null);
  summary.set(null);
  spec.set(null);
  runLabel.set(label);
}

function onEvent(ev) {
  if (ev.type === 'start') {
    provenance.set(ev.story);
  } else if (ev.type === 'say') {
    caption.set(ev.text);
  } else if (ev.type === 'done') {
    summary.set(ev.summary);
    caption.update((v) => (v ? `${v} Done.` : 'Done.'));
    runLabel.set('Complete');
  }
}

async function run(fetcher, label) {
  if (!svgEl) {
    error.set('Open the Board panel before running a lesson.');
    return;
  }
  controller?.abort();
  controller = new AbortController();
  const signal = controller.signal;
  playing.set(true);
  hasRun.set(true);
  resetRunState(label);

  try {
    const data = await fetcher();
    if (signal.aborted) return;
    spec.set(data.spec);
    caption.set('');
    if (data.timeline) {
      await playTimeline(svgEl, data.timeline, onEvent, signal);
    } else {
      await play(svgEl, data.events, onEvent, signal);
    }
  } catch (e) {
    if (!(e instanceof Aborted)) {
      error.set(e.message);
      caption.set('');
      runLabel.set('Error');
    }
  } finally {
    if (controller?.signal === signal) {
      playing.set(false);
      controller = null;
    }
  }
}

// Natural-language tuning: pull plain-English DIRECTIVE phrases out of the topic and
// fold them into the chips, then teach the clean subject. Only unambiguous multi-word
// directives match — never bare subject words like "deep sea" or "simple machines"
// (the same false-positive trap the backend director avoids by not scanning the topic).
const CUES = [
  { re: /\b(for kids|for children|for a child|kid[- ]friendly|eli5|explain like i'?m (5|five))\b/gi, set: { audience: 'child', style: 'cartoon', tone: 'playful', energy: 'lively' } },
  { re: /\b(for experts?|for professionals?|advanced level|graduate level)\b/gi, set: { audience: 'expert', tone: 'formal' } },
  { re: /\b(keep it short|keep it brief|make it quick|in brief|tl;?dr)\b/gi, set: { depth: 'brief' } },
  { re: /\b(go deep|in depth|in detail|be thorough|comprehensive overview|deep dive)\b/gi, set: { depth: 'deep' } },
  { re: /\b(make it fun|be playful|keep it fun)\b/gi, set: { tone: 'playful', energy: 'lively' } },
  { re: /\b(keep it formal|be formal|formally)\b/gi, set: { tone: 'formal' } },
  { re: /\b(keep it calm|slow it down|calmly)\b/gi, set: { energy: 'calm' } },
  { re: /\b(high[- ]energy|make it lively|be energetic)\b/gi, set: { energy: 'lively' } },
];
const SETTERS = { audience, style, depth, tone, energy };

function applyTopicCues() {
  let t = get(topic);
  if (!t.trim()) return;
  const apply = {};
  for (const cue of CUES) {
    if (cue.re.test(t)) {
      cue.re.lastIndex = 0;
      t = t.replace(cue.re, '');
      Object.assign(apply, cue.set);
    }
  }
  if (!Object.keys(apply).length) return;
  // tidy the leftover subject (stray commas / double spaces the strip left behind)
  t = t.replace(/\s+,/g, ',').replace(/,\s*,/g, ',').replace(/\s{2,}/g, ' ').replace(/^[\s,]+|[\s,]+$/g, '');
  topic.set(t);
  for (const [field, value] of Object.entries(apply)) SETTERS[field]?.set(value);
}

export function teach() {
  applyTopicCues();
  return run(() => getTimeline(payload()), 'Planning lesson...');
}

export function go() {
  if (get(script).trim()) {
    return run(() => animate({ script: get(script), ...payload() }), 'Animating storyboard...');
  }
  return teach();
}

export function stop() {
  controller?.abort();
  controller = null;
  playing.set(false);
  runLabel.set('Stopped');
  caption.set('Stopped.');
  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }
}

export async function copyPrompt() {
  try {
    const { prompt } = await getScriptPrompt(payload());
    await navigator.clipboard.writeText(prompt);
    promptMsg.set('Prompt copied. Paste it into your model, then paste the JSON here.');
  } catch (e) {
    promptMsg.set(`Could not copy prompt: ${e.message}`);
  }
  clearTimeout(promptTimer);
  promptTimer = setTimeout(() => promptMsg.set(''), 6000);
}

export function sourceIsWeak(src) {
  return src === 'box';
}
