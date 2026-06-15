import {
  createSeed,
  deleteSeed,
  listSeeds,
  patchSeed,
  type CreateSeedBody,
  type Seed,
} from '$lib/api';

interface SeedBookmarkState {
  seeds: Seed[];
  loaded: boolean;
}

const state = $state<SeedBookmarkState>({
  seeds: [],
  loaded: false,
});

function sortSeeds(seeds: Seed[]): Seed[] {
  return [...seeds].sort((a, b) => {
    const dateCmp = b.added_at.localeCompare(a.added_at);
    return dateCmp || a.url.localeCompare(b.url);
  });
}

export const seedBookmarksStore = {
  get seeds() {
    return state.seeds;
  },
  get loaded() {
    return state.loaded;
  },

  async refresh(): Promise<void> {
    const r = await listSeeds();
    state.seeds = r.seeds;
    state.loaded = true;
  },

  async add(body: CreateSeedBody): Promise<boolean> {
    const r = await createSeed(body);
    if (r.added) {
      const now = new Date().toISOString();
      state.seeds = sortSeeds([
        { url: r.url, label: body.label ?? null, added_at: now },
        ...state.seeds.filter((s) => s.url !== r.url),
      ]);
      state.loaded = true;
    } else if (!state.loaded) {
      await this.refresh();
    }
    return r.added;
  },

  async remove(url: string): Promise<void> {
    await deleteSeed(url);
    state.seeds = state.seeds.filter((s) => s.url !== url);
    state.loaded = true;
  },

  // Rename the label without disturbing added_at — backend updates the
  // row in place, the store mirrors locally so the row doesn't jump in
  // the date-sorted list.
  async renameLabel(url: string, label: string | null): Promise<void> {
    const normalized = label && label.trim() ? label.trim() : null;
    await patchSeed(url, { label: normalized });
    state.seeds = state.seeds.map((s) =>
      s.url === url ? { ...s, label: normalized } : s,
    );
    state.loaded = true;
  },
};
