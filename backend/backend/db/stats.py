"""Header-bar dashboard counts.

Single SQL round-trip under one read lock so a parallel writer can't make
the four totals disagree with each other (e.g. a flag could otherwise be
counted against an already-deleted resource).

A "page" is a crawled resource — ``resources.state = 'crawled'`` replaced
the old ``nodes.stub = 0`` filter; "domains" is the distinct host count over
those crawled resources.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .flags import ACTIVE_STATUSES

if TYPE_CHECKING:
    from .core import CrawlDB


def header_counts(db: "CrawlDB") -> dict[str, int]:
    """Return ``{domains, pages, flags, monitors}`` for the header bar."""
    active_flags = ",".join("?" * len(ACTIVE_STATUSES))
    with db.read() as c:
        row = c.execute(
            f"""
            SELECT
              (SELECT COUNT(DISTINCT host) FROM resources
                WHERE state = 'crawled' AND host IS NOT NULL),
              (SELECT COUNT(*)             FROM resources WHERE state = 'crawled'),
              (SELECT COUNT(*)             FROM flags
                WHERE status IN ({active_flags})),
              (SELECT COUNT(*)             FROM monitors WHERE enabled = 1)
            """,
            ACTIVE_STATUSES,
        ).fetchone()
    return {
        "domains": int(row[0] or 0),
        "pages": int(row[1] or 0),
        "flags": int(row[2] or 0),
        "monitors": int(row[3] or 0),
    }


__all__ = ["header_counts"]
