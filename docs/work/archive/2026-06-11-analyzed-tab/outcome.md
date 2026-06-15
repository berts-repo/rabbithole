# Outcome — B8 Analyzed-nodes tab

Closed 2026-06-11. A small Phase **B8** (LLM + Embed + Search) follow-on: a
read-only bottom-pane **Analyzed** tab that surveys which nodes have actually
been analyzed by the LLM worker — one row per node, dropped-result jobs excluded
server-side. The inspect counterpart to the Intel/Analyse *compose* surface and
the Activity *monitor* surface.

## What shipped

**Backend — one query + one route.**
- `db/llm.py::list_analyzed_nodes` — nodes with ≥1 *successful* completed
  per-resource analysis, newest-analyzed first. Mirrors the `list_queue` join
  (`json_extract(jobs.payload, '$.analysis_id')`), then joins `resources` for
  identity and `pages`→`page_versions` for the current title (same chain as
  `pages.get_page_detail`). Returns `node_id`, `url`, `title`, `state`, the
  distinct `analysis_types` (`GROUP_CONCAT(DISTINCT …)`, single-arg form —
  required with `DISTINCT`), and `last_analyzed` (`MAX(jobs.finished_at)`).
- Dropped jobs are excluded: the worker marks a job `done` even when output is
  unusable, writing a `<dropped:...>` sentinel into `analyses.result`
  (no_content / ollama_unreachable / invalid_output). A node whose every
  analysis was dropped is filtered out with `result NOT LIKE '<dropped:%'`.
- `routes/llm.py` — `GET /api/analyzed-nodes` (limit-capped 1..500, default
  200). A top-level path, *not* under `/api/analyses/...`, so it cannot collide
  with the `int` path param of `get_analysis`. Splits the DB's comma-joined
  `analysis_types` string into a list so the client gets a clean shape.

**Frontend — tab + pure helpers.**
- `lib/api/types.ts` `AnalyzedNodeRow` + `lib/api/analyses.ts` `listAnalyzedNodes`.
- New `analyzed` bottom tab registered in `stores/bottomTabs.ts` and rendered in
  `BottomPane.svelte`.
- `views/bottom/AnalyzedTab.svelte` — loads once on first switch, ⟳ refresh
  re-fetches; URL/title filter; per-row host ●/○ visibility dot
  (`domainVisibilityStore`, matching Flags / Domains); right-click opens the
  shared `rowMenu`; row click is a **full select** (CLAUDE.md selection model),
  which drives the right-pane Analysis tab — so the tab needs no detail view of
  its own.
- Filter + display formatting split to a DOM-free `views/bottom/analyzed.ts`
  (the same `flags.ts` / `domains.ts` split) for unit testing.

## Verification

- Backend: `tests/test_b8_analyzed_nodes.py` (5 tests) — 824 pytest green.
- Frontend: `views/bottom/analyzed.test.ts` — 508 vitest green; check 0/0;
  single `bundle.js` + `bundle.css` build clean.

## Notes

- Shipped alongside an unrelated **graph stub-halo spacing** tweak (committed
  separately): stronger force repulsion (`scalingRatio`), the halo spiral now
  starts past the hub's own radius, smaller uncrawled stubs, and `positions`
  size-reference rendering. Two stale `geometry.test.ts` expectations
  (`haloOffset` slot-0, `nodeSize` stub) were updated to the new constants.
- Recorded in `docs/reference/features.md` (bottom-pane Analyzed bullet).
