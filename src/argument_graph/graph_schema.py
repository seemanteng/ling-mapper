"""Student/reference argument graph contract: eRST-style units and relations.

Nodes are proposition units that tile the text; edges are directed relations from
a fixed eRST (GUM) inventory. Primary edges form a single-rooted dependency tree;
secondary edges must be licensed by a quoted signal. See plan section 4.

Direction convention: `source` is the satellite (dependent) and `target` its
nucleus (head). A multinuclear relation is a chain from each later member to the
first member (head-ordered dependency conversion of RST). A unit interrupted by
another is split into parts joined by `same-unit` (later part -> first part);
relations of the whole attach to the first part.
"""
from typing import Any

SCHEMA_VERSION = "argument_graph/0.1"

# GUM relation names; definitions quoted/adapted from Zeldes et al. (2025), Table A.12.
# R = reader, W = writer, N = nucleus (target), S = satellite (source).
RELATIONS = {
    "explanation-evidence": ("satellite", "S provides evidence which increases R's belief in N"),
    "explanation-justify": ("satellite", "S increases R's acceptance of W's right to say N"),
    "adversative-concession": ("satellite", "R is meant to look past an incompatibility of N with S"),
    "adversative-antithesis": ("satellite", "R is meant to prefer N as an alternative to S"),
    "adversative-contrast": ("multinuclear", "W presents multiple Ns as incompatible, but of equal prominence"),
    "causal-cause": ("satellite", "S is the cause of N, and N is more prominent"),
    "causal-result": ("satellite", "S is the result of N, and N is more prominent"),
    "contingency-condition": ("satellite", "N occurs depending on S"),
    "elaboration-additional": ("satellite", "S elaborates on N as a whole (default when no other relation applies)"),
    "restatement-partial": ("satellite", "S partly realizes the same role and content as a previous N"),
    "restatement-repetition": ("multinuclear", "Multiple Ns realize the same role and content"),
    "attribution-positive": ("satellite", "S states a source for the information in N"),
    "evaluation-comment": ("satellite", "S provides an assessment of N by W"),
    "context-background": ("satellite", "S provides information to increase R's understanding of N"),
    "organization-preparation": ("satellite", "S is primarily used to signal an upcoming N (e.g. a heading or announcement)"),
    "mode-means": ("satellite", "S indicates the means by which N happens"),
    "topic-solutionhood": ("satellite", "N is a solution to a problem presented by S"),
    "topic-question": ("satellite", "N is the answer to the question posed by S"),
    "organization-phatic": ("satellite", "W holds the floor, without contributing propositional content"),
    "joint-list": ("multinuclear", "W presents multiple Ns in parallel, additive to one another"),
    "joint-other": ("multinuclear", "Any other collection of unlike units of equal prominence"),
    # Not a discourse relation: joins the parts of one unit that another unit interrupts.
    "same-unit": ("multinuclear", "The parts form one discontinuous unit interrupted by another unit"),
}
SIGNAL_TYPES = {"dm", "orphan", "graphical", "lexical", "morphological", "numerical",
                "reference", "semantic", "syntactic"}
ROLES = {"lead", "position", "claim", "counterclaim", "rebuttal", "evidence",
         "concluding_summary", "unannotated"}
# Does the writer put this unit forward as their own view?
STANCES = {"endorsed", "conceded", "rejected", "reported", "unclear"}
POLARITIES = {"positive", "negative"}
SUPPORT = {"explanation-evidence", "explanation-justify"}
SOLUTION = {"topic-solutionhood"}
ADVERSATIVE = {"adversative-concession", "adversative-antithesis", "adversative-contrast"}
NOT_OWN = {"conceded", "rejected"}


def _span_errors(obj, text, where):
    start, end, quote = obj.get("start"), obj.get("end"), obj.get("text")
    if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)):
        return [f"{where}: invalid offsets {start}-{end}"]
    if text[start:end] != quote:
        return [f"{where}: text does not equal source slice [{start}:{end}]"]
    return []


def validate_graph(graph: dict[str, Any], text: str) -> list[str]:
    """Return every contract violation (empty list = valid). Never repairs the graph."""
    errors = []
    if graph.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    units = graph.get("units") or []
    by_id = {}
    for u in units:
        uid = u.get("id")
        if not uid or uid in by_id:
            errors.append(f"unit {uid!r}: empty or duplicate id")
            continue
        by_id[uid] = u
        errors += _span_errors(u, text, f"unit {uid}")
        if u.get("role") not in ROLES:
            errors.append(f"unit {uid}: role {u.get('role')!r} not in {sorted(ROLES)}")
        if u.get("stance") not in STANCES:
            errors.append(f"unit {uid}: stance {u.get('stance')!r} not in {sorted(STANCES)}")
        if u.get("polarity") not in POLARITIES:
            errors.append(f"unit {uid}: polarity {u.get('polarity')!r} not in {sorted(POLARITIES)}")
    if not units:
        return errors + ["graph has no units"]

    # Tiling: units do not overlap, and every non-whitespace character is covered.
    ordered = sorted((u for u in by_id.values() if isinstance(u.get("start"), int) and isinstance(u.get("end"), int)),
                     key=lambda u: u["start"])
    covered = 0
    for u in ordered:
        if u["start"] < covered:
            errors.append(f"unit {u['id']}: overlaps a preceding unit")
        elif text[covered:u["start"]].strip():
            errors.append(f"text [{covered}:{u['start']}] is not covered by any unit")
        covered = max(covered, u["end"])
    if text[covered:].strip():
        errors.append(f"text [{covered}:{len(text)}] is not covered by any unit")

    relations = graph.get("relations") or []
    heads, primary_pairs, secondary_pairs, rel_ids = {}, set(), set(), set()
    for r in relations:
        rid, s, t, label, tier = r.get("id"), r.get("source"), r.get("target"), r.get("label"), r.get("tier")
        where = f"relation {rid}"
        if not rid or rid in rel_ids:
            errors.append(f"{where}: empty or duplicate id")
        rel_ids.add(rid)
        if s not in by_id or t not in by_id or s == t:
            errors.append(f"{where}: endpoints must be two distinct unit ids")
            continue
        if label not in RELATIONS:
            errors.append(f"{where}: label {label!r} not in inventory")
        if tier not in ("primary", "secondary"):
            errors.append(f"{where}: tier must be primary or secondary")
        if label in RELATIONS and RELATIONS[label][0] == "multinuclear" and by_id[s]["start"] < by_id[t]["start"]:
            errors.append(f"{where}: multinuclear chain must run from later member to first member")
        if label == "same-unit":
            lo, hi = sorted((by_id[s], by_id[t]), key=lambda u: u["start"])
            if not any(lo["end"] <= u["start"] and u["end"] <= hi["start"] for u in by_id.values()):
                errors.append(f"{where}: same-unit parts must be separated by an interrupting unit")
            if tier != "primary":
                errors.append(f"{where}: same-unit must be a primary edge")
        signals = r.get("signals") or []
        for i, sig in enumerate(signals):
            if sig.get("type") not in SIGNAL_TYPES:
                errors.append(f"{where}: signal {i} type {sig.get('type')!r} not in {sorted(SIGNAL_TYPES)}")
            errors += _span_errors(sig, text, f"{where} signal {i}")
        if not signals and r.get("implicit") is not True:
            errors.append(f"{where}: needs a quoted signal or implicit=true")
        if tier == "primary":
            if s in heads:
                errors.append(f"unit {s}: more than one primary head")
            heads[s] = t
            primary_pairs.add((s, t))
        elif tier == "secondary":
            if not signals:
                errors.append(f"{where}: secondary edges must be licensed by a quoted signal")
            if (s, t) in secondary_pairs:
                errors.append(f"{where}: duplicate secondary edge in this direction")
            secondary_pairs.add((s, t))
    # Stance must agree with the adversative structure, so neither is chosen freely.
    required = {"adversative-concession": "conceded", "adversative-antithesis": "rejected"}
    anchored = set()
    for r in relations:
        if r.get("label") in ADVERSATIVE and r.get("source") in by_id and r.get("target") in by_id:
            anchored |= {r["source"], r["target"]}
            want = required.get(r["label"])
            if want and by_id[r["source"]].get("stance") != want:
                errors.append(f"relation {r.get('id')}: {r['label']} satellite must have stance {want!r}")
    for uid, u in by_id.items():
        if u.get("stance") in NOT_OWN and uid not in anchored:
            errors.append(f"unit {uid}: stance {u['stance']!r} needs an adversative relation")
    for s, t in secondary_pairs & primary_pairs:
        errors.append(f"secondary edge {s}->{t} duplicates a primary edge")

    # Primary structure: exactly one root, every other unit has one head, no cycles.
    roots = [uid for uid in by_id if uid not in heads]
    if graph.get("root") not in by_id:
        errors.append("root must name a unit")
    if roots != [graph.get("root")]:
        errors.append(f"primary tree must have exactly the declared root; units without a head: {roots}")
    for start in by_id:
        seen, node = set(), start
        while node in heads:
            if node in seen:
                errors.append(f"primary cycle through unit {start}")
                break
            seen.add(node)
            node = heads[node]
    return sorted(set(errors), key=errors.index)


def argument_edges(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive support/attack from relation class plus writer stance (no separate label).

    Support: an evidence/justify satellite the writer endorses supports its nucleus, and an
    endorsed problem (topic-solutionhood satellite) supports the solution it motivates.
    Attack: in an adversative relation, the endorsed unit attacks the one the writer
    concedes or rejects (a quoted counterargument is attacked, not asserted).
    """
    units = {u["id"]: u for u in graph.get("units") or []}
    derived = []
    for r in graph.get("relations") or []:
        s, t = units.get(r.get("source")), units.get(r.get("target"))
        if not s or not t:
            continue
        if r["label"] in SUPPORT | SOLUTION and s["stance"] not in NOT_OWN:
            derived.append({"type": "support", "source": s["id"], "target": t["id"], "relation": r["id"],
                            "basis": "problem-solution" if r["label"] in SOLUTION else "reason"})
        elif r["label"] in ADVERSATIVE:
            for attacker, target in ((t, s), (s, t)):
                if target["stance"] in NOT_OWN and attacker["stance"] not in NOT_OWN:
                    derived.append({"type": "attack", "source": attacker["id"], "target": target["id"],
                                    "relation": r["id"], "basis": "adversative"})
    return derived
