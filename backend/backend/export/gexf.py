"""GEXF 1.3 serializer for the graph payload.

PLAN.md:309 — ``xml.etree.ElementTree`` only; all node/edge attribute values
are escaped by the library, never by string templating. That eliminates the
class of injection bugs where an analyst-controlled URL or title contains
``"`` or ``<``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any


_GEXF_NS = "http://gexf.net/1.3"
_VIZ_NS = "http://gexf.net/1.3/viz"


# Node attribute declaration. Index → (id, type) lets us round-trip the
# fields the F4 canvas plus most graph-analysis tools (Gephi, Cytoscape)
# care about. Values for missing/None fields are simply omitted, which
# Gephi treats as the attribute's default.
_NODE_ATTRS: tuple[tuple[str, str, str], ...] = (
    # (gexf_id, label, type)
    ("0", "url", "string"),
    ("1", "domain", "string"),
    ("2", "depth", "integer"),
    ("3", "status_code", "integer"),
    ("4", "stub", "boolean"),
    ("5", "analysis_excluded", "boolean"),
    ("6", "pagerank", "double"),
    ("7", "betweenness", "double"),
    ("8", "in_degree", "integer"),
    ("9", "out_degree", "integer"),
    ("10", "cluster_id", "integer"),
    ("11", "infra_cluster_id", "string"),
    ("12", "first_seen", "string"),
    ("13", "is_bridge", "boolean"),
)

# Map our payload key → GEXF attribute id. ``in_degree_count`` /
# ``out_degree_count`` flatten to ``in_degree`` / ``out_degree`` for cleanliness.
_NODE_FIELD_MAP: dict[str, str] = {
    "raw_url": "0",
    "domain": "1",
    "depth": "2",
    "status_code": "3",
    "stub": "4",
    "analysis_excluded": "5",
    "pagerank": "6",
    "betweenness": "7",
    "in_degree_count": "8",
    "out_degree_count": "9",
    "cluster_id": "10",
    "infra_cluster_id": "11",
    "first_seen": "12",
    "is_bridge": "13",
}

_EDGE_ATTRS: tuple[tuple[str, str, str], ...] = (
    ("0", "source", "string"),
    ("1", "label", "string"),
)


def payload_to_gexf(payload: dict[str, Any]) -> bytes:
    """Serialize the graph payload to a GEXF 1.3 byte string.

    The output is UTF-8 with an XML declaration, ready to drop straight
    into a Response body. ``ET.tostring`` handles all character escaping;
    callers must not splice strings into the result.
    """
    root = ET.Element("gexf", {"xmlns": _GEXF_NS, "version": "1.3"})
    graph = ET.SubElement(
        root,
        "graph",
        {"defaultedgetype": "directed", "mode": "static"},
    )

    # Attribute declarations.
    node_attrs = ET.SubElement(graph, "attributes", {"class": "node"})
    for attr_id, title, attr_type in _NODE_ATTRS:
        ET.SubElement(
            node_attrs,
            "attribute",
            {"id": attr_id, "title": title, "type": attr_type},
        )
    edge_attrs = ET.SubElement(graph, "attributes", {"class": "edge"})
    for attr_id, title, attr_type in _EDGE_ATTRS:
        ET.SubElement(
            edge_attrs,
            "attribute",
            {"id": attr_id, "title": title, "type": attr_type},
        )

    # Nodes.
    nodes_el = ET.SubElement(graph, "nodes")
    for node in payload.get("nodes", []):
        n_el = ET.SubElement(
            nodes_el,
            "node",
            {"id": str(node["id"]), "label": node.get("label") or node["raw_url"]},
        )
        atts_el = ET.SubElement(n_el, "attvalues")
        for field_key, gexf_id in _NODE_FIELD_MAP.items():
            value = node.get(field_key)
            if value is None:
                continue
            ET.SubElement(
                atts_el,
                "attvalue",
                {"for": gexf_id, "value": _format_value(value)},
            )
        color = node.get("color")
        if color:
            r, g, b = _hex_to_rgb(color)
            ET.SubElement(
                n_el,
                f"{{{_VIZ_NS}}}color",
                {"r": str(r), "g": str(g), "b": str(b)},
            )

    # Edges.
    edges_el = ET.SubElement(graph, "edges")
    for idx, edge in enumerate(payload.get("edges", [])):
        e_el = ET.SubElement(
            edges_el,
            "edge",
            {
                "id": str(idx),
                "source": str(edge["from"]),
                "target": str(edge["to"]),
            },
        )
        atts_el = ET.SubElement(e_el, "attvalues")
        for payload_key, gexf_id in (("source", "0"), ("label", "1")):
            value = edge.get(payload_key)
            if value is None:
                continue
            ET.SubElement(
                atts_el,
                "attvalue",
                {"for": gexf_id, "value": _format_value(value)},
            )

    # Register the viz namespace so the serializer emits prefix `viz:` on
    # `<viz:color>` (rather than an inline xmlns declaration on every node).
    ET.register_namespace("viz", _VIZ_NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _format_value(value: Any) -> str:
    """Stringify a payload value for GEXF attribute serialization."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        # Compact, fixed-precision representation; avoids "1e-05" creeping
        # into Gephi imports that some plugins choke on.
        return f"{value:.6g}"
    return str(value)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (0, 0, 0)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (0, 0, 0)


__all__ = ["payload_to_gexf"]
