# Remediation Status

Parent: [`../at-rest-data-exposure.md`](../at-rest-data-exposure.md).
Managed under [`../../../LIBRARIAN.md`](../../../LIBRARIAN.md).

## What has now been completed — the DB-access seam (the enabler)

`docs/work/NEXT.md` queue item 1, the **"Backend DB-access seam,"** has been
implemented as described in [`architecture.md`](architecture.md). The
crawler-privacy plan framed this work as deliberately *security-enabling*, not
mere tidying:

> "The enabling work is Finding 1 (the DB-access seam) — with one chokepoint
> where the DB is opened, turning on SQLCipher later is a small change rather
> than a retrofit. Do the seam; defer the encryption itself."

The chokepoint is now in place. The `NEXT.md` queue entry has been moved to
"Removed from queue" to reflect this: the architectural prerequisite is done;
the encryption itself is the remaining (still-deferred) work.

## What remains deferred — the eventual control

The eventual at-rest control would be **database-level encryption — SQLCipher**,
a build of SQLite that transparently encrypts the database file *and its WAL/
journal sidecars*. With the seam in place, adopting it is now a contained
change. Concretely:

1. **Driver swap inside `db/core.py` only.** Replace the stdlib
   `sqlite3.connect(...)` at `core.py:409` with a SQLCipher-capable driver
   (`sqlcipher3-binary` is the simpler default; `pysqlcipher3` pins to system
   libs). No other module needs to change — the seam guarantees that.
2. **Key as the first statement** in `_configure_connection()` (`core.py:429`).
   `PRAGMA key = '<derived key>'` must run **before** `PRAGMA journal_mode=WAL`
   and before any other access — SQLCipher requires the key on the very first
   I/O. Follow with `PRAGMA cipher_memory_security = ON`.
3. **Plumb the key through `get_active_db`** to `CrawlDB(path, key=...)`.
   Never log it; never persist it.
4. **Wrong-key behavior.** A wrong `PRAGMA key` does not error until the
   first query — use that first query as the unlock check.

Independent of the encryption decision itself, two smaller hardening steps
fall out of the same review and should be considered on their own merits:

- **Enable `PRAGMA secure_delete = ON`** in `_configure_connection()` and add
  a `VACUUM`-after-large-delete path. This makes purges actually purge,
  encrypted or not.
- **Encrypt the registry file.** As noted in [`asset.md`](asset.md),
  `~/.local/share/rabbithole/registry.json` is cleartext and indexes every
  project. With the SQLCipher key (or a separate user-passphrase-derived
  key) available, wrap the registry in `services/registry.py` so an attacker
  with disk access cannot enumerate projects.

This remains **deferred pending an explicit owner threat-model decision**, per
[`threat-model.md`](threat-model.md). It is not yet scheduled work.

## What an owner would weigh to decide

If and when the owner revisits this, the decision turns on:

- **Threat model.** Has the audience or risk context changed? Are users
  plausibly exposed to device theft, seizure, or border inspection? If
  physical/device security comes into scope, encryption follows.
- **Key management — the genuinely hard part.** Encryption converts "protect
  the file" into "protect the key," and **a key stored in cleartext next to the
  database protects nothing.** The owner must choose where the key lives, each
  option with trade-offs:
  - a **user passphrase** entered when opening a project, with the SQLCipher
    key derived via Argon2id (e.g. 256 MiB / 4 iterations / 1 lane) — strong
    against a stolen device, but adds friction and risks permanent data loss
    if forgotten;
  - a **keyfile** — convenient, but only helps if stored somewhere the attacker
    would *not* also obtain;
  - the **OS keyring** (libsecret/GNOME Keyring/KWallet on Linux) — good UX and
    protects a copied-off file, but yields to an attacker who has the unlocked
    user session;
  - a **passphrase combined with an OS-keyring secret** — survives a stolen
    disk image even with the user-account password compromised, at the cost
    of two unlock sources;
  - a **hardware-backed store** (TPM, YubiKey HMAC-SHA1) — strongest, but more
    complex.
- **Idle re-lock and panic wipe.** Two follow-on UX questions worth answering
  alongside the key model:
  - *Idle re-lock* — after N minutes idle, zero the key in memory and require
    re-unlock. Limits the cold-boot/unlocked-laptop window.
  - *Panic wipe* — a UI affordance (or watchdog trigger) that `cipher_rekey`s
    the database to a random key the user immediately forgets, rendering the
    file unreadable. Useful in coercion or seizure scenarios.
- **Ephemeral mode.** A separate "one-shot investigation" affordance that
  opens the DB in `:memory:` and never writes to disk. Independent of the
  encryption decision; useful even today.
- **Recovery and rotation.** A forgotten passphrase means unrecoverable
  investigation data unless a recovery path is designed. Key rotation should be
  considered too.
- **Coverage of all files.** Any solution must cover the `*.db`, `*.db-wal`,
  and `*.db-shm` files together, **plus the registry file and any backups**.
- **Relationship to OS full-disk encryption.** If the owner instead (or also)
  relies on the user enabling OS full-disk encryption (LUKS, BitLocker,
  FileVault), that covers a *powered-off* device cheaply — but the app cannot
  assume it is on, and it does not protect a running machine, a copied-off
  file, or anything that has reached a backup destination. This is worth
  stating in user-facing guidance regardless.
- **Cost vs. benefit and UX.** Database encryption is fast in practice, but the
  passphrase/unlock flow is a real UX change for a single-user local tool.

## Operational defenses that complement (and outlast) code changes

Encryption-at-rest is the largest control the *project* can ship. Several
defenses sit outside the codebase and apply regardless of whether SQLCipher is
ever turned on. They are documented in full in
`~/Documents/rabbithole-attack-vectors-and-journalism-defense.md`; summarised
here so this document is self-contained:

- **Host choice matters more than any single code change.** For high-risk
  journalism work the recommendation is Tails (live USB, amnesic, with an
  optional LUKS-encrypted Persistent Volume) or Whonix (gateway-enforced Tor).
  Running on a daily-driver desktop alongside personal browsers and accounts
  is the highest-risk configuration.
- **Dedicated UNIX user account** for Rabbithole on shared hosts. The 0600
  mode on project DBs only becomes a real defense against other accounts
  (and against the daily-driver browser process) when Rabbithole runs as a
  separate user.
- **Full-disk encryption** (LUKS / FileVault / BitLocker) on whatever host
  Rabbithole runs on. Power off — not suspend — when leaving the device
  unattended or crossing a border.
- **Backup hygiene.** Audit cloud-sync agents and backup tools to confirm
  `~/.local/share/rabbithole` is excluded. Backups, if wanted, should land on
  encrypted media the analyst controls.
- **Minimization.** Real-name-to-pseudonym mappings should stay off the
  machine entirely. No technical control protects what the analyst typed
  into a `notes` field.

The project should consider mentioning the backup-exclusion and
host-selection guidance in user-facing documentation (README or a security
note), since these are the defenses the tool cannot enforce but cannot
substitute for either.

## Current recommendation

The architectural prerequisite is complete. The remaining decision is
whether to ship SQLCipher (and the registry-file wrapper alongside it) by
default, gate it behind a setting, or leave it deferred. That decision is
gated on the threat-model question in
[`threat-model.md`](threat-model.md), not on engineering cost: the
engineering cost has dropped substantially since the seam closed. Keep this
document alongside the threat model so the deferral is revisited
deliberately if Rabbithole's audience or risk context shifts.

---
