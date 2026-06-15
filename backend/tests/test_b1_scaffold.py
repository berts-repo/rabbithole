"""Phase B1 scaffold — auth, host, CSP, health, SPA fallback."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.security.auth import COOKIE_NAME, EXPECTED_ORIGIN


def test_health_returns_ok(client):
    client.get("/")  # bootstrap: GET / sets the session cookie
    r = client.get("/api/health", headers={"Origin": EXPECTED_ORIGIN})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_api_accepts_missing_origin_on_get_with_cookie(client):
    """Browsers omit Origin on same-origin GETs and EventSource — the cookie
    (HttpOnly + SameSite=Strict) is the auth gate for safe methods."""
    client.get("/")
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_api_rejects_missing_origin_on_post(client):
    """Mutations still require Origin — CSRF defense for state-changing requests."""
    client.get("/")
    r = client.post("/api/health")
    assert r.status_code == 403
    assert r.json() == {"error": "bad_origin"}


def test_api_rejects_mismatched_origin_on_post(client):
    """`localhost` vs `127.0.0.1` mismatch is rejected on mutations
    (DNS-rebind defense, mirrors the loopback-host check in security.net)."""
    client.get("/")
    r = client.post(
        "/api/health", headers={"Origin": "http://localhost:7654"}
    )
    assert r.status_code == 403


def test_api_rejects_missing_cookie(client):
    r = client.get("/api/health", headers={"Origin": EXPECTED_ORIGIN})
    assert r.status_code == 401


def test_api_rejects_wrong_cookie(client):
    client.cookies.set(COOKIE_NAME, "not-the-real-token")
    r = client.get("/api/health", headers={"Origin": EXPECTED_ORIGIN})
    assert r.status_code == 401


def test_api_unknown_path_returns_404(client):
    client.get("/")
    r = client.get("/api/does-not-exist", headers={"Origin": EXPECTED_ORIGIN})
    assert r.status_code == 404


def test_host_header_rejected_for_other_hosts(app):
    bad = TestClient(app, base_url="http://example.com")
    r = bad.get("/")
    assert r.status_code == 400


def test_csp_header_on_root(client):
    r = client.get("/")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "img-src 'self' data: blob:" in csp
    assert "connect-src 'self'" in csp
    assert "worker-src blob:" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp


def test_csp_header_on_api_response(client):
    client.get("/")
    r = client.get("/api/health", headers={"Origin": EXPECTED_ORIGIN})
    assert "Content-Security-Policy" in r.headers
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "no-referrer"


def test_root_issues_httponly_strict_cookie(client):
    r = client.get("/")
    set_cookie = r.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie
    assert "samesite=strict" in set_cookie.lower()


def test_session_token_rotates_per_process():
    # Two distinct app instances issue distinct tokens.
    from backend.main import create_app

    a = create_app()
    b = create_app()
    assert a.state.session.token != b.state.session.token
    assert len(a.state.session.token) >= 32
