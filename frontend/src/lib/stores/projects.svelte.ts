// Projects list + active project. Loaded from /api/projects on mount;
// owned entirely by the backend (projects.json). The picker modal hides
// itself when activeId is non-null. On switch, the page reloads so the
// session cookie + backend DB handle re-sync from a clean state.

import {
  ApiError,
  createProject,
  deleteProject,
  listProjects,
  switchProject,
  type CreateProjectBody,
  type Project,
} from '$lib/api';

export interface CrawlConflict {
  crawl_id: number;
  seed_url: string;
  pages_crawled: number;
}

interface ProjectsState {
  projects: Project[];
  activeId: string | null;
  loading: boolean;
  error: string | null;
}

const state = $state<ProjectsState>({
  projects: [],
  activeId: null,
  loading: false,
  error: null,
});

export const projectsStore = {
  get projects() {
    return state.projects;
  },
  get activeId() {
    return state.activeId;
  },
  get loading() {
    return state.loading;
  },
  get error() {
    return state.error;
  },

  async load(): Promise<void> {
    state.loading = true;
    state.error = null;
    try {
      const list = await listProjects();
      state.projects = list.projects;
      state.activeId = list.active_id;
    } catch (e) {
      state.error = e instanceof Error ? e.message : String(e);
    } finally {
      state.loading = false;
    }
  },

  async create(body: CreateProjectBody): Promise<Project> {
    return createProject(body);
  },

  /**
   * Switch the active project. Resolves to either:
   *   { ok: true } — caller should reload the page
   *   { ok: false, conflict } — caller should confirm and re-call with force=true
   * Throws on non-409 errors so the caller can toast them.
   */
  async switch(
    id: string,
    force = false,
  ): Promise<{ ok: true } | { ok: false; conflict: CrawlConflict }> {
    try {
      await switchProject(id, force);
      return { ok: true };
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const body = e.body as { error?: string } & Partial<CrawlConflict>;
        if (
          body?.error === 'crawl_running' &&
          typeof body.crawl_id === 'number' &&
          typeof body.seed_url === 'string' &&
          typeof body.pages_crawled === 'number'
        ) {
          return {
            ok: false,
            conflict: {
              crawl_id: body.crawl_id,
              seed_url: body.seed_url,
              pages_crawled: body.pages_crawled,
            },
          };
        }
      }
      throw e;
    }
  },

  async remove(id: string): Promise<void> {
    await deleteProject(id);
    state.projects = state.projects.filter((p) => p.id !== id);
    if (state.activeId === id) state.activeId = null;
  },
};
