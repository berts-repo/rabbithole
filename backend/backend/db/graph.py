"""Server-side graph payload builder.

PLAN.md:306 — ``Server-side graph computation: PageRank, betweenness
centrality, Louvain clusters, infrastructure clusters (shared header
fingerprints), bridge detection.``

The single entry point is :func:`build_payload`. It reads the active DB
(snapshot of ``resources``/``pages``/``page_versions`` + ``edges`` +
``graph_filters`` + ``response_headers``), builds a ``networkx.DiGraph``,
joins the current page version per resource, computes the metrics the F4 canvas
needs, derives ``infra_cluster_id`` via IDF over response headers, and
returns a JSON-serializable dict in the shape the frontend consumes.

The function is sync + CPU-bound (NetworkX). The route handler wraps it in
``asyncio.to_thread`` so the event loop stays responsive while a 5 000-node
graph is being scored.

Size caps mirror the legacy implementation:
  * betweenness: exact below 1 000; ``k=200`` for 1 000–3 000; ``k=100`` for
    3 000–8 000; **skipped** (returns 0.0 for every node) above 8 000.
  * Louvain: skipped above 5 000 nodes (returns ``cluster_id=None``).
  * Bridge / articulation-point detection: no size cap — cheap.

Server-side filter (PLAN.md:308): one and only one — ``graph_filters.term``,
case-insensitive substring against URL OR title. The match drops the node
and every incident edge before metrics run.

``flag_status`` reflects the highest-priority *active* flag on the node
(``pending``, ``flagged``, or ``investigating`` — :data:`db.flags.ACTIVE_STATUSES`).
Resolved ``done``/``dismissed`` flags do not surface — they leave the node with
``flag_status=None`` so the graph dot disappears.
"""
from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

import networkx as nx

from . import labels as labels_db
from .flags import ACTIVE_STATUSES

if TYPE_CHECKING:
    from .core import CrawlDB


# ---------------------------------------------------------------------------
# Tunables (kept in sync with the legacy reference in
# /home/captain/Documents/onion_rabbithole/server/routes/graph.py).
# ---------------------------------------------------------------------------

_BETWEENNESS_EXACT_MAX = 1_000
_BETWEENNESS_K200_MAX = 3_000
_BETWEENNESS_K100_MAX = 8_000
_LOUVAIN_MAX = 5_000

# IDF threshold: pairs seen on fewer than this many nodes don't cluster.
_INFRA_MIN_DF = 2

# Headers we always strip before IDF — they change per response, leak
# session/cache state, or are operational noise. Names compared case-
# insensitively against the stored ``response_headers.key``.
_EPHEMERAL_HEADERS = frozenset(
    name.lower()
    for name in (
        "Date",
        "Content-Length",
        "Cache-Control",
        "Expires",
        "Age",
        "Set-Cookie",
        "ETag",
        "Last-Modified",
        "Server-Timing",
        "Vary",
        "X-Request-Id",
        "X-Request-ID",
        "Request-Id",
        "CF-Ray",
    )
)

# Headers we collapse patch versions for: ``Apache/2.4.54`` → ``Apache/2.4``.
_VERSION_NORMALIZED_HEADERS = frozenset(("server", "x-powered-by"))
_PATCH_VERSION_RE = re.compile(r"(\d+\.\d+)\.\d+(?=\D|$)")

# A Content-Security-Policy carries a per-request ``'nonce-…'`` token, so the
# raw header value is unique on every page load — left alone it never reaches
# the _INFRA_MIN_DF floor and CSP is silently useless for clustering. We strip
# nonces (a base64-ish blob in single quotes) before comparing.
_CSP_NONCE_RE = re.compile(r"'nonce-[^']*'", re.IGNORECASE)

# Monochromatic node tone. The frontend uses `color` only as the default
# tint when color-mode is "Domain"; F4b color modes (Cluster, Depth,
# Category, Infra) override at render time. A single tone keeps the canvas
# coherent with the dark terminal palette — domain differentiation is
# carried by layout + clustering instead of hue.
_NODE_COLOR = "#2eb89a"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_payload(db: "CrawlDB") -> dict[str, Any]:
    """Build the ``GET /api/graph`` payload from the active DB.

    Sync + CPU-bound; callers should run this off the event loop. Holds
    the DB lock (via ``db.read()``) for the read pass only — the NX compute
    happens in plain Python and doesn't need the DB.
    """
    excluded_terms = _load_filter_terms(db)
    (
        nodes_rows,
        edges_rows,
        header_rows,
        flag_status_by_node,
        alias_by_domain,
        resource_labels,
        domain_labels,
    ) = _load_data(db)

    nodes: dict[int, dict[str, Any]] = {}
    for row in nodes_rows:
        url = row["url"]
        title = row["title"]
        if _matches_any(excluded_terms, url, title):
            continue
        nid = int(row["id"])
        nodes[nid] = _seed_node_dict(
            row,
            flag_status_by_node.get(nid),
            alias_by_domain,
            resource_labels.get(nid, ()),
            domain_labels,
        )

    edges: list[dict[str, Any]] = []
    for row in edges_rows:
        from_id = int(row["from_id"])
        to_id = int(row["to_id"])
        if from_id not in nodes or to_id not in nodes:
            continue
        edges.append({
            "from": from_id,
            "to": to_id,
            "source": row["source"],
            "label": row["label"],
        })

    _populate_metrics(nodes, edges)
    _populate_infra_clusters(nodes, header_rows)

    return {
        "nodes": list(nodes.values()),
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# DB reads
# ---------------------------------------------------------------------------


def _load_filter_terms(db: "CrawlDB") -> list[str]:
    with db.read() as c:
        rows = c.execute("SELECT term FROM graph_filters").fetchall()
    terms: list[str] = []
    for row in rows:
        t = (row["term"] or "").strip().lower()
        if t:
            terms.append(t)
    return terms


def _load_data(db: "CrawlDB"):
    with db.read() as c:
        # One row per resource. Identity/state from ``resources``; durable
        # page state from ``pages``; title/status from the current
        # ``page_versions`` row; ``depth`` is the shallowest depth the URL was
        # discovered at across crawls (denormalized ``nodes.depth`` is gone).
        # Never-crawled resources have NULL page/version columns.
        nodes_rows = c.execute(
            """SELECT r.id AS id, r.url AS url, r.host AS domain,
                      r.network AS network,
                      r.state AS state, r.first_seen AS first_seen,
                      pv.title AS title, pv.http_status AS status_code,
                      p.category AS category,
                      p.analysis_excluded AS analysis_excluded,
                      p.reviewed AS reviewed,
                      cd.depth AS depth
                 FROM resources r
                 LEFT JOIN pages p ON p.resource_id = r.id
                 LEFT JOIN page_versions pv ON pv.id = p.current_version_id
                 LEFT JOIN (
                     SELECT node_id, MIN(depth) AS depth
                       FROM crawl_nodes GROUP BY node_id
                 ) cd ON cd.node_id = r.id"""
        ).fetchall()
        edges_rows = c.execute(
            "SELECT from_id, to_id, source, label, anchor_text FROM edges"
        ).fetchall()
        # Headers are keyed per current page version now — map back to the
        # owning resource id so infra-clustering keys by node (resource).
        header_rows = c.execute(
            """SELECT r.id AS node_id, rh.key AS key, rh.value AS value
                 FROM response_headers rh
                 JOIN page_versions pv ON pv.id = rh.page_version_id
                 JOIN pages p ON p.id = pv.page_id
                 JOIN resources r ON r.id = p.resource_id"""
        ).fetchall()
        # Active flag per node: lowest priority number wins (1=High > 2=Medium
        # > 3=Low); dismissed/done rows never surface.
        _active = ",".join("?" * len(ACTIVE_STATUSES))
        flag_rows = c.execute(
            f"""SELECT node_id, status FROM flags
                WHERE status IN ({_active})
                ORDER BY priority ASC, id DESC""",
            ACTIVE_STATUSES,
        ).fetchall()
        alias_rows = c.execute(
            "SELECT host, alias FROM domains WHERE alias IS NOT NULL"
        ).fetchall()
    flag_status_by_node: dict[int, str] = {}
    for row in flag_rows:
        nid = int(row["node_id"])
        # First row per node wins because ORDER BY already ranks by priority.
        if nid not in flag_status_by_node:
            flag_status_by_node[nid] = row["status"]
    alias_by_domain: dict[str, str] = {r["host"]: r["alias"] for r in alias_rows}
    # Label membership (item 11): direct resource labels and via-domain labels,
    # ids only — the frontend catalog store resolves id → name/color. One bulk
    # query each rather than per-node.
    resource_labels = labels_db.all_resource_label_ids(db)
    domain_labels = labels_db.all_domain_label_ids(db)
    return (
        nodes_rows,
        edges_rows,
        header_rows,
        flag_status_by_node,
        alias_by_domain,
        resource_labels,
        domain_labels,
    )


# ---------------------------------------------------------------------------
# Filter predicate
# ---------------------------------------------------------------------------


def _matches_any(terms: list[str], url: str | None, title: str | None) -> bool:
    if not terms:
        return False
    u = (url or "").lower()
    t = (title or "").lower()
    for term in terms:
        if term in u or term in t:
            return True
    return False


# ---------------------------------------------------------------------------
# Node shape
# ---------------------------------------------------------------------------


def _seed_node_dict(
    row: Any,
    flag_status: str | None,
    alias_by_domain: dict[str, str],
    label_ids: "tuple[int, ...] | list[int]",
    domain_labels: dict[str, list[int]],
) -> dict[str, Any]:
    """Convert a joined resource/page/version row to the payload shape, pre-metrics.

    Metric fields (``pagerank``, ``betweenness``, ``cluster_id``,
    ``infra_cluster_id``, ``is_bridge``, ``in_degree_count``,
    ``out_degree_count``) are filled in by later passes.
    """
    url = row["url"]
    title = row["title"]
    domain = row["domain"]
    alias = alias_by_domain.get(domain) if domain else None
    # Via-domain labels minus any already attached directly to the resource —
    # the "via domain" badge dedupes at query time (source-spec decision); a
    # label both direct and via-domain renders once, as direct.
    direct = list(label_ids)
    direct_set = set(direct)
    via_domain = [
        lid
        for lid in (domain_labels.get(domain, ()) if domain else ())
        if lid not in direct_set
    ]
    return {
        "id": int(row["id"]),
        "label": alias or _short_label(title, url),
        "alias": alias,
        "title_text": title or url,
        "raw_url": url,
        "color": _NODE_COLOR,
        "domain": domain,
        # Network the resource belongs to ('tor' | 'i2p'); drives the
        # client-side `network` colour mode and lets analysts tell the two
        # apart at a glance.
        "network": row["network"],
        "depth": row["depth"],
        "flag_status": flag_status,
        # Default values overwritten in _populate_metrics / _populate_infra_clusters.
        "is_bridge": False,
        "betweenness": 0.0,
        "pagerank": 0.0,
        "cluster_id": None,
        "infra_cluster_id": None,
        "first_seen": row["first_seen"],
        # Synthetic domain-cluster nodes are an F4 render-time concern;
        # real nodes always carry False here.
        "is_cluster": False,
        # Canonical lifecycle state replaces the old `stub` boolean
        # (unknown / known / crawled / dead — see resources.STATES).
        "state": row["state"],
        "analysis_excluded": bool(row["analysis_excluded"]),
        "reviewed": bool(row["reviewed"]),
        # Surfaced for the F4b client-side `Category` colour mode. Stays
        # null for not-yet-crawled resources and any the auto-categoriser
        # hasn't tagged.
        "category": row["category"],
        "in_degree_count": 0,
        "out_degree_count": 0,
        # Label membership (item 11): direct attachments and inherited
        # via-domain ones, ids only — the catalog store resolves name/color.
        "label_ids": direct,
        "domain_label_ids": via_domain,
    }


def _short_label(title: str | None, url: str) -> str:
    """Pick a human-readable short label for the graph node.

    Prefer the page title (truncated). Fall back to the URL path. Cap at
    40 chars so it fits the canvas label without taking over the viewport.
    """
    if title:
        return title if len(title) <= 40 else title[:37] + "..."
    # Fall back to URL — strip scheme for legibility.
    stripped = re.sub(r"^https?://", "", url)
    return stripped if len(stripped) <= 40 else stripped[:37] + "..."


# ---------------------------------------------------------------------------
# Metrics — PageRank, betweenness, Louvain, articulation points
# ---------------------------------------------------------------------------


def _populate_metrics(
    nodes: dict[int, dict[str, Any]], edges: list[dict[str, Any]]
) -> None:
    """Mutate ``nodes`` in place with degree counts + computed metrics.

    Degree counts are computed over the full graph (uncrawled resources
    included) so an unfetched URL still reports the right "how many pages link
    to me". PageRank, betweenness, Louvain, and articulation points run over
    the *crawled* subgraph only — link-directory crawls produce
    uncrawled:crawled ratios of 250:1, and centrality over a placeholder-
    dominated graph spends minutes of Python compute on swamped signal.
    """
    if not nodes:
        return

    g = nx.DiGraph()
    g.add_nodes_from(nodes.keys())
    for e in edges:
        g.add_edge(e["from"], e["to"])

    # in/out degree — full graph, cheap.
    for node_id, in_deg in g.in_degree():
        nodes[node_id]["in_degree_count"] = int(in_deg)
    for node_id, out_deg in g.out_degree():
        nodes[node_id]["out_degree_count"] = int(out_deg)

    crawled_ids = {nid for nid, n in nodes.items() if n.get("state") == "crawled"}
    if not crawled_ids:
        return
    fg = g.subgraph(crawled_ids).copy()

    # PageRank — always compute. NX returns a damping-factor PR. Empty
    # edges still yield a valid result (uniform distribution).
    try:
        pr = nx.pagerank(fg)
    except nx.PowerIterationFailedConvergence:
        pr = {n: 0.0 for n in fg.nodes()}
    for node_id, score in pr.items():
        nodes[node_id]["pagerank"] = float(score)

    # Betweenness — sample to keep large graphs tractable. Mirrors
    # legacy thresholds (server/routes/graph.py).
    n_nodes = fg.number_of_nodes()
    if n_nodes <= _BETWEENNESS_EXACT_MAX:
        bc = nx.betweenness_centrality(fg)
    elif n_nodes <= _BETWEENNESS_K200_MAX:
        bc = nx.betweenness_centrality(fg, k=min(200, n_nodes))
    elif n_nodes <= _BETWEENNESS_K100_MAX:
        bc = nx.betweenness_centrality(fg, k=min(100, n_nodes))
    else:
        bc = {n: 0.0 for n in fg.nodes()}
    for node_id, score in bc.items():
        nodes[node_id]["betweenness"] = float(score)

    # Louvain clusters on the undirected view. Skip for huge graphs.
    undirected = fg.to_undirected()
    if n_nodes <= _LOUVAIN_MAX:
        try:
            communities = nx.algorithms.community.greedy_modularity_communities(
                undirected
            )
        except Exception:  # noqa: BLE001 — fallback to "no clusters"
            communities = ()
        for cluster_idx, members in enumerate(communities):
            for node_id in members:
                nodes[node_id]["cluster_id"] = int(cluster_idx)

    # Articulation points (bridges) — nodes whose removal disconnects a
    # connected component. Cheap; no size cap.
    bridges = set(nx.articulation_points(undirected))
    for node_id in bridges:
        nodes[node_id]["is_bridge"] = True


# ---------------------------------------------------------------------------
# Infrastructure clusters — IDF over shared response-header pairs
# ---------------------------------------------------------------------------


def _normalize_csp(value: str) -> str:
    """Canonicalize a Content-Security-Policy value for clustering.

    Drops per-request ``'nonce-…'`` tokens and sorts directives, so two pages
    serving the same policy compare equal regardless of nonce or directive
    order. Content-based ``'sha256-…'`` source values are left intact — they
    are stable and make good fingerprints.
    """
    directives: list[str] = []
    for raw in value.split(";"):
        # Drop nonce tokens, then collapse internal whitespace.
        tokens = _CSP_NONCE_RE.sub(" ", raw).split()
        if tokens:
            directives.append(" ".join(tokens))
    directives.sort()
    return "; ".join(directives)


def _populate_infra_clusters(
    nodes: dict[int, dict[str, Any]], header_rows: list[Any]
) -> None:
    """Assign ``infra_cluster_id`` based on the rarest shared header pair.

    Two nodes share a cluster when they expose the same non-ephemeral
    ``(header_key, header_value)`` pair. Of every shared pair a node owns,
    we pick the one with the highest IDF score (rarer = more distinctive)
    and use its ``key:value`` as the cluster id string.
    """
    if not nodes or not header_rows:
        return

    # Build per-node pair lists, applying the ephemeral filter + patch-version
    # normalization in a single pass.
    surviving_ids = set(nodes.keys())
    per_node_pairs: dict[int, list[tuple[str, str]]] = {}
    df: dict[tuple[str, str], int] = {}

    for row in header_rows:
        node_id = int(row["node_id"])
        if node_id not in surviving_ids:
            continue
        key = row["key"]
        value = row["value"]
        if key is None or value is None:
            continue
        key_lower = key.lower()
        if key_lower in _EPHEMERAL_HEADERS:
            continue
        normalized_value = value
        if key_lower in _VERSION_NORMALIZED_HEADERS:
            normalized_value = _PATCH_VERSION_RE.sub(r"\1", value)
        elif key_lower == "content-security-policy":
            normalized_value = _normalize_csp(value)
        pair = (key, normalized_value)
        per_node_pairs.setdefault(node_id, []).append(pair)

    # First pass for DF: count each pair once per distinct node.
    for node_id, pairs in per_node_pairs.items():
        for pair in set(pairs):
            df[pair] = df.get(pair, 0) + 1

    n_total = len(nodes)
    # Pre-compute IDF for pairs that meet the minimum DF.
    idf_score: dict[tuple[str, str], float] = {}
    for pair, count in df.items():
        if count < _INFRA_MIN_DF:
            continue
        # Guard against log(0) — n_total >= count always, so log(N/df) >= 0.
        idf_score[pair] = math.log(n_total / count) if count > 0 else 0.0

    for node_id, pairs in per_node_pairs.items():
        best_pair: tuple[str, str] | None = None
        best_score = -1.0
        for pair in set(pairs):
            score = idf_score.get(pair)
            if score is None:
                continue
            if score > best_score:
                best_score = score
                best_pair = pair
        if best_pair is None:
            continue
        nodes[node_id]["infra_cluster_id"] = f"{best_pair[0]}:{best_pair[1]}"


__all__ = ["build_payload"]
