# Maintenance

Standing upkeep obligations that are **not** tied to an active work package.
Each item has an external or time-based *trigger* and an *action* to take when
the trigger fires.

This is current-truth reference: it records what the app needs in order to stay
correct over time. It is not a work queue — active implementation work lives in
`docs/work/`.

When an item is acted on, update its row in place (for example, bump the
mirrored version) rather than deleting it — the obligation recurs.

| Area | Trigger | Action |
| --- | --- | --- |
| Tor Browser request profile | Each Tor Browser **major** release | Re-check `_TOR_BROWSER_UA` and `_TOR_REQUEST_HEADERS` in `backend/backend/security/net.py` against the new stable Tor Browser, then bump `rv:` / `Firefox/` and any changed headers. Currently mirrors **Tor Browser 15.0 (Firefox 140 ESR)**; next is **Tor Browser 16.0** (Firefox ESR ~153), expected ~mid-Q3 2026. A stale profile drifts the crawler out of the Tor Browser anonymity set it is meant to blend into. |
