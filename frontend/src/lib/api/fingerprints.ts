// Header-fingerprint cluster + member routes (Fingerprints sub-tab).

import { apiFetch, qs, BASE } from './core';
import type { FingerprintCluster, FingerprintMember } from './types';

export const listFingerprints = (minSites: number) =>
  apiFetch<{ clusters: FingerprintCluster[] }>(
    `/fingerprints${qs({ min_sites: minSites })}`,
  );

export const listFingerprintMembers = (key: string, value: string) =>
  apiFetch<{ members: FingerprintMember[] }>(
    `/fingerprints/members${qs({ key, value })}`,
  );

// CSV export uses an <a download> against this URL — same pattern as
// collectionExportUrl. apiFetch can't stream Content-Disposition.
export const fingerprintsCsvUrl = (minSites: number): string =>
  `${BASE}/fingerprints/export.csv${qs({ min_sites: minSites })}`;
