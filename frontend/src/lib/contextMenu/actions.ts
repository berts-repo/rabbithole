// Shared context-menu action implementations.
//
// Each action takes only the data it needs — a URL, a node id, or a
// GraphNode array — so any surface that can produce that minimum
// (graph node, bottom-pane row, future right-pane / search-result row)
// can call into the same handlers and get the same side effects:
// toasts, graph-poller refreshes, payload-cache invalidation.
//
// What lives here vs. with each surface:
//   - HERE: anything driven by the global stores (toast / navigation /
//     batchConfirm / seedBookmarks / workspaceSnapshots / graphPoller /
//     graphStore.egoFocus) plus the URL-only and id-only API calls.
//   - WITH THE SURFACE: anything that depends on the surface's own
//     state — Sigma renderer (actFocus, renderer.refresh on alias save,
//     viewport-coord rename popover) and modal state (openMonitor /
//     openRename / openAnalysis / openCollection / openEdge).
//
// Phase shared-ui-primitives additions:
//   - Selection shape: { nodes: GraphNode[], urls: string[] }
//   - Multi-target verb helpers: sendToCrawl, addToCollection, flag,
//     removeFlag, queueAnalysis, copyUrls, removeFromCollection, hide,
//     unhide, markReviewed.
//   The single-node wrappers (actFlag, actRemoveFlag, etc.) are kept as
//   thin delegators during migration; callers are converted incrementally.

import {
  addGraphFilter,
  addItemsToCollection,
  ApiError,
  clearNodeFlags,
  createFlag,
  createStubNode,
  createStubNodes,
  openNodeInBrowser,
  patchDomainAlias,
  patchPageAlias,
  patchNodeAnalysisExcluded,
  patchNodeReviewed,
  removeItemFromCollection,
  type GraphNode,
} from '$lib/api';
import { explainError } from '$lib/api/errors';
import { isUncrawled } from '$lib/nodeState';
import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';
import { graphPinsStore } from '$lib/stores/graphPins.svelte';
import { graphStore } from '$lib/stores/graph.svelte';
import { labelsStore } from '$lib/stores/labels.svelte';
import {
  intelComposeStore,
  targetFromIds,
  targetFromNodes,
} from '$lib/stores/intelCompose.svelte';
import { navigationStore } from '$lib/stores/navigation.svelte';
import { graphPoller } from '$lib/pollers/graph.svelte';
import { findPendingStore } from '$lib/stores/findPending.svelte';
import { seedBookmarksStore } from '$lib/stores/seedBookmarks.svelte';
import { toastStore } from '$lib/stores/toast.svelte';
import { workspaceSnapshots } from '$lib/stores/workspaceSnapshots.svelte';
import type { RenameTarget } from './rename';
import type { LabelTarget } from './labels';

// Re-export the pure rename seam so surfaces can pull types + the action
// from one module.
export { renameModal, renameTargetIdentity } from './rename';
export type { RenameTarget, RenameModal } from './rename';

// Re-export the pure label-apply seam alongside it.
export { labelPickerModal, labelTargetIdentity } from './labels';
export type { LabelTarget, LabelPickerModal } from './labels';

// ---------------- Utilities ----------------

// Copy plain text via the clipboard API, falling back to the legacy
// execCommand path on insecure contexts (plain http://127.0.0.1 dev).
export async function copyToClipboard(text: string): Promise<void> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
  } catch {
    // fall through
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
  } finally {
    document.body.removeChild(ta);
  }
}

export function explainApiError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${fallback}: ${err.message}`;
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}

export function plural(n: number, singular: string, plural?: string): string {
  return n === 1 ? singular : (plural ?? `${singular}s`);
}

// ---------------- Single-target actions ----------------

export async function actCopyUrl(url: string): Promise<void> {
  try {
    await copyToClipboard(url);
    toastStore.show('URL copied');
  } catch (err) {
    toastStore.show(explainApiError(err, 'Copy failed'), 'error');
  }
}

// Launch Tor Browser via the backend. The caller is responsible for
// gating the menu row on `servicesStore.killSwitch.phase === 'armed'`;
// the backend re-checks the cached kill-switch + validates the browser
// path at exec time and surfaces failures as 409 / 412 / 422.
export async function actOpenInTor(nodeId: number): Promise<void> {
  try {
    const r = await openNodeInBrowser(nodeId);
    toastStore.show(`Opened in ${r.browser}`);
  } catch (err) {
    toastStore.show(explainApiError(err, 'Open failed'), 'error');
  }
}

// Single-node flag: an analyst right-clicking *is* the confirmation, so
// the row lands as `flagged` (not the watchlist auto-flagger's `pending`).
export async function actFlag(nodeId: number, priority: number): Promise<void> {
  try {
    await createFlag({ node_id: nodeId, status: 'flagged', priority });
    toastStore.show('Node flagged');
    void graphPoller.refresh();
  } catch (err) {
    toastStore.show(explainApiError(err, 'Flag failed'), 'error');
  }
}

export async function actRemoveFlag(nodeId: number): Promise<void> {
  try {
    await clearNodeFlags(nodeId);
    toastStore.show('Flag removed');
    void graphPoller.refresh();
  } catch (err) {
    toastStore.show(explainApiError(err, 'Flag removal failed'), 'error');
  }
}

export async function actToggleReviewed(
  nodeId: number,
  currentReviewed: boolean,
): Promise<void> {
  const next = !currentReviewed;
  try {
    await patchNodeReviewed(nodeId, next);
    toastStore.show(next ? 'Marked reviewed' : 'Marked unreviewed');
    void graphPoller.refresh();
  } catch (err) {
    toastStore.show(explainApiError(err, 'Reviewed toggle failed'), 'error');
  }
}

// Phase B "Send to Crawl" — load the URL into CrawlControls' manual input
// on the Crawl sub-tab. The batch-confirm store buffers the URL if the
// sidebar isn't mounted yet; CrawlSidebar flushes the buffer on mount.
export function actQueueCrawl(url: string): void {
  navigationStore.setLeft('crawl');
  batchConfirmStore.loadIntoControls(url);
  toastStore.show(`Loaded into Crawl: ${url}`);
}

// "Send to Find" — switch the left pane to its Find sub-tab and
// stage the query so the (F5-owned) sidebar drains it on mount. Today
// the Find sub-tab is still a placeholder; the staging buffer makes
// this forward-compatible with F5 without doing F5's work.
export function actSendToFind(query: string): void {
  navigationStore.setLeft('find');
  findPendingStore.load(query);
  toastStore.show(`Loaded into Find: ${query}`);
}

export async function actSaveSeedBookmark(url: string): Promise<void> {
  try {
    const added = await seedBookmarksStore.add({ url });
    toastStore.show(
      added ? 'Saved to crawl bookmarks' : 'Already in crawl bookmarks',
    );
  } catch (err) {
    toastStore.show(explainApiError(err, 'Save bookmark failed'), 'error');
  }
}

// Hide every URL matching this string from the graph (server-side filter).
// Clears ego-focus if it was set on a now-hidden node, then invalidates
// payload caches so the optimistic-apply path on the next tab switch
// can't bring the node back.
export async function actHideFromGraph(url: string): Promise<void> {
  try {
    await addGraphFilter(url);
    toastStore.show('Hidden from graph');
    if (graphStore.egoFocus) graphStore.setEgoFocus(null);
    workspaceSnapshots.invalidatePayloads();
    void graphPoller.refresh();
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      toastStore.show('Already hidden');
      return;
    }
    toastStore.show(explainApiError(err, 'Hide failed'), 'error');
  }
}

// Materialize a URL as an uncrawled (`known`) graph node without crawling,
// flagging, or collecting it. The "pin this discovered onion to the graph"
// verb for Search results, whose rows otherwise never become nodes. Idempotent:
// the backend upsert returns the existing resource if the URL is already known.
export async function actAddToGraph(url: string): Promise<void> {
  try {
    const { id } = await createStubNode({ url });
    // Pin the new node rather than flipping the global `show_uncrawled`
    // toggle: a project with crawl history holds thousands of discovered
    // uncrawled placeholders, and revealing all of them on one click is the
    // opposite of "add THIS one". The pin forces just this id into the
    // canvas; the rest of the halo stays hidden.
    graphPinsStore.pin(id);
    // Symmetry with actHideFromGraph: a structural change to the node set
    // must drop the SWR payload cache, or the next tab switch optimistically
    // re-applies a snapshot that predates this node and the canvas renders
    // without it (the "added but the graph is empty" report).
    workspaceSnapshots.invalidatePayloads();
    toastStore.show('Pinned to graph');
    void graphPoller.refresh();
  } catch (err) {
    toastStore.show(explainApiError(err, 'Add to graph failed'), 'error');
  }
}

// Bulk "Add all to Graph" — materialize every URL as an uncrawled node and pin
// them in one batch. Backs the Search tab's page-level action. Rejects (bad
// onions) are reported but don't sink the batch; only the ids that landed are
// pinned. A no-op on an empty list.
export async function actAddAllToGraph(urls: string[]): Promise<void> {
  if (urls.length === 0) return;
  try {
    const { nodes, invalid } = await createStubNodes(urls);
    graphPinsStore.pinMany(nodes.map((n) => n.id));
    workspaceSnapshots.invalidatePayloads();
    let msg = `Pinned ${nodes.length} ${plural(nodes.length, 'node')} to graph`;
    if (invalid.length > 0) msg += ` (${invalid.length} skipped)`;
    toastStore.show(`${msg}.`);
    void graphPoller.refresh();
  } catch (err) {
    toastStore.show(explainApiError(err, 'Add all to graph failed'), 'error');
  }
}

// Toggle a node's pin. Drives the graph node menu's Pin / Unpin row — the
// removal path for an uncrawled pin (Hide from Graph is crawled-only). No
// network: pins are a client-side, persisted view concern.
export function actTogglePin(nodeId: number): void {
  if (graphPinsStore.has(nodeId)) {
    graphPinsStore.unpin(nodeId);
    toastStore.show('Unpinned from graph');
  } else {
    graphPinsStore.pin(nodeId);
    toastStore.show('Pinned to graph');
  }
}

// Rename whatever target it's handed. The single save path for every rename
// surface: it owns the unified post-save effect (success toast + graph
// refresh) so the new name appears everywhere consistently. It *throws* on
// failure (rather than swallowing into a toast) so the popover can keep
// rendering inline 409/400 validation and stay open. The graph's optional
// instant label-repaint stays with the surface, layered on top of — not
// instead of — this refresh.
export async function renameTarget(
  target: RenameTarget,
  alias: string | null,
): Promise<void> {
  if (target.kind === 'domain') {
    await patchDomainAlias(target.host, alias);
  } else {
    // Page rename — keyed by resource id, on the same seam (item 11, D1).
    await patchPageAlias(target.pageId, alias);
  }
  toastStore.show(alias ? `Renamed to ${alias}` : 'Alias cleared');
  void graphPoller.refresh();
}

// Attach or detach one label on whatever target it's handed (item 11), keyed
// by the typed join table the target maps to. Returns whether a row actually
// changed (attach/detach are idempotent server-side). Throws on API failure so
// the picker can keep its checkbox state honest. The graph refresh is the
// caller's call — toggling a dozen labels then refreshing once on close beats
// a poll per click.
export async function setLabel(
  target: LabelTarget,
  labelId: number,
  on: boolean,
): Promise<boolean> {
  if (target.kind === 'resource') {
    return on
      ? labelsStore.attachResource(labelId, target.resourceId)
      : labelsStore.detachResource(labelId, target.resourceId);
  }
  return on
    ? labelsStore.attachDomain(labelId, target.host)
    : labelsStore.detachDomain(labelId, target.host);
}

// ---------------- Multi-target actions ----------------

// Phase B "Send to Crawl" (multi-select). Stages the URLs in the batch-
// confirm strip; the analyst confirms mode / collection / depth before
// any row enters the queue (no silent push). Re-crawl is intentional —
// available regardless of stub state under Option B.
export function actCrawlSelected(
  nodes: GraphNode[],
  sourceLabel = 'Graph selection',
): void {
  if (nodes.length === 0) return;
  navigationStore.setLeft('crawl');
  batchConfirmStore.stage({
    source: 'graph_menu',
    sourceLabel,
    urls: nodes.map((n) => n.raw_url),
  });
  toastStore.show(
    `Staged ${nodes.length} ${plural(nodes.length, 'URL')} in Crawl tab.`,
  );
}

// Flag every selected node that isn't already flagged. Already-flagged
// nodes are skipped because the backend doesn't dedupe on (node_id,
// status) — a naive batch would multiply rows on repeat clicks. The
// settled-only reporting keeps the toast honest if a single call 500s.
export async function actFlagAll(nodes: GraphNode[]): Promise<void> {
  const toFlag = nodes.filter((n) => !n.flag_status);
  const already = nodes.length - toFlag.length;
  const results = await Promise.allSettled(
    // Bulk flag → analyst-confirmed `flagged` at default Medium priority;
    // per-item severity on a batch action is overkill.
    toFlag.map((n) => createFlag({ node_id: n.id, status: 'flagged' })),
  );
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  let msg = `Flagged ${ok} ${plural(ok, 'node')}`;
  const notes: string[] = [];
  if (already > 0) notes.push(`${already} already flagged`);
  if (failed > 0) notes.push(`${failed} failed`);
  if (notes.length > 0) msg += ` (${notes.join(', ')})`;
  toastStore.show(`${msg}.`);
  void graphPoller.refresh();
}

// Mark every crawled (non-stub) node reviewed. Stubs are filtered out
// because the column is meaningless on them — the analyst hasn't read
// content that doesn't exist yet.
export async function actMarkReviewedAll(nodes: GraphNode[]): Promise<void> {
  const crawled = nodes.filter((n) => !isUncrawled(n));
  const toMark = crawled.filter((n) => !n.reviewed);
  const already = crawled.length - toMark.length;
  const uncrawledExcluded = nodes.length - crawled.length;
  const results = await Promise.allSettled(
    toMark.map((n) => patchNodeReviewed(n.id, true)),
  );
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  let msg = `Marked ${ok} reviewed`;
  const notes: string[] = [];
  if (already > 0) notes.push(`${already} already reviewed`);
  if (uncrawledExcluded > 0) notes.push(`${uncrawledExcluded} uncrawled excluded`);
  if (failed > 0) notes.push(`${failed} failed`);
  if (notes.length > 0) msg += ` (${notes.join(', ')})`;
  toastStore.show(`${msg}.`);
  void graphPoller.refresh();
}

// Add every crawled URL to the server-side graph filter. Stubs have no
// canonical record yet, so adding them as filter terms would hide the
// stub but leave the eventual crawled page un-hidden — exclude them.
export async function actHideAll(nodes: GraphNode[]): Promise<void> {
  const crawled = nodes.filter((n) => !isUncrawled(n));
  const uncrawledExcluded = nodes.length - crawled.length;
  const results = await Promise.allSettled(
    crawled.map((n) => addGraphFilter(n.raw_url)),
  );
  let ok = 0;
  let already = 0;
  let failed = 0;
  for (const r of results) {
    if (r.status === 'fulfilled') {
      ok++;
    } else if (r.reason instanceof ApiError && r.reason.status === 409) {
      already++;
    } else {
      failed++;
    }
  }
  let msg = `Hidden ${ok} from graph`;
  const notes: string[] = [];
  if (already > 0) notes.push(`${already} already hidden`);
  if (uncrawledExcluded > 0) notes.push(`${uncrawledExcluded} uncrawled excluded`);
  if (failed > 0) notes.push(`${failed} failed`);
  if (notes.length > 0) msg += ` (${notes.join(', ')})`;
  toastStore.show(`${msg}.`);
  if (graphStore.egoFocus) graphStore.setEgoFocus(null);
  if (ok > 0) workspaceSnapshots.invalidatePayloads();
  void graphPoller.refresh();
}

// ============================================================
// Multi-target Selection helpers (shared-ui-primitives phase)
// ============================================================
//
// Every command surface (ActionBar, context menus, keyboard shortcuts)
// should call these rather than re-implementing command logic. The
// `Selection` shape is caller-agnostic — it doesn't matter whether the
// targets came from a graph multi-select, a bottom-pane row, or a
// right-pane action.

/** Uniform selection shape for all multi-target verb helpers. */
export interface Selection {
  nodes: GraphNode[];
  /** Raw URLs; may contain entries for nodes not present in the graph payload. */
  urls: string[];
}

/** Build a Selection from a single GraphNode. */
export function selectionFromNode(node: GraphNode): Selection {
  return { nodes: [node], urls: [node.raw_url] };
}

/** Build a Selection from a list of GraphNodes. */
export function selectionFromNodes(nodes: GraphNode[]): Selection {
  return { nodes, urls: nodes.map((n) => n.raw_url) };
}

// ---------------- Verb helpers (targets form) ----------------

/**
 * Stage the selection's URLs in the CrawlControls batch-confirm strip
 * and switch the left pane to Crawl.
 */
export function sendToCrawl(
  targets: Selection,
  sourceLabel = 'Selection',
): void {
  if (targets.urls.length === 0) return;
  if (targets.urls.length === 1) {
    actQueueCrawl(targets.urls[0]);
    return;
  }
  actCrawlSelected(targets.nodes, sourceLabel);
}

/**
 * Add every node in the selection to the given collection.
 * Already-added nodes are skipped (409 is silently ignored).
 */
export async function addToCollection(
  targets: Selection,
  collectionId: number,
): Promise<void> {
  if (targets.nodes.length === 0) return;
  try {
    await addItemsToCollection(
      collectionId,
      targets.nodes.map((n) => n.id),
    );
    toastStore.show(
      `Added ${targets.nodes.length} ${plural(targets.nodes.length, 'node')} to collection.`,
    );
  } catch (err) {
    toastStore.show(explainError(err, 'Add to collection failed'), 'error');
  }
}

/**
 * Remove every node in the selection from the given collection.
 */
export async function removeFromCollection(
  targets: Selection,
  collectionId: number,
): Promise<void> {
  if (targets.nodes.length === 0) return;
  const results = await Promise.allSettled(
    targets.nodes.map((n) => removeItemFromCollection(collectionId, n.id)),
  );
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  let msg = `Removed ${ok} from collection`;
  if (failed > 0) msg += ` (${failed} failed)`;
  toastStore.show(`${msg}.`);
}

/**
 * Flag every node in the selection that isn't already flagged.
 */
export async function flag(targets: Selection): Promise<void> {
  if (targets.nodes.length === 0) return;
  await actFlagAll(targets.nodes);
}

/**
 * Remove flags from every node in the selection.
 */
export async function removeFlag(targets: Selection): Promise<void> {
  if (targets.nodes.length === 0) return;
  const results = await Promise.allSettled(
    targets.nodes.map((n) => clearNodeFlags(n.id)),
  );
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  let msg = `Removed ${ok} ${plural(ok, 'flag')}`;
  if (failed > 0) msg += ` (${failed} failed)`;
  toastStore.show(`${msg}.`);
  void graphPoller.refresh();
}

/**
 * Queue an analysis: stage the selection as the Intel compose target and
 * switch the left pane to the Intel sub-tab, where ComposeForm picks it up
 * pre-populated. This is the single funnel — every surface that wants to
 * "Queue Analysis" routes here rather than re-implementing type/model choice.
 *
 * Pure staging (no network); the analyst confirms type/model and submits in
 * the compose form. Empty selections are a no-op.
 */
export function queueAnalysis(targets: Selection, sourceLabel = 'Selection'): void {
  if (targets.nodes.length === 0) return;
  intelComposeStore.stage(targetFromNodes(targets.nodes, sourceLabel));
  navigationStore.setLeft('intel');
  toastStore.show(
    `Staged ${targets.nodes.length} ${plural(targets.nodes.length, 'node')} in Intel.`,
  );
}

/**
 * Queue Analysis from raw node ids — for surfaces (e.g. the Search tab) that
 * hold a crawled node id but not a full GraphNode. Same funnel as
 * {@link queueAnalysis}: stage the target and switch to the Intel sub-tab.
 */
export function queueAnalysisIds(nodeIds: number[], sourceLabel = 'Selection'): void {
  if (nodeIds.length === 0) return;
  intelComposeStore.stage(targetFromIds(nodeIds, sourceLabel));
  navigationStore.setLeft('intel');
  toastStore.show(
    `Staged ${nodeIds.length} ${plural(nodeIds.length, 'node')} in Intel.`,
  );
}

/**
 * Copy all URLs in the selection to the clipboard, newline-separated.
 */
export async function copyUrls(targets: Selection): Promise<void> {
  if (targets.urls.length === 0) return;
  try {
    await copyToClipboard(targets.urls.join('\n'));
    toastStore.show(
      `Copied ${targets.urls.length} ${plural(targets.urls.length, 'URL')}.`,
    );
  } catch (err) {
    toastStore.show(explainError(err, 'Copy failed'), 'error');
  }
}

/**
 * Hide all URLs in the selection from the graph.
 */
export async function hide(targets: Selection): Promise<void> {
  if (targets.nodes.length === 0) return;
  await actHideAll(targets.nodes);
}

/**
 * Mark all crawled nodes in the selection as reviewed.
 */
export async function markReviewed(
  targets: Selection,
  reviewed: boolean,
): Promise<void> {
  if (targets.nodes.length === 0) return;
  if (reviewed) {
    await actMarkReviewedAll(targets.nodes);
    return;
  }
  // Mark unreviewed — no existing multi-helper, implement inline.
  const crawled = targets.nodes.filter((n) => !isUncrawled(n));
  const uncrawledExcluded = targets.nodes.length - crawled.length;
  const results = await Promise.allSettled(
    crawled.map((n) => patchNodeReviewed(n.id, false)),
  );
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  let msg = `Marked ${ok} unreviewed`;
  const notes: string[] = [];
  if (uncrawledExcluded > 0) notes.push(`${uncrawledExcluded} uncrawled excluded`);
  if (failed > 0) notes.push(`${failed} failed`);
  if (notes.length > 0) msg += ` (${notes.join(', ')})`;
  toastStore.show(`${msg}.`);
  void graphPoller.refresh();
}

/**
 * Set analysis_excluded on all nodes in the selection.
 */
export async function setAnalysisExcluded(
  targets: Selection,
  excluded: boolean,
): Promise<void> {
  if (targets.nodes.length === 0) return;
  const results = await Promise.allSettled(
    targets.nodes.map((n) => patchNodeAnalysisExcluded(n.id, excluded)),
  );
  const ok = results.filter((r) => r.status === 'fulfilled').length;
  const failed = results.length - ok;
  let msg = excluded
    ? `Excluded ${ok} from analysis`
    : `Un-excluded ${ok} from analysis`;
  if (failed > 0) msg += ` (${failed} failed)`;
  toastStore.show(`${msg}.`);
}
