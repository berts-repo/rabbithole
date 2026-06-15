// Pure helpers for the Settings → Graph hide-rules subsection.
//
// `graph_filters` rows store substrings; the backend matches them against
// each node's URL and title. Validation is intentionally light — the
// backend already rejects empty / whitespace-only terms with a 400 —
// but trimming + duplicate detection here saves a round trip on the
// obvious typos.

export function normalizeTerm(raw: string): string {
  return raw.trim();
}

export function isValidTerm(term: string): boolean {
  return normalizeTerm(term).length > 0;
}

export function isDuplicate(term: string, existing: readonly string[]): boolean {
  const t = normalizeTerm(term);
  return existing.some((e) => e === t);
}
