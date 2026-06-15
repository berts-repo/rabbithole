"""F3 — ``find_active`` returns live counters for the Crawl status row.

The status poller (`/api/crawl/status` every 2 s while running) reads
``pages_crawled``, ``pages_failed`` and ``pages_queued`` from the
``active_row`` payload.
"""
from __future__ import annotations

from backend.db import crawl as crawl_db
from backend.db import jobs as jobs_db


SEED_URL = "http://duckduckgogg42xjoc72x3sjasowoarfbgcmvfimaftt6twagswzczad.onion/"


def _mark_running(db, crawl_id: int) -> None:
    """Attach a ``running`` ``kind='crawl'`` job so ``find_active`` sees it.

    Live crawl status lives on the linked job (``payload.crawl_id``), not a
    ``crawls.status`` column, after the schema reset.
    """
    jobs_db.create_job(
        db,
        kind="crawl",
        target_type="url",
        target_id=crawl_id,
        status="running",
        payload={"crawl_id": crawl_id, "url": SEED_URL},
    )


def test_find_active_returns_all_counters(db):
    crawl_id = crawl_db.create_crawl(
        db, seed_url=SEED_URL, mode="BFS", collection_id=None, max_depth=None
    )
    _mark_running(db, crawl_id)
    crawl_db.bump_counter(db, crawl_id, "pages_crawled")
    crawl_db.bump_counter(db, crawl_id, "pages_failed")
    crawl_db.bump_counter(db, crawl_id, "pages_queued")
    crawl_db.bump_counter(db, crawl_id, "pages_queued")

    row = crawl_db.find_active(db)
    assert row is not None
    assert row["id"] == crawl_id
    assert row["seed_url"] == SEED_URL
    assert row["mode"] == "BFS"
    assert row["status"] == "running"
    assert row["pages_crawled"] == 1
    assert row["pages_failed"] == 1
    assert row["pages_queued"] == 2
    assert row["collection_id"] is None


def test_find_active_returns_none_when_no_active(db):
    assert crawl_db.find_active(db) is None


def test_find_active_carries_collection_id(db):
    # Workspace-tabs wiring: the status poller's active_row needs to know
    # which collection a running crawl was targeting, so the toolbar can
    # render the "crawling → {label}" chip on the Global tab.
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO collections(name, description) VALUES (?, NULL)",
            ("targeted",),
        )
        cid = int(cur.lastrowid)
    crawl_id = crawl_db.create_crawl(
        db, seed_url=SEED_URL, mode="BFS", collection_id=cid, max_depth=None
    )
    _mark_running(db, crawl_id)

    row = crawl_db.find_active(db)
    assert row is not None
    assert row["collection_id"] == cid
