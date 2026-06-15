// Label catalog store (item 11, Phase 2) — the single source of truth for the
// label taxonomy across the picker, chips, color mode, and collapse ordering.
//
// Holds the rank-ordered label list with member counts. Per-resource /
// per-domain membership is NOT here — that rides on the entity payloads
// (node detail, domain profile). This store is the catalog only: what labels
// exist, in what order, with how many members.
//
// Mutations go through the API client and patch the local list optimistically
// where cheap, falling back to a refresh when the server is the authority on
// the new shape (create assigns id+rank, reorder re-ranks the whole list).

import {
  attachDomainLabel,
  attachResourceLabel,
  createLabel,
  deleteLabel,
  detachDomainLabel,
  detachResourceLabel,
  listLabels,
  reorderLabels,
  updateLabel,
  type CreateLabelBody,
  type Label,
  type UpdateLabelBody,
} from '$lib/api';

interface LabelState {
  labels: Label[];
  loaded: boolean;
}

const state = $state<LabelState>({
  labels: [],
  loaded: false,
});

// Server returns labels in rank order; keep that invariant on any local
// splice so callers can render the list as-is.
function byRank(labels: Label[]): Label[] {
  return [...labels].sort((a, b) => a.rank - b.rank || a.id - b.id);
}

export const labelsStore = {
  get labels() {
    return state.labels;
  },
  get loaded() {
    return state.loaded;
  },
  // Picker order: the analyst-visible labels (presets the analyst hid drop
  // out), already rank-sorted.
  get visible() {
    return state.labels.filter((l) => !l.hidden);
  },

  byId(id: number): Label | undefined {
    return state.labels.find((l) => l.id === id);
  },

  // Resolve a payload's id list to full labels, dropping any id the catalog
  // doesn't know (a label deleted between payload build and render) and
  // preserving the payload's rank order. Backs the chip components.
  resolve(ids: readonly number[]): Label[] {
    const out: Label[] = [];
    for (const id of ids) {
      const l = this.byId(id);
      if (l) out.push(l);
    }
    return out;
  },

  async refresh(): Promise<void> {
    const r = await listLabels(true);
    state.labels = byRank(r.labels);
    state.loaded = true;
  },

  // Load once; subsequent callers reuse the cached catalog. The picker calls
  // this on open so the first paint isn't blocked on a fetch every time.
  async ensureLoaded(): Promise<void> {
    if (state.loaded) return;
    await this.refresh();
  },

  async create(body: CreateLabelBody): Promise<Label> {
    const created = await createLabel(body);
    state.labels = byRank([...state.labels, created]);
    state.loaded = true;
    return created;
  },

  async update(id: number, body: UpdateLabelBody): Promise<Label> {
    const updated = await updateLabel(id, body);
    state.labels = byRank(state.labels.map((l) => (l.id === id ? updated : l)));
    return updated;
  },

  async remove(id: number): Promise<void> {
    await deleteLabel(id);
    state.labels = state.labels.filter((l) => l.id !== id);
  },

  // Reorder is the server's call (it re-ranks the whole list, appending any
  // omitted ids); mirror the authoritative result back.
  async reorder(ids: number[]): Promise<void> {
    const r = await reorderLabels(ids);
    state.labels = byRank(r.labels);
  },

  // --- attach / detach -----------------------------------------------------
  //
  // Idempotent server-side. We bump the cached member count only when the row
  // actually changed, so repeat clicks don't inflate the badge.

  async attachResource(labelId: number, resourceId: number): Promise<boolean> {
    const { attached } = await attachResourceLabel(labelId, resourceId);
    if (attached) this._bumpResourceCount(labelId, +1);
    return attached;
  },

  async detachResource(labelId: number, resourceId: number): Promise<boolean> {
    const { detached } = await detachResourceLabel(labelId, resourceId);
    if (detached) this._bumpResourceCount(labelId, -1);
    return detached;
  },

  async attachDomain(labelId: number, host: string): Promise<boolean> {
    const { attached } = await attachDomainLabel(labelId, host);
    if (attached) this._bumpDomainCount(labelId, +1);
    return attached;
  },

  async detachDomain(labelId: number, host: string): Promise<boolean> {
    const { detached } = await detachDomainLabel(labelId, host);
    if (detached) this._bumpDomainCount(labelId, -1);
    return detached;
  },

  _bumpResourceCount(labelId: number, delta: number): void {
    state.labels = state.labels.map((l) =>
      l.id === labelId
        ? { ...l, resource_count: Math.max(0, l.resource_count + delta) }
        : l,
    );
  },

  _bumpDomainCount(labelId: number, delta: number): void {
    state.labels = state.labels.map((l) =>
      l.id === labelId
        ? { ...l, domain_count: Math.max(0, l.domain_count + delta) }
        : l,
    );
  },
};
