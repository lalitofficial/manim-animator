<script>
  import { onDestroy, onMount } from 'svelte';
  import { caption, error, go, hasRun, playing, runLabel, setBoardElement, topic } from '../lib/workspaceStore.js';

  let svgEl;

  onMount(() => {
    setBoardElement(svgEl);
  });

  onDestroy(() => {
    setBoardElement(null);
  });
</script>

<div class="board-panel">
  <div class="panel-bar">
    <div class="state">{$playing ? $runLabel : 'Ready'}</div>
    <div class="pill" class:hot={$playing}>{$playing ? 'running' : 'idle'}</div>
  </div>

  <div class="stage">
    <svg
      bind:this={svgEl}
      viewBox="0 0 896 512"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Animated lesson board"
    ></svg>

    {#if !$playing && !$hasRun}
      <div class="empty">
        <div class="glyph">
          <svg viewBox="0 0 24 24" aria-hidden="true"
            ><path
              d="M4 5h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-6l-2 3-2-3H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1Zm3 4v2h10V9H7Zm0 4v2h7v-2H7Z"
            /></svg
          >
        </div>
        <div class="headline">Your board is ready</div>
        <div class="sub">Pick a mode on the left, then watch the lesson draw itself.</div>
        <button class="cta" on:click={go}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
          Teach “{$topic || 'a topic'}”
        </button>
      </div>
    {/if}
  </div>

  <div class="caption" class:empty={!$caption}>{$caption || 'Narration appears here while the board plays.'}</div>
  {#if $error}<div class="error">{$error}</div>{/if}
</div>

<style>
  .board-panel {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
    background: var(--bg);
  }
  .panel-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .state {
    color: var(--fg);
    font-size: 13px;
    font-weight: 600;
  }
  .pill {
    flex: 0 0 auto;
    border-radius: var(--r-full);
    color: var(--on-surface-variant);
    background: var(--surface-4);
    padding: 4px 11px;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .pill.hot {
    background: var(--success-container);
    color: var(--success);
  }
  .stage {
    position: relative;
    min-height: 0;
    flex: 1;
    display: grid;
    place-items: center;
    overflow: hidden;
    border-radius: var(--r-md);
    background: radial-gradient(120% 120% at 50% 35%, #0d1219, #070a0e 70%);
  }
  svg {
    width: 100%;
    height: 100%;
    min-height: 220px;
    display: block;
  }

  /* Inviting empty state instead of a dead void. */
  .empty {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 10px;
    text-align: center;
    padding: 24px;
    pointer-events: none;
  }
  .glyph {
    position: relative;
    width: 64px;
    height: 64px;
    display: grid;
    place-items: center;
    border-radius: var(--r-lg);
    background: var(--surface-3);
    margin-bottom: 4px;
    animation: glyph-float 4s ease-in-out infinite;
  }
  /* soft pulsing halo behind the glyph */
  .glyph::before {
    content: "";
    position: absolute;
    inset: -10px;
    border-radius: inherit;
    background: radial-gradient(closest-side, rgba(168, 199, 250, 0.28), transparent 75%);
    animation: glyph-halo 4s ease-in-out infinite;
  }
  .glyph svg {
    width: 34px;
    height: 34px;
    min-height: 0;
    fill: var(--primary);
  }
  @keyframes glyph-float {
    0%,
    100% {
      transform: translateY(0);
    }
    50% {
      transform: translateY(-6px);
    }
  }
  @keyframes glyph-halo {
    0%,
    100% {
      opacity: 0.55;
      transform: scale(0.96);
    }
    50% {
      opacity: 1;
      transform: scale(1.12);
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .glyph,
    .glyph::before {
      animation: none;
    }
  }
  .headline {
    font-size: 17px;
    font-weight: 600;
    color: var(--on-surface);
  }
  .sub {
    font-size: 13px;
    color: var(--on-surface-variant);
    max-width: 320px;
    line-height: 1.45;
  }
  .cta {
    pointer-events: auto;
    margin-top: 8px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border: 0;
    border-radius: var(--r-full);
    background: var(--primary);
    color: var(--on-primary);
    padding: 11px 20px 11px 16px;
    font-size: 14px;
    font-weight: 600;
    box-shadow: var(--elev-2);
    transition: filter 120ms ease, transform 90ms ease;
  }
  .cta:hover {
    filter: brightness(1.05);
  }
  .cta:active {
    transform: scale(0.97);
  }
  .cta svg {
    width: 20px;
    height: 20px;
    min-height: 0;
    fill: currentColor;
  }
  .caption {
    min-height: 34px;
    border-radius: var(--r-sm);
    padding: 8px 12px;
    color: var(--on-surface);
    /* Video-grade narration: bigger + bolder so it reads as a lesson subtitle, not UI chrome. */
    font-size: 20px;
    font-weight: 600;
    line-height: 1.4;
    text-align: center;
    background: var(--surface-2);
  }
  .caption.empty {
    color: var(--on-surface-variant);
  }
  .error {
    color: var(--error);
    border-radius: var(--r-sm);
    background: var(--error-container);
    padding: 8px 12px;
    font-size: 13px;
  }
</style>
