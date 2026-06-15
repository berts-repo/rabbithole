# Checklist — GraphCanvas Decomposition

## Shared contract
- [ ] decide controller factory + subscribe shape; document in
      `lib/graph/controllers/README.md` (one short paragraph)

## Controllers (one commit per controller; smoke after each)
- [ ] `hoverController.ts` + `hoverController.test.ts`
- [ ] `egoFocusController.ts` + `egoFocusController.test.ts`
- [ ] `visibilityController.ts` + `visibilityController.test.ts`
- [ ] `reducerController.ts` + `reducerController.test.ts`
- [ ] `layoutController.ts` + `layoutController.test.ts`
- [ ] `sigmaEventController.ts` + `sigmaEventController.test.ts`
- [ ] `contextMenuAdapter.ts` + `contextMenuAdapter.test.ts`

## `GraphCanvas.svelte` shrink
- [ ] component body reduces to mount + controllers + DOM
- [ ] file LOC ≤ 500 (target 300–400)
- [ ] no behavior change vs. baseline

## Verify
- [ ] `npm run build` clean (TS strict, no new `any`)
- [ ] `vitest` green via test-runner subagent
- [ ] browser smoke: pan, zoom, hover, click select, multi-select,
      context menu, draw-edge, ego focus, layout switch, filter
      toggle — all identical to pre-decomposition baseline
