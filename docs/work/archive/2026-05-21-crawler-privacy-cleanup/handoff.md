# Handoff

Status: ready to implement.

Read first:

1. `plan.md`
2. `../../../reference/security-model.md`
3. `../../../reference/backend-structure.md`

Likely files:

- `backend/backend/security/net.py`
- `backend/backend/crawler/runtime.py`
- `backend/backend/db/settings.py`
- `frontend/src/components/crawl/CrawlControls.svelte`

Recommended order: P1 request profile, P2 per-host Tor isolation, then P3 crawl
pacing profile.
