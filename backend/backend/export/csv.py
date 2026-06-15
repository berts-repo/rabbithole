"""Nodes CSV serializer with formula-injection defence.

PLAN.md:310 — ``any value starting with = + - @ \\t \\r prefixed with '`` to
neutralize spreadsheet formula injection. The single-quote prefix is the
standard Excel/Sheets opt-out: the cell is rendered as the literal text
(quote omitted) while no formula evaluation happens on open.
"""
from __future__ import annotations

import csv
import io
from typing import Any


_HEADER: tuple[str, ...] = (
    "id",
    "url",
    "domain",
    "depth",
    "status_code",
    "category",
    "stub",
    "analysis_excluded",
    "pagerank",
    "betweenness",
    "in_degree",
    "out_degree",
    "cluster_id",
    "infra_cluster_id",
    "first_seen",
    "title",
)

# Excel/LibreOffice/Sheets treat these leading bytes as the start of a
# formula or an Excel command. Include tab + CR — they're equivalent to
# field separators in some import paths.
_FORMULA_PREFIXES: tuple[str, ...] = ("=", "+", "-", "@", "\t", "\r")


def payload_to_nodes_csv(payload: dict[str, Any]) -> str:
    """Render the payload's node list as a CSV string.

    Caller is responsible for encoding to bytes if returning over HTTP.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(_HEADER)
    for node in payload.get("nodes", []):
        row = (
            node.get("id"),
            node.get("raw_url"),
            node.get("domain"),
            node.get("depth"),
            node.get("status_code"),
            node.get("category"),
            node.get("stub"),
            node.get("analysis_excluded"),
            node.get("pagerank"),
            node.get("betweenness"),
            node.get("in_degree_count"),
            node.get("out_degree_count"),
            node.get("cluster_id"),
            node.get("infra_cluster_id"),
            node.get("first_seen"),
            node.get("title_text"),
        )
        writer.writerow(_safe(v) for v in row)
    return buf.getvalue()


def _safe(value: Any) -> str:
    """Stringify ``value`` and prepend ``'`` if a leading byte triggers
    formula evaluation in common spreadsheet apps."""
    if value is None:
        return ""
    if isinstance(value, bool):
        s = "true" if value else "false"
    elif isinstance(value, float):
        s = f"{value:.6g}"
    else:
        s = str(value)
    if s and s[0] in _FORMULA_PREFIXES:
        return "'" + s
    return s


__all__ = ["payload_to_nodes_csv"]
