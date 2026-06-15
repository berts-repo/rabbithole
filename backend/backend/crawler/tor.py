"""Tor reachability probe.

PLAN.md:281 — ``GET /api/tor/status`` probes Tor via a SOCKS5h test connect.
We don't fetch a check page (that would leak a circuit just to learn whether
the SOCKS port is up); we just open a TCP connection to the proxy's host:port,
confirm it accepts, and close immediately. The proxy URL has already been
validated to be loopback by ``security.net.validate_tor_proxy``.

The connect uses ``loop.sock_connect`` on a pre-built ``socket.socket`` — that
path does not invoke the sync name resolver banned by the B0 guard and by
the test suite's autouse fixture. Loopback IPs are passed in literal form so
no name resolution is needed.
"""
from __future__ import annotations

import asyncio
import socket
import time
from typing import TypedDict

from ..security.net import TOR_PROXY_RE, validate_tor_proxy


class TorProbeResult(TypedDict):
    ok: bool
    latency_ms: int | None
    error: str | None


_CONNECT_TIMEOUT_SECONDS = 2.0


def _parse_proxy(proxy: str) -> tuple[str, int]:
    validate_tor_proxy(proxy)
    match = TOR_PROXY_RE.match(proxy)
    assert match is not None  # validate_tor_proxy already raised otherwise
    host_port = proxy[len("socks5h://"):]
    host, _, port = host_port.rpartition(":")
    return host, int(port)


async def probe_tor(proxy: str) -> TorProbeResult:
    """Return a snapshot of Tor's SOCKS-port reachability.

    Never raises — any failure is reported in the ``error`` field so the
    caller (kill switch loop, route handler) doesn't have to catch.
    """
    try:
        host, port = _parse_proxy(proxy)
    except ValueError as exc:
        return TorProbeResult(ok=False, latency_ms=None, error=f"bad_proxy: {exc}")

    family = socket.AF_INET6 if host == "::1" else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM, 0)
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    start = time.monotonic()
    try:
        await asyncio.wait_for(
            loop.sock_connect(sock, (host, port)),
            timeout=_CONNECT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return TorProbeResult(ok=False, latency_ms=None, error="timeout")
    except OSError as exc:
        return TorProbeResult(ok=False, latency_ms=None, error=str(exc))
    finally:
        sock.close()
    elapsed_ms = int((time.monotonic() - start) * 1000)
    return TorProbeResult(ok=True, latency_ms=elapsed_ms, error=None)


__all__ = ["probe_tor", "TorProbeResult"]
