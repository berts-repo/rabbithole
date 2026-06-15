// Typed API client for backend phases B0–B5.
// Same-origin fetch; the session cookie set by GET / on first load carries
// auth automatically. One function per route handler under
// backend/backend/routes/, grouped into one module per backend domain.
//
// This barrel is what `$lib/api` resolves to — it re-exports the core
// error type, every response/request type, and every route function +
// path constant, so call sites keep importing from a single specifier.
// `BASE`, `apiFetch` and `qs` stay module-internal, as they were before
// the split.

export { ApiError } from './core';
export type * from './types';

export * from './health';
export * from './projects';
export * from './settings';
export * from './retention';
export * from './crawl';
export * from './crawlQueue';
export * from './jobs';
export * from './watchlist';
export * from './engines';
export * from './entities';
export * from './nodes';
export * from './notes';
export * from './pages';
export * from './graph';
export * from './collections';
export * from './monitors';
export * from './analyses';
export * from './autoRules';
export * from './embed';
export * from './llm';
export * from './prompts';
export * from './domains';
export * from './labels';
export * from './flags';
export * from './fingerprints';
export * from './search';
export * from './harvest';
