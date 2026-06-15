# Physics Layout Experiment

**Status:** Proposal. Disposable prototype in a worktree. Decide adopt-vs-throw after analyst-side testing.

## Why this exists

The current layout is `radialLayoutByDomain` — deterministic, one pass at first paint, fast. It replaced an earlier FA2 / Barnes-Hut physics pass that was removed because it ran synchronous-to-convergence on every payload version (pinned CPU under SwiftShader) and because Sigma's autoRescale re-fitted the camera on every settle frame (clicks missed).

Slice 7 (domain cluster nodes) made the radial / clustering relationship explicit — a cluster is literally a domain hub, and the radial pass already had an `is_cluster` pivot branch. That tightness raises a fair question: if clustering and layout want the same shape, would a *differently-shaped* physics pass do this more naturally?

This experiment is the answer. It is **not** a commitment to ship physics. It is a sized-down prototype to see whether physics produces a more legible / alive layout *without* resurrecting the original failure modes.

## Goal

Decide whether the layout's source-of-truth should be physics or explicit radial-by-domain. Decision is binary: adopt physics (then strip radial), or throw away the worktree and keep radial.

## What we will build

- **Async FA2 settle** running for a fixed wall-clock budget (~300–500 ms total, chunked via `requestAnimationFrame`) — not convergence-bound. When the budget runs out, the simulation stops and positions are frozen for the rest of the page lifetime.
- **Domain-weighted edges**: same-domain edges 3–5×, cross-domain 1×. Adjusted at layout time on a temp graph; the real graphology instance is not weighted.
- **Synthetic intra-domain edges** between fetched members so a domain whose pages don't link laterally (forum pattern: every page from the homepage, no peer links) still attracts itself. Synthesized on the temp graph only — never seen by the renderer.
- **autoRescale stays off** for the entire settle and forever after. Camera is locked from first paint.
- Both `radialLayoutByDomain` and the new async-physics function exist in parallel during the experiment. A build-time constant flips between them. No analyst-visible toggle.

## What we will not build

- No new settings UI, no filter shelf row, no analyst-visible toggle.
- No pause/resume physics button. Settle runs once, finishes, simulation stops.
- No new layout-picker toolbar tab. The historical F4b layout-picker notes now
  live in `../../work/archive/2026-05-21-build-plan-history/plan.md`; any new
  implementation should get its own `docs/work/` package.
- No replacement of `radialLayoutByDomain` until the adopt decision is made.

## Integration points

- `GraphCanvas.svelte::applyPayloadAndLayout` — branch on the build flag to call `radialLayoutByDomain` or the new `physicsSettle`.
- `firstLayoutDone` semantics stay — physics also runs once, then locks.
- Reset effect — re-randomise positions + re-arm `firstLayoutDone`. Works for both paths unchanged.
- Stub halo (`positionStubsAroundParents`) — called after settle completes. Stubs never enter physics.
- Cluster synthesis (`graph.svelte.ts::rebuildInto`) — unchanged. Physics operates on whatever graphology contains, including synthetic clusters when `groupByDomain` is on; while collapsed, members aren't in graphology, so physics doesn't see them either.
- Bbox lock (`renderer.setCustomBBox`) — applied once after settle completes.
- The symmetric expand-fan (`sunflowerAround` in `graph.svelte.ts`) stays during the experiment. If physics wins, it gets deleted as part of adoption.

## Decision criteria

~30 minutes of analyst-side testing against a real crawl with ~200–500 fetched nodes across 5–15 domains.

| Aspect | Radial wins if… | Physics wins if… |
|---|---|---|
| Visual grouping | Each domain reads cleanly as a fan around a hub | Domain clumps form naturally and cross-domain structure is more legible |
| Click reliability | Nothing breaks (it doesn't today) | Settle never re-fires after release; hit-testing matches the rendered positions |
| Stability across polls | No shift between polls | Settle on first paint only; polls don't perturb |
| Cluster expand/collapse | Symmetric — already shipped in Slice 7 | Brief re-settle on toggle and the result feels more natural than the sunflower re-fan |
| Cost | Layout is sub-ms today | Total settle budget under 500 ms even on SwiftShader |
| Determinism | Same payload → same visuals across sessions matters | Camera lock papers over the cross-session variance well enough |

## Worktree setup

- Branch: `experiment/physics-layout`
- Spawn via a disposable worktree/branch; keep the experiment isolated from
  active implementation work.
- One commit per logical chunk so the diff is reviewable if we end up keeping it.

## Risks

- **Re-introducing the original CPU pin.** The async settle has to genuinely respect a wall-clock budget. Mitigation: hard ceiling on rAF tick count, plus a wall-clock check on each tick.
- **autoRescale resurfacing.** The previous failure came from autoRescale fighting clicks. Mitigation: explicit `renderer.setSetting('autoRescale', false)` at mount and after settle, even though it's already off.
- **Synthetic edges leaking to the renderer.** They're for layout weighting only. Mitigation: synthesize on a temp graph, copy positions back, never touch the live graphology instance.
- **Cluster nodes throwing the simulation off.** A synthetic cluster has very high in/out degree (sum of all members). Mitigation: cap effective degree for layout weighting, or run settle on a graph that omits collapsed members entirely (which is already true today).

## Open questions to answer during the experiment

- Does the short settle actually look better, or just different?
- Do clusters feel right under physics, or does the synthetic-edge weighting fight them?
- Does the expand transition feel more natural under a brief re-settle than the current `sunflowerAround` fan?
- Is the determinism loss (same payload, slightly different visuals across sessions) noticeable in practice, or does the camera lock paper over it?

## If we adopt physics

- Delete `radialLayoutByDomain` and its callers in `GraphCanvas.svelte`.
- Delete the centroid + sunflower paths in `graph.svelte.ts::rebuildInto` — physics handles both transitions naturally.
- Delete `sunflowerAround` helper in `graph.svelte.ts`.
- Sweep the stale FA2 comments in `GraphCanvas.svelte` (the queued comment-sweep work) but with replacement text describing the new async-budget settle, not the old convergence loop.
- Update `../../reference/frontend-structure.md`, `../../reference/features.md`, and
  the relevant graph work package outcome to note the layout source change.

## If we throw it away

- Delete the worktree branch.
- Resume the comment sweep on `main` as planned.
- Log the experiment outcome here at the bottom of this file (or move this file to a rationale archive), so the gravity question doesn't get re-raised without context.
- Keep force layout as an *opt-in* picker question for a future focused
  graph-layout work package, independent of the default.
