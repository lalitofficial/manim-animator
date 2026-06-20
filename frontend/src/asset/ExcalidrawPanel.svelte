<script>
  import {
    excalIndex,
    excalLibrary,
    excalItem,
    excalImportLibrary,
    excalSync,
    excalSyncStatus,
  } from '../lib/api.js';
  import { bumpData } from '../lib/assetStore.js';

  let libraries = [];
  let query = '';
  let loaded = false;
  let loading = '';
  let error = '';
  let sync = null; // {running, done, total, name, store}

  let active = null; // selected library
  let items = [];
  let svg = '';
  let pickedItem = -1;
  let importMsg = '';

  $: q = query.trim().toLowerCase();
  $: shown = !q
    ? libraries
    : libraries.filter(
        (l) =>
          l.name.toLowerCase().includes(q) ||
          l.authors.join(' ').toLowerCase().includes(q) ||
          l.item_names.some((n) => n.toLowerCase().includes(q)),
      );

  async function load() {
    loading = 'index';
    error = '';
    try {
      libraries = (await excalIndex(false)).libraries || [];
      loaded = true;
    } catch (e) {
      error = `Couldn't reach the Excalidraw catalog: ${e.message}`;
    } finally {
      loading = '';
    }
  }

  async function openLib(lib) {
    active = lib;
    items = [];
    svg = '';
    pickedItem = -1;
    importMsg = '';
    loading = 'lib';
    try {
      items = (await excalLibrary(lib.path)).items || [];
    } catch (e) {
      error = e.message;
    } finally {
      loading = '';
    }
  }

  async function preview(i) {
    pickedItem = i;
    importMsg = '';
    loading = 'item';
    try {
      svg = (await excalItem(active.path, i)).svg || '';
    } catch (e) {
      error = e.message;
    } finally {
      loading = '';
    }
  }

  async function importSet(lib) {
    importMsg = `importing all of "${lib.name}"…`;
    try {
      const res = await excalImportLibrary(lib.path);
      importMsg = `✅ imported ${res.renderable}/${res.items} from "${lib.name}" — search them in the Catalog`;
      bumpData();
    } catch (e) {
      importMsg = '✗ ' + e.message;
    }
  }

  let syncTimer;
  async function startSync() {
    error = '';
    try {
      await excalSync(0);
      poll();
    } catch (e) {
      error = e.message;
    }
  }
  async function poll() {
    clearTimeout(syncTimer);
    sync = await excalSyncStatus();
    if (sync.running) {
      syncTimer = setTimeout(poll, 1200);
    } else {
      bumpData(); // sync done → refresh the Catalog
    }
  }

  // highlight which item names matched the search, per library
  function matched(lib) {
    if (!q) return [];
    return lib.item_names.filter((n) => n.toLowerCase().includes(q)).slice(0, 5);
  }
</script>

<div class="ex">
  <div class="note">
    <b>MIT candidate sets</b> — references for review, not trusted cartoon foreground. Import
    crops an item to board size and saves it as a candidate; publishing into the runtime ladder is
    a later, gated step.
  </div>

  <div class="syncbar">
    <button class="sync" on:click={startSync} disabled={sync && sync.running}>
      {sync && sync.running ? 'Syncing…' : 'Sync ALL sets → Catalog'}
    </button>
    {#if sync}
      {#if sync.running}
        <span class="prog">{sync.done}/{sync.total} · {sync.name}</span>
      {:else if sync.store}
        <span class="prog">{sync.store.count} icons imported ({sync.store.packs} sets) — search them in the Catalog</span>
      {/if}
    {/if}
  </div>

  {#if !loaded}
    <button class="load" on:click={load} disabled={loading === 'index'}>
      {loading === 'index' ? 'Loading catalog…' : 'Browse library catalog'}
    </button>
    {#if error}<div class="err">{error}</div>{/if}
  {:else}
    <div class="bar">
      <input placeholder="Search all sets & items — azure, cloud, aws, database…" bind:value={query} />
      <span class="count">{shown.length}/{libraries.length} sets</span>
    </div>
    {#if error}<div class="err">{error}</div>{/if}

    <div class="split">
      <div class="libs">
        {#each shown as lib (lib.id)}
          <button class="lib" class:active={active && active.id === lib.id} on:click={() => openLib(lib)}>
            <div class="thumb">
              {#if lib.preview}
                <img loading="lazy" alt={lib.name} src={lib.preview} />
              {:else}
                <span class="noimg">no preview</span>
              {/if}
            </div>
            <div class="lname">{lib.name}</div>
            <div class="lmeta">{lib.authors.join(', ') || '—'} · {lib.item_count} items</div>
            {#if matched(lib).length}
              <div class="hits">{#each matched(lib) as m}<span class="hit">{m}</span>{/each}</div>
            {/if}
          </button>
        {/each}
      </div>

      {#if active}
        <div class="detail">
          <div class="dhead">
            <div>
              <b>{active.name}</b>
              <div class="lmeta">{active.authors.join(', ')} · MIT</div>
            </div>
            <button class="setimp" on:click={() => importSet(active)}>Import set ({active.item_count})</button>
          </div>
          <div class="dbody">
            <div class="itemcol">
              <div class="lbl">Items {loading === 'lib' ? '…' : ''}</div>
              <div class="ilist">
                {#each items as it, i}
                  <button class="iname" class:active={pickedItem === i} on:click={() => preview(i)}>
                    {it.name}<span class="sz">{it.elements} el</span>
                  </button>
                {/each}
              </div>
            </div>
            <div class="prevcol">
              <div class="lbl">Preview {loading === 'item' ? '…' : ''}</div>
              <div class="stage">{#if svg}{@html svg}{:else}<span class="muted">Pick an item</span>{/if}</div>
              {#if importMsg}<div class="impmsg">{importMsg}</div>{/if}
            </div>
          </div>
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .ex {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: 10px;
  }
  .note {
    border-left: 3px solid #d29922;
    background: #1c1a12;
    color: #ffd9a8;
    padding: 8px 10px;
    font-size: 12px;
    border-radius: 4px;
    margin-bottom: 10px;
  }
  .err {
    color: #ff9492;
    padding: 6px 0;
    font-size: 13px;
  }
  .load {
    align-self: start;
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 7px;
    padding: 10px 18px;
    font-weight: 600;
  }
  .bar {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 10px;
  }
  .bar input {
    flex: 1;
    background: var(--surface-3);
    border: 1px solid transparent;
    color: var(--fg);
    border-radius: var(--r-full);
    padding: 9px 14px;
    transition: background 120ms ease, box-shadow 120ms ease;
  }
  .bar input:focus {
    background: var(--surface-4);
    box-shadow: 0 0 0 2px var(--primary);
  }
  .count {
    color: var(--muted);
    font-size: 12px;
    white-space: nowrap;
  }
  .split {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    min-height: 0;
  }
  .libs {
    overflow: auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 10px;
    align-content: start;
    padding-right: 4px;
  }
  .lib {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 9px;
    padding: 7px;
    text-align: left;
    color: var(--fg);
    cursor: pointer;
  }
  .lib:hover {
    border-color: var(--accent);
  }
  .lib.active {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .thumb {
    height: 96px;
    background: #f6f8fa;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .thumb img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .noimg {
    color: #999;
    font-size: 11px;
  }
  .lname {
    font-weight: 600;
    font-size: 13px;
    margin-top: 6px;
  }
  .lmeta {
    color: var(--muted);
    font-size: 11px;
  }
  .hits {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    margin-top: 4px;
  }
  .hit {
    font-size: 10px;
    background: #1f6feb22;
    color: #9ecbff;
    border-radius: 999px;
    padding: 1px 6px;
  }
  .detail {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 9px;
    display: flex;
    flex-direction: column;
    min-height: 0;
    overflow: hidden;
  }
  .dhead {
    padding: 10px 12px;
    border-bottom: 1px solid var(--line);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .setimp {
    background: var(--green);
    color: #d2f5dd;
    border: 0;
    border-radius: 7px;
    padding: 7px 11px;
    font-weight: 600;
    font-size: 12px;
    white-space: nowrap;
  }
  .syncbar {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
  }
  .sync {
    background: var(--accent);
    color: #fff;
    border: 0;
    border-radius: 7px;
    padding: 9px 16px;
    font-weight: 700;
  }
  .sync:disabled {
    opacity: 0.6;
  }
  .prog {
    color: var(--muted);
    font-size: 12px;
  }
  .dbody {
    flex: 1;
    display: grid;
    grid-template-columns: 1fr 1fr;
    min-height: 0;
  }
  .itemcol {
    border-right: 1px solid var(--line);
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: 8px;
  }
  .prevcol {
    display: flex;
    flex-direction: column;
    min-height: 0;
    padding: 8px;
  }
  .lbl {
    font-size: 11px;
    text-transform: uppercase;
    color: var(--muted);
    letter-spacing: 0.04em;
    margin-bottom: 6px;
  }
  .ilist {
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .iname {
    flex: 1;
    text-align: left;
    background: var(--bg);
    border: 1px solid var(--line);
    color: var(--fg);
    border-radius: 6px;
    padding: 6px 8px;
    font-size: 12px;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    gap: 6px;
  }
  .iname.active {
    border-color: var(--accent);
  }
  .sz {
    color: var(--muted);
    font-size: 10px;
  }
  .stage {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f6f8fa;
    border-radius: 6px;
    overflow: hidden;
    min-height: 90px;
  }
  .stage :global(svg) {
    max-width: 100%;
    max-height: 100%;
  }
  .impmsg {
    margin-top: 6px;
    font-size: 12px;
    color: var(--muted);
  }
  .muted {
    color: var(--muted);
    font-size: 12px;
  }
</style>
