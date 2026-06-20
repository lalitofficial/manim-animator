<script>
  import { onDestroy, onMount } from 'svelte';
  import { createDockview, themeGithubDark } from 'dockview-core';
  import BoardPanel from './board/BoardPanel.svelte';
  import ControlPanel from './board/ControlPanel.svelte';
  import InspectorPanel from './board/InspectorPanel.svelte';
  import ScriptPanel from './board/ScriptPanel.svelte';
  import { refreshStatus, status, playing, runLabel } from './lib/workspaceStore.js';
  import { componentFactory } from './lib/dockSvelte.js';

  let el;
  let api;

  const PANELS = {
    board: BoardPanel,
    controls: ControlPanel,
    inspector: InspectorPanel,
    script: ScriptPanel,
  };

  function buildLayout() {
    const compact = (el?.clientWidth || window.innerWidth) < 900;
    if (compact) {
      api.addPanel({
        id: 'controls',
        component: 'controls',
        title: 'Controls',
        minimumWidth: 240,
        minimumHeight: 240,
      });
      api.addPanel({
        id: 'board',
        component: 'board',
        title: 'Board',
        position: { referencePanel: 'controls', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 320,
      });
      api.addPanel({
        id: 'script',
        component: 'script',
        title: 'Story Input',
        position: { referencePanel: 'controls', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 220,
      });
      api.addPanel({
        id: 'inspector',
        component: 'inspector',
        title: 'Inspector',
        position: { referencePanel: 'controls', direction: 'within' },
        minimumWidth: 240,
        minimumHeight: 220,
      });
      api.getPanel('controls')?.api.setActive();
      return;
    }

    api.addPanel({
      id: 'board',
      component: 'board',
      title: 'Board',
      minimumWidth: 520,
      minimumHeight: 360,
    });
    api.addPanel({
      id: 'controls',
      component: 'controls',
      title: 'Controls',
      position: { referencePanel: 'board', direction: 'left' },
      initialWidth: 370,
      minimumWidth: 330,
      minimumHeight: 240,
    });
    api.addPanel({
      id: 'inspector',
      component: 'inspector',
      title: 'Inspector',
      position: { referencePanel: 'board', direction: 'right' },
      initialWidth: 360,
      minimumWidth: 280,
      minimumHeight: 240,
    });
    api.addPanel({
      id: 'script',
      component: 'script',
      title: 'Story Input',
      position: { referencePanel: 'controls', direction: 'below' },
      initialHeight: 250,
      minimumWidth: 330,
      minimumHeight: 180,
    });
    api.getPanel('board')?.api.setActive();
  }

  function resetLayout() {
    if (!api) return;
    api.clear();
    buildLayout();
  }

  onMount(() => {
    refreshStatus();
    api = createDockview(el, {
      theme: themeGithubDark,
      createComponent: componentFactory(PANELS),
    });
    buildLayout();
  });

  onDestroy(() => {
    api?.dispose();
  });
</script>

<div class="workspace">
  <header>
    <div>
      <div class="title">Live Board Studio</div>
    </div>
    <div class="status-strip">
      {#if $status}
        <span class="tag" class:warn={$status.story_provider === 'template'}>brain {$status.story_provider}</span>
        <span class="tag">draw {$status.svg_provider}</span>
      {:else}
        <span class="tag">loading status</span>
      {/if}
      <span class="tag run-state" class:hot={$playing}>{$playing ? $runLabel : 'ready'}</span>
    </div>
    <button class="m3-icon" on:click={resetLayout} title="Reset panel layout" aria-label="Reset panel layout">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5a7 7 0 1 1-6.32 10H3.55A9 9 0 1 0 5.6 5.6L3 3v7h7L7.05 7.05A6.96 6.96 0 0 1 12 5Z" /></svg>
    </button>
  </header>
  <div class="dock" bind:this={el} />
</div>

<style>
  .workspace {
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    background: var(--bg);
  }
  header {
    flex: 0 0 auto;
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 52px;
    padding: 6px 8px 6px 16px;
    background: var(--surface-2);
    box-shadow: var(--elev-1);
    z-index: 1;
  }
  .title {
    color: var(--fg);
    font-size: 15px;
    font-weight: 600;
    letter-spacing: 0.01em;
    white-space: nowrap;
  }
  .status-strip {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-left: auto;
    justify-content: flex-end;
  }
  .tag {
    border-radius: var(--r-full);
    background: var(--surface-4);
    color: var(--on-surface-variant);
    padding: 4px 11px;
    font-size: 11.5px;
    font-weight: 600;
  }
  .tag.warn {
    background: var(--warn-container);
    color: var(--on-warn);
  }
  .tag.hot {
    background: var(--success-container);
    color: var(--success);
  }
  .dock {
    flex: 1;
    min-height: 0;
    position: relative;
  }
  @media (max-width: 780px) {
    header {
      min-height: 44px;
      align-items: center;
      flex-direction: row;
      flex-wrap: wrap;
    }
    .status-strip {
      margin-left: auto;
      justify-content: flex-start;
    }
  }
  @media (max-width: 640px) {
    .status-strip .tag:not(.run-state) {
      display: none;
    }
  }
</style>
