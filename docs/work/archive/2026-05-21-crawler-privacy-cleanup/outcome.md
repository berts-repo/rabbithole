# Outcome — Crawler Privacy Cleanup

Closed: 2026-05-26

## What shipped

- P1: Tor Browser-like request headers replacing the unique Rabbithole
  user-agent fingerprint.
- P2: Per-onion-host SOCKS5h credentials for Tor circuit isolation — each
  host gets a distinct `username:password` credential pair so Tor builds
  separate circuits per target.
- P3: Crawl pacing profiles (`fast` / `polite` / `stealth`) with `polite`
  as the default. Polite adds a short jittered inter-request delay; stealth
  uses human-scale delays. Persisted as the `crawl.pacing` setting.

All backend crawler/security tests pass. Reference docs updated.
