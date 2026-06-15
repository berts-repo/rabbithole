# Codebase Reduction Refactor

This proposal tracks opportunities to shrink Rabbithole's production codebase
by deleting, combining, or simplifying behavior. Unlike extraction work, the
success metric is net production code removed while preserving or intentionally
improving the analyst workflow.

## Scope

This can include behavior changes when the new behavior is a better product
model and removes complexity. Combining two overlapping features into one
clearer workflow is in scope if the owner accepts the behavior change and the
replacement fully covers the important use cases.

Good candidates:

- dead code, unused exports, stale compatibility paths, and obsolete feature
  flags
- duplicate UI implementations now covered by shared primitives
- duplicate action wiring now covered by shared action helpers
- overlapping panes, tabs, modals, or menus that can become one workflow
- state branches that model distinctions users do not need
- custom helpers that can be replaced by standard library, framework, or local
  shared utilities
- backend routes, DB helpers, or service branches that now have one canonical
  path

Out of scope:

- splitting files without reducing total behavior
- introducing new abstraction layers that increase net production LOC
- removing behavior only because it is unimplemented elsewhere
- changing security or Tor/privacy behavior without a dedicated threat-model
  review
- large schema cuts already covered by the Schema Reset package

## Evaluation Rules

Each finding should answer:

- What code can be removed?
- What behavior changes, if any?
- What user workflow replaces the old behavior?
- What tests or manual checks prove the change is safe?
- Is this independent, or should it wait for another package?

Count production code separately from tests, docs, generated files, and
fixtures. Tests can grow when they protect a deletion, but the reported savings
should be production LOC.

## Plan

1. Inventory candidates with no edits: search for duplicate components, unused
   exports, unreachable state branches, overlapping commands, and stale
   compatibility code.
2. Classify each candidate as delete, combine, simplify, or defer.
3. For behavior-changing candidates, record the proposed replacement workflow
   and owner decision before implementation.
4. Implement independent no-behavior-change deletions first.
5. Batch behavior-changing reductions as explicit active packages with
   checklists and verification notes.
6. Report every closed reduction with before/after production LOC, files
   deleted or simplified, and tests run.

## Finding Template

```text
### CRR-NN - Title

Status: candidate | accepted | rejected | blocked | shipped
Type: delete | combine | simplify | defer
Area:
Depends on:

Current shape:

Proposed reduction:

Behavior change:

Replacement workflow:

Estimated production LOC impact:

Verification:

Decision notes:
```

## Findings

### CRR-01 - Remaining One-Off Shared UI Candidates

Status: candidate
Type: simplify
Area: frontend panes, modals, tab strips, action bars
Depends on: Shared UI Primitives landing

Current shape:

Item 2 added shared primitives and action helpers, but follow-up sweeps may
still find local button, badge, empty-state, tab-strip, and action wiring
patterns that can be replaced by the shared components.

Proposed reduction:

Search for duplicate local UI structures and replace them with
`$lib/ui` primitives or `$lib/contextMenu/actions.ts` helpers when doing so
removes net production code.

Behavior change:

None intended.

Replacement workflow:

The same commands and pane interactions should remain available through the
shared primitive surfaces.

Estimated production LOC impact:

Unknown until inventory.

Verification:

Frontend tests, typecheck, and focused smoke checks for affected panes.

Decision notes:

Do not count a replacement as successful if it only moves lines into a new
helper and increases net production LOC.

### CRR-02 - Overlapping Analysis Entry Points

Status: candidate
Type: combine
Area: analysis and intel workflows
Depends on: Analysis / Intel Pane, Schema Reset where status vocabulary matters

Current shape:

The queue already identifies fragmented analysis entry points across the
right pane, bottom Analyses tab, Queue Analysis modal, Cluster Q&A, and future
left Intel pane.

Proposed reduction:

Collapse overlapping compose, monitor, and inspect flows into one canonical
analysis workflow as part of the Analysis / Intel Pane package.

Behavior change:

Likely. The user-facing entry points may change, but the important analysis
capabilities should remain available through one clearer workflow.

Replacement workflow:

Use the left Intel pane for compose and worker controls, the bottom pane for
status/history, and the right pane for inspecting the current selection.

Estimated production LOC impact:

Unknown until package design.

Verification:

Focused tests for analysis submission/status handling plus manual smoke checks
for single page, domain, collection, and cluster analysis paths.

Decision notes:

This is a valid codebase-reduction candidate because combining features is in
scope when the product model is better and the behavior change is explicit.

### CRR-03 - Workspace Scope Duplication

Status: candidate
Type: combine
Area: graph workspaces, bottom-pane lists, visibility filtering
Depends on: NodeSet Workspaces

Current shape:

Graph workspace state and bottom-pane list state are separate concepts even
though upcoming NodeSet Workspaces will let lists open as scoped graph tabs.

Proposed reduction:

After NodeSet Workspaces lands, look for old global/collection-only workspace
branches, duplicate list-to-filter glue, and special cases that can collapse
into the typed `NodeSet` model.

Behavior change:

Yes, if old special-case workspace behavior is replaced by the generalized
NodeSet model.

Replacement workflow:

Lists, saved scopes, and search-like node sets open through the same graph tab
scope model.

Estimated production LOC impact:

Unknown until NodeSet implementation.

Verification:

Graph workspace tests, visibility-controller tests, and manual checks for
global, collection, and list-derived graph tabs.

Decision notes:

This should wait until both active refactor packages are closed and NodeSet
Workspaces is implemented.
