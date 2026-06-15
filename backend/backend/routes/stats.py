"""``GET /api/stats`` — counts for the header stats bar.

Returns four scalars (domains, pages, flags, monitors). The SQL lives in
``db/stats.py``; it runs as one round-trip under the read lock so a
parallel writer can't make the four totals disagree with each other.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import stats as stats_db
from ..db.core import CrawlDB
from .deps import get_active_db

router = APIRouter()


@router.get("/api/stats")
def stats(db: CrawlDB = Depends(get_active_db)) -> dict[str, int]:
    return stats_db.header_counts(db)


__all__ = ["router"]
