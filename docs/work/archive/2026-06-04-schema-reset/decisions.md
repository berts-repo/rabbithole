# Decisions

Owner sign-off gates from `schema-reset-checklist.md` Phase 1, resolved with the
owner at promotion (2026-06-04).

## Gate 1 — DROP `status` from `analyses` / `collection_analyses` — CONFIRMED

The two source specs contradicted: `schema-reset.md` implied keep ("get the new
state vocabulary on their `status` column"); `unified-activity-view.md` listed
the columns under "What Gets Deleted". **Resolution: DROP.** Status is read from
the linked `jobs` row, identical to how `crawls` was resolved ("loses its own
`status` column so the two never drift"). The typed *tables* are retained — only
the redundant `status` *column* goes. If analyses ever need a result-level state
distinct from job state, it returns as a differently-named column, not `status`.

## Gate 2 — Fill-in decisions D1–D6

D1, D2, D3, D5, D6 **accepted as written** in `schema-reset-ddl.md`:

- **D1** — `AUTOINCREMENT` on all surrogate PKs (no rowid reuse rebinding stale
  refs; matches current `nodes`).
- **D2** — carry `analysis_excluded` + `opened_at` onto `pages`.
- **D3** — `CHECK` enums on `jobs.kind`/`target_type`/`status` (bad values never
  reach disk; `kind` uses the full activity set).
- **D5** — `response_headers` keyed by `page_version_id`, current-version rows
  only (deleted in the crawl txn on version advance).
- **D6** — `findings` indexed on `resource_id` and `kind`.

### D4 — REVISED (owner-confirmed)

Original D4 proposed `pages.review_state` as **un-CHECKed free TEXT** "for now,"
to be tightened when item 7 (Intel pane) defines review states. Owner rejected
the "for now" framing: an un-validated column with no consuming workflow is the
worst of both worlds — no integrity guard *and* no feature.

**Resolution:** keep today's boolean as `pages.reviewed`
(`INTEGER NOT NULL DEFAULT 0`), preserving exact current behavior. The typed,
`CHECK`-constrained `review_state` machine is built **whole by item 7** as an
additive migration when it designs the review workflow — states and the UI that
drives them, together. No half-built column ships in this reset.

Column mapping update: old `nodes.reviewed` (0/1) → `pages.reviewed` (0/1),
**not** `pages.review_state`. Update `schema-reset-ddl.md` `pages` DDL + the
column-mapping table to match.

## Migration strategy — DB delete, no export

Reaffirmed from `schema-reset.md`: DB delete is the migration. No in-place
migration, no adapter, no pre-wipe export of curated config (owner-declined).
The DB is disposable dev data. `SCHEMA_VERSION` 2 → 3.
