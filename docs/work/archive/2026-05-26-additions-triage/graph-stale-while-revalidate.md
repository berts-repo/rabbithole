# Graph stale-while-revalidate + diff-update

**Status:** Slice 1 shipped 2026-05-19 (drag-to-move + applyDiff).
Slice 2 shipped 2026-05-19 (per-tab payload + camera cache + first-visit skeleton).
Slice 3 shipped 2026-05-19 (graph_filters invalidation; crawl intentionally skipped).
Decision recorded in `docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md` Finding #6.

**Audience:** an agent picking this up cold. You haven't seen the test
session — everything you need is in this doc plus the linked files.

## Problem

Switching workspace tabs (Global ↔ collection) currently shows a
visible flash: status line briefly reads `10 nodes · 10 edges` for
~1-2 s before settling to the real count. The graph passes through an
inconsistent intermediate state on every switch.

Two adjacent issues share the same root cause:

1. **Per-tab camera memory** — docs/work/archive/2026-05-20-f4b-toolbar-modals/checklist.md line 56-58: zoom
   position is currently reset to "fit" on every switch. The user
   wants the initial-fit behaviour on first open, but if they zoom in
   and the tab stays open, the zoom should survive the next switch
   away and back.
2. **15 s poll wipes manual drags** — every poll tick re-runs
   `applyPayloadAndLayout()` and rebuilds the graph from the new
   payload, blowing away any positions the user dragged in the
   interim. This is a long-standing background irritation, not
   specifically called out in the F4b checklist but trivial to fold
   into the same fix.

All three are symptoms of the same architectural choice: the graph
apply path treats every payload as a full rebuild. A diff-update apply
path fixes all three at once.

## Architectural constraints (load-bearing — do NOT break)

- **One graphology instance for the page lifetime.** Sigma's WebGL
  context doesn't re-mount. Mutate the existing instance, never
  spawn new graphs per tab. Marked explicitly in
  `docs/work/archive/2026-05-20-f4b-toolbar-modals/changes.md:144-147` ("DO NOT refactor toward N graphology
  instances") and `graph.svelte.ts:50-56` comment.
- **Single-flight `/api/graph` cache stays global.** Backend doesn't
  carry per-collection cache slots; post-filter (slice 3) is cheap on
  each scoped request. Don't introduce per-tab backend caching to
  solve a frontend race.
- **Snapshot positions are page-lifetime.** The
  `workspaceSnapshots.svelte.ts` Map<workspaceId, Snapshot> already
  exists from slice 2. Extend it; don't replace it.
- **`consumePending` deferred-restore pattern is already half the
  answer.** Slice 3 introduced `pendingRestoreId` + `consumePending`
  so collection→collection switches defer position-restore until
  after `applyPayload` rebuilds the graph. Generalise this; don't
  invent a new mechanism.

## Approach: stale-while-revalidate + diff-update

Two changes, both small:

### 1. Per-tab payload cache

Extend `workspaceSnapshots.svelte.ts` to also hold the last-seen
`/api/graph` payload per tab, alongside the existing positions /
selection / ego-focus.

```ts
type Snapshot = {
  positions: Map<string, {x: number, y: number}>;
  selectedNodeId: number | null;
  selectedIds: Set<number>;
  egoFocus: EgoFocus | null;
  // new:
  payload: GraphPayload | null;     // last-known graph payload
  camera: { x: number, y: number, ratio: number, angle: number } | null;
};
```

On tab switch (`workspaceSnapshots.onSwitch`):
- Capture current tab's payload + camera state alongside positions.
- If the next tab has a cached payload: immediately push it through
  `graphStore.applyCached(payload)` (new helper) so the graph renders
  the cached data + cached positions instantly.
- Fire `graphPoller.refresh()` as today. The fetch runs in the
  background.

On poll response (`applyPayloadAndLayout`):
- If a cached payload was applied: take the diff-update path
  (see below) instead of full rebuild.
- Otherwise (first-ever load of this tab): take the existing
  rebuild path, then `consumePending` as today.

### 2. Diff-update apply path

Replace the unconditional `graph.clear() + addNode(...)` rebuild
inside `applyPayloadAndLayout` with a diff:

```
new_node_ids = set(payload.nodes.map(n => n.id))
existing_ids = set(graph.nodes())

to_add    = new_node_ids - existing_ids
to_remove = existing_ids - new_node_ids
to_update = new_node_ids & existing_ids
```

- `to_add` — new nodes; place at their layout-computed default
  position; mark them as "auto-positioned" (vs "user-dragged"
  — see below).
- `to_remove` — drop with `graph.dropNode(id)`.
- `to_update` — update attributes (label, color, flag_status, depth,
  etc.) but **preserve x/y if the node is marked user-dragged**;
  otherwise update x/y to the new layout-computed value.

A node becomes "user-dragged" the moment Sigma fires `node:drag` or
`node:dragend` for it. Store this as a per-node attribute
(`userPositioned: true`) on the graphology node. The drag handler
already exists in `GraphCanvas.svelte`; extend it to set the flag.

Same edge diff in parallel: add/remove/update by `(source, target,
type)` key.

### 3. First-switch skeleton

If `workspaceSnapshots.has(nextId) === false` (first time visiting
this tab), the cached-payload path is skipped — there's nothing to
apply optimistically. The existing rebuild path runs; show a small
"Loading workspace…" placeholder over the canvas until the first
payload lands. Use a new `<GraphLoadingOverlay>` component, or reuse
an existing toast/empty-state pattern (check
`frontend/src/components/empty/` first).

After the first response, the cache is warm for that tab and future
switches use the optimistic path.

### 4. Cache invalidation

The cached payload goes stale when:
- A crawl writes new nodes — `crawl.status` SSE events already exist;
  invalidate the affected tab's cache on those events. The Global
  tab's cache invalidates on any crawl event; a collection tab's
  cache invalidates only when a crawl with that `collection_id` runs.
- A graph filter (`graph_filters` server-side hide) is added or
  removed — already triggers a poll refresh today; pipe the same
  signal into a cache drop.
- A node is hidden/un-hidden via right-click "Hide from Graph" —
  immediate poll refresh; drop the cache for the affected tab.
- A flag/review status changes — these don't change *which* nodes
  exist, only attributes. Diff-update handles them naturally;
  no cache drop needed.

If in doubt, drop the cache. Stale-while-revalidate tolerates
cache misses gracefully — the user just sees the skeleton instead
of the optimistic view.

## Files affected (preliminary; planner: confirm with grep before edits)

**Stores**
- `frontend/src/lib/stores/workspaceSnapshots.svelte.ts` — extend
  `Snapshot` type; new payload + camera fields; new
  `applyCached(id)` helper.
- `frontend/src/lib/stores/graph.svelte.ts` — new diff-update path
  in `applyPayload` (or new helper called from
  `applyPayloadAndLayout`).
- `frontend/src/lib/pollers/graph.svelte.ts` — feed responses into
  whichever apply path the snapshot indicates.

**Components**
- `frontend/src/components/graph/GraphCanvas.svelte` — drag handler
  marks `userPositioned: true`; first-switch placeholder mount;
  camera capture/restore on switch.
- `frontend/src/views/GraphTab.svelte` — bridge effect already
  calls `onSwitch` + `refresh()`; add the optimistic-apply step.

**No backend changes expected.** This is purely a frontend caching
+ apply-path refactor. The single-flight `/api/graph` cache stays
exactly as it is.

## Migration / rollout

- No schema changes. No backend changes. No API contract changes.
- No flag needed — the diff-update path is strictly better than the
  rebuild path. Land it once verified.
- Verify against the F4b checklist switch-flash item (line 46) +
  the per-tab camera ask (line 56-58) + a manual drag-survives-poll
  spot-check.

## Test plan

Unit:
- `workspaceSnapshots.applyCached(id)` round-trips payload +
  positions + camera correctly.
- Diff-update on identical payloads is a no-op (no node attribute
  writes fire).
- Diff-update with one node added produces exactly one `addNode`
  call and zero updates on survivors.
- Diff-update with one user-dragged node where the new payload has
  a different x/y for that node preserves the dragged position.

Browser smoke:
- Open Global, drag a node visibly off-centre, wait 15 s — node
  should not snap back.
- Open Global, switch to a collection tab, switch back — no flash;
  cached graph reappears instantly with the dragged position
  preserved.
- Crawl a new page into the active collection tab — node appears
  within ~15 s without disturbing other dragged positions.
- Open a never-visited collection tab — skeleton placeholder
  visible until the first payload lands.

## Open questions (planner to resolve or escalate)

1. **Camera restore animation.** Sigma's `animatedReset({duration:
   200})` is currently called when `consumePending()` returns true
   (slice 3). Should the new optimistic path skip the animation
   entirely (instant snap to cached camera) or animate from the
   previous tab's camera position? Snap is probably right for
   stale-while-revalidate ("you saw this exact view a second ago,
   restore it") but worth a UX gut-check.
2. **Cache size cap.** Open tabs are at most ~8-10 by usage pattern
   (Global + a handful of collections). Each payload is a few tens
   of KB. No cap needed in practice; document the assumption.
3. **Snapshot-version interaction.** `workspaceSnapshots.version`
   currently triggers `renderer.refresh()` after position restores
   (slice 2). Diff-update may not need this bump for every
   poll-driven update (most updates are attribute changes that
   trip their own existing effects). Audit which effects observe
   `version` and decide whether to bump on diff-update poll
   responses or only on switch-driven restores.
4. **Selection survival.** A node that's currently selected and gets
   removed by a diff (e.g. server-side hide) — what happens? Likely:
   drop from `selectedIds`, clear `selectedNodeId` if it matched.
   Confirm against right-pane behaviour.

## Reference: linked decisions in this round

- Domain colour mode → make it work (Finding #1)
- `infra_cluster_id` → normalise CSP + hash at write time (Finding #2)
- Empty colour mode → grey button + tooltip (Finding #3)
- Flag enum → three states + typed constants (Finding #4)
- Workspace tabs → persist server-side (Finding #5)

This Finding #6 fix interacts with #5 (the per-tab cache complements
the server-side tab persistence: on app load, restore the open-tab
list, then warm the active tab's cache from a fresh fetch; inactive
tabs hydrate on first switch).
