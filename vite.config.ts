import { defineConfig } from 'vite';

// In CI, actions/configure-pages hands us the site's real base path; this is the
// fallback, matching the GitHub Pages path for the repository's current name. `||`
// rather than `??` on purpose: that action yields an empty string when Pages is not
// enabled yet, and an empty base would publish broken asset URLs.
// actions/configure-pages reports the base path WITHOUT a trailing slash, and
// Vite hands `base` to import.meta.env.BASE_URL verbatim - so joining it with
// "data/bundle.json" produced "/Indonesian-Railway-data/bundle.json" in the
// deployed build while the asset URLs looked fine. Normalise it here.
const rawBase = process.env.BASE_PATH || '/Indonesian-Railway-/';
const base = rawBase.endsWith('/') ? rawBase : `${rawBase}/`;

export default defineConfig({
  base,
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
