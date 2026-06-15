# Decisions — Label System (item 11)

Owner-settled decisions from the planning conversation. The data-model and
taxonomy decisions in
[`source-spec.md`](source-spec.md) still hold; the ones below are this package's
additions and overrides.

## D1 — Page rename lands on the existing rename seam, not a new component

The rename consolidation already shipped a target-agnostic seam: `RenameTarget`
(`domain | page`) in `lib/contextMenu/rename.ts`, one `renameTarget()` save path
in `contextMenu/actions.ts`, with the `page` branch stubbed
(`throw "Page rename not yet available"`). Page rename is therefore: add
`pages.alias` column + `PATCH` endpoint + `patchPageAlias` client, then replace
the stub body. **No new popover, no fork.** Every surface that already renames a
domain gets page rename with identical post-save behavior for free.

`pages.alias` (not `resources.alias`): the URL is the immutable identifier; the
analyst names the *content* crawled, not the endpoint. Mirrors the source spec.

## D2 — Additive v5 → v6 migration; labels are not a `findings` kind

New tables `labels`, `resource_labels`, `domain_labels` + column `pages.alias`
land as a non-destructive forward migration (`SCHEMA_VERSION` 5 → 6) on the
existing `core.py` migration seam — **no DB delete**. Two typed join tables, not
one polymorphic `(target_type, target_id)` table, because `resources.id` is
INTEGER and `domains.host` is TEXT; typed FKs give clean cascade-on-delete.
Labels stay out of `findings` (kind remains `entity | note`): they need a
managed taxonomy (preset palette, color, `builtin`) and referential integrity on
attachment that a stringly-typed findings row loses.

## D3 — Preset taxonomy ships as the source spec lists it

Seeded `builtin = 1` presets: **Market, Forum, Directory, Blog, Service, Scam,
Avoid**. Broad site-*types* plus the one analyst-only exclusion tag (`Avoid`).
Narrower classifications ("Drug marketplace", "Ransomware leak site") are
analyst-created custom labels (`builtin = 0`). Presets recolor/redescribe but do
not delete (hideable via settings toggle); custom labels are fully
editable/deletable with cascade.

## D4 — Collapse is a distinct verb from Hide

Two different graph operations; keep them separate in code and in the menu:

- **Hide** — the node is *gone* from the view. Already exists ("Hide from Graph"
  / "Hide All"; adds the URL to `graph_filters`, applied server-side). Unchanged.
- **Collapse** — many nodes *fold into one* summary node that stays on the
  canvas. This package's new capability. Collapse is a *summarize*, never a kind
  of hide.

Rationale: they answer different analyst questions ("make this disappear" vs.
"treat this group as one thing"), and conflating them would overload the hide
filter with a second meaning.

## D5 — One analyst-ranked label list resolves every "which group wins"

`collapse-by-label` is a **grouping mode**, not a one-shot action: the analyst
can fold several labels at once ("Markets as one node, Forums as one node"),
which makes it at least as strong as the existing group-by-domain. The instant
multiple labels can be collapsed, a page tagged both Market *and* Scam can only
physically live in one folded node, so a single rule decides its home:

> A page folds into the **highest-ranked collapsed label it carries**. The rank
> is an explicit, analyst-controlled ordering of the taxonomy.

Properties that make this the right long-term model (not a v1 shortcut):

- **Deterministic + legible** — same graph, same folding every time; the user
  reads their ranked list and predicts exactly where any page lands.
- **Analyst controls what matters** — warnings (`Avoid`, `Scam`) rank high by
  default, so those clusters stay the *complete* set even when their pages are
  also Markets; the weaker label gives ground.
- **One ordering powers three features** — the same rank decides the collapse
  home, the "dominant label" for **color-by-label**, and the picker order. One
  concept, reused.
- **Overlap stays visible** — a folded node shows the overlap, e.g.
  `Scam · 12 pages (4 also Market)`, so nothing is silently swallowed.

**Rejected alternative — node duplication** (a dual-labeled page appears in
*both* label nodes): double-counts member tallies (12 + 8 for 17 unique pages)
and makes edge ownership / selection ambiguous. For an aggregate summary node,
ranking is cleaner *and* more truthful in the counts that matter.

## D6 — Domain collapse is the floor of that same ranking

The only place domain-collapse and label-collapse conflict is a page that is in
a collapsed domain **and** in a collapsed label — it can sit in one folded node,
not two. Resolve it with the **same** D5 ordering by treating `domain` as the
lowest rank:

> Fold a page into the highest-ranked collapsed label it has; if it has none and
> its domain is collapsed, fold it into the domain.

So a `Scam` page inside a collapsed `NightMarket` is pulled into the `Scam` node
(Scam outranks "domain"); the domain node just shows fewer pages. No separate
"domain vs label" rule — domain is one entry at the floor of the one list. This
keeps label clusters analytically *complete*, the safer default for OSINT.

(The coherent alternative — a collapsed site is always one indivisible blob —
would put `domain` at the *top* of the ranking instead. Owner chose
domain-at-the-floor for complete label clusters.)

## D7 — Collapse is selective and name-aware, extending the existing machinery

Today `groupByDomain` is a single global toggle that folds *every* multi-page
site into a `cluster:<domain>` node, with an `expandedDomains` exception set.
This package adds **selective** collapse — a per-target "Collapse" action that
folds just the chosen domain/label independent of the global toggle — over the
same `clusterDomain` cluster-key + `synthesizeClusterRaw` seam.

Bug to fix while there: `synthesizeClusterRaw` hardcodes `alias: null` and
labels the folded node with the bare host, *ignoring* `domains.alias`. The
collapsed domain node must show the **alias when set**, host otherwise — that is
half of what "collapse by a rename" means. The label cluster node is named by
the label.

## D8 — Collapse state persists per workspace tab, reusing the workspace store

Collapse is a *view arrangement*, not a durable fact — but it persists.
**Per workspace tab, saved with the project**, riding on the existing workspace
persistence (`workspace.svelte.ts` already persists each tab's source + label
via the settings store). One mechanism delivers both things the owner asked for:

- **different folding per tab** — a "Markets overview" tab folded by label, a
  "NightMarket deep-dive" tab folded by domain, each remembering its own state
  (this subsumes the "per collection" idea — collections already *are* workspace
  tabs);
- **survives restart** — written with the rest of the workspace.

**Rejected** a separate per-collection persistence tier: redundant with tab
persistence and would drift from it. The renames and labels themselves stay
durable in the DB regardless of any tab; only the *folding* is tab-scoped.

## Deferred (unchanged from source spec)

- Whether the auto-categorizer (`pages.category`, single-valued, auto) and
  labels (multi-valued, manual) eventually unify — stay separate layers for now.
- Whether `Avoid`-labeled domains also suppress crawl-on-discovery — a Crawl &
  Queue *policy* setting, not a labeling decision; lives with `settings-modal.md`
  Wave 2.
- Whether the label color drives chip text color or only the swatch — decide at
  build time against dark-theme legibility.
