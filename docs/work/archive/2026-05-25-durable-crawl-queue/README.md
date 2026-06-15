# Durable Crawl Queue

Status: active — Phase A shipped (backend queue + minimum frontend);
source spec revised to Option B on 2026-05-26 (single-verb intake +
batch-confirm strip); Phase B ready to start. See `plan.md` "Phase B
status" for sequencing and `checklist.md` for the punch list.
Date: 2026-05-25 (Phase B re-cut 2026-05-26)

This package turns Crawl / Bulk Import from a one-row-at-a-time seed picker into
a project-wide persistent crawl queue. Every URL that the analyst wants crawled
— from manual input, paste, bookmarks, graph menus, search results, right-panel
entities, collections, bottom-pane lists, or scheduled crawls — lands in one
`crawl_queue` table and a single FIFO runner dispatches them under the existing
one-active-crawl rule.

Source spec: `source-spec.md` (promoted from `docs/work/additions/` when this
became active work; owner-resolved decisions in the spec are treated as fixed
and are not re-litigated here).

## Vocabulary

This work touches two things that share the word "queue." They are different
and both stay in the project long-term:

- **Durable crawl queue** (NEW) — persistent SQLite `crawl_queue` table that
  holds queued URLs across crawls and process restarts.
- **Per-crawl frontier** (EXISTS, `backend/backend/crawler/frontier.py`) — the
  in-memory data structure that lives inside ONE crawl and decides which
  discovered link to fetch next (BFS / DFS / Cross-site / Diverse / Focused).
  Out of scope; not touched by this work.

## Read order

1. `plan.md`
2. `checklist.md`
3. `handoff.md`
4. `source-spec.md` (promoted source spec)
5. `../../../reference/data-model.md`
6. `../../../reference/backend-structure.md`
