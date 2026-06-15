# Outcome — Analysis / Intel Pane (item 7)

Closed 2026-06-09. Built the left-pane **Intel** sub-tab and consolidated the
fragmented analysis entry points into one compose / monitor / inspect pattern,
on an additive `SCHEMA_VERSION 4 → 5` migration (no DB delete).

## What shipped

**Backend (v5, additive).**
- New tables: `prompt_templates` (project-local analyzer presets, built-ins
  seeded + hideable), `auto_analysis_rules` (single typed home for both
  `crawl` and `collection_add` triggers, D4), `cluster_analyses`
  (fingerprint-keyed cluster synthesis, D1). Nullable `prompt_id` FK added to
  `analyses` / `collection_analyses` / `cluster_analyses` (NULL = ad-hoc
  free-form prompt).
- Routes: `/api/prompts`, `/api/auto-analysis-rules`, cluster analyses under
  `/api/clusters/...`, and a load/capacity block on `/api/llm/status`. Worker
  honors a configurable `llm.batch_size` concurrency.
- Auto-analysis: collection-add trigger wired (Phase 1); crawl trigger migrated
  off the legacy `llm.auto_enqueue.*` settings onto seeded `crawl`-kind rules
  (Phase 3, D4) with a parity test.

**Frontend.**
- Intel sub-tab (collapsible sections): Analyse compose form, worker controls +
  live load indicator, auto-analysis rules, embedding status, collection
  analysis.
- One compose path per target kind: **nodes** funnel through `ComposeForm` via
  the `queueAnalysis` helper (graph menu, right-pane action bar, right-pane
  Analysis tab all stage rather than open a modal); **collections** in
  `CollectionAnalysis`; **clusters** inline in the cluster `QnATab`.

## The Phase-4 discovery (and why scope grew)

Phase 1's `cluster_analyses` was **non-functional**: it stored only the
membership *fingerprint* (a one-way hash), so the worker had no way to fetch the
member pages — and the worker never claimed cluster jobs at all. Today's QnATab
"worked" only because it wrote per-node `analyses` rows (the very path D1 says to
retire). Routing cluster Q&A to `cluster_analyses` therefore required finishing
that backend before the frontend rewrite — required under either UX option,
since both write to the same table. This pass:
- added a `resource_ids` JSON membership snapshot to `cluster_analyses` (DDL +
  guarded ALTER), so the worker can read the membership back;
- wired `claim_next_cluster` + `_process_cluster_job` (synthesis) into the
  worker tick — one synthesis job per idle tick, after collections;
- added a `Cluster Q&A` multi-page prompt spec and made `render_multi`
  question-aware, so a cluster question is asked once across the concatenated
  membership → **one synthesis answer** (not one row per page, which the
  single-result table can't hold);
- tightened the route to reject single-page types for clusters.

## Owner decisions (Phase 4)

- **Cluster Q&A UX → Option B (inline ask).** The question box stays in the
  cluster workspace (no pane jump) while sharing the `createClusterAnalysis`
  dispatch and `cluster_analyses` storage. Chosen over funnel-to-Intel because
  Q&A is the most iterative loop; "one compose path" is satisfied at the
  dispatch level, not by forcing a single UI box.
- **Prompt templates → deferred (Option C), out of this package.** Worker
  body-substitution is a data-integrity concern for the *typed* output contracts
  (Risk Score→int, Category→enum), not the injection surface first assumed (page
  content is the real injection vector and already exists). Follow-up target:
  editable bodies drive free-form types only; typed types stay on the audited
  `prompts.py`. Tracked in `NEXT.md`.

## Verification

- Backend 714 passed + lint-security OK. (One crawl-runtime test is
  timing-flaky under full-suite load; passes in isolation, untouched here.)
- Frontend svelte-check 0 errors, 393 vitest, single `bundle.js`/`bundle.css`.
- New coverage: cluster e2e in `test_b8_llm_worker` (synthesis + question
  threading + no-content drop), `test_intel_cluster_analyses` (membership
  round-trip + single-page rejection), and `fingerprint.test.ts` pinned to the
  backend `compute_fingerprint` so the two implementations can't drift.

## LOC reconciliation

Frontend consolidation is **−151 net** (358 removed, 207 added incl. the tested
fingerprint helper) — `QueueAnalysisModal` deleted, the bespoke cluster
per-node poll gone, ComposeForm's dead cluster/collection dispatch branches and
`ComposeTarget` kinds removed. It does not reach the spec's −300..−600 because
that target assumed the Option-A unified funnel (every surface collapsing to one
form) that Option B traded away for the in-context cluster loop, and because the
cluster backend Phase 1 left unfinished had to be built (net-additive).

## Deferred / follow-ups

- Prompt-template management UI + worker body-substitution (Option C above).
- Label/score predicate filters on auto-analysis rules (waits on item 11).
- Per-analyzer worker pool (single concurrency number for now).
- Cross-project / shareable prompt templates (D3 chose project-local).
