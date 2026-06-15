<script lang="ts">
  import { Play } from 'lucide-svelte';
  import { TextButton } from '$lib/ui';
  import {
    createStubNode,
    lookupNodes,
    type NodeLookupRow,
  } from '$lib/api';
  import { stateLabel as resourceStateLabel } from '$lib/nodeState';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { batchConfirmStore } from '$lib/stores/batchConfirm.svelte';

  type Props = { onSendToCrawl: (url: string) => void };
  const { onSendToCrawl }: Props = $props();

  let pasted = $state('');
  let lookups = $state<Record<string, NodeLookupRow>>({});
  let lookupTimer: ReturnType<typeof setTimeout> | null = null;

  const lines = $derived(parseLines(pasted));

  function parseLines(raw: string): string[] {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const line of raw.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (seen.has(trimmed)) continue;
      seen.add(trimmed);
      out.push(trimmed);
    }
    return out;
  }

  // Debounced lookup whenever the parsed list changes.
  $effect(() => {
    const current = lines;
    if (lookupTimer !== null) clearTimeout(lookupTimer);
    if (current.length === 0) {
      lookups = {};
      return;
    }
    lookupTimer = setTimeout(() => {
      void refreshLookup(current);
    }, 300);
    return () => {
      if (lookupTimer !== null) clearTimeout(lookupTimer);
    };
  });

  async function refreshLookup(urls: string[]) {
    try {
      const r = await lookupNodes({ urls });
      lookups = r.results;
    } catch {
      // Keep last known state. Lookup failure shouldn't blow up the UI.
    }
  }

  async function onMarkKnown(url: string) {
    try {
      await createStubNode({ url });
      await refreshLookup(lines);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Failed to mark known: ${msg}`, 'error');
    }
  }

  function onCrawl(url: string) {
    onSendToCrawl(url);
  }

  function onQueueAll() {
    if (lines.length === 0) return;
    batchConfirmStore.stage({
      source: 'bulk',
      sourceLabel: 'Bulk Import',
      urls: lines,
    });
    clear();
  }

  function clear() {
    pasted = '';
    lookups = {};
  }

  function stateLabel(row: NodeLookupRow | undefined): string {
    if (!row) return 'checking…';
    if (row.state === 'invalid') return 'Invalid';
    return resourceStateLabel(row.state);
  }
</script>

<div class="bulk">
  <textarea
    bind:value={pasted}
    rows="4"
    placeholder="Paste domains or URLs, one per line…"
  ></textarea>

  {#if lines.length > 0}
    <ul class="rows">
      {#each lines as line (line)}
        {@const row = lookups[line]}
        <li class="row" data-state={row?.state ?? 'checking'}>
          <div class="row-body">
            <span class="badge" data-state={row?.state ?? 'checking'}>{stateLabel(row)}</span>
            <span class="url" title={line}>{line}</span>
          </div>
          <div class="row-actions">
            {#if row?.state !== 'invalid'}
              <TextButton size="small" title="Send to Crawl" onclick={() => onCrawl(line)}>
                {#snippet icon()}<Play size={10} />{/snippet}
                Send to Crawl
              </TextButton>
            {/if}
            {#if row?.state === 'unknown'}
              <TextButton
                size="small"
                title="Add as a known URL without crawling it"
                onclick={() => onMarkKnown(line)}>+ Mark Known</TextButton>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
    <div class="footer">
      <TextButton variant="primary" onclick={onQueueAll}>
        Queue all {lines.length} URL{lines.length === 1 ? '' : 's'}
      </TextButton>
      <TextButton variant="ghost" size="small" onclick={clear}>Clear</TextButton>
    </div>
  {/if}
</div>

<style>
  .bulk {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  textarea {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 8px;
    font: inherit;
    font-size: 11px;
    width: 100%;
    resize: vertical;
    min-height: 60px;
  }
  textarea:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
    max-height: 240px;
    overflow-y: auto;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    border: 1px solid var(--border);
    font-size: 11px;
    min-width: 0;
  }
  .row-body {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    flex: 1;
  }
  .url {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    color: var(--text);
    min-width: 0;
  }
  .row-actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }
  .badge {
    font-size: 9px;
    padding: 1px 6px;
    border: 1px solid var(--border);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    flex-shrink: 0;
  }
  .badge[data-state='crawled'] {
    color: var(--accent);
    border-color: var(--accent);
  }
  .badge[data-state='known'] {
    color: #ffd58a;
    border-color: #ffd58a;
  }
  .badge[data-state='unknown'] {
    color: var(--muted);
  }
  .badge[data-state='invalid'] {
    color: #ffb3c0;
    border-color: #ff5577;
  }
  .footer {
    display: flex;
    align-items: center;
    gap: 6px;
  }
</style>
