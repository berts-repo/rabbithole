# Graph Tab — Left Pane — Intel Sub-tab

The Intel sub-tab is the control panel for all local AI analysis. Everything runs through
Ollama at `http://127.0.0.1:11434` — page content never leaves the machine.

---

## Layout

Five collapsible sections. Each section header is a toggle button; collapsed state is
persisted per section.

Status polling runs on timers while the tab is active:
- LLM service status refreshes every **8 seconds**
- Embedding model status refreshes every **10 seconds**

Selecting a node in the graph auto-fills the URL field in both **Q&A** and **Queue Analysis**.

---

## Section 1 — LLM Service

Controls the background worker that drains the analysis queue.

**Status row**
- Dot: green = running, grey = stopped, amber = Ollama unreachable
- Model name displayed when running
- Queue depth badge (amber) showing how many jobs are waiting

**Start**
- Starts the background worker
- On startup it does two things automatically:
  1. **Crash recovery** — any jobs stuck in progress from a previous crash are reset to pending
  2. **Legacy bridge** — older pending analysis work is re-added to the current queue
- Then enters a poll loop every 2 seconds, pulling batches of up to 5 jobs in priority order
- If Ollama goes down mid-run the service pauses and retries every 30 s; it resumes automatically when Ollama comes back

**Stop**
- Stops the worker cleanly after the current batch finishes
- Only works for a manually started worker; a crawl-owned worker ignores this button and
  shows a toast: "Worker is running a crawl — stop the crawl first."

The Start/Stop state here is shared with the LLM pill in the app header — both always
reflect the same worker and both can control it.

**The queue is persistent.** Jobs survive restarts and accumulate from all sources (crawl runs, manual Queue Analysis submissions, Collection Analysis bulk jobs). They drain in priority order as the service runs.

---

### Queue list

Shown below the Start/Stop controls. Lists every pending and running job in priority order.

Each row shows:
- **URL** (truncated) with domain in smaller grey text below
- **Type** badge (e.g. `summary`, `risk score`, `Q&A`)
- **Status** badge: `running` (pulsing teal dot) · `pending` (grey) · `waiting` (amber, muted — stub node not yet crawled; job will fire automatically when the site is crawled)
- **✕ button** — removes the job from the queue. No confirmation.
- **⊘ Exclude button** — marks the page as excluded from analysis. The job is removed and
  the page will not be re-queued automatically (e.g. by crawl auto-queue). Excluded pages
  can be re-included from the right panel Page tab.

`waiting` jobs are shown at the bottom of the queue below all `pending` jobs and cannot be reordered — they are not eligible to run until their node is crawled. The LLM worker skips them entirely.

**The running job** is always pinned at position 1 with a pulsing dot. Its ✕ button
cancels the in-progress job and resets it.

**Selecting a row** (click) highlights it and reveals inline controls:
- ↑ / ↓ arrows — move the job one position up or down in the queue
- **Move to top** button — jumps the job to position 2 (immediately after any running job)

Reordering updates the `priority` field on the `analyses` record. The worker always pulls
the highest-priority pending job next.

Empty state: "No jobs in queue." shown when idle.

---

## Section 2 — Analyse

Queue any analysis type against a single URL. URL auto-fills when a node is selected anywhere in the app.

**Fields**
- **URL** — the target page (auto-fills on node click). On stub nodes the job is queued with `waiting` status and fires automatically when the stub is crawled.
- **Type** — one of:
  - `Summary` — prose summary of page content
  - `Risk Score` — heuristic danger/sensitivity score
  - `Entities (LLM)` — extract people, orgs, and locations via the model
  - `Category (LLM)` — classify the page's subject area
  - `Domain Label` — infer a short human-readable label for the whole `.onion` domain
  - `Q&A` — ask a natural-language question about the page
- **Question** — free-text input; appears only when `Q&A` is selected. Enter key submits.
- **Model** — dropdown of available local models

**Queue** adds one job to the queue. The LLM service picks it up on its next poll cycle. The result appears in the right panel Analysis tab once complete.

---

## Section 3 — Embedding Model

Separate background process that generates vector embeddings for every crawled page
(used for semantic search and similarity features). Independent of the LLM service.

The embed service starts automatically when the backend starts and restarts itself on
crash. Start/Stop controls (and the auto-start toggle) live in **Settings → Embedding**
for analysts who need to disable it on low-powered machines.

**Status row**
- Dot: green = running, amber = paused, grey = stopped
- Label reflects current status string from the embed service

**Progress line**
- `N / M pages embedded (X%)` — how much of the DB has been embedded
- Queue depth line shown when there are pages waiting

**Pause / Resume** — throttle or resume the embedding worker without fully stopping it.
Use this for day-to-day control. To fully stop the service, go to Settings → Embedding.

---

## Section 4 — Collection Analysis

Run analysis across a named collection. Two modes: per-URL bulk jobs, and collection-scoped synthesis.

**Fields**
- **Collection** — dropdown of all saved collections with item counts
- **Type** — one of:

  *Per-URL (queues one job per crawled URL in the collection):*
  - `Summary` · `Risk Score` · `Entities (LLM)` · `Category (LLM)` · `Domain Label`

  *Collection-scoped (one job synthesising across the whole collection):*
  - `Cluster Summary` — summarise the thematic clusters in the collection
  - `Site Relationships` — describe relationships between sites
  - `Investigation Digest` — narrative digest for investigative context
  - `Seed Suggestions` — suggest new `.onion` seeds to explore

Stub items are excluded from all analysis types. A note shows: "N of M items will be analysed (X stubs excluded)."

**Queue / Analyse** button — for per-URL types: enqueues one job per crawled URL. For collection-scoped types: queues a single synthesis job and polls every 4 s until done; result appears inline below the button (max 200 px, scrollable).

---

## Typical Workflow

1. Start the LLM service once (Section 1)
2. Run a crawl — the crawler auto-enqueues summary jobs for each page it fetches
3. The service drains the queue in the background; results appear in node details
4. Click any node in the graph → its URL auto-fills in the Analyse section
5. Use Analyse to run deeper analysis (risk score, entities, domain label, Q&A) on nodes of interest
6. Use Collection Analysis to batch-process a pinned set of sites

---
