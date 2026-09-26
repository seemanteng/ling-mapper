"""Export records' gold spans and hierarchy candidate links as a Gephi GEXF graph.

Nodes are discourse spans; edges run child -> candidate parent. Edge semantics
are unverified: `child_role` is exported for colouring, not as a relation type.
"""
import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path

GEXF = "http://gexf.net/1.3"
VIZ = "http://gexf.net/1.3/viz"
# Okabe-Ito palette (colour-blind safe).
COLOURS = {
    "lead": (153, 153, 153), "position": (0, 114, 178), "claim": (86, 180, 233),
    "counterclaim": (213, 94, 0), "rebuttal": (204, 121, 167), "evidence": (0, 158, 115),
    "concluding_summary": (230, 159, 0), "unannotated": (220, 220, 220),
}
SIZES = {"position": 14, "claim": 11, "counterclaim": 11, "rebuttal": 11}
SLOT, LEVEL, ESSAY_GAP = 260.0, 160.0, 520.0
LABEL_CHARS = 45


def tree_positions(spans, parent_of):
    """Tidy layered layout: roots on top in essay order, children below their parent.

    Leaves take consecutive slots; a parent is centred over its children.
    Returns {annotation_id: (x, y)} and the layout width.
    """
    children = {aid: [] for aid in spans}
    for child, parent in parent_of.items():
        children[parent].append(child)
    for kids in children.values():
        kids.sort(key=lambda aid: spans[aid]["start"])
    positions, next_slot = {}, [0]

    def place(aid, depth, seen):
        seen = seen | {aid}
        kids = [k for k in children[aid] if k not in seen and k not in positions]
        for kid in kids:
            place(kid, depth + 1, seen)
        placed = [positions[k][0] for k in kids if k in positions]
        if placed:
            x = sum(placed) / len(placed)
        else:
            x = next_slot[0] * SLOT
            next_slot[0] += 1
        positions[aid] = (x, -depth * LEVEL)

    roots = [aid for aid in spans if aid not in parent_of]
    for aid in sorted(roots, key=lambda aid: spans[aid]["start"]) + sorted(spans, key=lambda a: spans[a]["start"]):
        if aid not in positions:  # second pass catches cycles with no root
            place(aid, 0, set())
    return positions, max(next_slot[0] - 1, 0) * SLOT


NODE_ATTRS = [("role", "string"), ("essay", "string"), ("text", "string"),
              ("start", "integer"), ("order", "integer"), ("holistic_score", "string")]
EDGE_ATTRS = [("child_role", "string"), ("parent_role", "string"), ("status", "string")]


def attributes(parent, cls, attrs):
    block = ET.SubElement(parent, "attributes", {"class": cls})
    for i, (name, kind) in enumerate(attrs):
        ET.SubElement(block, "attribute", {"id": str(i), "title": name, "type": kind})


def values(parent, attrs, data):
    block = ET.SubElement(parent, "attvalues")
    for i, (name, _) in enumerate(attrs):
        ET.SubElement(block, "attvalue", {"for": str(i), "value": str(data[name])})


def build(records, include_unannotated=False):
    ET.register_namespace("", GEXF)
    ET.register_namespace("viz", VIZ)
    root = ET.Element(f"{{{GEXF}}}gexf", {"version": "1.3"})
    graph = ET.SubElement(root, "graph", {"defaultedgetype": "directed"})
    attributes(graph, "node", NODE_ATTRS)
    attributes(graph, "edge", EDGE_ATTRS)
    nodes, edges = ET.SubElement(graph, "nodes"), ET.SubElement(graph, "edges")
    n_nodes = n_edges = 0
    offset = 0.0
    for rec in records:
        spans = {g["annotation_id"]: g for g in rec["gold_spans"] or []
                 if include_unannotated or g["role"] != "unannotated"}
        parent_of = {}
        for link in rec["metadata"].get("hierarchy_candidates", []):
            child, parents = link["annotation_id"], link["candidate_parent_ids"]
            if link["status"] == "unique_candidate" and child in spans and parents[0] in spans:
                parent_of[child] = parents[0]
        positions, width = tree_positions(spans, parent_of)
        for order, g in enumerate(sorted(spans.values(), key=lambda g: g["start"])):
            text = " ".join(g["text"].split())
            label = f"{g['role'].replace('_', ' ').upper()}: {text[:LABEL_CHARS]}" + ("…" if len(text) > LABEL_CHARS else "")
            node = ET.SubElement(nodes, "node", {"id": g["annotation_id"], "label": label})
            values(node, NODE_ATTRS, {"role": g["role"], "essay": rec["example_id"], "text": g["text"],
                                      "start": g["start"], "order": order,
                                      "holistic_score": rec["metadata"].get("holistic_score") or ""})
            r, gr, b = COLOURS.get(g["role"], (0, 0, 0))
            ET.SubElement(node, f"{{{VIZ}}}color", {"r": str(r), "g": str(gr), "b": str(b)})
            x, y = positions[g["annotation_id"]]
            ET.SubElement(node, f"{{{VIZ}}}position", {"x": f"{x + offset:.1f}", "y": f"{y:.1f}", "z": "0.0"})
            ET.SubElement(node, f"{{{VIZ}}}size", {"value": str(SIZES.get(g["role"], 9))})
            n_nodes += 1
        for child, parent in parent_of.items():
            edge = ET.SubElement(edges, "edge", {"id": f"e{n_edges}", "source": child, "target": parent})
            values(edge, EDGE_ATTRS, {"child_role": spans[child]["role"],
                                      "parent_role": spans[parent]["role"],
                                      "status": "unverified_candidate"})
            n_edges += 1
        offset += width + ESSAY_GAP
    ET.indent(root)
    return ET.ElementTree(root), n_nodes, n_edges


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="records.jsonl or pilot.jsonl")
    parser.add_argument("--output", type=Path, required=True, help="Output .gexf file")
    parser.add_argument("--essay", action="append", help="Example ID to include (repeatable); default all")
    parser.add_argument("--include-unannotated", action="store_true")
    args = parser.parse_args()
    with args.records.open() as handle:
        records = [json.loads(line) for line in handle]
    if args.essay:
        records = [r for r in records if r["example_id"] in set(args.essay)]
        if not records:
            parser.error("No matching essays")
    tree, n_nodes, n_edges = build(records, args.include_unannotated)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(args.output, encoding="utf-8", xml_declaration=True)
    print(json.dumps({"essays": len(records), "nodes": n_nodes, "edges": n_edges, "output": str(args.output)}))


if __name__ == "__main__":
    main()
