# Rename Consolidation

## Status

Implementation-ready foundation refactor. **Precondition for item 11
(Label system)** — the label spec plans to "extend the
`RenameAliasPopover` pattern to `pages.alias`," but that pattern is
domain-hardwired and re-implemented per call site today. Consolidate it
into one reusable seam first, then build page rename and label-apply on
that seam instead of cloning the current shape across every new surface.

This finishes a migration the code already declares it is mid-way through:
`lib/contextMenu/actions.ts:1-24` documents the intended split — modal
state lives *with the surface*, toasts/refresh/API calls live in the
shared action layer — and notes the single-target wrappers are "kept as
thin delegators **during migration**." Rename never got migrated; it is
the last hand-rolled harness.

Builds on:
- `shared-ui-primitives.md` — `contextMenu/actions.ts` is the shared
  multi-target action layer this folds rename into.
- `graphcanvas-decomposition.md` — the per-surface modal state that stays
  with the surface.

## Problem

Rename today is one clean leaf component wrapped in three hand-rolled,
drifted harnesses. All three drive `RenameAliasPopover.svelte`, but each
re-declares its own scaffolding:

1. **Triplicated harness.** The modal-state shape
   `{ kind: 'rename'; x; y; host; currentAlias }` is typed out by hand in
   `RowContextMenu.svelte:59` and again in `GraphCanvas.svelte:75`, with a
   third near-variant (`{ x; y }`) in `PageTab.svelte:215`. Each site has
   its own open function (`renameAlias`, `openRenamePopover`,
   `openAliasPopover`) computing popover coordinates a different way, and
   its own `onSaved` handler.

2. **Inconsistent post-save behavior — user-visible.** Saving from the
   graph repaints the node label *instantly* by reaching into graphology
   (`GraphCanvas.svelte:239`, `g.setNodeAttribute(n, 'label', alias)`).
   Saving from the Page tab updates *nothing* immediately — it shows a
   toast and waits for the next graph-payload refresh
   (`PageTab.svelte:224-229`). Same action, two different felt latencies.

3. **Domain-hardwired leaf.** `RenameAliasPopover.svelte` imports
   `patchDomainAlias` directly (line 3), its props are `host` /
   `currentAlias`, its title says "Domain." It has no notion of *what* is
   being renamed, so it cannot be extended to pages — only forked.

4. **Semantic trap on the Page tab.** Because `pages.alias` does not exist
   yet, the Page tab's "Rename alias" button renames the **whole domain**
   (`PageTab.svelte:204-212` reads the domain alias from the graph
   payload). A user drilling into one page who clicks "rename" relabels the
   entire site. This is not a real feature; it is the only alias the app
   has, surfaced in a misleading place.

If labels clone this pattern, the harm multiplies: labels touch far more
surfaces (every list row, right panel, graph, a new bottom tab, context
menus) than rename's three. Each would seed its own modal state, open
function, and save/refresh handler.

## Goal

One reusable rename seam:

- A **target-agnostic** rename popover that renames whatever it is handed.
- **One** open/save/refresh path in the shared action layer, so every
  surface gets identical post-save behavior.
- Page rename (`pages.alias`) lands as a *second target kind* on that
  seam, not a forked component.

## Non-Goals

- No new rename *surfaces* beyond what exists (graph menu, graph canvas,
  Page tab) plus the page-target the seam enables.
- Does not touch `domains.alias` semantics, the 64-char limit, the
  whitespace-clears rule, or the duplicate-alias (409) contract.
- Does not build any label code. This is purely the foundation labels then
  build on.

## The Seam

### Target abstraction

```ts
// One discriminated target, mirroring the resource/domain split the rest
// of the app already keys on (domains.host TEXT vs resources/pages INTEGER).
type RenameTarget =
  | { kind: 'domain'; host: string }
  | { kind: 'page'; pageId: number };
```

### Shared action (lives in `actions.ts` — the "HERE" side)

A single `renameTarget(target, alias)` action switches on `kind`, calls
the right endpoint (`patchDomainAlias` or the new page-alias PATCH), and
runs the **one** unified post-save effect: toast + graph-payload
invalidation/refresh so the new name appears everywhere consistently. The
graph's optional instant-repaint (`setNodeAttribute`) stays *with the
surface* as a fast-path optimization layered on top of — not instead of —
the shared refresh, matching the `actions.ts` "renderer.refresh lives with
the surface" note.

### Popover (the leaf — the "WITH THE SURFACE" side)

`RenameAliasPopover.svelte` becomes target-agnostic:

- Props change from `host` / `currentAlias` to `target: RenameTarget`,
  `currentName: string | null`, and an injected `onSave(value)` /
  `onClose`. It no longer imports `patchDomainAlias`.
- The static "Domain" meta row becomes a label derived from
  `target.kind` ("Domain" / "Page"). Rename to a neutral name
  (`RenameTargetPopover.svelte`) or keep the filename — cosmetic, decide
  at build.

### Open helper

One open helper computes popover coordinates and sets the per-surface
modal state, replacing the three bespoke `openRename*` functions. Callers
pass a `RenameTarget` and an anchor (cursor coords or an element rect);
the helper returns/sets the modal state shape so the three (soon four)
call sites stop re-declaring it.

## What Page Rename Inherits For Free

Once the seam exists, page rename is: the new `pages.alias` column +
endpoint (server side, owned by the Label package's phase 1/2), then
pointing the Page tab's existing button at a `{ kind: 'page' }` target
instead of the domain. The misleading domain-rename-from-a-page behavior
is corrected in the same move. No new popover, no new save path.

## Affected Surfaces

Frontend:
- `components/graph/RenameAliasPopover.svelte` — target-agnostic props;
  drop the direct `patchDomainAlias` import.
- `lib/contextMenu/actions.ts` — add `renameTarget()` + the open helper;
  unify the post-save refresh.
- `lib/contextMenu/RowContextMenu.svelte`, `components/graph/GraphCanvas.svelte`,
  `views/right/PageTab.svelte` — drop the hand-rolled modal-state shape,
  open function, and `onSaved` handler; call the shared helper.
- `lib/contextMenu/sections.ts` — the "Rename alias…" menu entry is
  unchanged in copy; its handler now routes through the shared action.

Backend: **none.** The page-alias column + PATCH route are owned by the
Label package (where `pages.alias` is specced). This refactor is
frontend-only against the existing `PATCH /api/domains/{host}`; it merely
leaves a typed `{ kind: 'page' }` slot for that endpoint to fill.

## Phasing

1. **Generalize the leaf + add the shared action.** Make the popover
   target-agnostic; add `renameTarget()` + the open helper to `actions.ts`
   with the unified refresh. Domain rename still the only live target.
2. **Migrate the three call sites** onto the helper; delete the
   triplicated state/open/save code. Behavior identical for the user
   except that the Page tab save now refreshes consistently with the
   graph. Vitest the helper + the popover's target switch.

Page rename itself (the `{ kind: 'page' }` target going live) is **not**
in this package — it activates inside the Label package once `pages.alias`
exists. This spec only guarantees the slot is there.

## Code Size Expectation

Net roughly flat to slightly negative: removing three copies of the
harness roughly offsets the new shared helper + target type. The win is
reuse and one consistent save path, not LOC.

## User-Visible Changes

- Saving a rename from the Page tab now updates as promptly as saving from
  the graph (no more wait-for-next-refresh lag).
- No copy or layout changes. The "Rename alias…" menu entry and the
  popover look the same.
- (Deferred to the Label package, enabled by this) the Page tab's rename
  button will rename the *page*, not the whole domain.

## Deferred / Out of Scope

- The actual `pages.alias` column, its PATCH endpoint, and flipping the
  Page tab button to the page target — owned by item 11 (Label system).
- Whether to fold label-apply into the same open helper — likely yes, but
  proven against this seam during the Label package's phase 2, not here.
- Renaming the popover file vs. keeping `RenameAliasPopover.svelte` — a
  build-time cosmetic call.
