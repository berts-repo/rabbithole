import { defineConfig } from 'vitest/config';
import { resolve } from 'node:path';

// Vitest runs the extracted pure graph-interaction modules
// (src/lib/graph/interactions/*) as plain Node logic — no Svelte compile,
// no DOM. Component and store (.svelte / .svelte.ts) files are
// deliberately out of scope here; the frontend's structural guard stays
// `npm run check` + `npm run build`. A standalone config (not a merge of
// vite.config.ts) keeps the Svelte plugin and dev-server proxy out of the
// test run.
export default defineConfig({
  resolve: {
    alias: {
      $lib: resolve(__dirname, 'src/lib'),
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
});
