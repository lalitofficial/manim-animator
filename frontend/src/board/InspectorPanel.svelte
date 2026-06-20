<script>
  import { sourceIsWeak, spec, status, summary, provenance } from '../lib/workspaceStore.js';

  const shown = (value) => (value == null || value === '' ? '-' : value);
  // Has a run produced anything yet?
  $: hasRun = $provenance || $summary || $spec;
</script>

<div class="inspector">
  <!-- At-a-glance: the few things you actually watch, as status chips. -->
  <div class="glance">
    {#if $status}
      <span class="tag" class:warn={$status.story_provider === 'template'} class:ok={$status.story_provider !== 'template'}
        >brain · {$status.story_provider}{$status.story_model ? ` (${$status.story_model})` : ''}</span
      >
      <span class="tag" class:ok={$status.ollama_reachable} class:warn={!$status.ollama_reachable}
        >ollama · {$status.ollama_reachable ? `up ${$status.ollama_models?.length || 0}` : 'down'}</span
      >
      <span class="tag">drawing · {$status.svg_provider}</span>
    {:else}
      <span class="tag">loading…</span>
    {/if}
  </div>

  {#if $status?.warnings?.length}
    <div class="warns">
      {#each $status.warnings as warning}<div>{warning}</div>{/each}
    </div>
  {/if}

  <!-- This run: provenance + what was drawn, in one compact block. -->
  <div class="run">
    <div class="run-title">This run</div>
    {#if !hasRun}
      <div class="empty">Teach a topic to see how the story and drawings resolved.</div>
    {:else}
      {#if $provenance}
        {#if $provenance.fallback}
          <div class="notice warn"><b>{shown($provenance.requested)}</b> fell back to template — {shown($provenance.reason)}</div>
        {:else if $provenance.used === 'template'}
          <div class="notice warn">Offline template story.</div>
        {:else}
          <div class="notice ok">Story by <b>{shown($provenance.used)}</b></div>
        {/if}
      {/if}
      {#if $summary}
        <div class="tags">
          {#each Object.entries($summary.by_source || {}) as [src, n]}
            <span class="tag" class:warn={sourceIsWeak(src)} class:ok={!sourceIsWeak(src)}>{n} {src}</span>
          {/each}
          {#if $summary.dropped}<span class="tag warn">{$summary.dropped} dropped</span>{/if}
        </div>
        <div class="meta">{$summary.real_drawings} real · {$summary.placeholders} placeholder{$summary.placeholders === 1 ? '' : 's'}</div>
      {/if}
    {/if}
  </div>

  <!-- Director spec: power-user detail, collapsed by default. -->
  {#if $spec}
    <details class="director">
      <summary>Director spec</summary>
      <div class="kv">
        <span>mode</span><b>{$spec.mode}</b>
        <span>style</span><b>{$spec.style}{$spec.cinematic ? ' · cinematic' : ''}</b>
        <span>audience</span><b>{$spec.audience}</b>
        <span>depth</span><b>{$spec.depth}</b>
        <span>tone</span><b>{$spec.tone}</b>
        <span>energy</span><b>{$spec.energy}</b>
        <span>concepts</span><b>{$spec.concept_count}</b>
        <span>pace</span><b>{$spec.draw_speed}x</b>
      </div>
    </details>
  {/if}

  <a class="legacy" href="/legacy">Open legacy board</a>
</div>

<style>
  .inspector {
    height: 100%;
    min-height: 0;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px;
    background: var(--surface);
  }
  .glance,
  .tags {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .tag {
    max-width: 100%;
    overflow-wrap: anywhere;
    font-size: 12px;
    font-weight: 600;
    padding: 4px 11px;
    border-radius: var(--r-full);
    background: var(--surface-4);
    color: var(--on-surface-variant);
  }
  .tag.ok,
  .notice.ok {
    background: var(--success-container);
    color: var(--success);
  }
  .tag.warn,
  .notice.warn {
    background: var(--warn-container);
    color: var(--on-warn);
  }
  .warns {
    border-radius: var(--r-sm);
    background: var(--warn-container);
    color: var(--on-warn);
    padding: 8px 10px;
    font-size: 12px;
    line-height: 1.45;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .run {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
    border-radius: var(--r-md);
    background: var(--surface-1);
  }
  .run-title,
  .director summary {
    color: var(--on-surface-variant);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.09em;
    text-transform: uppercase;
  }
  .notice {
    border-radius: var(--r-sm);
    padding: 7px 10px;
    font-size: 12.5px;
    line-height: 1.4;
  }
  .empty,
  .meta {
    color: var(--on-surface-variant);
  }
  .meta {
    font-size: 12px;
  }
  .empty {
    font-size: 13px;
    line-height: 1.45;
  }
  .director {
    border-radius: var(--r-md);
    background: var(--surface-1);
    padding: 10px 12px;
  }
  .director summary {
    cursor: pointer;
    list-style: none;
  }
  .director summary::-webkit-details-marker {
    display: none;
  }
  .director summary::before {
    content: "▸ ";
    color: var(--on-surface-variant);
  }
  .director[open] summary::before {
    content: "▾ ";
  }
  .kv {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 5px 12px;
    font-size: 13px;
    margin-top: 10px;
  }
  .kv span {
    color: var(--on-surface-variant);
  }
  .kv b {
    overflow-wrap: anywhere;
  }
  .legacy {
    margin-top: auto;
    color: var(--on-surface-variant);
    opacity: 0.7;
    font-size: 12px;
    text-decoration: none;
  }
  .legacy:hover {
    opacity: 1;
    color: var(--fg);
  }
</style>
