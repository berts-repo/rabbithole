# Decisions — Analysis / Intel Pane

## Owner scope calls (2026-06-05)

### D1 — Cluster Q&A is IN scope for this package

Include the `cluster_analyses` table and fold the bespoke cluster `QnATab`
dispatch into the shared compose flow now.

**Why:** folding it is the only way to actually retire the bespoke cluster
Q&A path, which is the package's reason for existing (one compose/inspect
pattern, less code). Leaving it out keeps a fifth fragmented entry point alive
and defeats the consolidation goal. Argued from standardization + reuse +
smallest-code, not cosmetics.

**Consequence:** `cluster_analyses` ships in Phase 1 (cluster-fingerprint
keyed, see internal defaults). `views/right/cluster/QnATab.svelte` is rewritten
to route through the shared compose flow in Phase 4.

### D2 — Auto-analysis rules ship SIMPLE in v1

A boolean "auto-analyze newly crawled pages with analyzer X" plus a
per-collection rule list. No label/score/predicate filters in v1.

**Why:** complex predicates depend on the label system (item 11), which is not
built. The typed `auto_analysis_rules` table ships now with a `target filter
JSON` column so richer predicates are an additive change when item 11 lands —
no schema rework.

### D3 — Prompt templates: full CRUD, project-local, nullable FK

Ship the full create / edit / clone / delete typed `prompt_templates` table and
UI in v1. Templates are **project-local** (not cross-project shareable).
`prompt_id` columns on `analyses` / `collection_analyses` / `cluster_analyses`
are **nullable**.

**Why:** project-local matches the local-first single-user threat model — no
cross-project surface to secure. Nullable `prompt_id` means today's ad-hoc
free-form prompts (the only mode now) keep working unchanged; a row with a null
`prompt_id` is a free-form prompt, a row with a set `prompt_id` used a template.

## D4 — auto_analysis_rules is the single typed home (both triggers)

`auto_analysis_rules` is the canonical store for auto-analysis. It carries
`trigger_kind IN ('crawl','collection_add')`, so it is the full-shaped home, not
a collection-only side table.

**Build order (within this package, not deferred out of it):**
- **Phase 1** creates the table + module + routes and wires the **collection-add**
  trigger (the genuinely new capability). Phase 1 stays strictly additive — no
  crawler behavior change.
- **Phase 3** migrates the **crawl** trigger off the legacy `llm.auto_enqueue.*`
  settings onto seeded `crawl`-kind rules and rewrites
  `services/llm_worker.py:auto_enqueue_for_node` to read rules, with a parity
  test proving crawl auto-enqueue fires identically before/after.

**Why this split:** the end-user behavior is identical either way, so this is an
internal architecture choice (decided, not interviewed). Sequencing the crawl
migration after the table+UFI exist keeps the v4→v5 migration non-destructive
while the complete single-home consolidation still ships inside this package.

## Internal defaults (decided, not owner-facing)

- **Schema migration is additive / non-destructive.** `SCHEMA_VERSION 4 → 5`.
  No DB delete — distinct from the item-6 cutover. New tables created
  idempotently; new columns added via guarded `ALTER TABLE`.
- **Table DDL mirrors `analyses`** in shape (id, FK target, type, model,
  result, question, priority, created_at, updated_at) so the existing typed
  helpers and job-linking pattern carry over.
- **Cluster fingerprint** = the sorted set of member `resource_id`s, SHA-256
  hashed and truncated to a stable hex key, stored alongside a denormalized
  `label` snapshot taken at compose time. Re-running clustering re-attaches an
  analysis when the fingerprint matches; a changed membership orphans the old
  analysis as queryable history. (Spec §"Cluster id stability".)
- **Worker capacity** is a single concurrency number, not a per-analyzer pool.
  (Spec deferred decision resolved to the simple form.)
- **Preset prompts** seeded with `builtin = 1` — hideable, not deletable.
- **`prompt_templates` are project-local** — live in the project DB, no
  registry-level store.

## Deferred (out of this package)

- Cross-project / shareable prompt templates (D3 picks project-local).
- Label/score predicate filters on auto-analysis rules (waits on item 11).
- Per-analyzer worker pool UI (single concurrency number for now).
- Whether "synthesize this collection" becomes a distinct analyzer kind vs. a
  flag on collection-targeted analyses — kept as the existing
  collection-scoped types for now.
