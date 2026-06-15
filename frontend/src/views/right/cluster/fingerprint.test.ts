import { describe, expect, it } from 'vitest';
import { clusterFingerprint } from './fingerprint';

// Values pinned from the backend (`compute_fingerprint`) so the two
// implementations can't drift: a mismatch means a cluster's analyses would be
// filed under a key the worker/route never sees.
describe('clusterFingerprint', () => {
  it('matches the backend for a known membership', async () => {
    expect(await clusterFingerprint([1, 2, 3])).toBe('8a6ae15122001229');
    expect(await clusterFingerprint([42])).toBe('73475cb40a568e8d');
  });

  it('is order-independent and de-duplicates', async () => {
    expect(await clusterFingerprint([3, 1, 2, 1])).toBe(
      await clusterFingerprint([1, 2, 3]),
    );
  });

  it('distinguishes different memberships', async () => {
    expect(await clusterFingerprint([1, 2])).not.toBe(
      await clusterFingerprint([1, 2, 3]),
    );
  });
});
