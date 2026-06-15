# Next

The prioritized queue of upcoming work. Top of the list is next up.

`ACTIVE.md` holds what is being worked on now. When an item is picked up, create
or promote a package under `active/YYYY-MM-DD-slug/`, point `ACTIVE.md` at it,
and remove the item from this queue in the same change.

Mark anything not yet owner-confirmed with `(idea)` so it is not mistaken for
ready work.

## Queue

1. **Find result-row polish** — queued follow-up from item 9. Add the
   entity-value context menu for Find entity rows, and add **Open as graph tab**
   for Find result lists using the existing NodeSet workspace model. Source
   intent: [`../specs/explore-left-pane-find.md`](../specs/explore-left-pane-find.md).

2. **Prompt-template management UI + body substitution** — owner-deferred
   follow-up split out of item 7. The typed `prompt_templates` table, built-in
   seeds, and `prompt_id` provenance already ship; this adds create / edit /
   clone / delete UI and makes selected free-form template bodies drive the
   worker call. Keep typed contract prompts (Risk Score, Category, Domain Label)
   on audited backend prompt text so edited templates cannot break output
   validators.

3. **Crawler privacy cleanup** — Tor Browser-like request headers,
   per-onion-host Tor circuit isolation, and crawl pacing profiles. Preserve the
   current Tor-only egress and DNS-leak constraints from `CONTEXT.md`.

4. **(idea) I2P crawling** — future second-network backend for `.i2p` eepsites
   through a local I2P router HTTP proxy, with separate Tor/I2P routing, health
   checks, profile separation, and I2P resolution metadata. Spec:
   [`additions/i2p-crawling.md`](additions/i2p-crawling.md). Not ready for
   active work until the owner decides Rabbithole should expand beyond Tor onion
   crawling and resolves the lifecycle / SAM / address-book questions in the
   spec.

## Rules

- Keep this file to live queue items only.
- Do not summarize completed implementation history here; archive packages are
  the historical entry points.
- If a future item needs extra implementation notes, put them under
  `additions/` while unshipped. When it closes, move durable context into the
  archive package and remove or shrink the addition.
