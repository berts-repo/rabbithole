# Plan — Label System (item 11)

Three phases, build order not "do less." Each phase is shippable and leaves the
app green. Data model, taxonomy, and querying detail live in the source spec
([`source-spec.md`](source-spec.md)); the
collapse model lives in [`decisions.md`](decisions.md) D4–D8.

## Phase 1 — Schema + label CRUD + page rename column (backend)

Foundation. No UI yet beyond what an endpoint test exercises.

**Schema (`db/core.py`, v5 → v6 additive forward migration, no DB delete):**

```sql
CREATE TABLE labels (
    id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, color TEXT,
    description TEXT, builtin INTEGER NOT NULL DEFAULT 0,
    rank INTEGER NOT NULL DEFAULT 0,           -- D5 ordering (collapse/color/picker)
    hidden INTEGER NOT NULL DEFAULT 0,         -- preset hide-from-picker toggle
    created_at TEXT
);
CREATE TABLE resource_labels (
    label_id INTEGER NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
    resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    PRIMARY KEY (label_id, resource_id)
);
CREATE TABLE domain_labels (
    label_id INTEGER NOT NULL REFERENCES labels(id) ON DELETE CASCADE,
    host TEXT NOT NULL REFERENCES domains(host) ON DELETE CASCADE,
    PRIMARY KEY (label_id, host)
);
ALTER TABLE pages ADD COLUMN alias TEXT;
```

`rank` and `hidden` are added beyond the source spec to carry D5 (the single
analyst ordering) and D3 (preset hide toggle). The forward-migration block in
`core.py` creates the three tables `IF NOT EXISTS`, adds the column, seeds the
seven presets with sensible default ranks (warnings high — `Avoid`/`Scam` low
`rank` number = top), and bumps `SCHEMA_VERSION` to 6.

**DB modules:** `db/labels.py` — label CRUD, attach/detach for both join tables
(trivial join tables fold in here, not separate files), member-count queries,
and the rank read/write. `db/pages.py` — `alias` accessor mirroring
`db/domains.py`'s.

**Routes:** `routes/labels.py` — CRUD (`GET/POST/PATCH/DELETE /api/labels`),
attach/detach (`POST/DELETE /api/labels/:id/resources/:rid`,
`.../domains/:host`), reorder (`PATCH /api/labels/order`). `PATCH
/api/pages/:id/alias` mirroring the domain-alias route. Extend `routes/domains.py`
with a label-filter query param.

**Tests:** CRUD, unique-name 409, preset-undeletable, cascade-on-delete wipes
attachments, page-alias set/clear, rank reorder. Preset seeding idempotent
across a re-run migration.

Size: ~400–600 LOC backend.

## Phase 2 — Apply labels + page rename (the shared menu)

Where it starts to *feel* real. No new component shapes — reuse the seams.

- **Page rename:** replace the stub body of the `page` branch in
  `contextMenu/actions.ts` `renameTarget()` with a `patchPageAlias` call; add
  `lib/api/...` client. The popover, modal state, and refresh path already exist
  from the rename consolidation — page rename inherits identical post-save
  behavior. Drop the misleading domain-rename-from-PageTab path now that a true
  page alias exists.
- **Label apply/remove:** a multi-target "Apply / remove label" action helper on
  the shared `contextMenu/actions.ts` layer (sits with `flag`, `addToCollection`,
  etc.), surfaced in the node + domain right-click menus and the right-panel
  action bar. A small label-picker popover (search existing + create-new inline).
- **Chips:** label chips render next to resource/domain names in lists and the
  right panel, using the shared chip primitive. A label carried *via the domain*
  shows a "via domain" badge (source-spec dedupe-at-query-time decision).
- **Store:** `lib/stores/labels.svelte.ts` — label list + ranks + member counts,
  the source of truth for the picker, chips, color mode, and collapse ordering.

Tests: vitest on the picker/apply helper; the action-layer attach/detach.

## Phase 3 — Surfacing: browse, filter, color, collapse

The analyst-workflow payoff. Four surfaces over the Phase 1/2 foundation.

**3a. Bottom-pane Labels tab.** New `BottomTab` id `labels`
(`lib/stores/bottomTabs.ts` + backend `_BOTTOM_TAB_VALUES`), not in
`DEFAULT_VISIBLE_TABS` — reveals on first use like the `find` tab.
`views/bottom/LabelsTab.svelte`: labels with member counts; expand a label to
its labeled resources/domains (highlight-only on click, per the app selection
model). Drag-to-reorder writes `rank` (the D5 list lives here).

**3b. Left-pane label browser.** Inside the existing Find sub-tab strip:
browse labels, see counts, select one to highlight its members in the current
graph workspace.

**3c. Graph color + filter.** Add `label` to the color-mode list (node colored
by its **highest-ranked** label — same D5 order). Add a `labelFilter` predicate
to `visibilityController` (from graphcanvas-decomposition) as a **separate
dimension** from `graph_filters`: include/exclude labels compose with the
existing term-hide; neither is rewritten in terms of the other. The "Avoid"
workflow is just this filter with `Avoid` set to exclude.

**3d. Graph collapse (D4–D8).** The core new machinery, extending the
`clusterDomain` seam:

1. **Fix domain clusters to be alias-aware** — `synthesizeClusterRaw` reads
   `domains.alias` and labels the folded node with the alias when set, host
   otherwise (today it hardcodes `alias: null`).
2. **Selective collapse** — a per-target "Collapse" right-click action that
   folds the chosen domain (independent of the global `groupByDomain` toggle)
   into its `cluster:<domain>` node. Reuses the existing expand/collapse
   exception machinery (`expandedDomains` / `toggleDomainExpanded`).
3. **Collapse-by-label** — a new cluster type parallel to `clusterDomain`:
   `cluster:label:<id>` keyed by label, folding every page carrying that label
   across domains, named by the label, colored by its swatch. New module
   mirroring `clusterDomain.ts` (`clusterLabel.ts`).
4. **Unified fold resolution (D5/D6)** — one synthesis pass assigns each page to
   the **highest-ranked collapsed group it belongs to**, where `domain` is the
   floor rank. Folded nodes show overlap counts ("… 4 also Market").
5. **Persist per workspace tab (D8)** — the set of collapsed domains + collapsed
   labels rides on the workspace tab's persisted shape in `workspace.svelte.ts`,
   surviving restart, distinct per tab.

**3e. Settings modal Labels tab.** Lands in parallel once Phase 1 CRUD exists:
preset visibility (`hidden`) toggles, custom-label CRUD, color palette, and the
rank ordering (shared with 3a).

**3f. Label → NodeSet workspace tab.** Wire the already-specced
`NodeSetSource { kind:'label'; labelId }` so "all resources labeled X" opens as
its own graph workspace tab.

## Affected surfaces (delta from source spec)

Backend: `db/core.py` (v6 migration + seed), `db/labels.py` (new),
`db/pages.py` (alias), `routes/labels.py` (new), `routes/pages.py` (alias PATCH),
`routes/domains.py` (label filter param), `_BOTTOM_TAB_VALUES` (+`labels`).

Frontend: `lib/api/labels.ts` + page-alias client (new),
`lib/stores/labels.svelte.ts` (new), `contextMenu/actions.ts` (page-rename stub
body + label apply/remove helper), `views/bottom/LabelsTab.svelte` (new),
Find sub-tab (label browser), `lib/graph/model/clusterDomain.ts` (alias-aware),
`lib/graph/model/clusterLabel.ts` (new), `visibilityController` (`labelFilter`),
color-mode list (+`label`), `lib/stores/workspace.svelte.ts` (collapse state in
the persisted tab shape), Settings modal (Labels tab).

## Size

Net add ~1,500–2,500 LOC across backend + frontend. Feature addition; the win is
analyst workflow, not LOC reduction.
