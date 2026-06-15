# I2P Crawling Future Feature

## Status

Future feature note. Rabbithole currently centers on Tor onion crawling. This
document captures the intended shape of `.i2p` support if the project expands
to I2P eepsite crawling.

## Goal

Add I2P as a second anonymous-network backend for crawling and analyst preview,
while preserving Rabbithole's graph/crawl investigation workflow and privacy
model.

The first implementation should assume Rabbithole is already running inside an
analysis VM. The I2P router can run as software inside that same VM, bound to
localhost, instead of requiring a physical router or separate browser.

## Operating Model

I2P uses a local software router process. A normal browser, crawler, or HTTP
client can reach `.i2p` sites when configured to use the router's local HTTP
proxy.

Typical local endpoints:

- Router console: `http://127.0.0.1:7657`
- HTTP proxy: `127.0.0.1:4444`
- HTTPS proxy, when enabled: `127.0.0.1:4445`
- SAM bridge, for future app integrations: `127.0.0.1:7656`

Initial crawler support should use the HTTP proxy:

```text
Rabbithole crawler/browser
  -> http://127.0.0.1:4444
  -> local I2P router
  -> I2P tunnels
  -> .i2p eepsite
```

No different browser is required. If Rabbithole launches an analyst preview
browser, it should use a separate browser profile or browser context configured
with the I2P proxy.

## Product Shape

Model I2P as a network backend alongside Tor:

```text
*.onion -> Tor adapter via SOCKS5h
*.i2p   -> I2P adapter via HTTP proxy
normal  -> disabled or explicit clearnet adapter
```

The crawler should:

- Accept `.i2p` URLs as crawl targets.
- Route `.i2p` requests only through the I2P adapter.
- Avoid normal OS DNS resolution for `.i2p` hostnames.
- Treat slow bootstrap, unavailable peers, and intermittent resolution as
  expected network states.
- Keep I2P crawler/browser profiles separate from Tor profiles.
- Provide a health check for the local I2P router before starting I2P crawls.

The analyst preview should:

- Use a dedicated I2P proxy profile or browser context.
- Keep cookies, cache, downloads, and local storage separate from Tor and any
  clearnet profile.
- Preserve the same screenshot, page capture, and graph-link extraction
  semantics used by onion crawling where possible.

## Resolution Metadata

I2P human-readable `.i2p` names resolve through address books and subscriptions
to cryptographic destinations. Unlike onion v3 addresses, the hostname itself is
not the full self-authenticating service identifier.

Store I2P-specific resolution metadata when available:

```text
hostname: example.i2p
destination: base64 I2P destination, if known
address_book_source: local book, subscription, discovered link, or manual entry
first_seen_at: timestamp
last_resolved_at: timestamp
```

This gives analysts chain-of-custody context for how a crawled `.i2p` hostname
resolved at the time of collection.

## Security Notes

For the current VM-based deployment assumption, the simplest useful setup is:

```text
Analysis VM
  - Rabbithole app
  - crawler worker
  - I2P router software
  - optional preview browser automation
```

Required constraints:

- Bind I2P services to `127.0.0.1`, not the VM LAN interface.
- Route `.i2p` crawling only through `127.0.0.1:4444`.
- Flag or block attempts to fetch `.i2p` through Tor, clearnet, or the OS
  resolver.
- Keep downloads quarantined in the same way as Tor crawl artifacts.
- Do not expose the I2P router console or proxy outside the VM.

Virtualizing I2P improves process and device isolation but does not change I2P's
network anonymity model. Privacy still depends on correct proxy routing,
application-layer leak prevention, tunnel behavior, and I2P router state.

## Deferred Decisions

- Whether Rabbithole should manage the I2P router lifecycle or require the
  operator to start it.
- Whether to use only the HTTP proxy in v1 or also support SAM for richer
  destination metadata.
- How address-book subscriptions should be configured, audited, and displayed.
- Whether `.i2p` search/discovery belongs in the existing Search tab or a
  network-specific source picker.
- How much VM firewall policy Rabbithole should document versus enforce.
