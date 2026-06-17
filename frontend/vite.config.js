import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vite';

// Built to frontend/dist and served by FastAPI under /studio.
// In dev (`make ui`), Vite proxies /api to the uvicorn backend on :8000.
export default defineConfig({
  plugins: [svelte()],
  base: '/studio/',
  build: { outDir: 'dist', emptyOutDir: true },
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
});
