# Decisions — Find sub-tab (item 9)

## D1 — Keyword search covers page + entity + note (owner: "all three now")

The spec's Keyword mode lists three result types; the backend endpoint returned
pages only. Building pages-only would quietly miss data the analyst knows they
saved (an entity value not in visible page text, or their own note body) — a
false-negative trap. So keyword search now unions:

- **page** — FTS5 `MATCH` over current page text (existing `pages.keyword_search`,
  now tagged `type:'page'`).
- **entity** / **note** — `findings.value LIKE` over the unified `findings`
  table; entity rows carry `entity_type` from `metadata.$.type`.

**Why LIKE for findings, not FTS:** entity values (crypto addresses, handles,
emails) and notes are short, exact-ish strings — substring match is the right
tool, and there's no FTS index on `findings`. Single-user local DB sizes make a
`LIKE` scan acceptable; `idx_findings_kind` bounds it.

## D2 — Result ordering and the findings sub-cap

Cross-type relevance isn't comparable (FTS `rank` vs. substring hit), so the
policy is explicit rather than a fake unified score: **pages first (FTS-ranked),
then entity, then note**. To stop a flood of page hits from starving the
structured findings the analyst specifically came for, findings get their own
sub-cap (`_FINDINGS_SUBLIMIT = 25`) on top of the page `limit`, so they always
appear when present. Documented in `routes/search.py`.

## D3 — Note snippets truncated server-side

Note bodies run up to 8 KB. The result row shows a snippet, so the route
truncates note `value` to a short preview (~200 chars) to keep payloads small;
the full note stays available in the right panel.

## D4 — Results live in the bottom pane as tab `find`

Per spec, results are a list, and lists are a bottom-pane pattern (Domains,
Flags, …). A new `BottomTab` id `find` (label "Find") is added to
`bottomTabs.ts` and the backend `_BOTTOM_TAB_VALUES`. It is **not** in
`DEFAULT_VISIBLE_TABS` — running a Find auto-reveals it through the
`setBottom` auto-add, and it persists on the strip afterward like any tab. This
reuses the customizable-strip machinery rather than adding a special case.

## D5 — Semantic `distance` → `score` in the frontend

`db.embed.semantic_search` returns vec0 `distance` (lower = closer). The spec
shows a 0–1 similarity score (higher = closer). The mapping `score = 1 -
distance` (cosine distance) is applied in the frontend API client so the store
and UI speak the spec's vocabulary; the backend stays in its native metric.
