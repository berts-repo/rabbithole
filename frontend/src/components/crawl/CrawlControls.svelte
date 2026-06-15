<script lang="ts">
  import { onMount, untrack } from 'svelte';
  import { Star, Plus, X, Square, Play } from 'lucide-svelte';
  import { TextButton } from '$lib/ui';
  import {
    listCollections,
    createCollection,
    listWatchlist,
    enqueueCrawl,
    stopCrawl,
    getSetting,
    putSetting,
    type Seed,
    type Collection,
  } from '$lib/api';
  import { isSupportedUrl } from '$lib/onionUrl';
  import { crawlStore } from '$lib/stores/crawl.svelte';
  import { crawlStatusPoller } from '$lib/pollers/crawlStatus.svelte';
  import { servicesStore } from '$lib/stores/services.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { workspaceStore } from '$lib/stores/workspace.svelte';
  import { seedBookmarksStore } from '$lib/stores/seedBookmarks.svelte';
  import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';

  type Mode = 'Cross-site' | 'BFS' | 'DFS' | 'Diverse' | 'Focused';
  type Pacing = 'fast' | 'polite' | 'stealth';

  type Props = {
    seedUrl: string;
    onOpenSettings: () => void;
  };

  let { seedUrl = $bindable(''), onOpenSettings }: Props = $props();

  const MODES: { id: Mode; label: string; blurb: string }[] = [
    {
      id: 'Cross-site',
      label: 'Cross-site',
      blurb: 'Prioritises links that lead to new .onion hosts. Good for broad discovery.',
    },
    { id: 'BFS', label: 'BFS', blurb: 'Breadth-first. Maps a site completely.' },
    { id: 'DFS', label: 'DFS', blurb: 'Depth-first. Finds buried content.' },
    { id: 'Diverse', label: 'Diverse', blurb: 'Balances across many sites. Good for wide surveys.' },
    {
      id: 'Focused',
      label: 'Focused',
      blurb: 'Scores by Watchlist relevance.',
    },
  ];

  // Crawl request cadence — persisted via the `crawl.pacing` setting and read
  // by the backend crawl runtime at crawl start. `polite` is the default.
  const PACING: { id: Pacing; label: string }[] = [
    { id: 'fast', label: 'Fast — no delay' },
    { id: 'polite', label: 'Polite — short delay' },
    { id: 'stealth', label: 'Stealth — human-paced' },
  ];

  let mode = $state<Mode>('Cross-site');
  let stayOnDomain = $state(false);
  let pacing = $state<Pacing>('polite');

  // Depth cap (privacy / blast-radius hardening — see plan.md audit-trail
  // item 2). Default 3 matches the backend's DEFAULT_MAX_DEPTH; flipping
  // "Unlimited" sends max_depth=null so the analyst explicitly opted in.
  const DEFAULT_MAX_DEPTH = 3;
  let maxDepth = $state<number>(DEFAULT_MAX_DEPTH);
  let depthUnlimited = $state(false);

  let collectionId = $state<'none' | 'new' | number>('none');
  let newCollectionName = $state('');
  let collections = $state<Collection[]>([]);

  let bookmarksOpen = $state(false);
  let savePopoverOpen = $state(false);
  let bookmarkLabel = $state('');

  let watchlistCount = $state<number | null>(null);

  let starting = $state(false);
  let stopping = $state(false);
  let elapsedTick = $state(0);

  // Load collections + seeds on mount. Watchlist is lazy — fetched the first
  // time mode flips to Focused.
  $effect(() => {
    void refreshCollections();
    void seedBookmarksStore.refresh();
    void loadPacing();
  });

  // Expose the current control values to the batch-confirm strip so a
  // multi-row staging op picks up the analyst's existing mode / collection
  // / depth choice as the batch defaults.
  onMount(() => {
    batchConfirmStore.setControlsSnapshot(() => ({
      mode,
      stayOnDomain,
      maxDepth: depthUnlimited ? null : maxDepth,
      collectionId: typeof collectionId === 'number' ? collectionId : null,
      collectionNamePending:
        collectionId === 'new' && newCollectionName.trim()
          ? newCollectionName.trim()
          : null,
    }));
    return () => {
      batchConfirmStore.setControlsSnapshot(null);
    };
  });

  $effect(() => {
    if (mode === 'Focused' && watchlistCount === null) {
      void refreshWatchlist();
    }
  });

  // Cross-site forces stayOnDomain off (mutually exclusive).
  $effect(() => {
    if (mode === 'Cross-site') stayOnDomain = false;
  });

  // Tick once per second while running so the elapsed counter updates.
  $effect(() => {
    if (!crawlStore.running) return;
    const id = setInterval(() => {
      elapsedTick++;
    }, 1000);
    return () => clearInterval(id);
  });

  // Default the "Add results to collection" dropdown to the active
  // workspace's collection when the user hasn't picked anything yet
  // ('none'). We only reset back to 'none' when our own suggestion is
  // still in place — explicit picks (number or 'new') are left alone.
  let lastSuggestedId: number | null = null;
  $effect(() => {
    const active = workspaceStore.activeCollectionId();
    untrack(() => {
      if (active === null) {
        if (
          lastSuggestedId !== null &&
          collectionId === lastSuggestedId
        ) {
          collectionId = 'none';
        }
        lastSuggestedId = null;
        return;
      }
      if (collectionId === 'none' || collectionId === lastSuggestedId) {
        collectionId = active;
        lastSuggestedId = active;
      }
    });
  });

  async function refreshCollections() {
    try {
      const r = await listCollections();
      collections = r.collections;
    } catch {
      collections = [];
    }
  }

  async function loadPacing() {
    try {
      const r = await getSetting<Pacing>('crawl.pacing');
      if (r.value === 'fast' || r.value === 'polite' || r.value === 'stealth') {
        pacing = r.value;
      }
    } catch {
      // Leave the 'polite' default in place.
    }
  }

  async function persistPacing() {
    try {
      await putSetting('crawl.pacing', pacing);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Could not save pacing: ${msg}`, 'error');
    }
  }

  async function refreshWatchlist() {
    try {
      const r = await listWatchlist();
      watchlistCount = r.terms.length;
    } catch {
      watchlistCount = 0;
    }
  }

  const focusedWithoutTerms = $derived(
    mode === 'Focused' && watchlistCount !== null && watchlistCount === 0,
  );

  // A crawl must not be launched while the kill switch is engaged — the
  // analyst re-arms (after Tor recovers) before starting.
  const killSwitchArmed = $derived(servicesStore.killSwitch.phase === 'armed');

  const canStart = $derived(
    !crawlStore.running &&
      !starting &&
      isSupportedUrl(seedUrl) &&
      !focusedWithoutTerms &&
      killSwitchArmed,
  );

  async function onStart() {
    if (!canStart) return;
    starting = true;
    try {
      let resolvedCollectionId: number | null = null;
      if (typeof collectionId === 'number') {
        resolvedCollectionId = collectionId;
      } else if (collectionId === 'new') {
        if (!newCollectionName.trim()) {
          toastStore.show('Name the new collection or pick one.', 'warn');
          starting = false;
          return;
        }
        const created = await createCollection({ name: newCollectionName.trim() });
        resolvedCollectionId = created.id;
        await refreshCollections();
        collectionId = created.id;
        newCollectionName = '';
      }
      // priority=1000 keeps the manual Start row ahead of background
      // producers (scheduled fires at priority=0). The runner advances on
      // insert when idle, so queue + immediate dispatch is unchanged.
      const { results } = await enqueueCrawl({
        url: seedUrl.trim(),
        mode,
        source: 'manual',
        max_depth: depthUnlimited ? null : maxDepth,
        collection_id: resolvedCollectionId,
        priority: 1000,
      });
      const result = results[0];
      if (!result?.inserted) {
        const reason = result?.reason ?? 'unknown';
        const msg =
          reason === 'duplicate_active'
            ? 'This URL is already queued or running.'
            : reason === 'bad_url'
              ? `Bad URL: ${result?.message ?? 'invalid'}`
              : `Start failed: ${reason}`;
        toastStore.show(msg, 'warn');
        return;
      }
      // Open/activate the targeted collection's workspace tab so the
      // analyst gets immediate visual feedback. For the 'new' branch we
      // synthesise a Collection shape from the create response since
      // listCollections may not have refreshed yet.
      if (resolvedCollectionId !== null) {
        const row =
          collections.find((c) => c.id === resolvedCollectionId) ?? null;
        if (row) {
          workspaceStore.openCollectionTab(row);
        } else {
          void workspaceStore.openCollectionTabById(resolvedCollectionId);
        }
      }
      crawlStatusPoller.pokeOnce();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Start failed: ${msg}`, 'error');
    } finally {
      starting = false;
    }
  }

  async function onStop() {
    stopping = true;
    try {
      await stopCrawl();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Stop failed: ${msg}`, 'error');
    } finally {
      stopping = false;
    }
  }

  async function onSaveBookmark() {
    const url = seedUrl.trim();
    if (!isSupportedUrl(url)) {
      toastStore.show('Enter a valid .onion or .i2p URL first.', 'warn');
      return;
    }
    try {
      const added = await seedBookmarksStore.add({
        url,
        label: bookmarkLabel.trim() || null,
      });
      savePopoverOpen = false;
      bookmarkLabel = '';
      toastStore.show(added ? 'Bookmark saved.' : 'Already in crawl bookmarks.', 'info');
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Save failed: ${msg}`, 'error');
    }
  }

  async function onDeleteSeed(url: string) {
    try {
      await seedBookmarksStore.remove(url);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Delete failed: ${msg}`, 'error');
    }
  }

  function pickSeed(s: Seed) {
    seedUrl = s.url;
    bookmarksOpen = false;
  }

  const row = $derived(crawlStore.polledActiveRow);
  const elapsedLabel = $derived(formatElapsed(row?.started_at, elapsedTick));

  function formatElapsed(startedAt: string | null | undefined, _tick: number): string {
    if (!startedAt) return '0s';
    const start = Date.parse(startedAt);
    if (Number.isNaN(start)) return '—';
    const secs = Math.max(0, Math.floor((Date.now() - start) / 1000));
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
  }
</script>

<div class="controls">
  <div class="seed-row">
    <input
      type="text"
      data-crawl-seed-url
      bind:value={seedUrl}
      placeholder="http://abc…xyz.onion/"
      onkeydown={(e) => {
        if (e.key === 'Enter') void onStart();
      }}
    />
    <button
      type="button"
      class="icon-btn"
      aria-label="Saved seeds"
      title="Saved seeds"
      onclick={() => {
        bookmarksOpen = !bookmarksOpen;
        savePopoverOpen = false;
      }}
    >
      <Star size={14} />
    </button>
    <button
      type="button"
      class="icon-btn"
      aria-label="Save current URL"
      title="Save current URL"
      onclick={() => {
        savePopoverOpen = !savePopoverOpen;
        bookmarksOpen = false;
      }}
    >
      <Plus size={14} />
    </button>
  </div>

  {#if bookmarksOpen}
    <div class="popover">
      {#if seedBookmarksStore.seeds.length === 0}
        <p class="empty">No saved seeds.</p>
      {:else}
        <ul>
          {#each seedBookmarksStore.seeds as s (s.url)}
            <li>
              <button type="button" class="seed-row-btn" onclick={() => pickSeed(s)}>
                <span class="seed-label">{s.label || '(unlabeled)'}</span>
                <span class="seed-url">{s.url}</span>
              </button>
              <button
                type="button"
                class="del"
                aria-label="Delete {s.url}"
                onclick={() => onDeleteSeed(s.url)}
              >
                <X size={12} />
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}

  {#if savePopoverOpen}
    <div class="popover">
      <label>
        <span>Label (optional)</span>
        <input type="text" bind:value={bookmarkLabel} placeholder="Forum tip" />
      </label>
      <TextButton variant="primary" onclick={onSaveBookmark}>Save</TextButton>
    </div>
  {/if}

  <label class="field">
    <span>Mode</span>
    <select bind:value={mode}>
      {#each MODES as m (m.id)}
        <option value={m.id}>{m.label}</option>
      {/each}
    </select>
  </label>

  {#if mode === 'Focused'}
    {#if focusedWithoutTerms}
      <p class="note warn">
        ⚠ No Watchlist terms configured — Focused mode has no signal. Add terms in Settings → Watchlist before starting.
      </p>
    {:else}
      <p class="note">
        Focused mode uses your Watchlist terms as the relevance signal. Pages matching more terms are crawled first.
        <button type="button" class="link" onclick={onOpenSettings}>Manage watchlist →</button>
      </p>
    {/if}
  {/if}

  <label class="field" title="Cap how many link-hops away from the seed the crawler will follow. Lower = tighter; Unlimited may pull in tens of thousands of pages from adversary-controlled honeypots.">
    <span>Max depth</span>
    <div class="depth-row">
      <input
        type="number"
        min="1"
        max="20"
        bind:value={maxDepth}
        disabled={depthUnlimited}
      />
      <label class="depth-toggle">
        <input type="checkbox" bind:checked={depthUnlimited} />
        <span>Unlimited</span>
      </label>
    </div>
  </label>

  {#if depthUnlimited}
    <p class="note warn">⚠ Unlimited depth — this crawl can run indefinitely.</p>
  {/if}

  <label class="field checkbox" title={mode === 'Cross-site' ? 'Cross-site mode follows links across domains — disable it to use Stay on domain.' : ''}>
    <input
      type="checkbox"
      bind:checked={stayOnDomain}
      disabled={mode === 'Cross-site'}
    />
    <span>Stay on domain</span>
  </label>

  <label class="field" title="How fast the crawler issues requests. Stealth spaces fetches at human scale for targets that watch their logs.">
    <span>Pacing</span>
    <select bind:value={pacing} onchange={() => void persistPacing()}>
      {#each PACING as p (p.id)}
        <option value={p.id}>{p.label}</option>
      {/each}
    </select>
  </label>

  <label class="field">
    <span>Add results to collection</span>
    <select bind:value={collectionId}>
      <option value="none">— none —</option>
      {#each collections as c (c.id)}
        <option value={c.id}>{c.name}</option>
      {/each}
      <option value="new">+ New collection…</option>
    </select>
  </label>

  {#if collectionId === 'new'}
    <div class="new-collection">
      <input type="text" bind:value={newCollectionName} placeholder="Collection name" />
    </div>
  {/if}

  <div class="actions">
    <TextButton
      variant="primary"
      disabled={!canStart}
      title={!killSwitchArmed
        ? 'Kill switch engaged — re-arm after Tor recovers to start a crawl.'
        : ''}
      onclick={onStart}
    >
      {#snippet icon()}<Play size={12} />{/snippet}
      {starting ? 'Starting…' : 'Start'}
    </TextButton>
    <button
      type="button"
      class="danger"
      disabled={!crawlStore.running || stopping}
      onclick={onStop}
    >
      <Square size={12} />
      {stopping ? 'Stopping…' : 'Stop'}
    </button>
  </div>

  {#if crawlStore.running && row}
    <div class="status">
      <div class="status-seed" title={row.seed_url}>{row.seed_url}</div>
      <div class="status-counts">
        <span class="count crawled">{row.pages_crawled} crawled</span>
        <span class="count failed">{row.pages_failed} failed</span>
        <span class="count queued">{row.pages_queued} queued</span>
        <span class="elapsed">· {elapsedLabel}</span>
      </div>
    </div>
  {/if}
</div>

<style>
  .controls {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .seed-row {
    display: flex;
    gap: 4px;
  }
  .seed-row input {
    flex: 1;
    min-width: 0;
  }
  input,
  select {
    background: #17191f;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 7px;
    font-size: 11px;
    width: 100%;
  }
  option {
    background: #17191f;
    color: var(--text);
  }
  input:focus-visible,
  select:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .icon-btn {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 6px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
  }
  .icon-btn:hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .popover {
    border: 1px solid var(--border);
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-height: 200px;
    overflow-y: auto;
  }
  .popover ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .popover li {
    display: flex;
    gap: 4px;
    align-items: stretch;
  }
  .seed-row-btn {
    flex: 1;
    text-align: left;
    background: transparent;
    border: 1px solid transparent;
    color: inherit;
    padding: 4px 6px;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .seed-row-btn:hover {
    border-color: var(--border);
  }
  .seed-label {
    color: var(--text);
    font-size: 11px;
  }
  .seed-url {
    color: var(--muted);
    font-size: 10px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .del {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 0 6px;
    cursor: pointer;
  }
  .del:hover {
    color: #ff5577;
    border-color: #ff5577;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 10px;
    color: var(--muted);
  }
  .field.checkbox {
    flex-direction: row;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text);
  }
  .field.checkbox input {
    width: auto;
  }
  .depth-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .depth-row input[type='number'] {
    flex: 0 0 64px;
  }
  .depth-row input[type='number']:disabled {
    opacity: 0.45;
  }
  .depth-toggle {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--text);
    cursor: pointer;
  }
  .depth-toggle input {
    width: auto;
  }
  .note {
    margin: 0;
    padding: 6px 8px;
    border-left: 2px solid var(--accent);
    background: var(--accent-bg-subtle);
    font-size: 11px;
    color: var(--text);
  }
  .note.warn {
    border-left-color: #ffb347;
    background: rgba(255, 179, 71, 0.06);
    color: #ffd58a;
  }
  .link {
    background: transparent;
    border: none;
    color: var(--accent);
    cursor: pointer;
    padding: 0;
    font-size: inherit;
    text-decoration: underline;
  }
  .new-collection input {
    width: 100%;
  }
  .actions {
    display: flex;
    gap: 6px;
  }
  /* Stretch both the native danger button and the TextButton component equally. */
  .actions > :global(*) {
    flex: 1;
    justify-content: center;
  }
  .actions button {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 10px;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    font-size: 11px;
  }
  .actions button:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .actions .danger {
    border-color: #ff5577;
    color: #ffb3c0;
  }
  .actions .danger:hover:not(:disabled) {
    background: rgba(255, 85, 119, 0.1);
  }
  .status {
    border: 1px solid var(--border);
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 11px;
  }
  .status-seed {
    color: var(--accent);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status-counts {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    color: var(--muted);
  }
  .count.crawled {
    color: var(--accent);
  }
  .count.failed {
    color: #ffb3c0;
  }
  .count.queued {
    color: var(--text);
  }
</style>
