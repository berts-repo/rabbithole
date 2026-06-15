# Onion Rabbithole — Builder Rules

Read `CONTEXT.md` first. It holds project context, source-of-truth rules, hard
constraints, and task-specific read orders. This file holds only the always-on
stack and UI rules that are easy to violate.

## Stack rules

- **Svelte 5 runes only** (`$state`, `$derived`, `$effect`, `$props`). No legacy reactive `$:`.
- **TypeScript strict**; type all API response shapes.
- **Graph:** Sigma.js (WebGL) + graphology.
- **CSS:** scoped Svelte `<style>` only. No Tailwind, no external CSS framework.
- **Build output:** `npm run build` emits a single `bundle.js` + `bundle.css` in `public/`. No chunk splitting — the Python server loads both into memory at startup.
- **Dev:** Vite on `:5173`, `/api` proxied to backend on `:7654`.

## Visual tokens

```css
--bg: #0a0f0d; --text: #a8ffdb; --border: #1a3a2a; --accent: #00d4aa; --muted: #667;
```

## Selection model (app-wide)

- **Full selection** — bottom-pane row click. Updates graph highlight + right panel + bottom-pane active row.
- **Highlight only** — graph node click or left-pane Find result click. Updates graph highlight + right panel. Does **not** move the bottom-pane active row.

## Settings

Gear icon (`AppHeader.svelte:52`) opens `SettingsStubModal.svelte` — the single home for all app settings.
