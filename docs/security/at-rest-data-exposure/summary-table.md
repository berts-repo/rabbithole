# Summary Table

Parent: [`../at-rest-data-exposure.md`](../at-rest-data-exposure.md).
Managed under [`../../../LIBRARIAN.md`](../../../LIBRARIAN.md).

| Aspect | Status |
| --- | --- |
| Vulnerability class | CWE-311 / CWE-312 — cleartext storage of sensitive data at rest |
| Affected assets | Project SQLite databases under `~/.local/share/rabbithole/projects/` (plus `-wal` / `-shm` sidecars), **and** the project-index file `~/.local/share/rabbithole/registry.json` |
| Impact | Confidentiality — full disclosure of investigation data, sources, subjects, analyst methods, and the catalogue of which investigations exist |
| Preconditions to exploit | File or device access (theft, loss, seizure, same-user malware, backup, cloud sync, shared machine). No skill needed once the file is obtained. |
| Network exposure | None — backend stays loopback-bound; this is a local at-rest issue only |
| Threat-model status | **Deliberately deferred and documented** in `CONTEXT.md`, `features.md`, and the crawler-privacy plan; physical/device security is out of current scope |
| Enabling architecture (DONE) | DB-access seam closed — all DB access goes through `CrawlDB.read()` / `CrawlDB.transaction()`; no `_conn` callsites remain outside `db/core.py` (`d05e5e7`). `NEXT.md` item 1 should be updated to reflect this. |
| Eventual control (deferred) | SQLCipher database-level encryption — driver swap + `PRAGMA key` in `CrawlDB._configure_connection()`; with Argon2id-derived key, idle re-lock, and optional panic-wipe |
| Companion gap | `registry.json` cleartext; should be wrapped with the same key model when encryption ships |
| Standalone hardening (encryption-independent) | `PRAGMA secure_delete = ON` + post-purge `VACUUM`; ephemeral (`:memory:`) project mode; backup-exclusion guidance in user docs |
| Operational defenses (not code) | Tails/Whonix host, dedicated UNIX user, FDE + power-off-not-suspend, backup audit, source-mapping kept off the machine. See `~/Documents/rabbithole-attack-vectors-and-journalism-defense.md`. |
| Recommended next step | Decide deferral status — engineering cost has dropped substantially now that the seam is closed; the decision is now a threat-model question, not an architecture question |
</content>
