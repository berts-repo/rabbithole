// Core fetch machinery for the typed API client. Every route module under
// lib/api/ is built on apiFetch + qs; ApiError is the single error type
// callers may instanceof-check, so it is defined here exactly once.

const BASE = '/api';

// ---------------- Error type ----------------

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message?: string) {
    super(message ?? `api error ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

// ---------------- Core fetch ----------------

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: 'same-origin',
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  // 204 / no body — return undefined cast as T.
  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    const msg =
      body && typeof body === 'object' && 'error' in body
        ? String((body as { error: unknown }).error)
        : `http ${res.status}`;
    throw new ApiError(res.status, body, msg);
  }

  return body as T;
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined) continue;
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  }
  return parts.length ? `?${parts.join('&')}` : '';
}

export { BASE, apiFetch, qs };
