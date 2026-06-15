# At-Rest Data Exposure

*Vulnerability class: CWE-311 (Missing Encryption of Sensitive Data) /
CWE-312 (Cleartext Storage of Sensitive Information).*

This is the entrypoint for the Rabbithole at-rest data exposure note. The
analysis is split into smaller files under `at-rest-data-exposure/`, but it is
one security topic: Rabbithole stores sensitive investigation state in
cleartext files on disk.

This documentation is managed under the project Librarian rules in
[`../../LIBRARIAN.md`](../../LIBRARIAN.md). Security and privacy notes should
continue to distinguish operator privacy toward malicious onion sites and
relays from physical/device security, which is currently deferred unless the
owner changes the threat model.

Two companion documents, both outside the repository, complete the picture:

- `~/Documents/data-at-rest-exposure-explained.md` — a general-education
  explainer of the vulnerability class, written for learning rather than for
  this project specifically.
- `~/Documents/rabbithole-attack-vectors-and-journalism-defense.md` — the
  attacker-perspective and operational-defense companion: ranked threat
  actors and the journalism-on-the-darkweb hygiene that no amount of code can
  do for the analyst.

## Files

Read these in order:

1. [`asset.md`](at-rest-data-exposure/asset.md) — what the database holds and
   why it is sensitive.
2. [`exposure.md`](at-rest-data-exposure/exposure.md) — the cleartext database,
   WAL sidecars, deleted rows, backups, and sync risk.
3. [`threat-model.md`](at-rest-data-exposure/threat-model.md) — why this is a
   known, documented deferral rather than a surprise defect.
4. [`architecture.md`](at-rest-data-exposure/architecture.md) — why the DB
   access seam now makes encryption a contained retrofit.
5. [`remediation.md`](at-rest-data-exposure/remediation.md) — completed
   enablers, remaining deferred controls, owner decisions, and operational
   defenses.
6. [`summary-table.md`](at-rest-data-exposure/summary-table.md) — compact
   status table.

## Summary

Rabbithole stores each project as a single, ordinary SQLite database file on
disk, unencrypted. Anyone who obtains that file through a lost or stolen
laptop, device seizure, malware, an unencrypted backup, a cloud-synced folder,
or a shared machine can open it with standard SQLite tooling and read the
investigation.

This is a confidentiality risk. It does not expose the application over the
network, and it requires file or device access to exploit. It is best read as a
currently accepted, explicitly documented deferral: Rabbithole's threat model
deliberately places physical/device security out of scope for now.

## Current Status

The architectural prerequisite for a future encryption retrofit is complete:
all backend DB access now goes through `CrawlDB.read()` and
`CrawlDB.transaction()`. The remaining decision is whether to ship SQLCipher
and related registry/key-management work. That decision is gated on the
project threat model, not on the old DB-access architecture.
