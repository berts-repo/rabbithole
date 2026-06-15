# Security Model

This application is designed as a local, single-user analyst tool. The backend
binds to loopback and enforces a narrow request, filesystem, and network
envelope.

## Local Binding

The backend runs on:

- host: `127.0.0.1`
- port: `7654`

`HostHeaderMiddleware` only accepts `127.0.0.1` and `127.0.0.1:7654`.

## Session And API Auth

`backend/backend/security/auth.py` owns API auth.

At process startup, the backend creates one in-memory random session token.
The browser receives it as an HTTP-only `crawl_token` cookie when the SPA is
served by the backend.

Every `/api/*` request must present the cookie. Unsafe methods also need the
expected Origin header.

Unsafe methods:

- `POST`
- `PUT`
- `PATCH`
- `DELETE`

Expected origin:

- `http://127.0.0.1:7654`

Safe methods skip Origin validation because browsers commonly omit `Origin` on
same-origin GETs and EventSource handshakes.

## Development Proxy

In development, Vite serves the frontend on `127.0.0.1:5173`. The frontend
calls `/__session` on startup; Vite proxies it to backend `/` so the backend can
mint the same session cookie flow used in production.

Vite also proxies `/api/*` to `127.0.0.1:7654` and injects the backend Origin
header expected by the auth middleware.

## Security Headers

`SecurityHeadersMiddleware` adds:

- Content-Security-Policy
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`

The CSP is intentionally local and restrictive. Frontend code should not add
`{@html}` unless the security model is deliberately revisited.

## Network Egress

`backend/backend/security/net.py` owns outbound HTTP session construction.

Network rules:

- Onion targets must be valid v3 `.onion` hosts/URLs.
- Tor proxy settings must use loopback `socks5h://127.0.0.1:<port>` or
  `socks5h://::1:<port>`.
- `socks5h` is required so DNS resolution happens through Tor.
- Literal loopback targets are allowed for local services such as Ollama.
- `localhost` is intentionally not treated as loopback for this purpose.
- SSL verification must not be disabled.
- `trust_env=False` prevents ambient proxy environment variables from changing
  backend egress.
- Onion egress sends the Tor Browser request profile — a fixed User-Agent and
  header set mirroring the current stable Tor Browser — so traffic blends into
  that anonymity set instead of carrying a unique, tool-named fingerprint.
- Each onion host gets a distinct SOCKS username/password pair, so Tor stream
  isolation (`IsolateSOCKSAuth`) builds one circuit per site — a relay in one
  site's path cannot correlate it with visits to other sites.
- Crawl request cadence is governed by the `crawl.pacing` setting
  (`fast` / `polite` / `stealth`, default `polite`); the crawl runtime spaces
  requests with a jittered inter-request delay accordingly.

`make_tor_session()` and `make_ollama_session()` are the only legitimate places
that construct `aiohttp.ClientSession`.

## Path And Project File Safety

`backend/backend/security/paths.py` owns path validation.

Important rules:

- `$HOME` must exist and be owned by the current user.
- Project base is derived as `~/.local/share/rabbithole/projects/`.
- Project names are normalized and limited to a conservative character set.
- Relative DB paths resolve under the project base.
- Absolute DB paths must resolve under `$HOME`.
- DB paths must end in `.db`.
- Traversal segments are rejected.
- Symlink and non-regular DB targets are rejected.
- Project root directories are created with mode `0700`.
- Sensitive project DB files are expected to be `0600`.

Containment is checked with realpath-based validation rather than trusting the
original user-supplied path.

## Kill Switch

The kill switch tracks Tor reachability and broadcasts state through the event
bus/SSE.

When Tor is considered down, the kill switch can:

- engage the frontend warning state
- publish `kill_switch.*` events
- cause in-flight crawls to stop with `tor_down`
- block or pause workflows that require Tor egress

The UI polls Tor/kill-switch state and also listens for live transitions.

## Build-Blocking Security Checks

`make lint-security` enforces guardrails:

- no `aiohttp.ClientSession(` outside `backend/backend/security/net.py`
- no Svelte `{@html}` in `frontend/src`
- no `ssl=False` or `verify=False` in backend code
- no `shell=True` in backend code
- no direct `socket.getaddrinfo` in backend code

Run `make test` to execute these checks before the backend test suite.

## Assumptions

This is not a multi-user web service security model. It assumes a local analyst
using a loopback-bound app. The design focuses on protecting local state,
reducing CSRF exposure, keeping onion egress inside Tor, avoiding DNS leaks,
and preventing accidental path escapes.
