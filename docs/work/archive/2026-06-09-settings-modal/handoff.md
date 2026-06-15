# Handoff

Picking up where this left off:

- Read `README.md` → `plan.md` → `decisions.md`, then `checklist.md` for state.
- The two owner decisions (left rail, autosave) are locked — see `decisions.md`.
- The backend validation layer already exists; do not build a new one. New
  backend code is only the two `PATCH` routes + db helpers.
- Graph tab binds the existing `graphFiltersStore` / `graphLayoutStore`; it
  does not issue its own setting writes for the graph defaults.
- Deleting the Hidden tab requires three coordinated edits: the component, the
  `BottomPane` registration, and the `workspace.bottomTab` validator enum.

Wave 2 (Tor/Privacy, Crawl & Queue, LLM/Ollama, Retention) stays queued — its
setting keys mostly already exist, but the tabs are out of scope here.
