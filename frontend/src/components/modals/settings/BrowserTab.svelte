<script lang="ts">
  // Settings → Browser. Controls how "Open in browser" launches the
  // external Tor Browser: the executable path (browser.path) and whether
  // each open reuses the running profile or starts fresh
  // (browser.launch_mode). Both autosave on change.
  //
  // When browser.path is unset the open route falls back to
  // discover_browser_path() (canonical Tor Browser install hints), so a
  // default install works without configuring anything here. The backend
  // path validator is intentionally strict (no symlinks, must be an
  // executable file under the browser allowlist) and rejects an empty
  // string — there is no "clear to auto-detect" today, so we only persist
  // a non-empty path and surface validation failures as a toast.

  import { onMount } from 'svelte';
  import { ApiError, getSetting, putSetting } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  type LaunchMode = 'fresh' | 'reuse';

  let path = $state('');
  let launchMode = $state<LaunchMode>('fresh');
  let loaded = $state(false);

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const [p, m] = await Promise.all([
        getSetting<string>('browser.path').catch(() => null),
        getSetting<string>('browser.launch_mode').catch(() => null),
      ]);
      if (p?.value) path = p.value;
      if (m?.value === 'reuse' || m?.value === 'fresh') launchMode = m.value;
      loaded = true;
    } catch {
      loaded = true;
    }
  }

  function errMsg(err: unknown): string {
    if (err instanceof ApiError) {
      const body = err.body as { message?: string } | undefined;
      return body?.message ?? err.message;
    }
    return err instanceof Error ? err.message : String(err);
  }

  async function savePath(): Promise<void> {
    const value = path.trim();
    if (!value) return; // empty = leave the stored value (clearing unsupported)
    try {
      await putSetting('browser.path', value);
      toastStore.show('Browser path saved.', 'info');
    } catch (err) {
      toastStore.show(`Invalid path: ${errMsg(err)}`, 'error');
    }
  }

  async function saveMode(value: LaunchMode): Promise<void> {
    launchMode = value;
    try {
      await putSetting('browser.launch_mode', value);
    } catch (err) {
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }
</script>

<div class="tab">
  <label class="field">
    <span>Browser executable path</span>
    <input
      type="text"
      placeholder="/path/to/tor-browser (leave blank to auto-detect)"
      bind:value={path}
      disabled={!loaded}
      onchange={() => void savePath()}
    />
    <span class="hint">
      Leave blank to auto-detect a standard Tor Browser install. Must be an
      executable file under the browser allowlist — symlinks are rejected.
    </span>
  </label>

  <label class="field">
    <span>Launch mode</span>
    <select
      value={launchMode}
      disabled={!loaded}
      onchange={(e) => void saveMode(e.currentTarget.value as LaunchMode)}
    >
      <option value="fresh">Fresh — new profile each open</option>
      <option value="reuse">Reuse — attach to the running browser</option>
    </select>
  </label>
</div>

<style>
  .tab {
    display: flex;
    flex-direction: column;
    gap: 14px;
    font-size: 12px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .field > span:first-child {
    color: var(--muted);
  }
  .field input,
  .field select {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font: inherit;
    font-size: 12px;
    width: 100%;
  }
  .field input:focus-visible,
  .field select:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .hint {
    color: var(--muted);
    font-size: 11px;
  }
</style>
