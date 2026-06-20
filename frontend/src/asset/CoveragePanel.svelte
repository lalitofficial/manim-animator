<script>
  import { onMount, onDestroy } from 'svelte';
  import { assetCoverage } from '../lib/api.js';
  import { dataVersion, selected } from '../lib/assetStore.js';

  let cov = null;
  let error = '';
  let loading = false;

  const SEGS = ['composed', 'catalog', 'sketch', 'box'];

  async function load() {
    loading = true;
    try {
      cov = await assetCoverage();
    } catch (e) {
      error = e.message;
    } finally {
      loading = false;
    }
  }

  let last = 0;
  const unsub = dataVersion.subscribe((v) => {
    if (v !== last) {
      last = v;
      load();
    }
  });

  function pct(n) {
    return cov && cov.total ? (n / cov.total) * 100 : 0;
  }
  function inspect(concept) {
    selected.set({ concept, bundle: '—', kind: 'box', style: 'box', source: 'box', license: '—', origin: '—', complexity: 0, aliases: [], also_in: [], bundle_enabled: true });
  }

  onMount(load);
  onDestroy(unsub);
</script>

<div class="coverage">
  <div class="head">
    <h3>Coverage</h3>
    <button class="refresh" on:click={load} disabled={loading}>{loading ? '…' : '↻'}</button>
  </div>
  {#if error}<div class="err">{error}</div>{/if}
  {#if cov}
    <div class="body">
      <div class="summary">
        Probed <b>{cov.total}</b> concepts · composed
        <b class="good">{(cov.composed_rate * 100).toFixed(0)}%</b> · fallback
        <b class="bad">{(cov.fallback_rate * 100).toFixed(0)}%</b>
      </div>
      <div class="bar">
        {#each SEGS as s}
          {#if cov.buckets[s]}
            <span class="seg {s}" style={`width:${pct(cov.buckets[s])}%`} title={`${s}: ${cov.buckets[s]}`} />
          {/if}
        {/each}
      </div>
      <div class="legend">
        {#each SEGS as s}
          <span><i class="dot {s}" />{s} {cov.buckets[s] || 0}</span>
        {/each}
      </div>

      <h4>Per-bundle</h4>
      <table>
        <tr><th>bundle</th><th>total</th><th>composed</th><th>boxed</th></tr>
        {#each Object.entries(cov.by_bundle).sort((a, b) => b[1].total - a[1].total) as [id, v]}
          <tr><td>{id}</td><td>{v.total}</td><td>{v.composed}</td><td class:flag={v.box}>{v.box}</td></tr>
        {/each}
      </table>

      <h4>Boxed concepts (no real asset)</h4>
      <div class="chips">
        {#if cov.boxed.length}
          {#each cov.boxed as c}
            <button class="chip" on:click={() => inspect(c)}>{c}</button>
          {/each}
        {:else}
          <span class="muted">full coverage on the probe set</span>
        {/if}
      </div>

      <h4>Frequently-requested missing nouns</h4>
      {#if cov.missing_nouns.length}
        <table>
          <tr><th>noun</th><th>requests</th></tr>
          {#each cov.missing_nouns as m}
            <tr><td>{m.concept}</td><td>{m.requests}</td></tr>
          {/each}
        </table>
      {:else}
        <span class="muted">no logged requests yet — the work queue is empty.</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .coverage {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 10px 5px;
  }
  h3 {
    margin: 0;
    font-size: 13px;
  }
  h4 {
    margin: 12px 0 5px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .refresh {
    width: 30px;
    height: 30px;
    display: grid;
    place-items: center;
    background: var(--field);
    border: 1px solid var(--line);
    color: var(--fg);
    border-radius: 6px;
    padding: 0;
  }
  .err {
    color: #ff9492;
    padding: 0 14px;
  }
  .body {
    overflow: auto;
    padding: 5px 10px 12px;
  }
  .summary {
    font-size: 13px;
  }
  .good {
    color: #4ac26b;
  }
  .bad {
    color: #ff7b72;
  }
  .bar {
    height: 18px;
    background: var(--bg);
    border-radius: 5px;
    overflow: hidden;
    display: flex;
    margin: 10px 0 6px;
  }
  .seg {
    height: 100%;
  }
  .seg.composed,
  .dot.composed {
    background: #2ea043;
  }
  .seg.catalog,
  .dot.catalog {
    background: #d29922;
  }
  .seg.sketch,
  .dot.sketch {
    background: #8957e5;
  }
  .seg.box,
  .dot.box {
    background: #da3633;
  }
  .legend {
    display: flex;
    gap: 10px;
    color: var(--muted);
    font-size: 12px;
  }
  .legend span {
    display: flex;
    align-items: center;
    gap: 5px;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    display: inline-block;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  th,
  td {
    text-align: left;
    padding: 4px 6px;
    border-bottom: 1px solid var(--line2);
  }
  td.flag {
    color: #ff7b72;
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
    background: #da363322;
    color: #ffb3ad;
    border: 0;
    cursor: pointer;
  }
  .muted {
    color: var(--muted);
    font-size: 13px;
  }
</style>
