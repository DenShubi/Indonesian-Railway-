import { defineConfig } from 'vite';

// `base` matches the GitHub Pages path for https://github.com/DenShubi/Indonesian-Railway-
// Dev server is unaffected; override with BASE_PATH when deploying elsewhere.
export default defineConfig({
  base: process.env.BASE_PATH ?? '/Indonesian-Railway-/',
  // MapLibre builds its worker from a URL relative to its own module, which breaks
  // once Vite pre-bundles the package into .vite/deps. Serving it unbundled keeps
  // `new Worker(new URL(...), import.meta.url)` resolvable in dev.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  worker: { format: 'es' },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
  },
});
