"""Egress factory + validators — the only place that builds aiohttp sessions.

Every outbound HTTP request the backend makes — crawler fetches, monitor
probes, harvest queries, embed worker downloads, Tor health probes, Ollama
calls — goes through ``make_tor_session``. The B0 lint guard fails the build
if a raw aiohttp session is constructed anywhere else in the backend
package (PLAN.md:194), and direct synchronous DNS resolution is banned
outright so name lookups never escape Tor.

The factory enforces three invariants:

1. The configured Tor proxy URL matches ``socks5h://(127.0.0.1|::1):<port>``
   — non-loopback proxies are refused at session-construction time even if
   the settings layer somehow let one through (defense in depth).
2. Remote targets must be valid v3 ``.onion`` hostnames (56-char base32).
   Anything else raises ``EgressError`` before a connector is built.
3. Loopback targets (Ollama at 127.0.0.1:11434, local Tor probe at the
   SOCKS port) bypass the SOCKS proxy and use a plain TCP connector. They
   are scoped narrowly: only literal ``127.0.0.1`` / ``::1`` qualify —
   ``localhost`` is rejected because of DNS-rebind risk, mirroring the
   Origin check in ``security/auth.py``.

The factory never disables certificate verification — the B0 guard forbids
the ``ssl``-disable kwarg anywhere under ``backend/``, and this file uses
``ssl.create_default_context()`` only.
"""
from __future__ import annotations

import re
import ssl as _ssl
from urllib.parse import urlsplit

import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType


class ConfigError(ValueError):
    """Raised when a configured value (e.g. tor.proxy) is unusable."""


class EgressError(ValueError):
    """Raised when a target is outside the allowed egress envelope."""


# --- Regexes — single source of truth for the whole backend. ----------------
# v3 onion: 56 base32 chars (a-z, 2-7) + ".onion".
ONION_HOST_RE = re.compile(r"^[a-z2-7]{56}\.onion$")
# Canonical TCP port pattern: 1–65535. Refuses port 0 and any value above the
# IANA range, both of which `\d{1,5}` would silently accept and which the
# connector layer would only catch at runtime.
_PORT_RE = (
    r"(?:6553[0-5]|655[0-2]\d|65[0-4]\d{2}|6[0-4]\d{3}|[1-5]\d{4}|[1-9]\d{0,3})"
)
ONION_URL_RE = re.compile(
    r"^https?://[a-z2-7]{56}\.onion(?::" + _PORT_RE + r")?(?:[/?#].*)?$"
)
# Loopback-only SOCKS5h proxy. ``socks5`` (no ``h``) leaks DNS — forbidden.
TOR_PROXY_RE = re.compile(
    r"^socks5h://(?:127\.0\.0\.1|::1):" + _PORT_RE + r"$"
)
# Loopback-only Ollama HTTP endpoint. Same DNS-rebind defense as ``TOR_PROXY_RE``
# — literal ``127.0.0.1`` / ``::1`` only, no ``localhost``.
OLLAMA_URL_RE = re.compile(
    r"^http://(?:127\.0\.0\.1|::1):" + _PORT_RE + r"(?:/.*)?$"
)

# --- I2P (.i2p eepsite) patterns --------------------------------------------
# Unlike v3 onion, an ``.i2p`` hostname is not self-authenticating: human-
# readable address-book names (``forum.i2p``) resolve through the router's
# address book, and only the ``*.b32.i2p`` form (52-char base32 destination
# hash) is cryptographic. ``I2P_HOST_RE`` accepts both — restricting to b32
# would reject most real links. ``I2P_B32_RE`` is kept so a later refinement
# can surface name-vs-destination per host.
_I2P_HOST_PAT = r"(?:[a-z0-9-]+\.)*[a-z0-9-]+\.i2p"
I2P_B32_RE = re.compile(r"^[a-z2-7]{52}\.b32\.i2p$")
I2P_HOST_RE = re.compile(r"^" + _I2P_HOST_PAT + r"$")
I2P_URL_RE = re.compile(
    r"^https?://" + _I2P_HOST_PAT + r"(?::" + _PORT_RE + r")?(?:[/?#].*)?$"
)
# I2P egress reuses the Tor SOCKS model: its SOCKS proxy (i2pd default 4447)
# resolves ``.i2p`` names router-side, so the same loopback-``socks5h`` shape
# as ``TOR_PROXY_RE`` applies and no ``.i2p`` name hits the OS resolver.
I2P_PROXY_RE = re.compile(
    r"^socks5h://(?:127\.0\.0\.1|::1):" + _PORT_RE + r"$"
)

LOOPBACK_HOSTS: frozenset[str] = frozenset({"127.0.0.1", "::1"})

# Streaming size cap enforced by B5 crawler. Exposed here so every consumer
# imports the same constant rather than re-declaring it.
MAX_RESPONSE_BYTES: int = 10 * 1024 * 1024

# Conservative timeouts shared by every outbound session. Per-call overrides
# are allowed via the ``timeout=`` kwarg on ``make_tor_session``.
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(connect=15, sock_read=30, total=60)

# Connection-pool cap: keeps us from saturating a single Tor circuit.
_POOL_LIMIT = 8


# --- Outbound request headers -----------------------------------------------
#
# Onion egress mimics the Tor Browser request profile. Tor Browser gives every
# one of its users an identical request fingerprint by design, so adopting its
# headers both blends our traffic into the largest available anonymity set and
# keeps the profile a fixed constant. The previous tool-named ``rabbithole/1.0``
# User-Agent did the opposite of "neutral": a unique constant is a permanent
# name tag, letting a hostile onion site recognise the crawler outright and
# block it or feed it poisoned decoy content.
#
# Mirrors Tor Browser 15.0 (Firefox 140 ESR) top-level-navigation headers.
# Bump ``rv:`` / ``Firefox/`` and re-check this set on each Tor Browser major
# release.
_TOR_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; rv:140.0) Gecko/20100101 Firefox/140.0"
)

# aiohttp only decompresses ``br`` when ``brotli`` (or ``brotlicffi``) is
# importable. Tor Browser advertises brotli for ``.onion`` targets (a secure
# context), so we do too — but we must never advertise an encoding aiohttp
# cannot decode, or a brotli-encoded response would raise mid-stream. ``zstd``
# is deliberately omitted: Tor Browser sends it, aiohttp 3.x cannot decode it,
# and that one-token divergence is unavoidable and acceptable.
try:  # pragma: no cover - import-availability branch
    import brotli as _brotli  # noqa: F401

    _HAS_BROTLI = True
except ImportError:  # pragma: no cover
    try:
        import brotlicffi as _brotlicffi  # noqa: F401

        _HAS_BROTLI = True
    except ImportError:
        _HAS_BROTLI = False

_ACCEPT_ENCODING = "gzip, deflate, br" if _HAS_BROTLI else "gzip, deflate"

# Ordered to follow Firefox's on-wire navigation header sequence as closely as
# aiohttp allows — header order is itself a fingerprinting dimension. Every
# fetch is modelled as a fresh address-bar navigation (Sec-Fetch-Site: none,
# Sec-Fetch-User: ?1), which is internally consistent with never sending a
# Referer.
_TOR_REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": _TOR_BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": _ACCEPT_ENCODING,
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i",
}

# Loopback-only User-Agent for the local Ollama HTTP API. That traffic never
# leaves the machine, so it carries no onion-facing fingerprinting surface.
_USER_AGENT = "rabbithole/1.0"


# --- Validators -------------------------------------------------------------


def validate_tor_proxy(value: object) -> str:
    """Return ``value`` if it is a loopback ``socks5h://`` URL; raise otherwise."""
    if not isinstance(value, str):
        raise ConfigError(f"tor.proxy must be a string, got {type(value).__name__}")
    candidate = value.strip()
    if not TOR_PROXY_RE.match(candidate):
        raise ConfigError(
            f"tor.proxy must match socks5h://(127.0.0.1|::1):<port>, got {value!r}"
        )
    return candidate


def validate_onion_host(host: object) -> str:
    """Lower-case + match the v3 onion regex; raise ``EgressError`` if not."""
    if not isinstance(host, str):
        raise EgressError(f"host must be a string, got {type(host).__name__}")
    lowered = host.strip().lower()
    if not ONION_HOST_RE.match(lowered):
        raise EgressError(f"not a v3 .onion host: {host!r}")
    return lowered


def validate_onion_url(url: object) -> str:
    """Match the v3 onion URL regex; raise ``EgressError`` if not."""
    if not isinstance(url, str):
        raise EgressError(f"url must be a string, got {type(url).__name__}")
    candidate = url.strip()
    if not ONION_URL_RE.match(candidate):
        raise EgressError(f"not a valid .onion URL: {url!r}")
    return candidate


def validate_i2p_host(host: object) -> str:
    """Lower-case + match the ``.i2p`` host regex; raise ``EgressError`` if not."""
    if not isinstance(host, str):
        raise EgressError(f"host must be a string, got {type(host).__name__}")
    lowered = host.strip().lower()
    if not I2P_HOST_RE.match(lowered):
        raise EgressError(f"not a .i2p host: {host!r}")
    return lowered


def validate_i2p_url(url: object) -> str:
    """Match the ``.i2p`` URL regex; raise ``EgressError`` if not."""
    if not isinstance(url, str):
        raise EgressError(f"url must be a string, got {type(url).__name__}")
    candidate = url.strip()
    if not I2P_URL_RE.match(candidate):
        raise EgressError(f"not a valid .i2p URL: {url!r}")
    return candidate


def validate_i2p_proxy(value: object) -> str:
    """Return ``value`` if it is a loopback ``socks5h://`` URL; raise otherwise."""
    if not isinstance(value, str):
        raise ConfigError(f"i2p.proxy must be a string, got {type(value).__name__}")
    candidate = value.strip()
    if not I2P_PROXY_RE.match(candidate):
        raise ConfigError(
            f"i2p.proxy must match socks5h://(127.0.0.1|::1):<port>, got {value!r}"
        )
    return candidate


def network_of_host(host: object) -> str:
    """Return ``'tor'`` for ``.onion`` hosts, ``'i2p'`` for ``.i2p`` hosts.

    Suffix-only — the full-shape check lives in ``validate_onion_host`` /
    ``validate_i2p_host``. This is the single place the suffix→network rule is
    defined. Raises ``EgressError`` for anything outside the two supported
    networks so clearnet can never slip through a dispatch.
    """
    if not isinstance(host, str):
        raise EgressError(f"host must be a string, got {type(host).__name__}")
    lowered = host.strip().lower()
    if lowered.endswith(".onion"):
        return "tor"
    if lowered.endswith(".i2p"):
        return "i2p"
    raise EgressError(f"unsupported network for host: {host!r}")


def network_of_url(url: object) -> str:
    """Network discriminant for a full URL (delegates to ``network_of_host``)."""
    if not isinstance(url, str):
        raise EgressError(f"url must be a string, got {type(url).__name__}")
    return network_of_host(urlsplit(url.strip()).hostname or "")


def validate_network_url(url: object) -> tuple[str, str]:
    """Validate ``url`` against whichever supported network its host names.

    Returns ``(network, normalised_url)`` where ``network`` is ``'tor'`` or
    ``'i2p'``. Replaces bare ``validate_onion_url`` at intake sites so any
    non-``.onion``/``.i2p`` target is still rejected with ``EgressError``.
    """
    network = network_of_url(url)
    if network == "tor":
        return ("tor", validate_onion_url(url))
    return ("i2p", validate_i2p_url(url))


def is_loopback_host(host: object) -> bool:
    """``True`` only for literal ``127.0.0.1`` / ``::1``. ``localhost`` is False
    on purpose (DNS-rebind defense)."""
    return isinstance(host, str) and host in LOOPBACK_HOSTS


def validate_ollama_url(value: object) -> str:
    """Return ``value`` if it is a loopback ``http://`` URL; raise otherwise.

    Used by ``llm.ollama_url`` setting validator and by ``make_ollama_session``
    as defense in depth.
    """
    if not isinstance(value, str):
        raise ConfigError(
            f"llm.ollama_url must be a string, got {type(value).__name__}"
        )
    candidate = value.strip()
    if not OLLAMA_URL_RE.match(candidate):
        raise ConfigError(
            "llm.ollama_url must match http://(127.0.0.1|::1):<port>, "
            f"got {value!r}"
        )
    return candidate


# --- Session factory --------------------------------------------------------


def make_session(
    target_host: str,
    *,
    proxy: str,
    timeout: aiohttp.ClientTimeout | None = None,
) -> aiohttp.ClientSession:
    """Build the single outbound session for a given target.

    Loopback targets (``127.0.0.1`` / ``::1``) get a plain ``TCPConnector``
    — Ollama and the local SOCKS probe port live here. Remote targets get a
    ``ProxyConnector`` pointing at the validated SOCKS5h URL, which forces
    proxy-side hostname resolution: ``.onion`` routes through Tor (``tor.proxy``,
    9050) and ``.i2p`` through the I2P SOCKS proxy (``i2p.proxy``, 4447). The
    caller selects the proxy for the host's network. Anything that is neither a
    loopback nor a supported-network host raises ``EgressError``.
    """
    proxy_url = validate_tor_proxy(proxy)
    effective_timeout = timeout or DEFAULT_TIMEOUT

    if is_loopback_host(target_host):
        connector = aiohttp.TCPConnector(
            limit=_POOL_LIMIT,
            ssl=_ssl.create_default_context(),
        )
    else:
        network = network_of_host(target_host)
        if network == "i2p":
            validate_i2p_host(target_host)
            # I2P has no per-stream circuit isolation knob like Tor's
            # IsolateSOCKSAuth — tunnels are managed by the router — so no
            # SOCKS credentials are supplied.
            username = password = None
        else:
            onion_host = validate_onion_host(target_host)
            # Per-onion-host SOCKS credentials drive Tor's stream isolation
            # (`IsolateSOCKSAuth`, on by default): a distinct user/pass pair
            # gets a distinct circuit. Keying both on the onion host gives one
            # circuit per site — pages within a site share it — mirroring Tor
            # Browser's per-first-party isolation and keeping a malicious relay
            # in one site's path from correlating it with another.
            username = password = onion_host
        # aiohttp_socks / python_socks parse `socks5://` only — the "h"
        # variant maps to `rdns=True` here. We've already enforced the
        # `socks5h://` form on the configured value via `TOR_PROXY_RE`,
        # so by the time we get here we know remote-side DNS is intended.
        proxy_host_port = proxy_url[len("socks5h://"):]
        # IPv6 forms come back without brackets; aiohttp_socks's parser
        # accepts the v4 / v6 hostname directly.
        host, _, port = proxy_host_port.rpartition(":")
        connector = ProxyConnector(
            proxy_type=ProxyType.SOCKS5,
            host=host,
            port=int(port),
            rdns=True,
            limit=_POOL_LIMIT,
            username=username,
            password=password,
        )

    return aiohttp.ClientSession(
        connector=connector,
        timeout=effective_timeout,
        headers=_TOR_REQUEST_HEADERS,
        trust_env=False,
    )


# Back-compat alias: existing callers and tests import ``make_tor_session``.
# The factory is now network-aware (``.onion`` via Tor, ``.i2p`` via the I2P
# SOCKS proxy), but the name is kept so the egress entry point is stable.
make_tor_session = make_session


def make_ollama_session(
    ollama_url: str,
    *,
    timeout: aiohttp.ClientTimeout | None = None,
) -> aiohttp.ClientSession:
    """Build the loopback HTTP session used to talk to a local Ollama server.

    Re-validates ``ollama_url`` so the settings layer can never let a
    non-loopback target through (defense in depth, same pattern as
    ``make_tor_session`` re-validates ``tor.proxy``). Returns a plain
    ``TCPConnector`` session — no SOCKS proxy, no Tor exposure of LLM
    traffic.

    The B0 grep guard whitelists this file as the single legitimate place
    that constructs ``aiohttp.ClientSession`` directly.
    """
    validate_ollama_url(ollama_url)
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }
    effective_timeout = timeout or DEFAULT_TIMEOUT
    connector = aiohttp.TCPConnector(
        limit=_POOL_LIMIT,
        ssl=_ssl.create_default_context(),
    )
    return aiohttp.ClientSession(
        connector=connector,
        timeout=effective_timeout,
        headers=headers,
        trust_env=False,
    )
