<script lang="ts">
  // Right pane — Domain tab (F6 phase 2).
  //
  // Scoped to the selected node's `.onion` host. Loads node detail (for
  // the host), domain profile, pages, entities, and monitors in parallel
  // on every host change. Stub nodes get a simplified branch: monitors
  // remain fully functional; profile + pages render "Not yet crawled."
  //
  // Spec: docs/specs/right-pane.md:121-189.

  import { Pause, Play, Tag, X } from 'lucide-svelte';
  import {
    ApiError,
    compareDomainSnapshots,
    createMonitor,
    deleteMonitor,
    getDomainProfile,
    getNode,
    listDomainEntities,
    listDomainPages,
    listDomainSnapshots,
    listMonitors,
    patchMonitor,
    type DomainComparePage,
    type DomainComparison,
    type DomainEntity,
    type DomainPage,
    type DomainProfile,
    type Monitor,
    type NodeRow,
  } from '$lib/api';
  import ContextMenu from '$lib/contextMenu/ContextMenu.svelte';
  import { bottomPanePresetStore } from '$lib/stores/bottomPanePreset.svelte';
  import { selectionStore } from '$lib/stores/selection.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { isUncrawled } from '$lib/nodeState';
  import { CollapsibleSection, EmptyState, IconButton } from '$lib/ui';
  import { createCollapseStore } from '$lib/stores/sectionCollapse.svelte';
  import { explainError } from '$lib/api/errors';
  import {
    buildSparkline,
    SPARKLINE_HEIGHT,
    SPARKLINE_WIDTH,
  } from '$lib/sparkline';
  import { buildEntityMenu } from './entityMenu';
  import type { MenuSection } from '$lib/contextMenu/ContextMenu.svelte';
  import LabelChips from '../../components/labels/LabelChips.svelte';
  import LabelPickerPopover from '../../components/labels/LabelPickerPopover.svelte';
  import { labelPickerModal, type LabelPickerModal } from '$lib/contextMenu/actions';
  import { graphPoller } from '$lib/pollers/graph.svelte';

  const sections = createCollapseStore('rabbithole.right.domain');

  // ---------------- Per-selection load ----------------

  let node = $state<NodeRow | null>(null);
  let profile = $state<DomainProfile | null>(null);
  let pages = $state<DomainPage[]>([]);
  let entities = $state<DomainEntity[]>([]);
  let monitors = $state<Monitor[]>([]);
  let loading = $state(false);
  let loadError = $state<string | null>(null);
  let fetchGen = 0;

  let rootEl = $state<HTMLDivElement | null>(null);

  // ---------------- Snapshot comparison (Phase 5) ----------------

  let snapshots = $state<string[]>([]);
  let cmpFrom = $state<string | null>(null);
  let cmpTo = $state<string | null>(null);
  let comparison = $state<DomainComparison | null>(null);
  let cmpLoading = $state(false);
  let cmpError = $state<string | null>(null);

  async function runCompare(): Promise<void> {
    if (!profile || !cmpFrom || !cmpTo) return;
    if (cmpFrom === cmpTo) {
      cmpError = 'Pick two different dates.';
      comparison = null;
      return;
    }
    cmpError = null;
    cmpLoading = true;
    try {
      comparison = await compareDomainSnapshots(profile.host, cmpFrom, cmpTo);
    } catch (err) {
      comparison = null;
      cmpError = explainError(err, 'Compare failed');
    } finally {
      cmpLoading = false;
    }
  }

  function selectComparePage(p: DomainComparePage): void {
    // Highlight-only per spec, matching the Pages list. The analyst can
    // switch to the Page tab to see the two versions diffed.
    selectionStore.highlight(p.resource_id);
  }

  $effect(() => {
    const id = selectionStore.selectedNodeId;
    void load(id);
  });

  async function load(id: number | null): Promise<void> {
    const gen = ++fetchGen;
    if (id === null) {
      reset();
      return;
    }
    loading = true;
    loadError = null;
    try {
      const n = await getNode(id);
      if (gen !== fetchGen) return;
      node = n;
      const host = n.domain;
      if (!host) {
        // Crawled node without a parsed host — extremely rare, treat as
        // empty domain context rather than as an error.
        profile = null;
        pages = [];
        entities = [];
        monitors = [];
        return;
      }
      // Profile + entities + monitors always work. Pages 404 for stub
      // hosts whose domain row exists but whose only nodes are stubs —
      // catch them so a missing list doesn't blank the whole tab.
      const [p, e, m, pg, snap] = await Promise.all([
        getDomainProfile(host).catch((err) => {
          if (err instanceof ApiError && err.status === 404) return null;
          throw err;
        }),
        listDomainEntities(host).catch((err) => {
          if (err instanceof ApiError && err.status === 404) {
            return { entities: [] };
          }
          throw err;
        }),
        listMonitors(host).catch((err) => {
          // Monitor list never 404s, but be defensive.
          if (err instanceof ApiError && err.status === 404) {
            return { monitors: [] };
          }
          throw err;
        }),
        listDomainPages(host).catch((err) => {
          if (err instanceof ApiError && err.status === 404) {
            return { pages: [] };
          }
          throw err;
        }),
        listDomainSnapshots(host).catch((err) => {
          if (err instanceof ApiError && err.status === 404) {
            return { dates: [] };
          }
          throw err;
        }),
      ]);
      if (gen !== fetchGen) return;
      profile = p;
      entities = e.entities;
      monitors = m.monitors;
      pages = pg.pages;
      // Seed the compare picker to previous → latest crawl date.
      snapshots = snap.dates;
      comparison = null;
      cmpError = null;
      cmpTo = snap.dates[0] ?? null;
      cmpFrom = snap.dates[1] ?? null;
    } catch (err) {
      if (gen !== fetchGen) return;
      reset();
      loadError =
        err instanceof Error ? err.message : 'Load failed';
    } finally {
      if (gen === fetchGen) loading = false;
    }
  }

  function reset(): void {
    node = null;
    profile = null;
    pages = [];
    entities = [];
    monitors = [];
    loading = false;
    loadError = null;
    snapshots = [];
    comparison = null;
    cmpError = null;
    cmpFrom = null;
    cmpTo = null;
  }

  // ---------------- Profile + sparkline ----------------

  let sparkline = $derived(
    buildSparkline(profile?.activity ?? [], SPARKLINE_WIDTH, SPARKLINE_HEIGHT),
  );

  // "Up" iff the last status is exactly 200; otherwise show the numeric
  // status (red), or `–` when no monitor has reported yet.
  let uptimeLabel = $derived.by(() => {
    const s = profile?.last_status ?? null;
    if (s === null) return { text: '–', tone: 'muted' as const };
    if (s === 200) return { text: 'Up', tone: 'good' as const };
    return { text: String(s), tone: 'bad' as const };
  });

  // ---------------- Pages list ----------------

  // Cap warning: backend caps at 200; profile carries the true count.
  let overCap = $derived(
    profile !== null && pages.length === 200 && profile.page_count > 200,
  );

  function selectPageRow(p: DomainPage): void {
    // Highlight-only per spec — does not move the bottom-pane active row.
    selectionStore.highlight(p.id);
  }

  function viewAllInDomainsTab(): void {
    if (!profile) return;
    bottomPanePresetStore.send('domains', profile.host);
    toastStore.show(`Filtered Domains by ${profile.host}`);
  }

  function viewFingerprintsForHost(): void {
    if (!profile) return;
    bottomPanePresetStore.send('fingerprints', profile.host);
    toastStore.show(`Filtered Fingerprints by ${profile.host}`);
  }

  // ---------------- Entity menu ----------------

  let entityMenu = $state<{
    x: number;
    y: number;
    sections: MenuSection[];
  } | null>(null);

  function openEntityMenu(e: MouseEvent, type: string, value: string): void {
    e.preventDefault();
    const parent = rootEl;
    if (!parent) return;
    const r = parent.getBoundingClientRect();
    entityMenu = {
      x: e.clientX - r.left,
      y: e.clientY - r.top,
      sections: buildEntityMenu(type, value),
    };
  }
  function closeEntityMenu(): void {
    entityMenu = null;
  }

  // ---------------- Monitors ----------------

  let monAlertOpen = $state(false);
  let monUrl = $state('');
  let monLabel = $state('');
  let monInterval = $state(1); // hours
  let monAlertChange = $state(true);
  let monAlertRestore = $state(true);
  let monDowntimeThreshold = $state(48);
  let monBusy = $state(false);

  // Default the add-form URL to the selected node's URL when first
  // populated. Re-running on host change so analysts don't keep typing
  // the same host over and over.
  $effect(() => {
    if (node && !monUrl) {
      monUrl = node.url;
    }
  });

  // Reset the form whenever the host changes (new selection).
  $effect(() => {
    const host = profile?.host ?? null;
    if (host !== null) {
      monLabel = '';
      monInterval = 1;
      monAlertChange = true;
      monAlertRestore = true;
      monDowntimeThreshold = 48;
      monAlertOpen = false;
    }
  });

  async function addMonitor(): Promise<void> {
    const url = monUrl.trim();
    if (!url || monBusy) return;
    monBusy = true;
    try {
      const created = await createMonitor({
        url,
        label: monLabel.trim() || null,
        interval_hours: Math.max(0.25, Number(monInterval) || 1),
        alert_on_change: monAlertChange,
        alert_on_restore: monAlertRestore,
        downtime_threshold_hours:
          Math.max(0.25, Number(monDowntimeThreshold) || 48),
      });
      monitors = [...monitors, created];
      monUrl = node?.url ?? '';
      monLabel = '';
      toastStore.show('Monitor added');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toastStore.show('Monitor already exists for that URL', 'error');
      } else {
        toastStore.show(explainError(err, 'Add monitor failed'), 'error');
      }
    } finally {
      monBusy = false;
    }
  }

  async function toggleMonitor(m: Monitor): Promise<void> {
    try {
      const updated = await patchMonitor(m.id, { enabled: !m.enabled });
      monitors = monitors.map((x) => (x.id === m.id ? updated : x));
    } catch (err) {
      toastStore.show(explainError(err, 'Monitor toggle failed'), 'error');
    }
  }

  async function removeMonitor(m: Monitor): Promise<void> {
    try {
      await deleteMonitor(m.id);
      monitors = monitors.filter((x) => x.id !== m.id);
    } catch (err) {
      toastStore.show(explainError(err, 'Monitor remove failed'), 'error');
    }
  }

  // ---------------- Helpers ----------------

  function pageDisplayPath(url: string, host: string | null): string {
    if (!host) return url;
    const idx = url.indexOf(host);
    if (idx === -1) return url;
    const tail = url.slice(idx + host.length);
    return tail || '/';
  }

  function monitorStatusLabel(s: number | null): {
    text: string;
    tone: 'good' | 'bad' | 'muted';
  } {
    if (s === null) return { text: '—', tone: 'muted' };
    if (s === 200) return { text: 'Up', tone: 'good' };
    return { text: String(s), tone: 'bad' };
  }

  // ---------------- Label picker (domain labels) ----------------

  let labelPopover = $state<LabelPickerModal | null>(null);

  function openLabelPopover(e: MouseEvent, host: string): void {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    labelPopover = labelPickerModal(
      { kind: 'domain', host },
      { x: r.left + r.width / 2, y: r.bottom + 16 },
      profile?.label_ids ?? [],
    );
  }
  // Domain labels flow onto every node on the domain as via-domain chips, so
  // refresh the graph; re-pull the profile so this tab's chips update too.
  async function onLabelsChanged(host: string): Promise<void> {
    void graphPoller.refresh();
    try {
      const fresh = await getDomainProfile(host);
      if (profile?.host === host) profile = fresh;
    } catch {
      // The graph refresh still carries the change; a failed re-pull is cosmetic.
    }
  }

</script>

<div class="root" bind:this={rootEl}>
  {#if selectionStore.selectedNodeId === null}
    <EmptyState title="No node selected." />
  {:else if loading && !node}
    <EmptyState title="Loading…" />
  {:else if loadError}
    <EmptyState title={loadError} error />
  {:else if node && node.domain}
    {@const host = node.domain}
    {@const isStub = isUncrawled(node)}

    <!-- Domain labels -->
    <div class="label-row">
      <LabelChips labelIds={profile?.label_ids ?? []} />
      <IconButton label="Labels" variant="ghost" size="small" onclick={(e) => openLabelPopover(e, host)}>
        <Tag size={11} />
      </IconButton>
    </div>

    <!-- Profile card -->
    {#if profile && !isStub}
      <section class="block">
        <div class="chips">
          <div class="stat">
            <span class="stat-label">Pages</span>
            <span class="stat-value">{profile.page_count}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Flags</span>
            <span class="stat-value">{profile.flag_count}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Entities</span>
            <span class="stat-value">{profile.entity_count}</span>
          </div>
          <div class="stat">
            <span class="stat-label">Uptime</span>
            <span class="stat-value tone-{uptimeLabel.tone}">{uptimeLabel.text}</span>
          </div>
        </div>

        <div class="profile-grid">
          <div class="cell">
            <span class="block-label">Activity</span>
            {#if sparkline.kind === 'empty'}
              <p class="empty">No dated pages</p>
            {:else if sparkline.kind === 'single'}
              <p class="single-day">
                {sparkline.point.date}: {sparkline.point.count} page{sparkline.point.count === 1 ? '' : 's'}
              </p>
            {:else}
              <svg
                class="sparkline"
                viewBox={sparkline.viewBox}
                width={sparkline.width}
                height={sparkline.height}
                role="img"
                aria-label="Pages crawled per day"
              >
                <polyline
                  points={sparkline.polyline}
                  fill="none"
                  stroke="var(--accent)"
                  stroke-width="1"
                />
                {#each sparkline.points as p, i (i)}
                  <circle cx={p.x} cy={p.y} r="1.5" fill="var(--accent)">
                    <title>{p.date}: {p.count} page{p.count === 1 ? '' : 's'}</title>
                  </circle>
                {/each}
              </svg>
            {/if}
          </div>
          <div class="cell">
            <span class="block-label">Entity types</span>
            {#if profile.entity_types.length === 0}
              <p class="empty">None extracted yet.</p>
            {:else}
              <div class="type-chips">
                {#each profile.entity_types as t (t.type)}
                  <span class="type-chip">{t.type} {t.count}</span>
                {/each}
              </div>
            {/if}
          </div>
        </div>
      </section>
    {:else if isStub}
      <section class="block">
        <p class="placeholder muted">Not yet crawled.</p>
      </section>
    {/if}

    <!-- Pages list -->
    {#if !isStub}
      <CollapsibleSection
        title="Pages ({pages.length}{overCap ? ` of ${profile?.page_count ?? '?'}` : ''})"
        collapsed={sections.isCollapsed('pages')}
        onToggle={() => sections.toggle('pages')}
      >
        {#if pages.length === 0}
          <p class="empty">No pages.</p>
        {:else}
          <ul class="pages">
            {#each pages as p (p.id)}
              {@const active = selectionStore.selectedNodeId === p.id}
              <button
                type="button"
                class="page-row"
                class:active
                onclick={() => selectPageRow(p)}
              >
                <span class="page-path">{pageDisplayPath(p.url, host)}</span>
                {#if p.title}
                  <span class="page-title">{p.title}</span>
                {/if}
                {#if p.status_code !== null}
                  <span class="page-status">HTTP {p.status_code}</span>
                {/if}
              </button>
            {/each}
          </ul>
          {#if overCap}
            <p class="cap-note">
              Showing 200 of {profile?.page_count} pages —
              <button
                type="button"
                class="link"
                onclick={viewAllInDomainsTab}
              >view all in the Domains tab</button>.
            </p>
          {/if}
        {/if}
      </CollapsibleSection>
    {/if}

    <!-- Snapshot comparison over time (Phase 5) -->
    {#if !isStub && snapshots.length >= 2}
      <CollapsibleSection
        title="Compare snapshots"
        collapsed={sections.isCollapsed('compare')}
        onToggle={() => sections.toggle('compare')}
      >
        <div class="cmp-bar">
          <select aria-label="Compare from date" bind:value={cmpFrom}>
            {#each snapshots as d (d)}
              <option value={d}>{d}</option>
            {/each}
          </select>
          <span class="cmp-arrow">→</span>
          <select aria-label="Compare to date" bind:value={cmpTo}>
            {#each snapshots as d (d)}
              <option value={d}>{d}</option>
            {/each}
          </select>
          <button
            type="button"
            class="cmp-btn"
            onclick={runCompare}
            disabled={cmpLoading || cmpFrom === cmpTo}
          >
            {cmpLoading ? '…' : 'Compare'}
          </button>
        </div>
        {#if cmpError}
          <p class="cmp-error">{cmpError}</p>
        {:else if comparison}
          <div class="cmp-summary">
            <span class="cmp-stat added">+{comparison.added} added</span>
            <span class="cmp-stat drifted">~{comparison.drifted} drifted</span>
            <span class="cmp-stat removed">−{comparison.removed} removed</span>
            <span class="cmp-stat muted">{comparison.identical} identical</span>
          </div>
          {#if comparison.pages.length === 0}
            <p class="empty">No added, removed, or drifted pages.</p>
          {:else}
            <ul class="cmp-pages">
              {#each comparison.pages as p (p.resource_id)}
                {@const active = selectionStore.selectedNodeId === p.resource_id}
                <li>
                  <button
                    type="button"
                    class="cmp-row"
                    class:active
                    onclick={() => selectComparePage(p)}
                  >
                    <span class="cmp-badge {p.status}">{p.status}</span>
                    <span class="cmp-path">{pageDisplayPath(p.url, host)}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        {/if}
      </CollapsibleSection>
    {/if}

    <!-- Entities list -->
    {#if !isStub}
      <CollapsibleSection
        title="Entities ({entities.length})"
        collapsed={sections.isCollapsed('entities')}
        onToggle={() => sections.toggle('entities')}
      >
        {#if entities.length === 0}
          <p class="empty">No entities extracted.</p>
        {:else}
          <div class="entities">
            {#each entities as e, i (i)}
              <button
                type="button"
                class="entity-row"
                onclick={(ev) => openEntityMenu(ev, e.type, e.value)}
                oncontextmenu={(ev) => openEntityMenu(ev, e.type, e.value)}
              >
                <span class="entity-type">{e.type}</span>
                <span class="entity-value">{e.value}</span>
              </button>
            {/each}
          </div>
        {/if}
        <button type="button" class="link clusters-link" onclick={viewFingerprintsForHost}>
          View fingerprint clusters →
        </button>
      </CollapsibleSection>
    {/if}

    <!-- Uptime monitors -->
    <CollapsibleSection
      title="Uptime monitors ({monitors.length})"
      collapsed={sections.isCollapsed('monitors')}
      onToggle={() => sections.toggle('monitors')}
    >
      {#if monitors.length === 0}
        <p class="empty">None.</p>
      {:else}
        <ul class="monitors">
          {#each monitors as m (m.id)}
            {@const st = monitorStatusLabel(m.last_status)}
            <li>
              <div class="mon-line">
                <span class="mon-label">{m.label ?? m.url}</span>
                <span class="mon-status-group">
                  {#if m.last_content_changed}
                    <span class="mon-changed" title="Content changed on the last check">changed</span>
                  {/if}
                  <span class="mon-status tone-{st.tone}">{st.text}</span>
                </span>
              </div>
              <div class="mon-line muted">
                <span>{m.url}</span>
                <span>every {m.interval_hours}h</span>
              </div>
              <div class="mon-actions">
                <IconButton
                  label={m.enabled ? 'Pause monitor' : 'Resume monitor'}
                  variant="ghost"
                  size="small"
                  onclick={() => toggleMonitor(m)}
                >
                  {#if m.enabled}
                    <Pause size={11} />
                  {:else}
                    <Play size={11} />
                  {/if}
                </IconButton>
                <IconButton
                  label="Remove monitor"
                  variant="ghost"
                  size="small"
                  onclick={() => removeMonitor(m)}
                >
                  <X size={11} />
                </IconButton>
              </div>
            </li>
          {/each}
        </ul>
      {/if}

      <!-- Add monitor form -->
      <div class="mon-form">
        <input
          bind:value={monUrl}
          type="text"
          class="mon-input"
          placeholder="http://example.onion/health"
          onkeydown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              void addMonitor();
            }
          }}
        />
        <div class="mon-row">
          <input
            bind:value={monLabel}
            type="text"
            class="mon-input flex"
            placeholder="Label (optional)"
          />
          <input
            bind:value={monInterval}
            type="number"
            min="0.25"
            step="0.25"
            class="mon-input narrow"
            aria-label="Interval (hours)"
          />
          <button
            type="button"
            class="mon-add"
            onclick={addMonitor}
            disabled={!monUrl.trim() || monBusy}
          >
            Add
          </button>
        </div>
        <details open={monAlertOpen} ontoggle={(e) => (monAlertOpen = (e.currentTarget as HTMLDetailsElement).open)}>
          <summary>Alert settings</summary>
          <label class="mon-check">
            <input type="checkbox" bind:checked={monAlertChange} />
            <span>Alert on content change</span>
          </label>
          <label class="mon-check">
            <input type="checkbox" bind:checked={monAlertRestore} />
            <span>Alert on restore</span>
          </label>
          <label class="mon-check">
            <span>Downtime alert after</span>
            <input
              type="number"
              min="0.25"
              step="0.25"
              class="mon-input narrow"
              bind:value={monDowntimeThreshold}
              aria-label="Downtime threshold (hours)"
            />
            <span>hours</span>
          </label>
        </details>
      </div>
    </CollapsibleSection>
  {:else if node && !node.domain}
    <p class="placeholder">Node has no domain context.</p>
  {/if}

  {#if entityMenu}
    <ContextMenu
      sections={entityMenu.sections}
      x={entityMenu.x}
      y={entityMenu.y}
      onClose={closeEntityMenu}
    />
  {/if}

  {#if labelPopover}
    {@const picker = labelPopover}
    <LabelPickerPopover
      x={picker.x}
      y={picker.y}
      target={picker.target}
      currentIds={picker.currentIds}
      onClose={() => (labelPopover = null)}
      onChanged={() => onLabelsChanged(picker.target.kind === 'domain' ? picker.target.host : '')}
    />
  {/if}
</div>

<style>
  .label-row {
    display: flex;
    align-items: center;
    gap: 4px;
    flex-wrap: wrap;
    margin-bottom: 8px;
  }
  .root {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 10px;
    font-size: 11px;
    color: var(--text);
  }
  /* Block primitive */
  .block {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
  }
  .block:first-child {
    border-top: none;
    padding-top: 0;
  }
  .block-label {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .empty {
    margin: 0;
    color: var(--muted);
    font-size: 11px;
    font-style: italic;
  }

  /* Profile chips */
  .chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .stat {
    flex: 1 1 auto;
    min-width: 56px;
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: 3px;
    background: rgba(0, 0, 0, 0.2);
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .stat-label {
    font-size: 9px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .stat-value {
    font-size: 14px;
    color: var(--text);
  }
  .tone-good {
    color: var(--accent);
  }
  .tone-bad {
    color: #ff6b6b;
  }
  .tone-muted {
    color: var(--muted);
  }

  /* Profile grid (sparkline + entity types) */
  .profile-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .cell {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .sparkline {
    display: block;
    width: 100%;
    max-width: 100%;
    height: auto;
  }
  .single-day {
    margin: 0;
    color: var(--text);
    font-size: 11px;
  }
  .type-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .type-chip {
    padding: 2px 6px;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--muted);
    font-size: 10px;
  }

  /* Pages */
  .pages {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    max-height: 220px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: 2px;
  }
  .page-row {
    display: grid;
    grid-template-columns: 1fr auto;
    column-gap: 8px;
    row-gap: 2px;
    align-items: baseline;
    padding: 4px 6px;
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }
  .page-row:last-child {
    border-bottom: none;
  }
  .page-row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .page-row.active {
    background: rgba(0, 212, 170, 0.14);
  }
  .page-path {
    grid-column: 1;
    font-family: ui-monospace, monospace;
    font-size: 11px;
    word-break: break-all;
    color: var(--text);
  }
  .page-title {
    grid-column: 1;
    color: var(--muted);
    font-size: 10px;
    line-height: 1.3;
  }
  .page-status {
    grid-column: 2;
    grid-row: 1 / span 2;
    align-self: center;
    color: var(--muted);
    font-size: 10px;
    white-space: nowrap;
  }
  .cap-note {
    margin: 6px 0 0;
    color: var(--muted);
    font-size: 10px;
  }

  /* Snapshot comparison */
  .cmp-bar {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .cmp-bar select {
    flex: 1 1 0;
    min-width: 0;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
    font-size: 10px;
    padding: 2px 4px;
  }
  .cmp-bar select:focus {
    border-color: var(--accent);
    outline: none;
  }
  .cmp-arrow {
    flex: 0 0 auto;
    color: var(--muted);
  }
  .cmp-btn {
    flex: 0 0 auto;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    font-size: 10px;
    padding: 2px 8px;
    cursor: pointer;
  }
  .cmp-btn:not(:disabled):hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .cmp-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .cmp-error {
    margin: 0;
    color: #ff6b6b;
    font-size: 11px;
  }
  .cmp-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    font-family: ui-monospace, monospace;
    font-size: 10px;
  }
  .cmp-stat.added {
    color: var(--accent);
  }
  .cmp-stat.drifted {
    color: #e0b860;
  }
  .cmp-stat.removed {
    color: #ff6b6b;
  }
  .cmp-stat.muted {
    color: var(--muted);
  }
  .cmp-pages {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    max-height: 200px;
    overflow-y: auto;
    border: 1px solid var(--border);
    border-radius: 2px;
  }
  .cmp-row {
    width: 100%;
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 4px 6px;
    background: transparent;
    border: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }
  .cmp-row:last-child {
    border-bottom: none;
  }
  .cmp-row:hover {
    background: rgba(0, 212, 170, 0.06);
  }
  .cmp-row.active {
    background: rgba(0, 212, 170, 0.14);
  }
  .cmp-badge {
    flex: 0 0 auto;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 1px 4px;
    border-radius: 8px;
    border: 1px solid var(--border);
  }
  .cmp-badge.added {
    color: var(--accent);
    border-color: var(--accent);
  }
  .cmp-badge.drifted {
    color: #e0b860;
    border-color: #b08a3a;
  }
  .cmp-badge.removed {
    color: #ff6b6b;
    border-color: #ff6b6b;
  }
  .cmp-path {
    font-family: ui-monospace, monospace;
    font-size: 11px;
    word-break: break-all;
  }
  .link {
    background: transparent;
    border: none;
    padding: 0;
    color: var(--accent);
    cursor: pointer;
    font: inherit;
    text-decoration: underline;
  }
  .link:hover {
    color: var(--text);
  }

  /* Entities */
  .entities {
    display: flex;
    flex-direction: column;
    max-height: 220px;
    overflow-y: auto;
  }
  .entity-row {
    display: flex;
    gap: 8px;
    align-items: baseline;
    padding: 3px 4px;
    background: transparent;
    border: none;
    color: var(--text);
    font-size: 11px;
    text-align: left;
    cursor: pointer;
    border-radius: 2px;
  }
  .entity-row:hover {
    background: rgba(0, 212, 170, 0.08);
  }
  .entity-type {
    flex: 0 0 64px;
    color: var(--muted);
    text-transform: lowercase;
    font-size: 10px;
  }
  .entity-value {
    font-family: ui-monospace, monospace;
    word-break: break-all;
  }
  .clusters-link {
    align-self: flex-start;
    margin-top: 4px;
    font-size: 11px;
  }

  /* Monitors */
  .monitors {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .monitors li {
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: 2px;
    display: flex;
    flex-direction: column;
    gap: 2px;
    background: rgba(0, 0, 0, 0.2);
    position: relative;
  }
  .mon-line {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 11px;
  }
  .mon-line.muted {
    color: var(--muted);
    font-size: 10px;
    word-break: break-all;
  }
  .mon-label {
    word-break: break-word;
  }
  .mon-status-group {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .mon-status {
    font-size: 11px;
  }
  .mon-changed {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #e0b860;
    border: 1px solid #b08a3a;
    border-radius: 8px;
    padding: 1px 4px;
  }
  .mon-actions {
    position: absolute;
    top: 4px;
    right: 4px;
    display: flex;
    gap: 4px;
  }
  .mon-form {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 6px;
  }
  .mon-input {
    width: 100%;
    box-sizing: border-box;
    padding: 4px 6px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--text);
    font: inherit;
  }
  .mon-input:focus {
    border-color: var(--accent);
    outline: none;
  }
  .mon-input.narrow {
    width: 64px;
    flex: 0 0 64px;
  }
  .mon-input.flex {
    flex: 1;
  }
  .mon-row {
    display: flex;
    gap: 4px;
  }
  .mon-add {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: 2px;
    color: var(--muted);
    font-size: 11px;
    padding: 3px 10px;
    cursor: pointer;
  }
  .mon-add:not(:disabled):hover {
    color: var(--accent);
    border-color: var(--accent);
  }
  .mon-add:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  details summary {
    cursor: pointer;
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 2px 0;
  }
  details summary:hover {
    color: var(--text);
  }
  .mon-check {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 4px;
    font-size: 11px;
    color: var(--text);
  }
</style>
