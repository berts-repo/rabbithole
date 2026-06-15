# Asset Sensitivity

Parent: [`../at-rest-data-exposure.md`](../at-rest-data-exposure.md).
Managed under [`../../../LIBRARIAN.md`](../../../LIBRARIAN.md).

Each Rabbithole project is one SQLite database file. Per `docs/reference/
data-model.md`, the schema in `backend/backend/db/core.py` defines the full set
of tables. Together they hold the entire substance of an investigation:

- **`nodes`** — every crawled onion page: its URL, title, domain, and the
  **full body text** of the page (`body_text`, `body_text_clean`), plus
  summaries and categories.
- **`response_headers`**, **`page_versions`** — per-page response metadata and
  crawl-history snapshots, i.e. *when* and *how often* a target was visited.
- **`edges`**, **`domains`**, **`seeds`** — the link graph between pages,
  per-domain metadata and analyst aliases, and saved seed URLs.
- **`entities`** — extracted identifiers: emails, BTC/XMR addresses, PGP keys,
  onion URLs, handles, and free-form blobs. This is exactly the kind of data
  that can tie a person to an activity.
- **`crawls`**, **`crawl_nodes`**, **`crawl_schedules`**, **`watchlist`** —
  the record of what was crawled, when, in what mode, and the terms the analyst
  is watching for.
- **`collections`**, **`collection_items`**, **`notes`**, **`flags`**,
  **`graph_filters`** — the analyst's own work product: how they grouped pages,
  their written **notes**, their flags and priorities, their filtering choices.
- **`monitors`**, **`probes`** — which onion sites the analyst is keeping under
  ongoing observation, and the uptime history of those checks.
- **`analyses`**, **`collection_analyses`** — local-LLM analysis prompts,
  questions, and results.
- **`nodes_fts`**, **`embeddings`** — a full-text search index over page
  content and vector embeddings derived from it.
- **`settings`**, **`search_engines`** — per-project configuration.

Alongside the per-project databases, a small **registry file** sits one
directory up at `~/.local/share/rabbithole/registry.json` (managed by
`backend/backend/services/registry.py`). It is written mode `0600` but, like
the databases, is **cleartext**. It indexes every project — name and DB
path — so it functions as a roadmap to every investigation on the machine.
Any control applied to the project DBs (encryption, secure deletion, exclusion
from backups) must cover the registry file too, or the catalogue of what
exists is leaked even when the contents are not.

Rabbithole is a **dark-web OSINT workbench for journalism and research**
(`CONTEXT.md`). For that use, this database is **highly sensitive**. It does not
merely contain crawled web text — it reveals:

- **Subjects** — who or what is being investigated.
- **Sources** — contacts and identifiers a journalist may be protecting.
- **The investigator's interests and methods** — the watchlist terms, the
  flagged pages, the notes, the monitored sites. Even with no single "secret"
  field, *the shape of the investigation itself* is sensitive: knowing what a
  reporter is looking into can endanger sources and the reporter alike.

In short, the asset is not just data — it is an investigation, and possibly the
safety of the people in it.

---
