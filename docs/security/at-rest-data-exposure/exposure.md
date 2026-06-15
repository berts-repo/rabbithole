# Exposure Mechanics

Parent: [`../at-rest-data-exposure.md`](../at-rest-data-exposure.md).
Managed under [`../../../LIBRARIAN.md`](../../../LIBRARIAN.md).

## The database is plaintext on disk

`CrawlDB` in `backend/backend/db/core.py` opens the project database with a
plain `sqlite3.connect(...)` call (`core.py:409`). There is no encryption layer.
The file is a standard SQLite database written in cleartext.

By the path rules in `docs/reference/security-model.md`, project databases live
under `~/.local/share/rabbithole/projects/`, the project root is created mode
`0700`, and DB files are expected to be `0600` (owner-only). Those Unix
permissions stop *another logged-in user account on the same machine* from
casually reading the file — useful, but it is **access control, not
encryption**. It does nothing once the file is copied off the machine, read
from a backup, accessed by malware running as the same user, or examined by
anyone who can bypass the running OS (for example, by reading the disk
directly).

## Reading it requires no skill

Because the file is cleartext, "exploiting" it is simply *opening it*. Any free
SQLite browser, or the standard `sqlite3` command-line tool, will display every
table and every row described in [`asset.md`](asset.md). There is nothing to
crack, no password prompt, no technical barrier. This is the defining
characteristic of a CWE-312 cleartext-storage exposure: **the hard part for an
attacker is getting the file; once they have it, reading it is trivial.**

## The WAL sidecar files are part of the exposure

`CrawlDB._configure_connection()` enables **WAL mode** (Write-Ahead Logging) via
`PRAGMA journal_mode=WAL` (`core.py:431`). WAL mode means SQLite does not write
only to the single `*.db` file — it also maintains two companion files next to
it:

- `*.db-wal` — the write-ahead log, holding recent changes not yet folded back
  into the main database file.
- `*.db-shm` — shared-memory coordination file.

These **`-wal`/`-shm` sidecar files can contain recent investigation data**.
Any reasoning about protecting the database — encryption, secure deletion,
careful handling — must treat all three files as one unit. Protecting `*.db`
alone and forgetting the sidecars would leave recent data exposed.

## "Deleted" rows are not actually gone

The schema uses `ON DELETE CASCADE` and the `nodes_fts` FTS5 index is wired
as `content='nodes'` with triggers (`core.py:336-352`), so a `DELETE FROM
nodes` does correctly cascade across rows and FTS entries. What is **not**
true is that the underlying bytes are erased:

- SQLite does not zero freed pages by default. Without
  `PRAGMA secure_delete = ON`, deleted content remains on disk until the
  page is reused, and a full `VACUUM` is what consolidates and rewrites the
  file.
- The WAL file holds prior-version rows until the next checkpoint.
- The `embeddings` table is a `sqlite-vec` virtual table; the vectors are
  not human-readable, but they are **semantically queryable offline** by
  anyone who has the file — a copied database lets an attacker search the
  investigation by *concept*, not just keyword, without ever running the
  app.

Practical consequence: "I deleted that page" is not, by itself, a defense
against an attacker who later obtains the file.

## Backups and sync amplify everything

A single unencrypted file is easy to copy, and copies escape:

- An **unencrypted backup** is a second cleartext copy, often on hardware
  (external drives, NAS) handled more loosely than the laptop.
- A **cloud-synced folder** (Dropbox, OneDrive, Google Drive, Nextcloud, …)
  pushes copies to a third-party server and to every other synced device.
  Rabbithole's loopback binding and auth do **not** reach here — sync is an OS-
  level concern outside the app entirely.
- The `*.db` file is small and self-contained, which makes it equally easy for
  an analyst to back up *and* for malware or an opportunistic copier to exfil.

The path rules keep the database in a predictable location under the user's
home directory; that is good for the app, and it also means anyone who knows
Rabbithole knows exactly where to look.

---
