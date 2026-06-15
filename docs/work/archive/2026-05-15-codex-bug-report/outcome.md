# Codex Bug Report

Date: 2026-05-15

## Confirmed bugs

### 1. Forced project switch can leave the old crawl task running against a closed database
Severity: high

Evidence:
- `backend/backend/services/project_state.py:146-194` handles `force=True` by updating matching `crawls` rows to `stopped`, then swapping `active_db` and closing `old_db`.
- `backend/backend/routes/projects.py:146-173` calls `state.switch(...)` directly and does not stop `app.state.crawl_runners`.
- `backend/backend/crawler/runtime.py:429-483` shows the crawl task lives independently in `CrawlRunnerRegistry` and keeps using the runner's `db` handle until the task exits.

Why this is a bug:
- The DB row is marked stopped, but the in-process crawl task is not actually stopped.
- The old `CrawlDB` handle is then closed out from under the runner.
- That leaves a race where the crawler can keep making requests and then hit failures or undefined behavior when it next touches the closed SQLite connection.

Likely user-visible impact:
- Forced switches can corrupt the operator's mental model: the UI says the old crawl stopped, but network work may still be happening.
- The old crawl can also fail noisily after the switch because its DB handle was closed mid-run.

Recommended fix:
- In the switch route, stop the in-process crawl runner before or during `force=true` handling, then swap the project only after the runner task has fully exited.

### 2. Deleting the active project drops the DB handle without coordinating with background tasks
Severity: high

Evidence:
- `backend/backend/routes/projects.py:179-201` closes `state.active_db` immediately when deleting the active project.
- This route does not stop or pause the crawl runner, embed worker, LLM worker, schedule daemon, or monitor daemon first.

Why this is a bug:
- Those background tasks all read `project_state.active_db` or keep their own handles/work in flight.
- Closing the active DB during delete can leave a running task operating on a closed connection or on state that has just been invalidated.

Likely user-visible impact:
- Intermittent worker crashes after delete.
- Inconsistent status reporting if a background task finishes after the project has already been removed from the registry.

Recommended fix:
- Treat delete of the active project as a coordinated shutdown: stop the crawl runner, stop or pause project-scoped workers, detach the project, then save the registry.

### 3. Worker auto-start and LLM crash-recovery are only reconciled at app startup
Severity: medium-high

Evidence:
- `backend/backend/main.py:97-109` applies `embedding.auto_start` and `llm.auto_start` only inside app lifespan startup.
- `backend/backend/routes/projects.py:80-138` and `:146-173` create/switch projects without reconciling worker state afterward.
- `backend/backend/services/llm_worker.py:186-195` only runs recovery of stale `running` jobs when `_recovered` is false.
- `backend/backend/services/llm_worker.py:553-560` resets `_recovered` only on explicit `worker.start()`.

Why this is a bug:
- If the server starts with no active project, later switching to a project with `embedding.auto_start=true` or `llm.auto_start=true` will not start those workers automatically.
- If the worker is already running and the operator switches to a different project, the LLM worker does not reset `_recovered`, so stale `running` jobs in the newly active project can stay stranded forever.

Likely user-visible impact:
- Auto-start settings are silently ignored after project creation/switch.
- Reopened projects can show analyses stuck in `running` even though no worker owns them anymore.

Recommended fix:
- After create/switch/detach, reconcile worker lifecycle against the new active project settings.
- Reset project-scoped worker state on project changes, especially the LLM worker's `_recovered` gate.

## Planned risks and placeholder debt

### 4. Several visible navigation surfaces are shipped as placeholders instead of disabled features
Severity: medium

Evidence:
- `frontend/src/views/LeftSidebar.svelte:28-33` renders `Search` and `Intel` tabs as `"content lands in F5"`.
- `frontend/src/views/RightPanel.svelte:49-51` renders every right-panel tab as `"content lands in F6"`.
- `frontend/src/views/BottomPane.svelte:30-32` renders every bottom workspace tab as `"content lands in F7"`.
- `checklist.md:45`, `checklist.md:95-104` explicitly documents these as expected gaps rather than implemented behavior.

Why this matters:
- These are not hidden dev stubs; they are reachable top-level UI paths.
- Users can click into areas that look implemented but are only placeholder text.

Likely impact:
- Bug reports that are really missing features.
- Higher support cost because the UI advertises capability before the feature exists.

Recommended fix:
- Hide or disable unfinished tabs until the corresponding phase lands, or label them as unavailable in the tab control itself instead of only in the body content.

### 5. `crawl.status` still requires polling because the SSE contract is incomplete
Severity: low-medium

Evidence:
- The archived historical build plan
  (`docs/work/archive/2026-05-21-build-plan-history/plan.md`) calls out the
  missing SSE counters as deferred follow-up work.
- `frontend/src/lib/stores/crawl.svelte.ts:1-13` documents that the frontend must combine SSE lifecycle events with `/api/crawl/status` polling because the SSE payload omits the live counters.

Why this matters:
- The architecture already has two sources of truth for one feature.
- That is manageable today, but it becomes a maintenance problem as more crawl UI becomes SSE-driven.

Likely impact:
- More synchronization edge cases between polled state and streamed state.
- Extra request load during active crawls for a gap the event stream should already cover.

Recommended fix:
- Extend `crawl.status` SSE payloads to include the counter trio, then remove the dedicated poller in one change.

## Verification limits

- I could not run the backend test suite in this environment because `pytest` is not installed (`python -m pytest -q` failed with `No module named pytest`).
- I could not run the frontend production build because the local toolchain is incomplete (`npm run build` failed because `vite` was not installed in the shell environment).

## Review decisions recorded on 2026-05-15

- **Issue 1: forced project switch during active crawl.** Chosen direction: keep the force-switch path, but show a "stopping old crawl..." progress state and complete the switch only after the in-process crawl runner has fully exited and the old DB handle is safe to close.
- **Issue 2: deleting the active project.** Chosen direction: allow delete from the active project, but require a confirmation path that explains active background work will be stopped first. After delete, keep the Project Picker modal open until the user selects or creates a new project.
- **Issue 3: project-scoped worker auto-start and recovery after activation.** Confirmed by follow-up review. Chosen direction: reconcile workers on every project activation event, including startup load, project switch, active-project delete follow-up, and any future create-and-activate flow.
- **Issue 4: placeholder tabs across left/right/bottom panes.** Cleared from bug review for now. User confirmed the frontend is still actively being implemented, so these placeholders are intentional work-in-progress rather than current defects.
- **Issue 5: `crawl.status` SSE counters.** Prioritize this first in the next implementation session. Chosen direction: include the counter trio in the `crawl.status` SSE payload and remove the extra poller so the crawl UI reads from one live contract.
