<script lang="ts">
  // Settings → Tor / Privacy. The durable home for the egress configuration
  // that every outbound request depends on: the Tor SOCKS5h proxy URL
  // (tor.proxy) and the kill switch (tor.kill_switch). Both autosave on
  // change via the per-key PUT /api/settings seam.
  //
  // The proxy validator (security/net.py validate_tor_proxy) is strict by
  // design — only socks5h://(127.0.0.1|::1):<port> is accepted, so DNS never
  // escapes Tor and egress can never be pointed at a non-loopback proxy. A
  // rejected value surfaces as a toast and the field keeps the typed text so
  // the analyst can correct it.
  //
  // Per-onion-host circuit isolation is shown read-only: it is always on
  // (SOCKS-auth keyed on the onion host in security/net.py) and has no off
  // switch by design, so there is nothing to toggle — only to confirm.

  import { onMount } from 'svelte';
  import { ApiError, getSetting, putSetting } from '$lib/api';
  import { toastStore } from '$lib/stores/toast.svelte';

  const DEFAULT_PROXY = 'socks5h://127.0.0.1:9050';
  const DEFAULT_I2P_PROXY = 'socks5h://127.0.0.1:4447';

  let proxy = $state('');
  let killSwitch = $state(false);
  let i2pEnabled = $state(false);
  let i2pProxy = $state('');
  let i2pKillSwitch = $state(false);
  let loaded = $state(false);

  onMount(() => void load());

  async function load(): Promise<void> {
    try {
      const [p, k, ie, ip, ik] = await Promise.all([
        getSetting<string>('tor.proxy').catch(() => null),
        getSetting<string>('tor.kill_switch').catch(() => null),
        getSetting<string>('i2p.enabled').catch(() => null),
        getSetting<string>('i2p.proxy').catch(() => null),
        getSetting<string>('i2p.kill_switch').catch(() => null),
      ]);
      proxy = p?.value || DEFAULT_PROXY;
      killSwitch = k?.value === 'true';
      i2pEnabled = ie?.value === 'true';
      i2pProxy = ip?.value || DEFAULT_I2P_PROXY;
      i2pKillSwitch = ik?.value !== 'false';
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

  async function saveProxy(): Promise<void> {
    const value = proxy.trim();
    if (!value) return; // empty = leave the stored value (clearing unsupported)
    try {
      const res = await putSetting('tor.proxy', value);
      proxy = (res.value as string) ?? value;
      toastStore.show('Tor proxy saved.', 'info');
    } catch (err) {
      toastStore.show(`Invalid proxy: ${errMsg(err)}`, 'error');
    }
  }

  async function saveKillSwitch(value: boolean): Promise<void> {
    killSwitch = value;
    try {
      await putSetting('tor.kill_switch', value);
    } catch (err) {
      killSwitch = !value;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function saveI2pEnabled(value: boolean): Promise<void> {
    i2pEnabled = value;
    try {
      await putSetting('i2p.enabled', value);
    } catch (err) {
      i2pEnabled = !value;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }

  async function saveI2pProxy(): Promise<void> {
    const value = i2pProxy.trim();
    if (!value) return;
    try {
      const res = await putSetting('i2p.proxy', value);
      i2pProxy = (res.value as string) ?? value;
      toastStore.show('I2P proxy saved.', 'info');
    } catch (err) {
      toastStore.show(`Invalid proxy: ${errMsg(err)}`, 'error');
    }
  }

  async function saveI2pKillSwitch(value: boolean): Promise<void> {
    i2pKillSwitch = value;
    try {
      await putSetting('i2p.kill_switch', value);
    } catch (err) {
      i2pKillSwitch = !value;
      toastStore.show(`Save failed: ${errMsg(err)}`, 'error');
    }
  }
</script>

<div class="tab">
  <label class="field">
    <span>Tor SOCKS5h proxy</span>
    <input
      type="text"
      placeholder={DEFAULT_PROXY}
      bind:value={proxy}
      disabled={!loaded}
      onchange={() => void saveProxy()}
    />
    <span class="hint">
      Must be <code>socks5h://127.0.0.1:&lt;port&gt;</code> (or <code>::1</code>)
      so hostname resolution stays inside Tor. Non-loopback proxies are
      rejected — onion crawling never egresses outside Tor.
    </span>
  </label>

  <label class="check">
    <input
      type="checkbox"
      checked={killSwitch}
      disabled={!loaded}
      onchange={(e) => void saveKillSwitch((e.target as HTMLInputElement).checked)}
    />
    <span>
      Kill switch — halt crawling and outbound probes when Tor is unreachable
    </span>
  </label>

  <div class="status">
    <span class="status-dot" aria-hidden="true"></span>
    <div class="status-text">
      <span class="status-title">Per-site circuit isolation — always on</span>
      <span class="hint">
        Each onion host gets its own Tor circuit (SOCKS-auth stream isolation),
        so a hostile relay on one site's path can't correlate it with another.
        Enforced in the egress layer; there is no off switch.
      </span>
    </div>
  </div>

  <hr class="divider" />

  <label class="check">
    <input
      type="checkbox"
      checked={i2pEnabled}
      disabled={!loaded}
      onchange={(e) =>
        void saveI2pEnabled((e.target as HTMLInputElement).checked)}
    />
    <span>Enable I2P — accept and crawl <code>.i2p</code> eepsites</span>
  </label>

  <label class="field">
    <span>I2P SOCKS5h proxy</span>
    <input
      type="text"
      placeholder={DEFAULT_I2P_PROXY}
      bind:value={i2pProxy}
      disabled={!loaded || !i2pEnabled}
      onchange={() => void saveI2pProxy()}
    />
    <span class="hint">
      The I2P router's SOCKS proxy (i2pd defaults to port 4447; on Java I2P start
      the SOCKS proxy tunnel). Must be
      <code>socks5h://127.0.0.1:&lt;port&gt;</code> so <code>.i2p</code> names
      resolve inside the router, never via the OS.
    </span>
  </label>

  <label class="check">
    <input
      type="checkbox"
      checked={i2pKillSwitch}
      disabled={!loaded || !i2pEnabled}
      onchange={(e) =>
        void saveI2pKillSwitch((e.target as HTMLInputElement).checked)}
    />
    <span>
      Kill switch — halt crawling and probes when the I2P router is unreachable
    </span>
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
  .field input {
    background: var(--bg);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 3px;
    padding: 5px 7px;
    font: inherit;
    font-size: 12px;
    width: 100%;
  }
  .field input:focus-visible {
    border-color: var(--accent);
    outline: none;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 7px;
    cursor: pointer;
  }
  .check input {
    cursor: pointer;
    flex: 0 0 auto;
  }
  .hint {
    color: var(--muted);
    font-size: 11px;
  }
  code {
    font-size: 11px;
    color: var(--text);
  }
  .status {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 8px 10px;
  }
  .status-dot {
    flex: 0 0 auto;
    width: 8px;
    height: 8px;
    margin-top: 3px;
    border-radius: 50%;
    background: var(--accent);
  }
  .status-text {
    display: flex;
    flex-direction: column;
    gap: 3px;
    min-width: 0;
  }
  .status-title {
    color: var(--text);
  }
  .divider {
    border: none;
    border-top: 1px solid var(--border);
    margin: 4px 0;
    width: 100%;
  }
</style>
