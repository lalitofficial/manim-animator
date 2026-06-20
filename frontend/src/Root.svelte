<script>
  import App from './App.svelte';
  import AssetStudio from './AssetStudio.svelte';

  const VIEWS = [
    { id: 'board', label: 'Board', icon: 'M5 5h14v14H5z M8 8h8v8H8z' },
    { id: 'assets', label: 'Assets', icon: 'M5 5h6v6H5z M13 5h6v6h-6z M5 13h6v6H5z M13 13h6v6h-6z' },
  ];

  function fromHash() {
    return location.hash.replace('#/', '') || 'board';
  }
  let view = fromHash();
  function go(id) {
    location.hash = '/' + id;
  }
  function onHash() {
    view = fromHash();
  }
</script>

<svelte:window on:hashchange={onHash} />

<div class="root">
  <nav class="rail">
    <div class="logo" title="Manim Animator">M</div>
    {#each VIEWS as v}
      <button
        class="nav"
        class:active={view === v.id}
        on:click={() => go(v.id)}
        title={v.label}
      >
        <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">
          <path d={v.icon} />
        </svg>
        <span class="lbl">{v.label}</span>
      </button>
    {/each}
  </nav>
  <main class="view">
    {#if view === 'assets'}
      <AssetStudio />
    {:else}
      <App />
    {/if}
  </main>
</div>

<style>
  .root {
    display: flex;
    height: 100vh;
    width: 100vw;
    overflow: hidden;
  }
  .rail {
    width: 56px;
    flex: 0 0 auto;
    background: #0b0f14;
    border-right: 1px solid var(--line);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 5px;
    padding: 8px 0;
  }
  .logo {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--accent), #2ea043);
    color: #fff;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 6px;
  }
  .nav {
    width: 46px;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    color: var(--muted);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 6px 0;
    cursor: pointer;
  }
  .nav:hover {
    color: var(--fg);
    background: #ffffff08;
  }
  .nav.active {
    color: var(--fg);
    background: #1f6feb22;
    border-color: var(--accent);
  }
  .glyph {
    width: 17px;
    height: 17px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .lbl {
    font-size: 10px;
    font-weight: 600;
  }
  .view {
    flex: 1;
    min-width: 0;
    height: 100vh;
    overflow: hidden;
  }
  @media (max-width: 640px) {
    .rail {
      width: 50px;
    }
    .logo {
      width: 32px;
      height: 32px;
      font-size: 14px;
    }
    .nav {
      width: 42px;
    }
    .lbl {
      font-size: 9px;
    }
  }
</style>
