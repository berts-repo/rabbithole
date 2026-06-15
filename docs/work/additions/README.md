# Additions

This folder is for live future work only: feature notes, deferred capability
sketches, and planned follow-up handoffs that have not shipped yet.

Completed implementation history belongs in `docs/work/archive/`.

## Live Additions

- [`i2p-crawling.md`](i2p-crawling.md) — future idea, not ready for active work.

## Recently Moved

- Settings Modal (Wave 1 + Wave 2) shipped; full record in
  [`../archive/2026-06-12-settings-wave2/`](../archive/2026-06-12-settings-wave2/).
  The spent `settings-modal.md` pointer was removed; deferred knobs live in
  [`../REVISIT.md`](../REVISIT.md).
- Graph domain spacing shipped (edge-weighting in `graph/layouts/force.ts`); the
  `graph-domain-spacing.md` note was cleared, with its two fallback layout
  options graduated to [`../REVISIT.md`](../REVISIT.md).
- Label system shipped and moved to
  [`../archive/2026-06-10-label-system/`](../archive/2026-06-10-label-system/).
- Rename consolidation shipped as the foundation for label/page rename and moved
  to
  [`../archive/2026-06-10-label-system/source-rename-consolidation.md`](../archive/2026-06-10-label-system/source-rename-consolidation.md).

## Maintenance Rule

When an addition is promoted to active work, copy or move the necessary context
into the active package. When that work closes, archive the package and remove
the full completed spec from this folder, leaving at most a small pointer if a
stable link is still needed.
