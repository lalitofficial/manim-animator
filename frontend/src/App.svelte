<script>
  import { onMount } from 'svelte';
  import { getStatus, getTimeline, animate, getScriptPrompt } from './lib/api.js';
  import { play, playTimeline, clearBoard, Aborted } from './lib/board.js';

  const MODES = ['learn', 'story', 'draw', 'explain'];
  const AUD = [['child', 'kid'], ['general', 'general'], ['expert', 'expert']];
  const STYLE = [['cartoon', 'cartoon'], ['whiteboard', 'whiteboard']];
  const DEPTH = ['brief', 'normal', 'deep'];
  const TONE = ['neutral', 'playful', 'formal'];
  const ENERGY = ['calm', 'normal', 'lively'];

  let topic = 'the water cycle';
  let mode = 'learn';
  let audience = 'general';
  let style = 'cartoon';
  let depth = 'normal';
  let tone = 'neutral';
  let energy = 'normal';

  let svgEl;
  let status = null;
  let playing = false;
  let error = '';
  let caption = '';
  let provenance = null; // story event
  let summary = null; // done summary
  let spec = null;
  let controller = null;

  // Bring-your-own-story: paste a storyboard a stronger model wrote.
  let inputMode = 'topic'; // 'topic' | 'script'
  let script = '';
  let promptMsg = '';

  onMount(async () => {
    try {
      status = await getStatus();
    } catch (e) {
      error = `status: ${e.message}`;
    }
  });

  async function run(fetcher) {
    controller?.abort();
    controller = new AbortController();
    const signal = controller.signal;
    playing = true;
    error = '';
    caption = 'Planning…';
    provenance = null;
    summary = null;
    try {
      const data = await fetcher();
      if (signal.aborted) return;
      spec = data.spec;
      caption = '';
      // The teach path ships a choreographed timeline (master-clock scheduler); the bring-your-own
      // /animate path still ships a flat event list (the legacy queue). Branch on the payload.
      if (data.timeline) {
        await playTimeline(svgEl, data.timeline, onEvent, signal);
      } else {
        await play(svgEl, data.events, onEvent, signal);
      }
    } catch (e) {
      if (!(e instanceof Aborted)) {
        error = e.message;
        caption = '';
      }
    } finally {
      if (controller?.signal === signal) playing = false;
    }
  }

  const teach = () => run(() => getTimeline({ topic, mode, audience, style, depth, tone, energy }));

  // Dispatch the active input: a topic (local model) or a pasted storyboard (your model).
  function go() {
    if (inputMode === 'script') {
      if (!script.trim()) {
        error = 'Paste a storyboard JSON first — use “Copy AI prompt”.';
        return;
      }
      run(() => animate({ script, topic, mode, audience, style, depth, tone, energy }));
    } else {
      teach();
    }
  }

  async function copyPrompt() {
    try {
      const { prompt } = await getScriptPrompt({ topic, mode, audience, style, depth, tone });
      await navigator.clipboard.writeText(prompt);
      promptMsg = '✓ Copied — paste into ChatGPT/Claude, then paste its JSON below.';
    } catch (e) {
      promptMsg = `Couldn't copy: ${e.message}`;
    }
    setTimeout(() => (promptMsg = ''), 6000);
  }

  function onEvent(ev) {
    if (ev.type === 'start') provenance = ev.story;
    else if (ev.type === 'say') caption = ev.text;
    else if (ev.type === 'done') {
      summary = ev.summary;
      caption = caption ? `${caption}  ✓` : '✓';
    }
  }

  function pickMode(m) {
    mode = m;
    go();
  }
  function pickAud(a) {
    audience = a;
    go();
  }
  function pickStyle(s) {
    style = s;
    go();
  }

  // human-readable source color
  const srcWarn = (s) => s === 'box';
</script>

<header>
  <div class="brand">MANIM ANIMATOR · <b>STUDIO</b></div>
  <div class="tags">
    {#if status}
      <span class="tag {status.story_provider === 'template' ? 'warn' : 'ok'}">brain: {status.story_provider}{status.story_model ? ` · ${status.story_model}` : ''}</span>
      <span class="tag {status.ollama_reachable ? 'ok' : 'warn'}">ollama: {status.ollama_reachable ? `up · ${status.ollama_models?.length || 0} models` : 'down'}</span>
      <span class="tag">drawing: {status.svg_provider}</span>
      <span class="tag">quickdraw: {status.quickdraw_cached}</span>
    {:else}
      <span class="tag">loading…</span>
    {/if}
  </div>
</header>

{#if status?.warnings?.length}
  <div class="warnbar">
    {#each status.warnings as w}<span>⚠ {w}</span>{/each}
  </div>
{/if}

<div class="controls">
  <div class="row chips">
    <span class="lbl">input</span>
    <button class="chip" class:active={inputMode === 'topic'} on:click={() => (inputMode = 'topic')}>topic</button>
    <button class="chip" class:active={inputMode === 'script'} on:click={() => (inputMode = 'script')}>bring your own story</button>
  </div>

  {#if inputMode === 'topic'}
    <div class="row">
      <input bind:value={topic} placeholder="Type a topic…" on:keydown={(e) => e.key === 'Enter' && go()} />
      <button class="primary" on:click={go} disabled={playing}>{playing ? 'Teaching…' : 'Teach'}</button>
    </div>
  {:else}
    <div class="row">
      <input bind:value={topic} placeholder="Topic (used for the prompt + scene backdrop)…" />
      <button class="chip" on:click={copyPrompt}>📋 Copy AI prompt</button>
      <button class="primary" on:click={go} disabled={playing}>{playing ? 'Animating…' : 'Animate'}</button>
    </div>
    <textarea
      bind:value={script}
      rows="6"
      spellcheck="false"
      placeholder={'Paste the JSON a strong model wrote, e.g. {"beats":[{"kind":"show","entity":"sun","concept":"sun","relation":{"at":"top_left"}}, …]}'}
    ></textarea>
    <div class="hint {promptMsg ? 'ok' : 'dim'}">
      {promptMsg || 'Copy AI prompt → paste into ChatGPT/Claude → paste its JSON above → Animate. The engine draws it.'}
    </div>
  {/if}

  <div class="row chips">
    <span class="lbl">mode</span>
    {#each MODES as m}
      <button class="chip" class:active={mode === m} on:click={() => pickMode(m)}>{m}</button>
    {/each}
    <span class="sep"></span>
    <span class="lbl">audience</span>
    {#each AUD as [val, label]}
      <button class="chip" class:active={audience === val} on:click={() => pickAud(val)}>{label}</button>
    {/each}
    <span class="sep"></span>
    <span class="lbl">style</span>
    {#each STYLE as [val, label]}
      <button class="chip" class:active={style === val} on:click={() => pickStyle(val)}>{label}</button>
    {/each}
  </div>
  <div class="row selects">
    <label>depth <select bind:value={depth} on:change={go}>{#each DEPTH as d}<option>{d}</option>{/each}</select></label>
    <label>tone <select bind:value={tone} on:change={go}>{#each TONE as t}<option>{t}</option>{/each}</select></label>
    <label>energy <select bind:value={energy} on:change={go}>{#each ENERGY as e}<option>{e}</option>{/each}</select></label>
  </div>
</div>

<main>
  <section class="board-wrap">
    <svg bind:this={svgEl} viewBox="0 0 896 512" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Animated lesson board"></svg>
    <div class="caption">{caption}</div>
    {#if error}<div class="error">⚠ {error}</div>{/if}
  </section>

  <aside class="panel">
    <h3>Story</h3>
    {#if provenance}
      {#if provenance.fallback}
        <div class="prov warn">⚠ <b>{provenance.requested}</b> failed → template<br /><span class="dim">{provenance.reason}</span></div>
      {:else if provenance.used === 'template'}
        <div class="prov warn">⚠ offline <b>template</b> — start Ollama (local, free) for real lessons</div>
      {:else}
        <div class="prov ok">✓ by <b>{provenance.used}</b></div>
      {/if}
    {:else}<div class="dim">—</div>{/if}

    <h3>Drawings</h3>
    {#if summary}
      <div class="sources">
        {#each Object.entries(summary.by_source) as [src, n]}
          <span class="tag {srcWarn(src) ? 'warn' : 'ok'}">{n} {src}</span>
        {/each}
        {#if summary.dropped}<span class="tag warn">{summary.dropped} dropped</span>{/if}
      </div>
      <div class="dim small">{summary.real_drawings} real · {summary.placeholders} placeholder box{summary.placeholders === 1 ? '' : 'es'}</div>
    {:else}<div class="dim">—</div>{/if}

    <h3>Director spec</h3>
    {#if spec}
      <div class="kv">
        <span>mode</span><b>{spec.mode}</b>
        <span>style</span><b>{spec.style}{spec.cinematic ? ' · 🎥' : ''}</b>
        <span>audience</span><b>{spec.audience}</b>
        <span>depth</span><b>{spec.depth}</b>
        <span>tone</span><b>{spec.tone}</b>
        <span>energy</span><b>{spec.energy}</b>
        <span>concepts</span><b>{spec.concept_count}</b>
        <span>pace</span><b>{spec.draw_speed}×</b>
      </div>
    {:else}<div class="dim">—</div>{/if}

    <a class="legacy" href="/legacy">v2 board (legacy)</a>
  </aside>
</main>

<style>
  header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 14px 20px;
    border-bottom: 1px solid var(--line);
  }
  .brand {
    font-size: 15px;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .brand b {
    color: var(--fg);
  }
  .tags,
  .sources {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .tags {
    margin-left: auto;
  }
  .tag {
    font-size: 12px;
    padding: 2px 9px;
    border-radius: 999px;
    background: var(--line2);
    color: #c9d1d9;
  }
  .tag.ok {
    background: var(--green);
    color: #d2f5dd;
  }
  .tag.warn {
    background: var(--warn);
    color: #ffd9a8;
  }
  .warnbar {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px 20px;
    background: #2d2410;
    color: #ffd9a8;
    font-size: 12.5px;
  }
  .controls {
    padding: 14px 20px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    border-bottom: 1px solid var(--line);
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  input {
    flex: 1;
    min-width: 220px;
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--fg);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 15px;
  }
  textarea {
    width: 100%;
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--fg);
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    resize: vertical;
  }
  .hint {
    font-size: 12.5px;
    margin-top: -2px;
  }
  .hint.dim {
    color: var(--muted);
  }
  .hint.ok {
    color: #7ee2a8;
  }
  .primary {
    background: #238636;
    border: 0;
    color: #fff;
    border-radius: 8px;
    padding: 10px 20px;
    font-weight: 600;
  }
  .lbl {
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .sep {
    width: 1px;
    height: 18px;
    background: var(--line);
    margin: 0 4px;
  }
  .chip {
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--muted);
    border-radius: 7px;
    padding: 5px 13px;
    font-size: 13px;
    font-weight: 600;
    text-transform: capitalize;
  }
  .chip.active {
    background: #1f6feb22;
    border-color: var(--accent);
    color: var(--fg);
  }
  .selects label {
    font-size: 12px;
    color: var(--muted);
    margin-right: 12px;
  }
  select {
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--fg);
    border-radius: 6px;
    padding: 4px 6px;
  }
  main {
    display: grid;
    grid-template-columns: 1fr 300px;
    gap: 16px;
    padding: 16px 20px;
    align-items: start;
  }
  .board-wrap {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  svg {
    width: 100%;
    height: auto;
    background: var(--bg);
    border: 1px solid var(--line);
    border-radius: 12px;
  }
  .caption {
    min-height: 22px;
    font-size: 16px;
    color: #c9d1d9;
    text-align: center;
  }
  .error {
    color: #ffb4b4;
    font-size: 13px;
  }
  .panel {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 12px;
    padding: 14px;
  }
  .panel h3 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    margin: 12px 0 6px;
  }
  .panel h3:first-child {
    margin-top: 0;
  }
  .prov {
    font-size: 13px;
    padding: 7px 9px;
    border-radius: 8px;
  }
  .prov.ok {
    background: var(--green);
    color: #d2f5dd;
  }
  .prov.warn {
    background: var(--warn);
    color: #ffd9a8;
  }
  .dim {
    color: var(--muted);
  }
  .small {
    font-size: 12px;
    margin-top: 5px;
  }
  .kv {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 3px 12px;
    font-size: 13px;
  }
  .kv span {
    color: var(--muted);
  }
  .legacy {
    display: block;
    margin-top: 16px;
    color: #484f58;
    font-size: 12px;
    text-decoration: none;
  }
</style>
