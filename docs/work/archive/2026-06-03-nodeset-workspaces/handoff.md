# Handoff — NodeSet Workspaces

## State

Package opened 2026-06-03. **Implementation landed in commit `c40d19a`**
(local `main`, not yet pushed). Engine + canvas/tabs wiring + five consumers
all in. `npm run check` at the 12-error pre-existing baseline (no new errors),
`npm run build` clean (single bundle), vitest 38 files / 354 tests green
(+12 new).

Remaining before close:
- **Browser smoke** (the one unchecked verification): open each source as a
  tab, confirm the induced subgraph, switch back to Global, close a nodeset
  tab, reload and confirm persistence (derived re-derive, captured restore).
- **Reference docs**: update the workspace-model description under
  `docs/reference/` (tabs are now typed scopes, not global/collection-only).
- **outcome.md** + archive + repoint `ACTIVE.md`.

Open follow-ons (not blockers):
- **Hidden consumer** — engine-ready (`{ kind: 'hidden' }` + `includeHidden`),
  but no v1 surface; needs a backend opt-in for server-hidden nodes or a
  client-hidden review list. See `decisions.md`.
- Label / local-search sources — label sources shipped in
  [`../2026-06-10-label-system/outcome.md`](../2026-06-10-label-system/outcome.md);
  local-search sources shipped in F5.

## Where things live

- Workspace store: `frontend/src/lib/stores/workspace.svelte.ts`
- Visibility seam: `frontend/src/lib/graph/controllers/visibilityController.ts`
  (`setScope`), installed from `frontend/src/components/graph/GraphCanvas.svelte`
- Tab bar / picker: `frontend/src/components/graph/WorkspaceTabs.svelte`,
  `WorkspacePicker.svelte`
- Graph poll (loads payload by active collection id, null ⇒ global):
  `frontend/src/lib/pollers/graph.svelte.ts`
- Bottom-pane lists: `frontend/src/views/bottom/{Domains,Flags,Fingerprints,
  Bookmarks,Hidden}Tab.svelte` (+ pure `.ts` helpers beside each)

## Gotchas

- `reconcileCollections` drops any tab whose `collectionId` is not a known
  collection — it must be taught to keep `kind === 'nodeset'` tabs (their
  `collectionId` is null).
- The `hidden` source must *show* nodes the controller normally hides, hence
  the `includeHidden` option on `setScope`.
- Graph nodes are pages/resources (each has `raw_url`), plus cluster nodes;
  `domain` is page→host. Flag/fingerprint rows carry the node id (`node_id` /
  `id`); bookmark seeds carry only `url`.
