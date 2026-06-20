<script>
  import { onMount, onDestroy } from 'svelte';
  import { createDockview, themeGithubDark } from 'dockview-core';
  import { componentFactory } from './lib/dockSvelte.js';
  import { stats, bumpData } from './lib/assetStore.js';
  import { publishAll, assetCatalog } from './lib/api.js';

  import CatalogPanel from './asset/CatalogPanel.svelte';
  import PreviewPanel from './asset/PreviewPanel.svelte';
  import BundlesPanel from './asset/BundlesPanel.svelte';
  import CoveragePanel from './asset/CoveragePanel.svelte';
  import VariantPanel from './asset/VariantPanel.svelte';
  import ExcalidrawPanel from './asset/ExcalidrawPanel.svelte';

  let el;
  let api;
  let s = null;
  const unsub = stats.subscribe((v) => (s = v));

  const PANELS = {
    catalog: CatalogPanel,
    preview: PreviewPanel,
    bundles: BundlesPanel,
    coverage: CoveragePanel,
    variant: VariantPanel,
    excalidraw: ExcalidrawPanel,
  };

  function buildLayout() {
    const compact = (el?.clientWidth || window.innerWidth) < 900;
    if (compact) {
      api.addPanel({
        id: 'catalog',
        component: 'catalog',
        title: 'Catalog',
        minimumWidth: 240,
        minimumHeight: 260,
      });
      api.addPanel({
        id: 'preview',
        component: 'preview',
        title: 'Preview',
        position: { referencePanel: 'catalog', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 260,
      });
      api.addPanel({
        id: 'bundles',
        component: 'bundles',
        title: 'Bundles',
        position: { referencePanel: 'catalog', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 260,
      });
      api.addPanel({
        id: 'coverage',
        component: 'coverage',
        title: 'Coverage',
        position: { referencePanel: 'catalog', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 260,
      });
      api.addPanel({
        id: 'variant',
        component: 'variant',
        title: 'Create Variant',
        position: { referencePanel: 'catalog', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 260,
      });
      api.addPanel({
        id: 'excalidraw',
        component: 'excalidraw',
        title: 'Excalidraw Candidates',
        position: { referencePanel: 'catalog', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 260,
      });
      api.getPanel('catalog')?.api.setActive();
      return;
    }

    api.addPanel({
      id: 'catalog',
      component: 'catalog',
      title: 'Catalog',
      initialWidth: 360,
      minimumWidth: 280,
      minimumHeight: 220,
    });
    api.addPanel({
      id: 'preview',
      component: 'preview',
      title: 'Preview',
      position: { referencePanel: 'catalog', direction: 'right' },
      initialWidth: 520,
      minimumWidth: 360,
      minimumHeight: 220,
    });
    api.addPanel({
      id: 'bundles',
      component: 'bundles',
      title: 'Bundles',
      position: { referencePanel: 'preview', direction: 'right' },
      initialWidth: 340,
      minimumWidth: 280,
      minimumHeight: 220,
    });
    api.addPanel({
      id: 'coverage',
      component: 'coverage',
      title: 'Coverage',
      position: { referencePanel: 'bundles', direction: 'below' },
      initialHeight: 280,
      minimumWidth: 280,
      minimumHeight: 200,
    });
    api.addPanel({
      id: 'variant',
      component: 'variant',
      title: 'Create Variant',
      position: { referencePanel: 'catalog', direction: 'below' },
      initialHeight: 300,
      minimumWidth: 280,
      minimumHeight: 220,
    });
    api.addPanel({
      id: 'excalidraw',
      component: 'excalidraw',
      title: 'Excalidraw Candidates',
      position: { referencePanel: 'variant', direction: 'within' },
    });
    // land on the catalog + variant tabs
    api.getPanel('catalog')?.api.setActive();
    api.getPanel('variant')?.api.setActive();
  }

  function resetLayout() {
    if (!api) return;
    api.clear();
    buildLayout();
  }

  let publishing = false;
  async function doPublishAll() {
    if (!confirm('Publish ALL renderable imported icons so the engine can draw them?')) return;
    publishing = true;
    try {
      const res = await publishAll();
      // refresh the stats header
      const data = await assetCatalog({ limit: 1 });
      stats.set(data.stats);
      bumpData();
      alert(`Published ${res.total_published} icons — engine-drawable now.`);
    } catch (e) {
      alert(e.message);
    } finally {
      publishing = false;
    }
  }

  onMount(() => {
    api = createDockview(el, {
      theme: themeGithubDark,
      createComponent: componentFactory(PANELS),
    });
    buildLayout();
  });

  onDestroy(() => {
    unsub();
    api?.dispose();
  });
</script>

<div class="wrap">
  <header>
    <div class="title">Asset Studio</div>
    {#if s}
      <div class="stats">
        <span class="stat"><b>{s.total}</b> assets</span>
        <span class="stat"><b>{s.by_kind?.family || 0}</b> family variants</span>
        <span class="stat"><b>{(s.by_kind?.catalog || 0) + (s.by_kind?.mono || 0)}</b> catalog/mono</span>
        <span class="stat" class:warn={s.candidates}><b>{s.candidates}</b> candidates</span>
      </div>
    {/if}
    <button class="publishall" on:click={doPublishAll} disabled={publishing}>
      {publishing ? 'Publishing…' : 'Publish all imported'}
    </button>
    <button class="m3-icon" on:click={resetLayout} title="Reset panel layout" aria-label="Reset panel layout">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5a7 7 0 1 1-6.32 10H3.55A9 9 0 1 0 5.6 5.6L3 3v7h7L7.05 7.05A6.96 6.96 0 0 1 12 5Z" /></svg>
    </button>
  </header>
  <div class="dock" bind:this={el} />
</div>

<style>
  .wrap {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  header {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 52px;
    padding: 6px 8px 6px 16px;
    background: var(--surface-2);
    box-shadow: var(--elev-1);
    z-index: 1;
    flex: 0 0 auto;
  }
  .publishall {
    margin-left: auto;
    background: var(--green, #1f6f3f);
    color: #d2f5dd;
    border: 0;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: 700;
    font-size: 13px;
    cursor: pointer;
  }
  .publishall:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .title {
    font-weight: 600;
    letter-spacing: 0.01em;
    white-space: nowrap;
  }
  .stats {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    color: var(--muted);
    font-size: 12px;
  }
  .stat b {
    color: var(--fg);
  }
  .stat.warn b {
    color: #ffd9a8;
  }
  header > :global(.m3-icon) {
    margin-left: auto;
  }
  .dock {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  @media (max-width: 640px) {
    .stats .stat:not(:first-child) {
      display: none;
    }
  }
</style>
