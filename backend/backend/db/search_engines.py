"""Search-engine registry queries.

PLAN.md:346. The ``search_engines`` table is just a label + URL template
(``{q}`` placeholder gets ``urllib.parse.quote_plus``-substituted by
``routes/harvest_search.py``). Per-engine enabled state lives in the
``settings`` table under the templated key
``search.engine.{id}.enabled`` — see ``db/settings.py::SEARCH_ENGINE_ENABLED_RE``.

``seed_defaults`` is called once per project create to give the analyst a
working Search tab from the first launch (decision locked with the user
2026-05-15). Idempotent — re-runs are no-ops via ``INSERT OR IGNORE``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .core import CrawlDB


# v3 onion search engines seeded into a fresh project, live-verified to return
# onion results through Tor. Each URL embeds the ``{q}`` placeholder the
# harvest-search route substitutes. Kept deliberately small — the analyst adds
# the engines they want under Settings → Engines.
#
# Ahmia gates results behind a per-page hidden form token: a bare query GET
# 302-bounces to its homepage, so the route primes the form (see
# ``routes/harvest_search.py::_fetch_engine_links``). OnionLand answers a plain
# GET directly.
DEFAULT_ENGINES: tuple[tuple[str, str], ...] = (
    (
        "Ahmia",
        "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={q}",
    ),
    (
        "OnionLand",
        "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={q}",
    ),
)


def list_engines(db: "CrawlDB") -> list[dict[str, Any]]:
    with db.read() as c:
        rows = c.execute(
            "SELECT id, label, url, network FROM search_engines ORDER BY id ASC"
        ).fetchall()
    return [
        {
            "id": int(r["id"]),
            "label": r["label"],
            "url": r["url"],
            "network": r["network"],
        }
        for r in rows
    ]


def get_engine(db: "CrawlDB", engine_id: int) -> dict[str, Any] | None:
    with db.read() as c:
        row = c.execute(
            "SELECT id, label, url, network FROM search_engines WHERE id = ?",
            (engine_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": int(row["id"]),
        "label": row["label"],
        "url": row["url"],
        "network": row["network"],
    }


def create_engine(
    db: "CrawlDB", *, label: str, url: str, network: str = "tor"
) -> int:
    """Insert a new engine. Returns the new id. Caller validates the URL shape
    and supplies the network it belongs to (derived from the URL)."""
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "INSERT INTO search_engines(label, url, network) VALUES (?, ?, ?)",
            (label, url, network),
        )
        return int(cur.lastrowid)


def update_engine(
    db: "CrawlDB", engine_id: int, *, label: str, url: str, network: str = "tor"
) -> bool:
    """Update an engine's label + url + network. Returns ``True`` if a row matched.

    Caller validates the URL shape (same ``validate_network_url`` gate as create)
    and passes the derived network. The per-engine
    ``search.engine.{id}.enabled`` setting is keyed by id, which does not change,
    so an edit leaves the enabled state untouched.
    """
    with db.transaction(immediate=True) as c:
        cur = c.execute(
            "UPDATE search_engines SET label = ?, url = ?, network = ? WHERE id = ?",
            (label, url, network, engine_id),
        )
        return cur.rowcount > 0


def delete_engine(db: "CrawlDB", engine_id: int) -> bool:
    with db.transaction(immediate=True) as c:
        c.execute(
            "DELETE FROM settings WHERE key = ?",
            (f"search.engine.{engine_id}.enabled",),
        )
        cur = c.execute(
            "DELETE FROM search_engines WHERE id = ?", (engine_id,)
        )
        return cur.rowcount > 0


def seed_defaults(db: "CrawlDB") -> int:
    """Insert ``DEFAULT_ENGINES`` if absent. Returns the count newly inserted.

    Idempotent: ``INSERT OR IGNORE`` on the unique ``url`` column means
    re-running on an already-seeded project is a no-op. After insert, each
    new engine gets ``search.engine.{id}.enabled = "true"`` written as a
    setting so the Search tab pre-selects it.
    """
    inserted_ids: list[int] = []
    with db.transaction(immediate=True) as c:
        for label, url in DEFAULT_ENGINES:
            cur = c.execute(
                "INSERT OR IGNORE INTO search_engines(label, url) VALUES (?, ?)",
                (label, url),
            )
            if cur.rowcount > 0:
                inserted_ids.append(int(cur.lastrowid))
        for new_id in inserted_ids:
            c.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                (f"search.engine.{new_id}.enabled", "true"),
            )
    return len(inserted_ids)


__all__ = [
    "DEFAULT_ENGINES",
    "create_engine",
    "delete_engine",
    "get_engine",
    "list_engines",
    "seed_defaults",
    "update_engine",
]
