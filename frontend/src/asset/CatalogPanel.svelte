<script>
  import { onMount, onDestroy } from 'svelte';
  import { assetCatalog, assetBundles, previewUrl } from '../lib/api.js';
  import { selected, stats, dataVersion } from '../lib/assetStore.js';

  let q = '';
  let bundle = '';
  let kind = '';
  let style = '';
  let items = [];
  let total = 0;
  let bundles = [];
  let loading = false;
  let error = '';
  let sel = null;
  const limit = 200;

  const KINDS = ['', 'core', 'cartoon', 'family', 'mono', 'catalog', 'override', 'candidate'];
  const STYLES = ['', 'colored', 'mono', 'line', 'candidate'];

  const unsub = selected.subscribe((v) => (sel = v));
  let lastVersion = 0;
  const unsubV = dataVersion.subscribe((v) => {
    if (v !== lastVersion) {
      lastVersion = v;
      load();
    }
  });

  async function load() {
    loading = true;
    error = '';
    try {
      const data = await assetCatalog({ q, bundle, kind, style, limit });
      items = data.items;
      total = data.total;
      stats.set(data.stats);
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  let debounce;
  function onSearch() {
    clearTimeout(debounce);
    debounce = setTimeout(load, 200);
  }

  function pick(a) {
    selected.set(a);
  }

  onMount(async () => {
    try {
      bundles = (await assetBundles()).bundles;
    } catch {
      bundles = [];
    }
    load();
  });
  onDestroy(() => {
    unsub();
    unsubV();
  });
</script>

<div class="catalog">
  <div class="bar">
    <input placeholder="Search concepts / aliases…" bind:value={q} on:input={onSearch} />
    <select bind:value={bundle} on:change={load}>
      <option value="">all bundles</option>
      {#each bundles as b}
        <option value={b.id}>{b.name}</option>
      {/each}
    </select>
    <select bind:value={kind} on:change={load}>
      {#each KINDS as k}
        <option value={k}>{k || 'all kinds'}</option>
      {/each}
    </select>
    <select bind:value={style} on:change={load}>
      {#each STYLES as s}
        <option value={s}>{s || 'all styles'}</option>
      {/each}
    </select>
    <span class="count">{total}{loading ? ' …' : ''}</span>
  </div>

  {#if error}
    <div class="err">{error}</div>
  {/if}

  <div class="grid">
    {#each items as a (a.concept)}
      <button
        class="card"
        class:active={sel && sel.concept === a.concept}
        class:off={!a.bundle_enabled}
        on:click={() => pick(a)}
        title={`${a.concept} · ${a.bundle} · ${a.license}`}
      >
        <div class="thumb">
          <img loading="lazy" alt={a.concept} src={previewUrl(a.concept)} />
        </div>
        <div class="name">{a.title || a.concept}</div>
        <div class="tags">
          <span class="tag k-{a.kind}">{a.kind}</span>
          {#if !a.bundle_enabled}<span class="tag off">off</span>{/if}
        </div>
      </button>
    {/each}
  </div>
</div>

<style>
  .catalog {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .bar {
    display: flex;
    gap: 6px;
    padding: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .bar input {
    flex: 1;
    min-width: 160px;
    background: var(--surface-3);
    border: 1px solid transparent;
    color: var(--fg);
    border-radius: var(--r-full);
    padding: 9px 14px;
    font-size: 13px;
    transition: background 120ms ease, box-shadow 120ms ease;
  }
  .bar input:focus {
    background: var(--surface-4);
    box-shadow: 0 0 0 2px var(--primary);
  }
  .bar select {
    background: var(--surface-3);
    border: 1px solid transparent;
    color: var(--fg);
    border-radius: var(--r-sm);
    padding: 8px 9px;
    font-size: 13px;
  }
  .bar select:focus {
    box-shadow: inset 0 -2px 0 var(--primary);
  }
  .count {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    font-size: 13px;
  }
  .err {
    color: #ff9492;
    padding: 8px 10px;
  }
  .grid {
    flex: 1;
    overflow: auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 8px;
    padding: 8px;
    align-content: start;
  }
  .card {
    background: var(--surface-2);
    border: 1px solid transparent;
    border-radius: var(--r-md);
    padding: 6px;
    cursor: pointer;
    text-align: center;
    color: var(--fg);
    transition: background 0.12s, box-shadow 0.12s, transform 0.06s;
  }
  .card:hover {
    background: var(--surface-3);
    transform: translateY(-1px);
  }
  .card.active {
    box-shadow: 0 0 0 2px var(--primary);
  }
  .card.off {
    opacity: 0.42;
  }
  .thumb {
    background: #f6f8fa;
    border-radius: 6px;
    height: 70px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .thumb img {
    max-width: 100%;
    max-height: 100%;
  }
  .name {
    font-size: 12px;
    font-weight: 600;
    margin-top: 5px;
    word-break: break-word;
  }
  .tags {
    display: flex;
    gap: 3px;
    justify-content: center;
    margin-top: 4px;
    flex-wrap: wrap;
  }
  .tag {
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 999px;
    background: var(--line2);
    color: #c9d1d9;
  }
  .tag.k-family,
  .tag.k-core,
  .tag.k-cartoon,
  .tag.k-override {
    background: #1f6feb22;
    color: #9ecbff;
  }
  .tag.k-catalog,
  .tag.k-mono {
    background: #d2992222;
    color: #ffd8a8;
  }
  .tag.k-candidate,
  .tag.off {
    background: #da363322;
    color: #ffb3ad;
  }
</style>
