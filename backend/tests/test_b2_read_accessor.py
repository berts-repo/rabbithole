"""Phase B2 — the ``CrawlDB.read()`` accessor (DB-access seam).

``read()`` is the public read counterpart of ``transaction()`` — the front
door for every ``SELECT`` in ``db/`` / ``services/`` / ``routes/``. These
tests pin down the three properties the seam refactor depends on:

  1. yields a usable, row-factory-aware connection,
  2. composes with ``transaction()`` (reentrant ``RLock``),
  3. serialises concurrent reads (matches the locking promise made in
     the docstring — multi-statement snapshots are coherent).
"""
from __future__ import annotations

import sqlite3
import threading
import time

from backend.db.core import CrawlDB


def test_read_yields_usable_row_factory_connection(db: CrawlDB) -> None:
    with db.read() as c:
        assert isinstance(c, sqlite3.Connection)
        row = c.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1  # sqlite3.Row factory set in _configure_connection


def test_read_holds_the_lock(db: CrawlDB) -> None:
    """While read() holds the lock, another thread cannot enter read()/transaction()."""
    started = threading.Event()
    other_acquired = threading.Event()

    def background() -> None:
        # Wait until the foreground holder is definitely inside read().
        started.wait(timeout=1.0)
        with db.read():
            other_acquired.set()

    t = threading.Thread(target=background)
    with db.read():
        t.start()
        started.set()
        # The other thread should be blocked on the lock for the duration.
        assert not other_acquired.wait(timeout=0.1)
    t.join(timeout=1.0)
    assert other_acquired.is_set(), "background read() must run after foreground releases"


def test_read_composes_inside_transaction(db: CrawlDB) -> None:
    """RLock means read() inside transaction() is a no-op nesting, not a deadlock."""
    with db.transaction() as tx:
        tx.execute(
            "INSERT INTO settings(key, value) VALUES ('seam.test.compose', 'a')"
        )
        with db.read() as c:
            row = c.execute(
                "SELECT value FROM settings WHERE key = 'seam.test.compose'"
            ).fetchone()
            assert row["value"] == "a"


def test_transaction_composes_inside_read(db: CrawlDB) -> None:
    """Inverse nesting (write inside an open read) must also be safe."""
    with db.read():
        with db.transaction() as tx:
            tx.execute(
                "INSERT INTO settings(key, value) VALUES ('seam.test.invert', 'b')"
            )
    with db.read() as c:
        row = c.execute(
            "SELECT value FROM settings WHERE key = 'seam.test.invert'"
        ).fetchone()
        assert row["value"] == "b"


def test_read_snapshot_is_coherent_across_statements(db: CrawlDB) -> None:
    """A multi-statement read() sees no interleaved writes from other threads."""
    with db.transaction() as c:
        c.execute(
            "INSERT INTO settings(key, value) VALUES ('seam.snap', '1')"
        )

    flip_started = threading.Event()

    def flipper() -> None:
        flip_started.wait(timeout=1.0)
        # Both writes happen while the reader is inside its read() block,
        # so neither can land between the reader's two SELECTs.
        with db.transaction(immediate=True) as c:
            c.execute(
                "UPDATE settings SET value = '2' WHERE key = 'seam.snap'"
            )

    t = threading.Thread(target=flipper)
    t.start()
    try:
        with db.read() as c:
            flip_started.set()
            # Give the writer thread real time to try to slip in.
            time.sleep(0.05)
            first = c.execute(
                "SELECT value FROM settings WHERE key = 'seam.snap'"
            ).fetchone()["value"]
            second = c.execute(
                "SELECT value FROM settings WHERE key = 'seam.snap'"
            ).fetchone()["value"]
        assert first == second == "1"
    finally:
        t.join(timeout=1.0)

    with db.read() as c:
        final = c.execute(
            "SELECT value FROM settings WHERE key = 'seam.snap'"
        ).fetchone()["value"]
    assert final == "2"
