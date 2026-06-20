<script>
  import {
    AUDIENCES,
    DEPTHS,
    ENERGIES,
    MODES,
    STYLES,
    TONES,
    audience,
    depth,
    energy,
    go,
    inputMode,
    mode,
    playing,
    stop,
    style,
    tone,
    topic,
  } from '../lib/workspaceStore.js';

  // Mode is the primary choice — give each one an icon card.
  const MODE_META = {
    learn: {
      label: 'Learn',
      d: 'M12 3 1 9l4 2.18v6L12 21l7-3.82v-6l2-1.09V17h2V9L12 3zM5 12.27 12 16l7-3.73v3.72L12 19.4l-7-3.41v-3.72z',
    },
    story: { label: 'Story', d: 'M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm6 3v8l6-4-6-4z' },
    draw: {
      label: 'Draw',
      d: 'M7 14c-1.66 0-3 1.34-3 3 0 1.31-1.16 2-2 2 .92 1.22 2.49 2 4 2 2.21 0 4-1.79 4-4 0-1.66-1.34-3-3-3zm13.71-9.37-1.34-1.34a.996.996 0 0 0-1.41 0L9 12.25 11.75 15l8.96-8.96a.996.996 0 0 0 0-1.41z',
    },
    explain: {
      label: 'Explain',
      d: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
    },
  };

  // One tap sets the whole "vibe" — 5 interacting knobs collapse into a preset.
  // The active preset is DERIVED from current values, so tweaking any knob below
  // auto-deselects it. No extra state, no "custom" mode to manage.
  const PRESETS = [
    { name: 'Kids', audience: 'child', style: 'cartoon', depth: 'brief', tone: 'playful', energy: 'lively' },
    { name: 'Classroom', audience: 'general', style: 'cartoon', depth: 'normal', tone: 'neutral', energy: 'normal' },
    { name: 'Storyteller', audience: 'general', style: 'cartoon', depth: 'normal', tone: 'playful', energy: 'lively' },
    { name: 'Expert', audience: 'expert', style: 'whiteboard', depth: 'deep', tone: 'formal', energy: 'calm' },
  ];
  const applyPreset = (p) => {
    $audience = p.audience;
    $style = p.style;
    $depth = p.depth;
    $tone = p.tone;
    $energy = p.energy;
  };
  $: activePreset = PRESETS.find(
    (p) =>
      p.audience === $audience && p.style === $style && p.depth === $depth && p.tone === $tone && p.energy === $energy,
  )?.name;

  // Smaller fixed sets → Material segmented buttons. No dropdowns, no nested boxes.
  const pairs = (list) => list.map((v) => (Array.isArray(v) ? v : [v, v]));
  $: rows = [
    { label: 'Style', value: $style, set: (v) => ($style = v), options: pairs(STYLES) },
    { label: 'For', value: $audience, set: (v) => ($audience = v), options: pairs(AUDIENCES) },
    { label: 'Depth', value: $depth, set: (v) => ($depth = v), options: pairs(DEPTHS) },
    { label: 'Tone', value: $tone, set: (v) => ($tone = v), options: pairs(TONES) },
    { label: 'Energy', value: $energy, set: (v) => ($energy = v), options: pairs(ENERGIES) },
  ];
</script>

<div class="control-panel">
  <div class="m3-field search" class:hot={$playing}>
    <svg class="lead" viewBox="0 0 24 24" aria-hidden="true"
      ><path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z" /></svg
    >
    <input
      bind:value={$topic}
      placeholder="What should the board teach?"
      on:keydown={(e) => e.key === 'Enter' && go()}
    />
    {#if $playing}
      <button class="m3-fab danger" on:click={stop} title="Stop playback" aria-label="Stop playback">
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5" /></svg>
      </button>
    {:else}
      <button
        class="m3-fab"
        on:click={go}
        title={$inputMode === 'script' ? 'Animate storyboard' : 'Teach topic'}
        aria-label={$inputMode === 'script' ? 'Animate storyboard' : 'Teach topic'}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
      </button>
    {/if}
  </div>

  <div class="modes">
    {#each MODES as m}
      <button class="mode" class:sel={$mode === m} on:click={() => ($mode = m)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_META[m].d} /></svg>
        <span>{MODE_META[m].label}</span>
      </button>
    {/each}
  </div>

  <div class="presets">
    {#each PRESETS as p}
      <button class="m3-chip" class:sel={activePreset === p.name} on:click={() => applyPreset(p)}>{p.name}</button>
    {/each}
  </div>

  <div class="group">
    <div class="group-title">
      Fine-tune{#if !activePreset}<span class="custom"> · custom</span>{/if}
    </div>
    {#each rows as row}
      <div class="row">
        <span class="key">{row.label}</span>
        <div class="m3-seg">
          {#each row.options as [value, text]}
            <button class:sel={row.value === value} on:click={() => row.set(value)}>{text}</button>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .control-panel {
    height: 100%;
    min-height: 0;
    overflow: auto;
    padding: 12px 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    background: var(--surface);
  }
  .search {
    padding-right: 5px;
    min-height: 48px;
    border-radius: var(--r-md);
  }
  .search.hot {
    box-shadow: inset 0 -2px 0 var(--success);
  }
  .search input {
    font-size: 15px;
  }

  /* Mode — the primary choice, as icon cards. */
  .modes {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
  }
  .mode {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    padding: 10px 4px 8px;
    border: 1px solid transparent;
    border-radius: var(--r-md);
    background: var(--surface-2);
    color: var(--on-surface-variant);
    transition: background 120ms ease, color 120ms ease, box-shadow 120ms ease;
  }
  .mode:hover:not(.sel) {
    background: var(--surface-3);
    color: var(--on-surface);
  }
  .mode svg {
    width: 22px;
    height: 22px;
    fill: currentColor;
  }
  .mode span {
    font-size: 11.5px;
    font-weight: 600;
  }
  .mode.sel {
    background: var(--secondary-container);
    color: var(--on-secondary-container);
    box-shadow: inset 0 0 0 1px var(--primary);
  }
  .mode.sel svg {
    fill: var(--primary);
  }

  /* Presets — collapse the 5 delivery knobs into one tap. */
  .presets {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .presets :global(.m3-chip) {
    flex: 1 1 auto;
    padding: 6px 10px;
  }

  /* The rest — grouped so it reads as one cohesive block, not floating toggles. */
  .group {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px 12px 14px;
    border-radius: var(--r-md);
    background: var(--surface-1);
  }
  .group-title {
    color: var(--on-surface-variant);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
    margin-bottom: 2px;
  }
  .custom {
    color: var(--primary);
    font-weight: 600;
  }
  .row {
    display: grid;
    grid-template-columns: 46px minmax(0, 1fr);
    align-items: center;
    gap: 10px;
  }
  .key {
    color: var(--on-surface-variant);
    font-size: 11px;
    font-weight: 600;
  }
  .row :global(.m3-seg) {
    width: 100%;
  }

  @media (max-width: 460px) {
    .row {
      grid-template-columns: 1fr;
      gap: 4px;
    }
  }
</style>
