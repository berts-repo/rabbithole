"""Phase B7d — monitor CRUD routes (no daemon yet — that's B7g)."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.db.core import CrawlDB


URL_A = "http://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion/"
URL_B = "http://bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.onion/"
HOST_A = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.onion"


@pytest.fixture
def active_db(app, tmp_path: Path) -> CrawlDB:
    db = CrawlDB(tmp_path / "b7d.db")
    app.state.project_state.active_db = db
    app.state.project_state.active_id = "test"
    try:
        yield db
    finally:
        app.state.project_state.active_db = None
        app.state.project_state.active_id = None
        db.close()


def test_list_empty(auth_client, active_db):
    r = auth_client.get("/api/monitors")
    assert r.status_code == 200
    assert r.json() == {"monitors": []}


def test_create_minimal(auth_client, active_db):
    r = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == URL_A
    assert body["interval_hours"] == 1.0
    assert body["enabled"] is True
    assert body["alert_on_change"] is True
    assert body["alert_on_restore"] is True
    assert body["downtime_threshold_hours"] == 48.0


def test_create_with_full_alerts(auth_client, active_db):
    r = auth_client.post(
        "/api/monitors",
        json={
            "url": URL_A,
            "label": "primary",
            "interval_hours": 0.5,
            "alert_on_change": False,
            "alert_on_restore": False,
            "downtime_threshold_hours": 12.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "primary"
    assert body["alert_on_change"] is False
    assert body["alert_on_restore"] is False
    assert body["downtime_threshold_hours"] == 12.0


def test_create_rejects_clearnet_400(auth_client, active_db):
    r = auth_client.post(
        "/api/monitors", json={"url": "http://example.com/", "interval_hours": 1.0}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "bad_url"


def test_create_rejects_short_interval_400(auth_client, active_db):
    r = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 0.1}
    )
    assert r.status_code == 400
    assert r.json()["error"] == "interval_too_short"


def test_create_rejects_duplicate_url_409(auth_client, active_db):
    r1 = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    )
    assert r1.status_code == 200
    r2 = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 2.0}
    )
    assert r2.status_code == 409
    assert r2.json()["error"] == "duplicate_url"


def test_patch_disable_persists(auth_client, active_db):
    mid = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    ).json()["id"]
    r = auth_client.patch(f"/api/monitors/{mid}", json={"enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    # And reading back confirms persistence.
    assert auth_client.get("/api/monitors").json()["monitors"][0]["enabled"] is False


def test_patch_label_only(auth_client, active_db):
    mid = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    ).json()["id"]
    r = auth_client.patch(f"/api/monitors/{mid}", json={"label": "renamed"})
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "renamed"
    assert body["interval_hours"] == 1.0  # untouched


def test_patch_interval_rejects_short_400(auth_client, active_db):
    mid = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    ).json()["id"]
    r = auth_client.patch(f"/api/monitors/{mid}", json={"interval_hours": 0.1})
    assert r.status_code == 400
    assert r.json()["error"] == "interval_too_short"


def test_patch_unknown_404(auth_client, active_db):
    r = auth_client.patch("/api/monitors/9999", json={"enabled": False})
    assert r.status_code == 404


def test_delete_cascades_probes(auth_client, active_db):
    mid = auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    ).json()["id"]
    with active_db.transaction(immediate=True) as c:
        c.execute(
            "INSERT INTO probes(monitor_id, checked_at, status_code) "
            "VALUES (?, '2026-05-14T00:00:00+00:00', 200)",
            (mid,),
        )
    r = auth_client.delete(f"/api/monitors/{mid}")
    assert r.status_code == 200
    with active_db._lock:  # noqa: SLF001
        rows = active_db._conn.execute(
            "SELECT * FROM probes WHERE monitor_id = ?", (mid,)
        ).fetchall()
    assert rows == []


def test_list_by_host_filters(auth_client, active_db):
    auth_client.post(
        "/api/monitors", json={"url": URL_A, "interval_hours": 1.0}
    )
    auth_client.post(
        "/api/monitors", json={"url": URL_B, "interval_hours": 1.0}
    )
    rows = auth_client.get(f"/api/monitors?host={HOST_A}").json()["monitors"]
    urls = {r["url"] for r in rows}
    assert urls == {URL_A}


def test_get_unknown_404(auth_client, active_db):
    r = auth_client.delete("/api/monitors/9999")
    assert r.status_code == 404


def test_record_probe_updates_last_status(active_db):
    """Direct DB-layer test for the atomic record_probe helper."""
    from backend.db import monitors as monitors_db
    mid = monitors_db.create_monitor(
        active_db, url=URL_A, label=None, interval_hours=1.0
    )
    monitors_db.record_probe(
        active_db, mid,
        url=URL_A,
        checked_at="2026-05-14T00:01:00+00:00",
        status_code=200,
    )
    monitors_db.record_probe(
        active_db, mid,
        url=URL_A,
        checked_at="2026-05-14T00:02:00+00:00",
        status_code=503,
    )
    row = monitors_db.get_monitor(active_db, mid)
    assert row["last_status"] == 503
    assert row["last_content_changed"] is None
    latest = monitors_db.latest_probe(active_db, mid)
    assert latest["status_code"] == 503
    assert latest["checked_at"] == "2026-05-14T00:02:00+00:00"
