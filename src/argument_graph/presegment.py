"""Rule-based clause pre-segmentation and annotation sheets.

Splits each essay into sentences, then into clauses at punctuation and clause
markers, with no language model involved, so the starting segmentation favours
none of the extractors being compared. The annotator merges or splits segments
where the rules got it wrong. Segments are exact slices of the unchanged essay
and together cover all of its non-whitespace text.
"""
import argparse
import csv
import json
import re
from pathlib import Path

from .schemas import ExampleRecord

SHEET_COLUMNS = ["essay_no", "example_id", "segment_no", "unit_id", "segment_text",
                 "What is the segment doing?", "Is this the writer's stance?",
                 "Segment it relates to", "How it relates", "Notes"]

# Never sentence-final; "etc." often is, so it is not listed.
ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "st", "vs", "e.g", "i.e", "u.s", "a.m", "p.m"}
# Subordinators and contrastive connectives that open a new clause wherever they occur.
CLAUSE_MARKERS = ("because", "but", "although", "though", "even though", "whereas", "unless",
                  "so that", "however", "therefore", "while", "cuz", "cause")
# Connectives and relatives that open a new clause only after a comma.
COMMA_MARKERS = ("so", "yet", "which", "who", "since", "while", "when", "if", "then", "plus", "also")
# "and"/"or" after a comma usually continue a list, so they split only before a likely subject.
COORDINATORS = ("and", "or")
SUBJECTS = ("i", "you", "he", "she", "it", "we", "they", "this", "that", "these", "those", "there",
            "it's", "they're", "there's", "students", "teachers", "kids", "children", "people",
            "parents", "schools", "most", "many", "some", "others", "everyone", "nobody", "no one")
# Sentence openers whose clause usually ends at the first comma ("If X, Y").
FRONTED = ("if", "when", "whenever", "although", "though", "even though", "while", "because",
           "since", "unless", "as long as", "once", "after", "before", "even if")
MIN_WORDS = 3
# "cause" is "because" ("cause you can") unless a word before it marks the verb or
# noun ("can cause", "the number one cause").
NOT_CONNECTIVE_BEFORE_CAUSE = {"can", "could", "would", "will", "may", "might", "should", "must", "to",
                               "and", "or", "which", "that", "also", "even", "the", "a", "one", "main"}
# Unpunctuated run-ons: a piece longer than this also splits before a bare
# coordinator that a likely subject follows ("... and they wouldnt feel rushed").
LONG_WORDS = 30

_SENTENCE_END = re.compile(r"[.!?]+[\"')\]]*(?=\s)")
_PUNCT_BREAK = re.compile(r"[;:](?=\s)")
_MARKER = re.compile(r"(?<=\s)(?:%s)\b" % "|".join(re.escape(m) for m in sorted(CLAUSE_MARKERS, key=len, reverse=True)),
                     re.IGNORECASE)
_COMMA_MARKER = re.compile(r",\s+(?=(?:%s)\b|(?:%s)\s+(?:%s)\b)" % (
    "|".join(COMMA_MARKERS), "|".join(COORDINATORS), "|".join(re.escape(w) for w in SUBJECTS)), re.IGNORECASE)
_BARE_COORDINATOR = re.compile(r"(?<=\s)(?=(?:and|or|so|then)\s+(?:%s)\b)" % "|".join(re.escape(w) for w in SUBJECTS),
                               re.IGNORECASE)
_FRONTED = re.compile(r"\s*[\"'(]*(?:%s)\b[^,]*," % "|".join(re.escape(m) for m in sorted(FRONTED, key=len, reverse=True)),
                      re.IGNORECASE)


def _words(text):
    return len(re.findall(r"\w+", text))


def _sentence_cuts(text, start, end):
    cuts = []
    for match in _SENTENCE_END.finditer(text, start, end):
        token = re.search(r"([\w.]+)[.!?]+[\"')\]]*$", text[start:match.end()])
        if token and match.group().startswith(".") and token.group(1).lower().rstrip(".") in ABBREVIATIONS:
            continue
        cuts.append(match.end())
    return cuts


def _clause_cuts(text, start, end):
    cuts = {m.end() for m in _PUNCT_BREAK.finditer(text, start, end)}
    for m in _MARKER.finditer(text, start, end):
        before = re.findall(r"[\w']+", text[start:m.start()])
        if m.group().lower() == "cause" and before and before[-1].lower() in NOT_CONNECTIVE_BEFORE_CAUSE:
            continue
        cuts.add(m.start())
    cuts |= {m.end() for m in _COMMA_MARKER.finditer(text, start, end)}
    fronted = _FRONTED.match(text, start, end)
    if fronted:
        cuts.add(fronted.end())
    return cuts


def _trim(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def presegment(text):
    """Return (start, end) offsets of clause-level segments in reading order."""
    segments = []
    for paragraph in re.finditer(r"[^\n]+", text):
        p_start, p_end = paragraph.span()
        bounds = [p_start, *_sentence_cuts(text, p_start, p_end), p_end]
        for s_start, s_end in zip(bounds, bounds[1:]):
            s_start, s_end = _trim(text, s_start, s_end)
            if s_start == s_end:
                continue
            cuts = _clause_cuts(text, s_start, s_end)
            bounds_here = sorted({s_start, s_end, *(c for c in cuts if s_start < c < s_end)})
            for a, b in zip(bounds_here, bounds_here[1:]):
                if _words(text[a:b]) > LONG_WORDS:
                    cuts |= {m.start() for m in _BARE_COORDINATOR.finditer(text, a, b)}
            cuts = sorted(c for c in cuts if s_start < c < s_end)
            pieces = []
            for a, b in zip([s_start, *cuts], [*cuts, s_end]):
                a, b = _trim(text, a, b)
                if a == b:
                    continue
                # Too-short pieces rejoin the previous clause of the same sentence.
                if pieces and (_words(text[a:b]) < MIN_WORDS or _words(text[pieces[-1][0]:pieces[-1][1]]) < MIN_WORDS):
                    pieces[-1] = (pieces[-1][0], b)
                else:
                    pieces.append((a, b))
            segments.extend(pieces)
    return segments


def write_sheets(directory, records):
    directory.mkdir(parents=True, exist_ok=True)
    index = []
    for essay_no, record in enumerate(records, 1):
        text = record.response_text
        original_id = record.metadata.get("original_id", record.example_id)
        segments = presegment(text)
        (directory / f"Essay {essay_no}.txt").write_text(text + "\n", encoding="utf-8")
        with (directory / f"Essay {essay_no}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(SHEET_COLUMNS)
            for n, (start, end) in enumerate(segments, 1):
                writer.writerow([essay_no, original_id, n, f"u{n}", text[start:end], "", "", "", "", ""])
            writer.writerow([""] * len(SHEET_COLUMNS))
            writer.writerow(["", "Overall Essay Comments: "] + [""] * (len(SHEET_COLUMNS) - 2))
            writer.writerow(["", "[Write here]"] + [""] * (len(SHEET_COLUMNS) - 2))
        index.append({"essay_no": essay_no, "example_id": record.example_id,
                      "holistic_score": record.metadata.get("holistic_score"),
                      "official_split": record.metadata.get("official_split"),
                      "word_count": len(text.split()), "segments": len(segments)})
    with (directory / "index.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(index[0]))
        writer.writeheader()
        writer.writerows(index)
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True, help="records.jsonl; essays are numbered in file order")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        parser.error("Output directory must be empty; choose a new directory to preserve prior sheets")
    lines = args.records.read_text(encoding="utf-8").splitlines()
    records = [ExampleRecord.from_dict(json.loads(line)) for line in lines if line.strip()]
    index = write_sheets(args.output_dir, records)
    print(json.dumps({"essays": len(index), "segments": sum(row["segments"] for row in index)}))


if __name__ == "__main__":
    main()
