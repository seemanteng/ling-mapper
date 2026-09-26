"""Common records with explicit model-input projection and offset validation."""
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourcePassage:
    document_id: str
    text: str
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoldSpan:
    annotation_id: str
    document_id: str
    start: int
    end: int
    text: str
    original_label: str
    role: str
    annotation_task: str = "discourse_element"
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExampleRecord:
    example_id: str
    prompt: str
    response_text: str
    source_passages: list[SourcePassage] | None = None
    rubric: list[dict[str, Any]] | None = None
    gold_spans: list[GoldSpan] | None = None
    gold_relations: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "1.0"

    def validate(self) -> None:
        if not self.example_id or not isinstance(self.prompt, str) or not isinstance(self.response_text, str):
            raise ValueError("Record requires an ID and string prompt/response")
        documents = {self.example_id: self.response_text}
        for source in self.source_passages or []:
            if not source.document_id or source.document_id in documents:
                raise ValueError("Duplicate or empty document ID")
            documents[source.document_id] = source.text
        ids = set()
        for span in self.gold_spans or []:
            if not span.annotation_id or span.annotation_id in ids:
                raise ValueError("Duplicate or empty annotation ID")
            ids.add(span.annotation_id)
            text = documents.get(span.document_id)
            if text is None or not 0 <= span.start < span.end <= len(text):
                raise ValueError("Invalid span bounds or document")
            if text[span.start:span.end] != span.text:
                raise ValueError("Span text does not equal source slice")
        for edge in self.gold_relations or []:
            if edge.get("source_id") not in ids or edge.get("target_id") not in ids:
                raise ValueError("Relation endpoint is not a validated annotation")
            if not edge.get("relation"):
                raise ValueError("Relation type required")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExampleRecord":
        data = dict(data)
        if data.get("source_passages") is not None:
            data["source_passages"] = [SourcePassage(**x) for x in data["source_passages"]]
        if data.get("gold_spans") is not None:
            data["gold_spans"] = [GoldSpan(**x) for x in data["gold_spans"]]
        record = cls(**data)
        if record.schema_version != "1.0":
            raise ValueError("Unsupported schema version")
        record.validate()
        return record

    def model_input(self) -> dict[str, Any]:
        """Allowlist: annotations, scores, dataset metadata never reach the model."""
        self.validate()
        return {
            "prompt": self.prompt,
            "response_text": self.response_text,
            "source_passages": None if self.source_passages is None else [
                {"document_id": p.document_id, "text": p.text} for p in self.source_passages
            ],
            "rubric": None if self.rubric is None else [
                {k: r[k] for k in ("criterion_id", "text") if k in r} for r in self.rubric
            ],
        }
