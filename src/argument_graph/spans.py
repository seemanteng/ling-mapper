"""Conservative span reconciliation without modifying source text."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Recovery:
    start: int | None
    end: int | None
    method: str
    reason: str | None = None


def occurrences(text: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    found = []
    start = text.find(needle)
    while start != -1:
        found.append((start, start + len(needle)))
        start = text.find(needle, start + 1)
    return found


def normalise_with_map(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Collapse whitespace runs, preserving original intervals for every character."""
    chars, positions = [], []
    for match in re.finditer(r"\s+|\S", text):
        chars.append(" " if match.group().isspace() else match.group())
        positions.append((match.start(), match.end()))
    return "".join(chars), positions


OFFSET_WINDOW = 10


def recover_span(text: str, annotation: str, raw_start: str, raw_end: str) -> Recovery:
    if not annotation.strip():
        return Recovery(None, None, "unresolved", "empty_or_whitespace_annotation")
    try:
        a, b = int(raw_start), int(raw_end)
    except (ValueError, TypeError):
        a, b = -1, -1
    # A literal match at the supplied location disambiguates repeated text.
    for end, method in ((b, "raw_exact"), (b + 1, "inclusive_exact")):
        if 0 <= a < end <= len(text) and text[a:end] == annotation:
            return Recovery(a, end, method)
    # Boundary whitespace often differs (e.g. newline vs space); prefer the
    # supplied location over a repeat elsewhere when it is unique nearby.
    if a >= 0:
        needle = annotation.strip()
        near = [(s, e) for s, e in occurrences(text, needle)
                if a - OFFSET_WINDOW <= s and e <= b + 1 + OFFSET_WINDOW]
        if len(near) == 1:
            return Recovery(*near[0], "offset_trimmed")
    for needle, method in ((annotation, "unique_exact"), (annotation.strip(), "unique_trimmed")):
        matches = occurrences(text, needle)
        if len(matches) == 1:
            return Recovery(*matches[0], method)
        if len(matches) > 1:
            return Recovery(None, None, "unresolved", "ambiguous_exact_text")
    normalised, positions = normalise_with_map(text)
    target, _ = normalise_with_map(annotation.strip())
    matches = occurrences(normalised, target)
    if len(matches) == 1:
        start, end = matches[0]
        return Recovery(positions[start][0], positions[end - 1][1], "unique_whitespace_normalised")
    return Recovery(None, None, "unresolved", "ambiguous_normalised_text" if matches else "text_not_found")


def candidate_spans(text: str, annotation: str) -> list[tuple[int, int]]:
    """Candidates at the strongest text-matching tier available."""
    if not annotation.strip():
        return []
    for needle in (annotation, annotation.strip()):
        matches = occurrences(text, needle)
        if matches:
            return matches
    normalised, positions = normalise_with_map(text)
    target, _ = normalise_with_map(annotation.strip())
    return [(positions[a][0], positions[b - 1][1]) for a, b in occurrences(normalised, target)]


SEARCH_METHODS = ('unique_exact', 'unique_trimmed', 'unique_whitespace_normalised')


def order_outliers(starts: list[int | None]) -> set[int]:
    """Indices in no longest strictly increasing subsequence of recovered starts.

    Such a span contradicts annotation order under every maximal consistent
    reading; spans in some but not all maximal readings (e.g. swaps) are kept.
    """
    idx = [i for i, s in enumerate(starts) if s is not None]
    ending = [1] * len(idx)
    for k in range(len(idx)):
        for j in range(k):
            if starts[idx[j]] < starts[idx[k]]:
                ending[k] = max(ending[k], ending[j] + 1)
    beginning = [1] * len(idx)
    for k in reversed(range(len(idx))):
        for j in range(k + 1, len(idx)):
            if starts[idx[k]] < starts[idx[j]]:
                beginning[k] = max(beginning[k], beginning[j] + 1)
    best = max(ending, default=0)
    return {idx[k] for k in range(len(idx)) if ending[k] + beginning[k] - 1 < best}


def recover_sequence(text: str, rows: list[dict], *, min_margin: int = 20,
                     distance_ratio: float = 2.0, max_distance: int = 100):
    """Resolve ambiguity against frozen, independently recovered neighbours.

    Input order is source CSV annotation order, not a sort by recovered position.
    Searched (not offset-confirmed) matches that contradict annotation order are
    rejected first. New decisions never become anchors in the same pass.
    """
    initial = [recover_span(text, r['discourse_text'], r['discourse_start'], r['discourse_end']) for r in rows]
    evidence = [{} for _ in rows]
    for i in order_outliers([r.start for r in initial]):
        if initial[i].method in SEARCH_METHODS:
            evidence[i] = {'decision': 'order_conflict', 'rejected': [initial[i].start, initial[i].end, initial[i].method]}
            initial[i] = Recovery(None, None, 'unresolved', 'sequence_conflict')
    results = list(initial)
    for i, (row, recovery) in enumerate(zip(rows, initial)):
        if recovery.reason not in ('ambiguous_exact_text', 'ambiguous_normalised_text'):
            continue
        candidates = candidate_spans(text, row['discourse_text'])
        previous = next((j for j in range(i - 1, -1, -1) if initial[j].start is not None), None)
        following = next((j for j in range(i + 1, len(rows)) if initial[j].start is not None), None)
        lower = initial[previous].end if previous is not None else 0
        upper = initial[following].start if following is not None else len(text)
        feasible = [(a, b) for a, b in candidates if lower <= a < b <= upper]
        evidence[i] = {'candidates': candidates, 'sequence_bounds': [lower, upper],
                       'anchor_indices': [previous, following], 'feasible_candidates': feasible}
        has_anchor = previous is not None or following is not None
        if has_anchor and len(feasible) == 1:
            results[i] = Recovery(*feasible[0], 'sequence_unique')
            continue
        if not feasible:
            evidence[i]['decision'] = 'sequence_conflict'
            continue
        try:
            supplied = int(row['discourse_start'])
        except (ValueError, TypeError):
            continue
        if not 0 <= supplied < len(text):
            continue
        ranked = sorted((abs(a - supplied), a, b) for a, b in feasible)
        if len(ranked) < 2:
            continue
        first, second = ranked[:2]
        evidence[i]['nearest_distances'] = [first[0], second[0]]
        if (first[0] <= max_distance and second[0] - first[0] >= min_margin
                and second[0] >= distance_ratio * max(first[0], 1)):
            results[i] = Recovery(first[1], first[2], 'nearest_clear')
    return results, evidence


def displacement(recovery: Recovery, row: dict) -> dict | None:
    if recovery.start is None:
        return None
    try:
        start, end = int(row['discourse_start']), int(row['discourse_end'])
    except (ValueError, TypeError):
        return None
    ds, de = recovery.start - start, recovery.end - end
    return {'start_delta': ds, 'end_delta': de, 'absolute_start_delta': abs(ds),
            'max_absolute_delta': max(abs(ds), abs(de)),
            'end_delta_note': 'Recovered end-exclusive minus raw end; raw convention may differ.'}
