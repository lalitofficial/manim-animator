<script>
  import { onMount, onDestroy } from 'svelte';
  import { assetBundles, toggleBundle } from '../lib/api.js';
  import { stats, bumpData } from '../lib/assetStore.js';

  let bundles = [];
  let counts = {};
  let error = '';
  let busy = '';

  const unsub = stats.subscribe((s) => (counts = (s && s.by_bundle) || {}));

  async function load() {
    try {
      bundles = (await assetBundles()).bundles;
    } catch (e) {
      error = e.message;
    }
  }

  async function flip(b) {
    if (b.locked) return;
    busy = b.id;
    try {
      const res = await toggleBundle(b.id, !b.enabled);
      if (res.ok) {
        b.enabled = res.enabled;
        bundles = bundles;
        bumpData(); // ask Catalog + Coverage to reload
      } else {
        error = res.error;
      }
    } catch (e) {
      error = e.message;
    } finally {
      busy = '';
    }
  }

  onMount(load);
  onDestroy(unsub);
</script>

<div class="bundles">
  <div class="head">
    <h3>Bundles</h3>
    <span class="hint">Toggle which groups runtime resolves. Core is always on.</span>
  </div>
  {#if error}<div class="err">{error}</div>{/if}
  <div class="list">
    {#each bundles as b (b.id)}
      <div class="row" class:locked={b.locked}>
        <div class="info">
          <div class="name">{b.name} <span class="n">{counts[b.id] || 0}</span></div>
          <div class="sub">{b.category} · priority {b.priority}</div>
        </div>
        <button
          class="switch"
          class:on={b.enabled}
          disabled={b.locked || busy === b.id}
          on:click={() => flip(b)}
          aria-label={b.enabled ? 'disable' : 'enable'}
        >
          <span class="knob" />
        </button>
      </div>
    {/each}
  </div>
</div>

<style>
  .bundles {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .head {
    padding: 8px 10px 6px;
  }
  h3 {
    margin: 0 0 4px;
    font-size: 13px;
  }
  .hint {
    color: var(--muted);
    font-size: 12px;
  }
  .err {
    color: #ff9492;
    padding: 0 14px 8px;
  }
  .list {
    flex: 1;
    overflow: auto;
    padding: 0 6px 6px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 7px 6px;
    border-bottom: 1px solid var(--line2);
  }
  .name {
    font-weight: 600;
    font-size: 13px;
  }
  .n {
    color: var(--muted);
    font-size: 12px;
    font-weight: 400;
  }
  .sub {
    color: var(--muted);
    font-size: 11px;
  }
  .switch {
    position: relative;
    width: 34px;
    height: 20px;
    border-radius: 999px;
    border: 0;
    background: #444c56;
    cursor: pointer;
    flex: 0 0 auto;
    padding: 0;
    transition: background 0.12s;
  }
  .switch.on {
    background: var(--green);
  }
  .switch:disabled {
    opacity: 0.55;
    cursor: default;
  }
  .knob {
    position: absolute;
    top: 3px;
    left: 3px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #fff;
    transition: transform 0.12s;
  }
  .switch.on .knob {
    transform: translateX(14px);
  }
</style>
