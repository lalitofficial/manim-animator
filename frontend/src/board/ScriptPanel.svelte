<script>
  import { copyPrompt, inputMode, promptMsg, script } from '../lib/workspaceStore.js';
</script>

<div class="script-panel">
  <div class="panel-head">
    <div class="title">Bring your own story</div>
    <button class="m3-icon" on:click={copyPrompt} title="Copy AI prompt" aria-label="Copy AI prompt">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 1H4a2 2 0 0 0-2 2v12h2V3h12V1Zm3 4H8a2 2 0 0 0-2 2v14h13a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2Zm0 14H8V7h11v12Z" /></svg>
    </button>
  </div>

  <div class="field" class:active={$inputMode === 'script'}>
    <textarea
      bind:value={$script}
      spellcheck="false"
      placeholder={'Paste storyboard JSON here, for example {"beats":[{"kind":"show","entity":"sun","concept":"sun","relation":{"at":"top_left"}}]}'}
    ></textarea>
  </div>

  <div class="state" class:on={$inputMode === 'script'}>
    {$inputMode === 'script' ? 'Play will animate this storyboard' : 'Empty — Play teaches the topic above'}
  </div>

  <div class="hint" class:ok={$promptMsg}>{$promptMsg || 'Use this when a stronger model writes the story direction. The board still handles drawing, voice and playback.'}</div>
</div>

<style>
  .script-panel {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px 12px;
    background: var(--surface);
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .title {
    font-size: 13px;
    font-weight: 600;
  }
  /* Filled M3 text field that lights up when it's the active input source. */
  .field {
    flex: 1;
    min-height: 110px;
    display: flex;
    border-radius: var(--r-sm);
    background: var(--surface-3);
    box-shadow: inset 0 -2px 0 transparent;
    transition: background 120ms ease, box-shadow 120ms ease;
  }
  .field:focus-within,
  .field.active {
    background: var(--surface-4);
    box-shadow: inset 0 -2px 0 var(--primary);
  }
  textarea {
    flex: 1;
    width: 100%;
    resize: none;
    background: transparent;
    border: 0;
    color: var(--on-surface);
    border-radius: var(--r-sm);
    padding: 10px 12px;
    font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  }
  textarea::placeholder {
    color: var(--on-surface-variant);
  }
  .state {
    display: inline-flex;
    align-self: flex-start;
    gap: 6px;
    padding: 3px 10px;
    border-radius: var(--r-full);
    background: var(--surface-3);
    color: var(--on-surface-variant);
    font-size: 11px;
    font-weight: 600;
  }
  .state.on {
    background: var(--secondary-container);
    color: var(--on-secondary-container);
  }
  .hint {
    min-height: 28px;
    color: var(--on-surface-variant);
    font-size: 12px;
    line-height: 1.45;
  }
  .hint.ok {
    color: var(--success);
  }
</style>
