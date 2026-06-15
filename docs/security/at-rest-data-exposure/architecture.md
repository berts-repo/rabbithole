# Enabling Architecture

Parent: [`../at-rest-data-exposure.md`](../at-rest-data-exposure.md).
Managed under [`../../../LIBRARIAN.md`](../../../LIBRARIAN.md).

A previous revision of this document described scattered direct access to
`CrawlDB._conn` from ~22 backend files as the structural weakness blocking a
clean encryption retrofit. **That weakness has since been resolved.** This
section is preserved (with updated content) because the architecture is the
load-bearing prerequisite for ever turning encryption on.

The May 22 commit `d05e5e7` ("Add DB read accessor seam") was the last in a
sequence that consolidated all DB access through two public methods on
`CrawlDB`:

- `CrawlDB.read()` (`db/core.py:567`) — lock-guarded, SELECT-only context
  manager.
- `CrawlDB.transaction(immediate=False)` (`db/core.py:586`) — reentrant
  write context manager.

`db/` helper modules, route modules, and services now all go through these
two seams. As of `main`:

```
grep -rn '\._conn\b' backend/backend/ | grep -v __pycache__ | grep -v core.py
# (no results)
```

The `Depends(get_active_db)` injection point established earlier provides the
single instance to every consumer. With both the construction site and the
access pattern now centralized, **the connection is a true chokepoint**:
`CrawlDB._configure_connection()` (`db/core.py:429`) is the one place where
how-the-connection-is-opened lives. Adding `PRAGMA key` (SQLCipher) or any
other connection-level security control is now a contained change, not a
sprawling retrofit.

The architectural prerequisite for `NEXT.md` queue item 1 is, for the
purposes of an encryption retrofit, complete. The remaining barriers to
turning encryption on are the driver swap and key management — both addressed
in [`remediation.md`](remediation.md).

---
