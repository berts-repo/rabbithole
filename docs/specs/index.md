# Onion Rabbithole — UI Rebuild Reference

Master index of all UI feature areas. Each section maps to a dedicated doc file.

---

## App Shell

| Area | Doc |
|------|-----|
| Header bar (tabs + status pills) | [app-shell.md](app-shell.md) |
| Global toolbar | [app-shell.md](app-shell.md) |
| Toast notifications | [app-shell.md](app-shell.md) |
| Project picker modal | [app-shell.md](app-shell.md) |

---

## Left Sidebar

Three sub-tabs: Find · Intel · Crawl.

| Area | Doc |
|------|-----|
| Find sub-tab | [explore-left-pane-find.md](explore-left-pane-find.md) |
| Intel sub-tab | [explore-left-pane-intel.md](explore-left-pane-intel.md) |
| Crawl sub-tab | [crawl-left-pane.md](crawl-left-pane.md) |

## Settings Modal

Five tabs: Graph · Engines · Watchlist · Browser · Embedding.

| Area | Doc |
|------|-----|
| All settings tabs | [explore-left-pane-settings.md](explore-left-pane-settings.md) |

---

## Graph Tab (Explore)

Default landing tab. Left sidebar / graph canvas / right panel.

| Area | Doc |
|------|-----|
| Workspace tabs (Global + collection tabs) | [explore-graph.md](explore-graph.md) |
| Graph toolbar | [explore-graph.md](explore-graph.md) |
| Graph canvas, node interactions, right-click menu, multi-select | [explore-graph.md](explore-graph.md) |
| Bottom pane (Collection · Bookmarks · Live Crawl · Analyses · Domains · Flags · Fingerprints · Hidden) | [explore-bottom-pane.md](explore-bottom-pane.md) |

---

## Right Panel (global, context-aware)

Three tabs when a single node is selected: Page · Domain · Analysis.
Switches to cluster workspace (Nodes · Q&A · Common) when multiple nodes are selected.

| Area | Doc |
|------|-----|
| All right panel states | [right-pane.md](right-pane.md) |

---

## Search Tab

| Area | Doc |
|------|-----|
| Dark-web search + engine management | [search-tab.md](search-tab.md) |

---

## Notes

- Center tabs: **Search · Explore** — two only.
- Left sidebar sub-tabs: **Find · Intel · Crawl** — three only. Settings is a modal (⚙ in header).
- Right panel single-node tabs: **Page · Domain · Analysis**.
- Right panel multi-select switches to cluster workspace: **Nodes · Q&A · Common**.

---

## Where things live

Start with `../../CONTEXT.md` for project-wide source-of-truth rules. This
directory preserves specs and intended product behavior; current implementation
truth lives under `../reference/`, and current work state lives in
`../work/ACTIVE.md`.

| Doc | Role | When to edit |
|---|---|---|
| `PLAN.md` | Compatibility pointer to the archived historical build plan. | Do not add new work here; use `../work/` for implementation plans. |
| `stack.md` | Original stack/schema/security contract source material. | When the intended contract changes; mirror current truth into `../reference/` when behavior changes. |
| `app-shell.md` / `explore-graph.md` / `right-pane.md` / etc. | UI/UX spec per surface. | When the agreed intended UX for that surface changes. |
| `security-decisions.md` | Rationale archive for security decisions behind the stack rules. | Only when a new security decision is taken; otherwise read-only. |

**Rule:** if implementation behavior changes, update the relevant
`../reference/` doc. Specs preserve intent and history; they are not the only
home for current behavior.

## Other reference

| Area | Doc |
|------|-----|
| Security decisions log (rationale behind `stack.md` rules) | [security-decisions.md](security-decisions.md) |
| Naming review inventory for user-facing terminology | [naming.md](naming.md) |
