// Cluster membership fingerprint — the stable key cluster analyses are stored
// under (decision D1). Must match the backend exactly
// (`backend/db/llm.py:compute_fingerprint`): the sorted, de-duplicated member
// resource ids are comma-joined, SHA-256 hashed, and truncated to 16 hex
// chars. The frontend computes it so the Q&A tab can fetch a cluster's prior
// answers on load (before composing a new one), without a round-trip just to
// learn the key. `fingerprint.test.ts` pins this against known backend values
// so the two implementations can't drift silently.
//
// `crypto.subtle` is available because 127.0.0.1 is a secure context.

export async function clusterFingerprint(resourceIds: number[]): Promise<string> {
  const uniqSorted = [...new Set(resourceIds.map((n) => Math.trunc(n)))].sort(
    (a, b) => a - b,
  );
  const joined = uniqSorted.join(',');
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(joined),
  );
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .slice(0, 16);
}
