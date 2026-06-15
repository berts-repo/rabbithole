# Crawler Privacy & Cleanup — Follow-up Plan

Status: active plan (supersedes the original exploration brief)
Date: 2026-05-21
Owner review: complete

## How this plan came to be

The original brief listed five maintainability findings for second-pass review.
During that review the project owner re-framed the priority: this is a dark-web
OSINT tool for journalism/research, and the concern that matters now is **privacy
toward the (potentially malicious) onion sites the crawler visits** — not
physical/device security, which is explicitly out of scope for now.

This document records the review outcome and the prioritized work.

## Threat model (owner-confirmed)

- In scope: what a hostile onion site (or a relay in the crawl path) can learn
  about, fingerprint, or do to the operator when the crawler visits it.
- Out of scope for now: physical device compromise (theft, seizure, disk
  imaging). At-rest encryption is therefore deferred — see below.

## Disposition of the original five findings

| # | Original finding | Disposition |
|---|------------------|-------------|
| 1 | Backend DB access standardization | **Keep — reframed.** Do it as a single DB-access *seam*. Not for tidiness: the seam is what makes optional at-rest encryption a small change later. Medium priority. |
| 2 | Placeholder surface normalization | **Defer.** `RightPanel`/`SearchTab` are correctly-scoped future-phase stubs; normalizing them before their feature content exists is premature. Revisit when F6/F8 work starts. |
| 3 | Frontend API client domain split | **Done.** Already split into `frontend/src/lib/api/` (core, types, per-domain modules, barrel, test). No action. |
| 4 | Backend hotspot decomposition | **Defer.** Largest modules (`db/core.py` ~600 lines, `services/llm_worker.py`, `crawler/runtime.py`) are sizeable but cohesive, not god-modules. Not worth disturbing now. |
| 5 | Documentation sprawl | **Done.** Tracked under `docs/work/archive/2026-05-21-docs-organization/plan.md`; execute future doc work through the Librarian role (`LIBRARIAN.md`, surfaced by `AGENTS.md`) and `docs/work/`. |

## At-rest encryption (deferred)

Owner decision: device seizure is not in the current threat model, so encrypting
the project database is deferred. It should remain *possible to add later as an
option*. The enabling work is Finding 1 (the DB-access seam) — with one
chokepoint where the DB is opened, turning on SQLCipher later is a small change
rather than a retrofit. Do the seam; defer the encryption itself.

## Priority track: crawler privacy toward malicious sites

Current strengths (leave alone — already good): single lint-enforced egress
factory, SOCKS5h with Tor-side DNS, onion-v3 validation on every URL and redirect
hop, manual redirect walking that rejects non-onion hops, 10 MB streaming cap,
`trust_env=False`, no sub-resource fetching, no `Referer` ever sent, sequential
(not concurrent) crawl loop.

### P1 — Request fingerprint: the crawler announces itself  [AGREED]

Problem: every request carries only `User-Agent: rabbithole/1.0` +
`Accept-Encoding: gzip, deflate`. A two-header request is unmistakably automated;
the UA names the exact tool, letting a hostile site block it or serve poisoned
decoy content. The `net.py:79` comment frames the fixed UA as a privacy win — it
is the opposite (a unique constant = a permanent name tag).

Fix: adopt the current stable Tor Browser request profile — its UA string plus
its full header set — as one named constant in `net.py`. Tor Browser gives all
its users an identical fingerprint by design, so this both blends into the
largest anonymity set and stays a fixed constant (satisfying the original
comment's concern). Note the Tor Browser version mirrored; bump on release.
Implementation note: only advertise `br` if brotli decompression is available
(aiohttp needs the `brotli` package).

Limit: defeats UA-based identification, not behavioral identification (see P3).

### P2 — No per-site Tor circuit isolation  [AGREED — direction A]

Problem: the SOCKS `ProxyConnector` passes no username/password, so Tor's stream
isolation does not separate circuits per onion site — a crawl of many sites can
ride shared circuits. Note this is a leak to malicious *relays* in the path, not
to the sites themselves; severity is low (defense-in-depth). Cost to fix: low.

Directions:
- **A (recommended) — per-onion-host credentials.** Distinct SOCKS user/pass per
  onion host → one circuit per site, mirroring Tor Browser's per-first-party
  isolation. Pages within one site share a circuit (fast, fine).
- B — per-crawl-job credentials. Coarser: isolates a crawl job from other jobs /
  monitor probes / harvest queries, but not site-from-site within a crawl.
- Defer — acceptable; lowest-priority of the three findings.
- (Per-request credentials: rejected — every request pays circuit-build latency
  and constant new circuits is itself an unusual pattern.)

### P3 — Behavioral fingerprint: crawl cadence  [AGREED — direction B, default polite]

The crawl loop is sequential — one page at a time (`runtime.py:163`), not
concurrent. The crawler does not flood sites.

Problem: there is no inter-request delay, think-time, or jitter — the next fetch
fires the instant the previous body finishes, a steady gap-free cadence no human
produces. FIFO/stack queue modes can also pull many pages from one host
back-to-back; `diverse` mode round-robins hosts and mitigates that.

Directions:
- A — fixed politeness delay + jitter between requests. Simple; slows every
  crawl uniformly.
- **B (recommended) — per-crawl pacing profile.** `fast` (no delay; bulk sweeps
  of low-risk sites), `polite` (short jittered delay; default), `stealth`
  (human-scale jittered think-time; for targets that watch their logs). Right
  pacing depends on the target, so let the operator choose; default `polite`.
- C — leave it. Sequential-with-no-delay is not aggressive; behavioral
  fingerprinting is partly inherent.

Limit: even `stealth` pacing does not make a crawl look human — link-following
order and breadth-first shape remain machine-like. It removes the timing tell.

## Recommended sequencing

1. P1 — request fingerprint (agreed; highest impact, self-contained, `net.py`).
2. P2 — circuit isolation (cheap; bundle with P1 — both live in `net.py`).
3. P3 — pacing profile (needs a settings key + UI; do after P1/P2).
4. Finding 1 — DB-access seam (separate track; enables later encryption).
5. Findings 2/4 deferred; Finding 5 + at-rest encryption tracked elsewhere.

## Decisions (resolved)

- P1: agreed — adopt the current Tor Browser request profile (UA + full header set).
- P2: agreed — direction A, per-onion-host circuit isolation via SOCKS credentials.
- P3: agreed — direction B, per-crawl pacing profile, default `polite`.

All three are ready to implement; recommended order is P1 → P2 → P3, then the
DB-access seam (Finding 1).
