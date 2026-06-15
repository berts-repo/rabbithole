// Shared crawl-URL regexes used by the Crawl sub-tab inputs (controls,
// bulk import, schedule form). Mirror backend/security/net.py
// (ONION_URL_RE / I2P_URL_RE) so the client rejects URLs the server would
// reject too. The backend remains the real gate — it also enforces the
// `i2p.enabled` setting, which the client does not check here.
//
// v3 onion: 56 base32 chars (a-z2-7). I2P: a `.i2p` host, either a readable
// address-book name (forum.i2p) or the `<b32>.b32.i2p` destination form.

const ONION_URL_RE = /^https?:\/\/[a-z2-7]{56}\.onion(?::\d{1,5})?(?:\/.*)?$/i;
const I2P_URL_RE = /^https?:\/\/(?:[a-z0-9-]+\.)+i2p(?::\d{1,5})?(?:\/.*)?$/i;

export function isOnionUrl(url: string): boolean {
  return ONION_URL_RE.test(url.trim());
}

export function isI2pUrl(url: string): boolean {
  return I2P_URL_RE.test(url.trim());
}

/** True for any crawlable URL — `.onion` or `.i2p`. */
export function isSupportedUrl(url: string): boolean {
  const trimmed = url.trim();
  return ONION_URL_RE.test(trimmed) || I2P_URL_RE.test(trimmed);
}

/** Trim + return on success, null on failure. Frontend-only — the backend
 *  still re-validates every URL before it touches the DB. */
export function normaliseOnionUrl(url: string): string | null {
  const trimmed = url.trim();
  return ONION_URL_RE.test(trimmed) ? trimmed : null;
}

/** Trim + return on success, null on failure, for either supported network. */
export function normaliseSupportedUrl(url: string): string | null {
  const trimmed = url.trim();
  return isSupportedUrl(trimmed) ? trimmed : null;
}
