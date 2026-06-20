<script>
  import { onDestroy } from 'svelte';
  import { previewUrl, publishAssets, unpublishAssets } from '../lib/api.js';
  import { selected, bumpData } from '../lib/assetStore.js';

  let a = null;
  let busy = false;
  let msg = '';
  const unsub = selected.subscribe((v) => {
    a = v;
    msg = '';
  });
  onDestroy(unsub);

  $: isCandidate = a && a.kind === 'candidate';
  $: isPublished = a && a.status === 'published';

  async function publish() {
    busy = true;
    try {
      await publishAssets([a.concept]);
      a = { ...a, status: 'published', source: 'published', bundle_enabled: true };
      selected.set(a);
      msg = 'Published — the engine can draw it now.';
      bumpData();
    } catch (e) {
      msg = e.message;
    } finally {
      busy = false;
    }
  }
  async function unpublish() {
    busy = true;
    try {
      await unpublishAssets([a.concept]);
      a = { ...a, status: 'candidate', source: 'candidate', bundle_enabled: false };
      selected.set(a);
      msg = 'Unpublished.';
      bumpData();
    } catch (e) {
      msg = e.message;
    } finally {
      busy = false;
    }
  }

  const META = [
    ['bundle', (x) => x.bundle],
    ['kind', (x) => x.kind],
    ['style', (x) => x.style],
    ['source', (x) => x.source],
    ['license', (x) => x.license],
    ['origin', (x) => x.origin],
    ['complexity', (x) => `${x.complexity} strokes`],
    ['family', (x) => x.family || '—'],
  ];
</script>

<div class="preview">
  {#if !a}
    <div class="empty">Select an asset to preview</div>
  {:else}
    <div class="stage">
      <img alt={a.concept} src={previewUrl(a.concept)} />
    </div>
    <div class="meta">
      <h3>{a.title || a.concept}</h3>
      {#if isCandidate}
        <div class="pubrow">
          {#if isPublished}
            <span class="pubbadge">✓ published · engine-drawable</span>
            <button class="demote" on:click={unpublish} disabled={busy}>Unpublish</button>
          {:else}
            <button class="promote" on:click={publish} disabled={busy || !a.complexity}>
              Publish — make engine-drawable
            </button>
          {/if}
        </div>
        {#if msg}<div class="pubmsg">{msg}</div>{/if}
      {/if}
      <div class="kv">
        {#each META as [label, get]}
          <div class="row"><span class="k">{label}</span><span class="v">{get(a)}</span></div>
        {/each}
      </div>
      {#if a.aliases && a.aliases.length}
        <div class="block">
          <div class="label">aliases</div>
          <div class="chips">{#each a.aliases as al}<span class="chip">{al}</span>{/each}</div>
        </div>
      {/if}
      {#if a.also_in && a.also_in.length}
        <div class="block">
          <div class="label">also resolves in</div>
          <div class="chips">{#each a.also_in as r}<span class="chip warn">{r}</span>{/each}</div>
          <div class="hint">A concept living in multiple rungs is a shadow worth reconciling.</div>
        </div>
      {/if}
      {#if !a.bundle_enabled}
        <div class="off-note">Its bundle <b>{a.bundle}</b> is disabled — currently resolves to the box backstop.</div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .preview {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .empty {
    margin: auto;
    color: var(--muted);
  }
  .stage {
    flex: 1;
    min-height: 160px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f6f8fa;
    border-bottom: 1px solid var(--line);
    overflow: hidden;
  }
  .stage img {
    max-width: 92%;
    max-height: 92%;
  }
  .meta {
    padding: 12px 14px;
    overflow: auto;
  }
  h3 {
    margin: 0 0 10px;
    font-size: 17px;
  }
  .pubrow {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 10px;
  }
  .promote {
    background: var(--green, #1f6f3f);
    color: #d2f5dd;
    border: 0;
    border-radius: 7px;
    padding: 9px 14px;
    font-weight: 700;
    cursor: pointer;
  }
  .promote:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .demote {
    background: #21262d;
    color: var(--fg);
    border: 1px solid var(--line);
    border-radius: 7px;
    padding: 7px 12px;
    cursor: pointer;
  }
  .pubbadge {
    color: #4ac26b;
    font-weight: 700;
    font-size: 13px;
  }
  .pubmsg {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 10px;
  }
  .kv {
    display: grid;
    gap: 2px;
  }
  .row {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    border-bottom: 1px solid var(--line2);
    font-size: 13px;
  }
  .k {
    color: var(--muted);
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.04em;
  }
  .block {
    margin-top: 12px;
  }
  .label {
    color: var(--muted);
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.04em;
    margin-bottom: 5px;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
  }
  .chip {
    font-size: 12px;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--line2);
    color: #c9d1d9;
  }
  .chip.warn {
    background: #d2992222;
    color: #ffd8a8;
  }
  .hint {
    color: var(--muted);
    font-size: 12px;
    margin-top: 6px;
  }
  .off-note {
    margin-top: 12px;
    padding: 8px 10px;
    border-left: 3px solid #d29922;
    background: #1c1a12;
    color: #ffd9a8;
    font-size: 13px;
    border-radius: 4px;
  }
</style>
