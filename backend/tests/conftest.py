"""Shared fixtures for the backend test suite."""
from __future__ import annotations

import socket
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.db.core import CrawlDB
from backend.main import HOST, PORT, create_app
from backend.security.auth import EXPECTED_ORIGIN


@pytest.fixture(autouse=True)
def _ban_getaddrinfo(monkeypatch):
    """Fail loud if any backend code path calls ``socket.getaddrinfo``.

    Every outbound HTTP request must go through ``security.net``, which
    routes onion lookups inside Tor (SOCKS5h) and only ever connects to
    literal loopback IPs locally. ``getaddrinfo`` would leak DNS outside
    Tor — PLAN.md:256 lists this as a B3 invariant for every subsequent
    phase. Tests that legitimately need DNS (none today) can use
    ``monkeypatch.undo()`` inside the test.
    """

    def _refuse(*args, **kwargs):
        raise AssertionError(
            "socket.getaddrinfo() was called from backend code — DNS "
            "must stay inside Tor (PLAN.md:256). Args: " + repr(args)
        )

    monkeypatch.setattr(socket, "getaddrinfo", _refuse)


@pytest.fixture
def tmp_home(tmp_path: Path, monkeypatch) -> Path:
    """Redirect ``$HOME`` to a throwaway directory.

    Many B4 paths derive from ``security.paths.validate_home`` (which
    re-reads ``$HOME`` every call). Pointing it at ``tmp_path`` keeps the
    test suite from ever touching the real ``~/.local/share/rabbithole/``.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


@pytest.fixture
def projects_dir(tmp_home: Path) -> Path:
    """The redirected ``~/.local/share/rabbithole/projects`` path.

    Not pre-created — most flows expect to ``mkdir(parents=True)`` it as
    part of saving the registry.
    """
    return tmp_home / ".local/share/rabbithole/projects"


@pytest.fixture
def app(tmp_home: Path):
    return create_app()


@pytest.fixture
def client(app):
    # TestClient derives the Host header from base_url, so requests look like
    # they came from the real loopback origin and pass HostHeaderMiddleware.
    return TestClient(app, base_url=f"http://{HOST}:{PORT}")


@pytest.fixture
def auth_client(client):
    """Client with the session cookie already issued.

    Bootstraps via ``GET /`` (which sets ``crawl_token``) and configures
    the ``Origin`` header for every subsequent request.
    """
    client.get("/")
    client.headers.update({"Origin": EXPECTED_ORIGIN})
    return client


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A throwaway DB file path under pytest's tmp_path.

    We use a real file (not `:memory:`) so WAL mode and sqlite-vec behave
    the way they do in production. `tmp_path` is wiped between tests.
    """
    return tmp_path / "rabbithole-test.db"


@pytest.fixture
def db(db_path: Path):
    instance = CrawlDB(db_path)
    try:
        yield instance
    finally:
        instance.close()
