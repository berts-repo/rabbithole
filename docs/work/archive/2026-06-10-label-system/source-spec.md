# Label System

## Status

Implementation-ready feature spec. Lands after the schema reset (item 6).
Adds three new tables (`labels`, `resource_labels`, `domain_labels`) plus
`pages.alias`, and ships three frontend surfaces (bottom-pane Labels tab,
left-pane label search inside the Intel/Find sub-tab strip, graph color
mode + label filter). All schema work is additive — no breaking changes to
the post-reset tables.

Builds on:
- `schema-reset.md` (resources/pages/graph_nodes split; labels' join
  tables target `resources(id)` and `domains(host)`)
- `pane-responsibility-reset.md` (bottom-pane owns lists)
- `shared-ui-primitives.md` (Labels tab + chip rendering use the shared
  components)
- `list-to-graph-tabs.md` (a label query becomes a NodeSet workspace tab)

Supersedes the open question in
[`list-to-graph-tabs.md`](list-to-graph-tabs.md) about how a label query
opens as a graph tab — this spec confirms labels are a valid NodeSet
source.

## Goal

Give the analyst a managed way to **categorize** resources (URLs / pages)
and domains as they work — "this is a market," "this is a drug
marketplace," "avoid this" — and then **query, filter, and visualize** by
those categories. The same UI section also covers free-text **renaming**
of pages (the domain rename already ships as `domains.alias`).

The driving workflow: an analyst crawls many similar sites. They tag each
one as they triage, then later pull up "every resource labeled Market,"
exclude "Avoid" sites from a view, or open a labeled set as its own graph
workspace tab.

## Two Distinct Concepts — Keep Them Separate

Rename and label share one UI panel but stay separate in the data model:

| Concept | Cardinality | Purpose | Example |
|---|---|---|---|
| **Rename** (alias / display name) | 1:1 — one name per target | Human-readable name replacing the raw host / URL | `abcd…xyz.onion` → "NightMarket"; page URL → "Vendor X profile" |
| **Label** (tag) | N:M — many labels per target, many targets per label | Shared classification from a managed taxonomy | "Market", "Drug marketplace", "Avoid" |

Folding rename into labels would force a unique display string to compete
with a shared category for the same field. They stay separate:

- `domains.alias` (already exists, post-reset unchanged) — domain rename.
- `pages.alias` (new column, this spec) — page rename.
- `labels` + two join tables (new, this spec) — taxonomy.
- One UI panel surfaces rename + labels side by side.

### Why not store labels in `findings`?

The schema-reset `findings` table holds content-extracted items (entities,
flags, notes). Labels are different in two ways that matter: they need a
**managed taxonomy** (preset palette, colors, descriptions, builtin flag)
and they need **referential integrity** on attachments (cascade-on-delete,
no stringly-typed value column). Storing them as `findings(kind='label')`
loses both. Typed join tables are smaller and clearer; ~30 LOC of schema
for a meaningfully different data type.

Schema-reset's `findings.kind` set is therefore `entity | flag | note`
(not `label`).

## Data Model Changes

New tables (project SQLite DB; authoritative schema in
`backend/backend/db/core.py`):

```sql
CREATE TABLE labels (
    id          INTEGER PRIMARY KEY,
    name        TEXT    UNIQUE NOT NULL,
    color       TEXT,                          -- swatch for graph + chips
    description TEXT,
    builtin     INTEGER NOT NULL DEFAULT 0,    -- 1 = seeded preset
    created_at  TEXT
);

-- Two typed join tables, not one polymorphic table: resources(id) is
-- INTEGER, domains(host) is TEXT, so a (target_type, target_id) shape
-- can't use FKs or cascade cleanly. Matches the analyses /
-- collection_analyses decision in schema-reset.md.
CREATE TABLE resource_labels (
    label_id    INTEGER NOT NULL REFERENCES labels(id)    ON DELETE CASCADE,
    resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    PRIMARY KEY (label_id, resource_id)
);

CREATE TABLE domain_labels (
    label_id INTEGER NOT NULL REFERENCES labels(id)    ON DELETE CASCADE,
    host     TEXT    NOT NULL REFERENCES domains(host) ON DELETE CASCADE,
    PRIMARY KEY (label_id, host)
);
```

Page rename column:

```sql
ALTER TABLE pages ADD COLUMN alias TEXT;
```

`pages.alias` (not `resources.alias`) because the URL is the immutable
identifier; the analyst is naming the *content* they crawled, not the
endpoint.

These are additive changes against the post-reset schema. No
`schema_version` bump dance; the schema reset cutover delivers a single
fresh schema and this lands on top.

## Label Taxonomy — Presets + Custom

- **Preset labels** ship seeded at schema creation (`builtin = 1`). Locked
  starter palette:
  - `Market` (commerce / vendor listings)
  - `Forum` (discussion boards)
  - `Directory` (link indexes)
  - `Blog` (single-author content)
  - `Service` (paste, mail, search, util)
  - `Scam` (known scam / phishing)
  - `Avoid` (analyst-only exclusion tag — drives the avoidance filter)
- **Custom labels** are analyst-created at any time (e.g. "Drug
  marketplace", "Ransomware leak site"). `builtin = 0`.
- **Edit / delete rules**:
  - Presets can be recolored and have their description edited.
  - Presets cannot be deleted (keeps a stable baseline) but can be hidden
    from the picker through a settings toggle.
  - Custom labels are fully editable and deletable. Deletion cascades to
    `resource_labels` / `domain_labels`.

## Where Labels Attach — Resource vs Domain

Labels apply to **both** resources and domains:

- A **domain label** classifies a whole site ("this onion is a market").
- A **resource label** classifies a single URL / page.

**No automatic propagation.** A domain label belongs to the domain (and
the domain's group-by-domain cluster node only). Page-level labels are
explicit. A "labels filter" can still match a resource by its domain's
labels at *query time* (`SELECT … JOIN domain_labels ON resources.host
= domain_labels.host …`) without stamping the label onto every page node.

This avoids re-creating the alias-clutter problem that prompted the
existing alias-on-graph discussion — every page node of a Market-labeled
domain rendering identically as "Market" would be unreadable.

## Relationship to Existing Features

- **Domain alias** (`domains.alias`) — becomes the "rename" half of the
  new UI panel. Resolves the open question of how an alias displays on
  the graph: aliases attach to the **domain node only** (or the
  group-by-domain cluster representative), never propagating to every
  page node. Page-level rename uses `pages.alias`.
- **`pages.category`** — the auto-categorizer writes a single-valued
  `category` per page. Labels are the *manual, multi-valued* analyst
  layer. They stay as separate auto vs manual layers for v1; revisit
  unification only if the auto-categorizer is reworked.
- **Collections** — a collection is a hand-built working set; a label is
  a classification. They're complementary. Collections already open as
  workspace tabs; labels become a new NodeSet source via
  [`list-to-graph-tabs.md`](list-to-graph-tabs.md).
- **`graph_filters`** — stays **untouched**. It remains the term-based
  hide list (regex / substring). Label-based hide is a **separate filter
  dimension** plugged into `visibilityController` (from
  `graphcanvas-decomposition.md`). Both filters compose; neither is
  rewritten in terms of the other. Rationale: term-match and label-match
  are different inputs (text vs FK), and a polymorphic kind column on
  `graph_filters` would reintroduce the polymorphic-table anti-pattern
  the schema reset just rejected.

## Surfacing Labels

1. **Left pane — label browser inside the Find sub-tab.** The Find
   sub-tab (specced in `pane-responsibility-reset.md` as one of three
   left-pane sub-tabs: Crawl / Intel / Find) hosts both the F5 keyword
   composer and the label browser. The analyst browses labels, sees
   member counts, selects a label to highlight its members in the current
   graph workspace.
2. **Bottom pane — Labels tab.** New tab alongside Collection · Bookmarks
   · Activity · Domains · Flags · Fingerprints · Hidden · Scheduled
   Crawls. Lists labels with member counts; expanding a label shows its
   labeled resources / domains.
3. **Graph.** Labels feed a new **color mode** (color nodes by their
   first / dominant label) and a **label filter** (include / exclude
   labels in visibility). The "Avoid" workflow is just the label filter
   with `Avoid` set to "hide."
4. **Right panel + context menus.** Apply / remove labels and rename
   from the node and domain right-click menus and the right-panel action
   bar. The existing `RenameAliasPopover.svelte` pattern extends to
   `pages.alias`.
5. **Settings modal — Labels tab.** Preset visibility toggles, custom
   label CRUD, color palette management. Lands as part of
   `settings-modal.md` once label CRUD endpoints exist; the bottom-pane
   Labels tab can ship before the settings tab.

## Querying and the "Avoid Sites" Workflow

Labels become a first-class query dimension:

- Filter the graph, NodeSet workspaces, search results, and bottom-pane
  lists by one or more labels (include and exclude).
- "Avoid drug marketplaces": exclude that label → matching resources
  dim or hide in the graph.
- A label query result is itself a node set, which opens as its own
  graph workspace tab via [`list-to-graph-tabs.md`](list-to-graph-tabs.md).
  The `NodeSetSource` discriminator `{ kind: 'label'; labelId: number }`
  is already specced.

## Suggested Phasing

Three phases inside this package:

1. **Schema + label CRUD.** `labels`, `resource_labels`, `domain_labels`,
   `pages.alias`; preset seeding; DB / route modules; tests for CRUD and
   cascade behavior. ~400–600 LOC backend.
2. **Assignment UI.** Apply / remove labels + page rename from context
   menus and the right-panel action bar. Reuses `RenameAliasPopover`
   pattern for the page alias.
3. **Surfacing.** Bottom-pane Labels tab, left-pane label search, graph
   color mode, graph label filter (incl. "Avoid"). Plus the
   `NodeSetSource.label` workspace flow wired to
   `list-to-graph-tabs.md`.

The Settings modal Labels tab lands in parallel with phase 3 once CRUD
endpoints exist.

## Affected Surfaces

Backend (new + modified):

- `backend/backend/db/core.py` — schema additions
- `backend/backend/db/labels.py` — new
- `backend/backend/db/resource_labels.py`, `domain_labels.py` — new
  (or combined into `labels.py` since they're trivial join tables)
- `backend/backend/db/pages.py` — `alias` column accessor
- `backend/backend/routes/labels.py` — new CRUD + apply / remove
- Existing `domains.py` route — extend with label-filter param

Frontend (new + modified):

- `frontend/src/lib/api/labels.ts` — new
- `frontend/src/lib/stores/labels.svelte.ts` — new
- `frontend/src/views/bottom/LabelsTab.svelte` — new
- Right-panel action bar — "Apply / remove label" action helper
- Page right-pane tab — page rename popover (mirrors domain alias)
- `frontend/src/views/left/` — label search inside the Find /
  Intel sub-tab strip (after items 6 + 8 ship)
- Graph color mode list — add `label` mode
- `visibilityController` — accept a `labelFilter` predicate

## Code Size Expectation

Net add: ~1,500–2,500 LOC across backend + frontend. This is a feature
addition, not a cleanup — the win is analyst workflow, not LOC reduction.

## User-Visible Changes

- New "Labels" panel in right-click menus + right-panel action bar —
  apply / remove labels per resource or domain alongside rename.
- New bottom-pane Labels tab.
- Label chips next to resource / domain names in lists and right panel.
- Graph color mode "Label" + label-based filter (include / exclude).
- "Avoid these sites" workflow via the `Avoid` preset label.
- Page rename available everywhere a domain rename is, via the same
  popover pattern.

## Deferred Decisions

- Whether the auto-categorizer (`pages.category`) and labels eventually
  unify, or stay as separate auto vs manual layers.
- Whether the label color also drives label-chip text color or only the
  swatch (legibility on dark theme depends on color choice).
- Whether a resource can carry the same label twice through both its
  domain and its own attachment (recommended: dedupe at query time;
  show "via domain" badge in the chip).
- Whether "Avoid"-labeled domains also suppress crawl-on-discovery (a
  crawl-policy question, not a labeling question — likely a Crawl &
  Queue setting in `settings-modal.md`).
