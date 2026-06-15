# Decisions

## Made

- **No dead controls.** Slice 1 surfaces only settings keys that already have a
  live backend consumer (confirmed by grep of `get_setting` call sites). A
  Wave-2-listed knob with no consumer is deferred to an enforcement slice rather
  than shipped as a UI control that does nothing. (CONTEXT.md proper-fix /
  argue-from-goals: a control with no effect is not "standardized config", it's
  misleading surface.)
- **`llm.model` stays free text.** No installed-models endpoint exists and the
  backend validator is a deliberate plain-string check (Ollama tags vary). A
  `<select>` would need a new `/api/llm/models` route; deferred.
- **Per-onion circuit isolation shown as read-only status, not a toggle.** It is
  always on (SOCKS-auth keyed on onion host in `security/net.py`) and there is
  no off switch by design. Surfacing it read-only is honest transparency; a fake
  toggle would not be.

## Made (Slice 2 — Retention, owner-confirmed)

- **Job-history only; page snapshots are never pruned.** The owner flagged that
  pruning old page copies would erase the page version-history + diff record
  (`features.md` page versioning) — investigation evidence. So retention prunes
  only terminal job-tracking rows (bookkeeping). Page snapshots, analyses,
  flags, notes are out of scope by design, stated in the tab UI.
- **"Log retention" dropped.** No app log store exists to clean, so the original
  Wave-2 "log retention" reduces to nothing actionable. Retention = job-history
  only until a log store exists.
- **Standalone Retention tab** (not a Crawl & Queue subsection) — it's a
  data-lifecycle concern, not a queue concern.
- **Default off (`retention.jobs_days = 0` = keep forever).** Installing the
  feature changes nothing until the analyst opts in — disk is cheaper than
  surprise data loss.
- **Enforcement = startup sweep + manual "Run cleanup now".** A continuous
  scheduled sweep was not added: this is a restart-frequent local single-user
  app, terminal job rows accrue slowly, and the manual button covers long
  sessions. A scheduled sweep can be added later if it proves needed.

## Open (later / owner)

- **Tor control-port / NEWNYM circuit refresh.** Needs a control-port client
  (port 9051 + auth) that does not exist. Overlaps NEXT.md item 4 "Crawler
  privacy cleanup". Decide whether circuit refresh lives in Settings or stays a
  crawl-privacy feature.
- **Crawl worker capacity / retry policy.** Needs a settings consumer in the
  crawl queue runner before it can be a real control.
