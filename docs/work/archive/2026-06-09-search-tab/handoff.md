# Handoff — Search tab completion (item 10)

Picked up 2026-06-09, graduated from `NEXT.md` item 10 when item 9 (Find
sub-tab) closed. Runs alongside the still-active item 8 (Settings Modal) — no
code conflict: item 8 owns the Settings modal / Engines management, item 10 owns
the Search tab that *consumes* those engines.

## Start here

The backend is done; the work is the frontend client + UI. Read
`backend/backend/routes/harvest_search.py` first to lock the SSE event contract,
then replace the `views/SearchTab.svelte` stub.

## Watch-outs

- **Untrusted content.** Engine results and probe titles/descriptions are
  attacker-controlled onion-page text. Render as auto-escaped text — never
  `{@html}`. Same discipline as the Find sub-tab's `parseSnippet`
  (`archive/2026-06-09-find-subtab/`).
- **Tor egress only.** The probe stage already routes through the Tor proxy
  server-side; the frontend must not fetch result URLs directly. All discovery
  traffic stays on the existing `/api/harvest/search` path.
- **Passive mode** is a persisted setting (`search.passive_mode`), shared with
  the Settings surface — toggle via `PUT /api/settings/...`, don't shadow it in
  local-only state.
- **Engine source-of-truth.** The selector reflects *enabled* engines from
  settings and can be overridden per-session without mutating those defaults.

## Open decisions

None recorded yet. Add `decisions.md` if owner choices arise (e.g. session
persistence of the last query/results across tab switches).
