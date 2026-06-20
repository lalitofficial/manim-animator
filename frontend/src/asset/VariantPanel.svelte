<script>
  import { onMount } from 'svelte';
  import { assetFamilies, assetBundles, variantPreviewSvg, variantGate, variantSave } from '../lib/api.js';
  import { bumpData } from '../lib/assetStore.js';

  let families = [];
  let bundles = [];
  let family = '';
  let params = {};
  let svg = '';
  let gate = null;
  let concept = '';
  let bundle = '';
  let approved = false;
  let status = '';
  let busy = false;

  $: fam = families.find((f) => f.family === family);

  function resetParams(f) {
    const p = {};
    for (const param of f.params) {
      const ex = f.example_params || {};
      p[param.name] = ex[param.name] ?? param.default ?? (param.type === 'bool' ? false : '');
    }
    params = p;
  }

  async function selectFamily(name) {
    family = name;
    const f = families.find((x) => x.family === name);
    if (f) {
      resetParams(f);
      const home = bundles.find((b) => (b.families || []).includes(name));
      bundle = home ? home.id : bundles[0]?.id || '';
      await run();
    }
  }

  async function run() {
    if (!family) return;
    busy = true;
    status = '';
    try {
      const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null));
      svg = await variantPreviewSvg(family, clean);
      gate = await variantGate(family, clean);
    } catch (e) {
      status = e.message;
      gate = null;
    } finally {
      busy = false;
    }
  }

  async function publish() {
    if (!concept.trim()) {
      status = 'name the variant first';
      return;
    }
    busy = true;
    try {
      const clean = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v != null));
      const res = await variantSave({ concept: concept.trim(), family, params: clean, bundle, approved, license: 'studio' });
      if (res.ok) {
        status = `Published "${concept.trim()}". The engine resolves it now.`;
        approved = false;
        bumpData();
      } else {
        status = 'Failed: ' + res.error;
      }
    } catch (e) {
      status = e.message;
    } finally {
      busy = false;
    }
  }

  onMount(async () => {
    [families, bundles] = [
      (await assetFamilies()).families,
      (await assetBundles()).bundles,
    ];
    if (families.length) selectFamily(families[0].family);
  });
</script>

<div class="variant">
  <div class="form">
    <label>Family
      <select value={family} on:change={(e) => selectFamily(e.target.value)}>
        {#each families as f}<option value={f.family}>{f.family}</option>{/each}
      </select>
    </label>
    {#if fam}
      <div class="doc">{fam.doc}</div>
      <div class="params">
        {#each fam.params as p}
          <label class="p">
            <span>{p.name}{p.required ? ' *' : ''}</span>
            {#if p.type === 'bool'}
              <input type="checkbox" bind:checked={params[p.name]} on:change={run} />
            {:else if p.type === 'color'}
              <input type="color" bind:value={params[p.name]} on:change={run} />
            {:else if p.type === 'enum'}
              <select bind:value={params[p.name]} on:change={run}>
                <option value=""></option>
                {#each p.options as o}<option value={o}>{o}</option>{/each}
              </select>
            {:else}
              <input bind:value={params[p.name]} on:change={run} />
            {/if}
          </label>
        {/each}
      </div>
    {/if}

    <div class="publish">
      <input class="cname" placeholder="concept name (e.g. red-panda)" bind:value={concept} />
      <select bind:value={bundle}>
        {#each bundles as b}<option value={b.id}>{b.name}</option>{/each}
      </select>
      <label class="appr"><input type="checkbox" bind:checked={approved} /> I approve this asset</label>
      <button class="go" on:click={publish} disabled={busy || !gate || !gate.approvable || !approved}>Publish</button>
    </div>
    {#if status}<div class="status">{status}</div>{/if}
  </div>

  <div class="right">
    <div class="stage">
      {#if svg}{@html svg}{:else}<span class="muted">Preview</span>{/if}
    </div>
    <div class="gates">
      <h4>Publishing gates</h4>
      {#if gate}
        {#each gate.checks as c}
          <div class="g"><i class="dot" class:ok={c.pass} class:no={!c.pass} /><b>{c.name}</b><span class="d">{c.detail}</span></div>
        {/each}
        <div class="verdict" class:ok={gate.approvable}>
          {gate.approvable ? 'All gates pass — approve to publish.' : 'Gates failing — fix before publishing.'}
        </div>
      {:else}
        <span class="muted">Adjust a parameter to run the gates.</span>
      {/if}
    </div>
  </div>
</div>

<style>
  .variant {
    height: 100%;
    display: grid;
    grid-template-columns: 1fr 1fr;
    min-height: 0;
  }
  .form {
    padding: 12px 14px;
    overflow: auto;
    border-right: 1px solid var(--line);
  }
  .right {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  label {
    display: grid;
    gap: 5px;
    font-size: 11px;
    text-transform: uppercase;
    color: var(--muted);
    letter-spacing: 0.04em;
    margin-bottom: 10px;
  }
  select,
  input:not([type='checkbox']):not([type='color']) {
    background: var(--surface-3);
    border: 1px solid transparent;
    color: var(--fg);
    border-radius: var(--r-sm);
    padding: 9px 10px;
    width: 100%;
    transition: background 120ms ease, box-shadow 120ms ease;
  }
  select:focus,
  input:not([type='checkbox']):not([type='color']):focus {
    background: var(--surface-4);
    box-shadow: inset 0 -2px 0 var(--primary);
  }
  input[type='color'] {
    height: 36px;
    width: 100%;
    background: var(--surface-3);
    border: 1px solid transparent;
    border-radius: var(--r-sm);
    padding: 2px;
  }
  .doc {
    color: var(--muted);
    font-size: 12px;
    margin-bottom: 10px;
  }
  .params {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 12px;
  }
  .p {
    text-transform: none;
    font-size: 12px;
  }
  .p span {
    color: var(--muted);
  }
  .publish {
    margin-top: 14px;
    display: grid;
    gap: 8px;
    border-top: 1px solid var(--line);
    padding-top: 12px;
  }
  .appr {
    flex-direction: row;
    align-items: center;
    text-transform: none;
    font-size: 13px;
    color: var(--fg);
    gap: 7px;
    margin: 0;
  }
  .appr input {
    width: auto;
  }
  .go {
    background: var(--green);
    color: #d2f5dd;
    border: 0;
    border-radius: 7px;
    padding: 10px;
    font-weight: 700;
  }
  .go:disabled {
    opacity: 0.5;
  }
  .status {
    margin-top: 8px;
    font-size: 13px;
    color: var(--muted);
  }
  .stage {
    flex: 1;
    min-height: 150px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f6f8fa;
    border-bottom: 1px solid var(--line);
    overflow: hidden;
  }
  .stage :global(svg) {
    max-width: 92%;
    max-height: 92%;
  }
  .gates {
    padding: 12px 14px;
    overflow: auto;
  }
  h4 {
    margin: 0 0 8px;
    font-size: 12px;
    text-transform: uppercase;
    color: var(--muted);
    letter-spacing: 0.05em;
  }
  .g {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    font-size: 13px;
  }
  .g b {
    width: 100px;
  }
  .g .d {
    color: var(--muted);
    font-size: 12px;
  }
  .dot {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex: 0 0 auto;
  }
  .dot.ok {
    background: #2ea043;
  }
  .dot.no {
    background: #da3633;
  }
  .verdict {
    margin-top: 8px;
    font-weight: 600;
    color: #ff7b72;
  }
  .verdict.ok {
    color: #4ac26b;
  }
  .muted {
    color: var(--muted);
  }
</style>
