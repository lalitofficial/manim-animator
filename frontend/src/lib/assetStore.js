/* Shared state across the Asset Studio dockview panels.
   Panels are independent components; these stores are their seam. */
import { writable } from 'svelte/store';

// The asset selected in the catalog → mirrored by the Preview panel.
export const selected = writable(null);

// Manifest headline counts → shown in the catalog header.
export const stats = writable(null);

// Bump to ask the Catalog (and Coverage) panels to reload — e.g. after a bundle
// toggle or a published variant changes what resolves.
export const dataVersion = writable(0);
export const bumpData = () => dataVersion.update((n) => n + 1);
