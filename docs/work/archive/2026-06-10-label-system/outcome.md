# Outcome — Label System (item 11)

Closed 2026-06-11. Project-wide labeling for pages and domains, page rename on
the consolidated rename seam, and the new graph **collapse** model. Shipped as
six green-on-their-own commits on an additive **`SCHEMA_VERSION` 5 → 6**
migration (no DB delete):

| Commit | Scope |
| --- | --- |
| `3320bae` | Backend (schema, `db/labels.py`, `routes/labels.py`, `pages.alias` + endpoint) + Phase 2 frontend foundation (`lib/api/labels.ts`, `labelsStore`). |
| `8c67036` | Phase 2 apply — membership read surface on payload/detail/profile, picker popover, right-panel chips, menu wiring, page-rename stub filled. |
| `d730c65` | Slice A — bottom-pane Labels tab + `GET /api/labels/:id/members` + `NodeSetSource{kind:'label'}`. |
| `669cab8` | Slice B — color-by-label mode + include/exclude `labelFilter`. |
| `e3fd0e7` | Slice C — graph collapse (domain + label folds, `foldPlan.ts`, per-tab persistence). |
| `c6ed999` | Slice D — left-pane label browser (Find sub-tab) + Settings Labels tab. |

## What shipped

**Data model (D2).** New tables `labels`, `resource_labels`, `domain_labels`
(two *typed* join tables — INTEGER resource id vs. TEXT host — for clean
cascade-on-delete) + a `pages.alias` column, all additive (`CREATE IF NOT
EXISTS` + idempotent preset seed; the only in-place change is the nullable
`pages.alias` backfill). Seven `builtin=1` presets (Market, Forum, Directory,
Blog, Service, Scam, Avoid, D3) — recolorable / redescribable / hideable but
never renamed or deleted; custom labels fully editable + deletable. `db/labels.py`
owns CRUD + attach/detach + counts + rank; `routes/labels.py` exposes them.

**Apply surface.** Labels attach from the shared right-click menu / right-panel
action bar (target-agnostic over both join tables); a picker popover (search +
create-inline, optimistic toggles, deferred graph refresh on close); right-panel
chips with a "via domain" badge. The payload, node detail, and domain profile
carry `label_ids` (direct, rank-ordered) + `domain_label_ids` (via-host,
server-deduped); attach / detach / delete / reorder bust the graph cache.
`labelsStore` is the single catalog — all mutations route through it so chips,
picker, color, and collapse stay in sync.

**Page rename (D1).** Filled the stubbed `page` branch of the existing
`renameTarget()` seam with `patchPageAlias` against `PATCH /api/pages/:id/alias`
— no new popover. Every surface that renames a domain now renames a page too.

**Four analyst surfaces.**
- **Bottom-pane Labels tab** — labels with member counts, lazy expand to members
  (highlight-only), drag-reorder writing `rank`, open-as-graph-tab.
- **Left-pane label browser** (Find sub-tab) — per-label in-graph member count
  off the rendered payload (direct ∪ via-domain), click highlights the set,
  second click clears.
- **Color-by-label** mode + include/exclude **label filter** in
  `visibilityController`, composed as a separate dimension from `graph_filters`.
- **Settings → Labels tab** — preset hide toggles, custom CRUD, color palette +
  description, drag-reorder.

**Collapse (D4–D8).** A distinct verb from Hide: many nodes fold into one
summary node that stays on the canvas. `foldPlan.ts` is the pure unified
resolver — a page folds into the highest-ranked collapsed label it carries
(D5), with domain at the floor of the same ranking (D6); folded nodes show
overlap counts. Domain folds are alias-aware (D7). Collapse state persists per
workspace tab via `graphCollapse.svelte.ts` + the `graph.collapse` setting (D8).

**The one ranking (D5).** A single analyst-controlled `labels.rank` (lower =
higher; warnings seeded at the top) resolves three features at once: picker
order, the dominant-label color, and the collapse fold home. One concept reused.

## Verify

- Frontend `svelte-check` 0/0; vitest **502 passed** (52 files); single
  `bundle.js` + `bundle.css` build (the >500 kB chunk warning is the expected
  single-bundle shape).
- Backend `pytest` **819 passed** (CRUD, 409 dup name, preset-undeletable,
  cascade-on-delete, page-alias set/clear, rank reorder, idempotent seed,
  membership maps, `graph.collapse` validator).

## Notes

- Untracked root `.md` files, screenshots, and `.playwright-mcp/` were kept out
  of every commit (explicit-path staging).
- Deferred, unchanged from the source spec: whether the auto-categorizer
  (`pages.category`) and labels eventually unify; whether `Avoid` suppresses
  crawl-on-discovery (a Crawl & Queue policy, Settings Wave 2); chip text vs.
  swatch coloring decided at build time. See `decisions.md`.
