"""Source graph contract: the propositions of a reading passage and how its author argues.

Sources are not essays, so they do not use essay roles or a single-rooted discourse tree.
Units still tile the text with exact quotes, so nothing is left out and every node is
traceable to its passage and paragraph number (the numbers students cite). Edges run from a
passage (one or more units) to a single unit, so a block of evidence supports its claim as a
whole rather than through its first unit only.

Unit types: `thesis` (the author's overall position; restatements are also thesis), `claim`
(a point the author argues), `fact` (a checkable statement about the world or the system),
`example` (a specific case offered for a point), `concession` (a point the author grants
while holding a claim anyway), `opposing_view` (a view the author reports in order to answer
it), `framing` (questions, headings and asides without propositional content of their own).

Edge types: `supports` (the passage is the author's reason or evidence for a thesis or claim),
`opposes` (the passage answers an opposing view), `concedes` (the passage is granted, and the
target is held despite it), `elaborates` (the passage adds detail that is not a reason).

A source with no thesis is a fact sheet: its units need no edges. In a source with a thesis,
every unit except framing takes part in at least one edge.
"""
from typing import Any

SCHEMA_VERSION = "source_graph/0.1"
UNIT_TYPES = {"thesis", "claim", "fact", "example", "concession", "opposing_view", "framing"}
STANCES = {"endorsed", "conceded", "reported"}
EDGE_TYPES = {"supports", "opposes", "concedes", "elaborates"}
ARGUED = {"thesis", "claim"}
REQUIRED_STANCE = {"concession": "conceded", "opposing_view": "reported"}


def paragraph_of(start, paragraphs):
    """Paragraph number whose [start, end) range contains `start`, or None (e.g. a sub-heading)."""
    return next((int(n) for n, (a, b) in paragraphs.items() if a <= start < b), None)


def validate_source_graph(graph: dict[str, Any], text: str, paragraphs: dict[str, list[int]]) -> list[str]:
    """Return every contract violation (empty list = valid). Never repairs the graph."""
    errors = []
    if graph.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    units = graph.get("units") or []
    by_id, pos = {}, 0
    for u in sorted(units, key=lambda u: u.get("start", -1)):
        uid = u.get("id")
        if not uid or uid in by_id:
            errors.append(f"unit {uid!r}: empty or duplicate id")
            continue
        by_id[uid] = u
        a, b = u.get("start"), u.get("end")
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(text)) or text[a:b] != u.get("text"):
            errors.append(f"unit {uid}: text does not equal source slice")
            continue
        if text[pos:a].strip():
            errors.append(f"text before unit {uid} is not covered: {text[pos:a].strip()[:60]!r}")
        if a < pos:
            errors.append(f"unit {uid} overlaps the previous unit")
        pos = max(pos, b)
        if u.get("paragraph") != paragraph_of(a, paragraphs):
            errors.append(f"unit {uid}: paragraph should be {paragraph_of(a, paragraphs)}")
        if u.get("type") not in UNIT_TYPES:
            errors.append(f"unit {uid}: unknown type {u.get('type')!r}")
        if u.get("stance") not in STANCES:
            errors.append(f"unit {uid}: unknown stance {u.get('stance')!r}")
        need = REQUIRED_STANCE.get(u.get("type"), "endorsed")
        if u.get("stance") != need:
            errors.append(f"unit {uid}: a {u.get('type')} must have stance {need}")
    if text[pos:].strip():
        errors.append(f"text after the last unit is not covered: {text[pos:].strip()[:60]!r}")
    in_edges = {uid: set() for uid in by_id}
    for e in graph.get("edges") or []:
        eid, kind, src, tgt = e.get("id"), e.get("type"), e.get("from") or [], e.get("to")
        if kind not in EDGE_TYPES:
            errors.append(f"edge {eid}: unknown type {kind!r}")
            continue
        missing = [x for x in [*src, tgt] if x not in by_id]
        if not src or missing:
            errors.append(f"edge {eid}: empty passage or unknown units {missing}")
            continue
        if tgt in src:
            errors.append(f"edge {eid}: target is part of its own passage")
        tgt_type, src_types = by_id[tgt]["type"], {by_id[x]["type"] for x in src}
        if kind == "supports":
            if tgt_type not in ARGUED:
                errors.append(f"edge {eid}: supports must point to a thesis or claim, not a {tgt_type}")
            if src_types & {"concession", "opposing_view"}:
                errors.append(f"edge {eid}: a concession or opposing view cannot support the author's claim")
        if kind == "opposes" and tgt_type != "opposing_view":
            errors.append(f"edge {eid}: opposes must point to an opposing_view, not a {tgt_type}")
        if kind == "concedes":
            if "concession" not in src_types:
                errors.append(f"edge {eid}: concedes needs a concession in its passage")
            if tgt_type not in ARGUED:
                errors.append(f"edge {eid}: concedes must point to a thesis or claim, not a {tgt_type}")
        for x in [*src, tgt]:
            in_edges[x].add(kind)
    for uid, u in by_id.items():
        if u["type"] == "concession" and "concedes" not in in_edges[uid]:
            errors.append(f"unit {uid}: concession is not linked by a concedes edge")
        if u["type"] == "opposing_view" and not in_edges[uid]:
            errors.append(f"unit {uid}: opposing view is not answered or linked")
    if any(u["type"] == "thesis" for u in by_id.values()):
        loose = [uid for uid, u in by_id.items() if u["type"] != "framing" and not in_edges[uid]]
        if loose:
            errors.append(f"units in no edge: {loose}")
    return errors


def build_source_graph(record: dict[str, Any], units, edges) -> tuple[dict[str, Any], list[str]]:
    """Locate unit quotes in order and assemble a graph.

    units: (id, exact quote, type, stance) in text order; edges: (type, [from ids], to id, note or None).
    """
    text, paragraphs = record["response_text"], record["metadata"]["paragraphs"]
    out, pos, errors = [], 0, []
    for uid, quote, kind, stance in units:
        a = text.find(quote, pos)
        if a == -1:
            errors.append(f"unit {uid}: not an exact quote after offset {pos}: {quote[:60]!r}")
            continue
        pos = a + len(quote)
        out.append({"id": uid, "start": a, "end": pos, "text": quote, "paragraph": paragraph_of(a, paragraphs),
                    "type": kind, "stance": stance})
    graph = {"schema_version": SCHEMA_VERSION, "example_id": record["example_id"],
             "source": {k: record["metadata"].get(k) for k in ("source_id", "title", "author")},
             "units": out,
             "edges": [dict({"id": f"e{i}", "type": kind, "from": list(src), "to": tgt}, **({"note": note} if note else {}))
                       for i, (kind, src, tgt, note) in enumerate(edges, 1)]}
    return graph, errors + validate_source_graph(graph, text, paragraphs)
