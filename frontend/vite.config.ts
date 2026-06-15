import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    alias: {
      $lib: resolve(__dirname, 'src/lib'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // Backend middleware (security/auth.py) requires Host: 127.0.0.1:7654
      // and Origin: http://127.0.0.1:7654 on every /api/* request. The
      // browser doesn't send Origin on same-origin GETs and sends
      // Host: 127.0.0.1:5173 on everything, so the proxy has to inject
      // both headers explicitly. The session cookie still rides through —
      // it's set on 127.0.0.1:5173 by the browser when GET / proxies
      // through and the backend's first-load Set-Cookie reaches us.
      '/api': {
        target: 'http://127.0.0.1:7654',
        changeOrigin: true,
        xfwd: false,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Origin', 'http://127.0.0.1:7654');
          });
        },
      },
      // Session bootstrap for dev mode. The backend mints the session
      // cookie only on GET /, which Vite intercepts to serve the dev page.
      // main.ts hits /__session once on startup so the browser ends up
      // with the cookie scoped to the page origin (127.0.0.1:5173).
      '/__session': {
        target: 'http://127.0.0.1:7654',
        changeOrigin: true,
        rewrite: () => '/',
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq) => {
            proxyReq.setHeader('Origin', 'http://127.0.0.1:7654');
          });
        },
      },
    },
  },
  build: {
    outDir: '../backend/public',
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'bundle.js',
        assetFileNames: (info) =>
          info.name?.endsWith('.css') ? 'bundle.css' : 'assets/[name][extname]',
      },
    },
  },
});
