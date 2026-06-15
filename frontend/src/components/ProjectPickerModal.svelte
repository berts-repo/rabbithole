<script lang="ts">
  import { X } from 'lucide-svelte';
  import { projectsStore, type CrawlConflict } from '$lib/stores/projects.svelte';
  import { toastStore } from '$lib/stores/toast.svelte';
  import { ApiError } from '$lib/api';

  // Prefer the backend's human-readable `message` (e.g. the path_in_use
  // explanation) over the bare error code ApiError.message carries.
  function errorText(e: unknown): string {
    if (e instanceof ApiError && e.body && typeof e.body === 'object' && 'message' in e.body) {
      const m = (e.body as { message?: unknown }).message;
      if (typeof m === 'string' && m) return m;
    }
    return e instanceof Error ? e.message : String(e);
  }

  type Props = { onClose?: () => void };
  const { onClose }: Props = $props();

  // Close button only enabled when there IS an active project — otherwise
  // the modal is blocking (initial-load case from app-shell.md).
  const canDismiss = $derived(onClose !== undefined && projectsStore.activeId !== null);

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && canDismiss) onClose?.();
  }

  let name = $state('');
  let path = $state('');
  let pathTouched = $state(false);
  let creating = $state(false);

  function slugify(raw: string): string {
    return raw
      .toLowerCase()
      .trim()
      .replace(/[\s_]+/g, '-')
      .replace(/[^a-z0-9.\-]/g, '')
      .replace(/-+/g, '-')
      .replace(/^[-.]+|[-.]+$/g, '');
  }

  // Auto-derive path from name until the user manually edits the path.
  $effect(() => {
    if (pathTouched) return;
    const slug = slugify(name);
    path = slug ? `scans/${slug}.db` : '';
  });
  let switching = $state<string | null>(null);
  let deleting = $state<string | null>(null);
  let conflict = $state<{ projectId: string; info: CrawlConflict } | null>(null);

  async function doSwitch(id: string, force = false) {
    switching = id;
    try {
      const result = await projectsStore.switch(id, force);
      if (result.ok) {
        location.reload();
      } else {
        conflict = { projectId: id, info: result.conflict };
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Switch failed: ${msg}`, 'error');
    } finally {
      switching = null;
    }
  }

  async function doDelete(id: string, displayName: string) {
    if (!confirm(`Remove "${displayName}" from the project list? The DB file is left on disk.`))
      return;
    deleting = id;
    try {
      await projectsStore.remove(id);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toastStore.show(`Delete failed: ${msg}`, 'error');
    } finally {
      deleting = null;
    }
  }

  async function doCreate(e: SubmitEvent) {
    e.preventDefault();
    if (!name.trim() || !path.trim()) {
      toastStore.show('Name and path are required.', 'warn');
      return;
    }
    creating = true;
    try {
      const proj = await projectsStore.create({ name: name.trim(), path: path.trim() });
      // Created — switch to it. Switch reloads on success.
      await doSwitch(proj.id);
    } catch (e) {
      toastStore.show(`Create failed: ${errorText(e)}`, 'error');
    } finally {
      creating = false;
    }
  }

  function cancelConflict() {
    conflict = null;
  }

  async function confirmConflict() {
    if (!conflict) return;
    const id = conflict.projectId;
    conflict = null;
    await doSwitch(id, true);
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="backdrop" role="presentation">
  <div class="modal" role="dialog" aria-modal="true" aria-labelledby="proj-title">
    <header>
      <h2 id="proj-title">Open project</h2>
      {#if canDismiss}
        <button type="button" class="close" aria-label="Close" onclick={() => onClose?.()}>
          <X size={14} />
        </button>
      {/if}
    </header>

    {#if projectsStore.loading && projectsStore.projects.length === 0}
      <p class="placeholder">Loading…</p>
    {:else if projectsStore.error && projectsStore.projects.length === 0}
      <p class="error">Couldn't load projects: {projectsStore.error}</p>
    {:else if projectsStore.projects.length === 0}
      <p class="placeholder">No projects yet. Create one below to get started.</p>
    {:else}
      <ul class="list">
        {#each projectsStore.projects as p (p.id)}
          <li>
            <button
              type="button"
              class="row"
              disabled={switching !== null}
              onclick={() => doSwitch(p.id)}
            >
              <span class="name">{p.name}</span>
              <span class="path">{p.path}</span>
              {#if switching === p.id}<span class="status">switching…</span>{/if}
            </button>
            <button
              type="button"
              class="del"
              aria-label="Delete {p.name}"
              disabled={deleting === p.id || switching !== null}
              onclick={() => doDelete(p.id, p.name)}
            >
              <X size={14} />
            </button>
          </li>
        {/each}
      </ul>
    {/if}

    <form class="create" onsubmit={doCreate}>
      <h3>New project</h3>
      <label>
        <span>Name</span>
        <input type="text" bind:value={name} placeholder="my-case" disabled={creating} />
      </label>
      <label>
        <span>Path</span>
        <input
          type="text"
          bind:value={path}
          placeholder="scans/case.db"
          disabled={creating}
          oninput={() => (pathTouched = true)}
        />
      </label>
      <button type="submit" class="create-btn" disabled={creating}>
        {creating ? 'Creating…' : 'Create'}
      </button>
    </form>
  </div>

  {#if conflict}
    <div class="confirm">
      <div class="confirm-card">
        <h3>Crawl in progress</h3>
        <p>
          This project has an active crawl on <code>{conflict.info.seed_url}</code>
          ({conflict.info.pages_crawled} pages so far). Stop it and switch?
        </p>
        <div class="actions">
          <button type="button" onclick={cancelConflict}>Cancel</button>
          <button type="button" class="danger" onclick={confirmConflict}>Stop crawl & switch</button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    background: var(--bg);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 950;
  }
  .modal {
    background: var(--bg);
    border: 1px solid var(--border);
    min-width: 460px;
    max-width: 600px;
    padding: 20px 24px;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  header h2 {
    margin: 0;
    font-size: 16px;
    color: var(--accent);
  }
  .close {
    background: transparent;
    border: none;
    color: var(--muted);
    cursor: pointer;
    padding: 2px;
    display: inline-flex;
    align-items: center;
  }
  .close:hover {
    color: var(--text);
  }
  .placeholder,
  .error {
    margin: 0 0 16px;
    font-size: 12px;
    color: var(--muted);
  }
  .error {
    color: #ffb3c0;
  }
  .list {
    list-style: none;
    margin: 0 0 20px;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 320px;
    overflow-y: auto;
  }
  .list li {
    display: flex;
    gap: 4px;
  }
  .row {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: 8px 12px;
    background: transparent;
    border: 1px solid var(--border);
    color: inherit;
    cursor: pointer;
    text-align: left;
  }
  .row:hover:not(:disabled) {
    border-color: var(--accent);
  }
  .row:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .name {
    color: var(--text);
    font-size: 13px;
  }
  .path {
    color: var(--muted);
    font-size: 11px;
  }
  .status {
    color: var(--accent);
    font-size: 11px;
  }
  .del {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 0 8px;
    cursor: pointer;
  }
  .del:hover:not(:disabled) {
    color: #ff5577;
    border-color: #ff5577;
  }
  .create {
    border-top: 1px solid var(--border);
    padding-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .create h3 {
    margin: 0 0 4px;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  .create label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 11px;
    color: var(--muted);
  }
  .create input {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 8px;
    font-size: 12px;
  }
  .create input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .create-btn {
    align-self: flex-end;
    background: transparent;
    border: 1px solid var(--accent);
    color: var(--accent);
    padding: 6px 16px;
    cursor: pointer;
    font-size: 12px;
  }
  .create-btn:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .create-btn:hover:not(:disabled) {
    background: var(--accent-bg);
  }
  .confirm {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 960;
  }
  .confirm-card {
    background: var(--bg);
    border: 1px solid var(--border);
    padding: 20px;
    max-width: 480px;
  }
  .confirm-card h3 {
    margin: 0 0 8px;
    font-size: 14px;
    color: #ffd58a;
  }
  .confirm-card p {
    margin: 0 0 16px;
    font-size: 12px;
  }
  .confirm-card code {
    color: var(--accent);
    background: var(--accent-bg);
    padding: 1px 4px;
  }
  .actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
  .actions button {
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 12px;
    cursor: pointer;
    font-size: 12px;
  }
  .actions .danger {
    border-color: #ff5577;
    color: #ffb3c0;
  }
  .actions .danger:hover {
    background: rgba(255, 85, 119, 0.12);
  }
</style>
