import json
from dataclasses import asdict, dataclass
from typing import Any


class LLMResponseError(ValueError):
    """Raised when a model response does not match the expected structure."""


@dataclass(frozen=True)
class PageText:
    page_id: str
    text: str


@dataclass(frozen=True)
class CorrectedPage:
    page_id: str
    raw_text: str
    corrected_text: str


@dataclass(frozen=True)
class DocumentMetadata:
    label_code: str
    label_name: str
    sender: str | None
    recipient: str | None
    date_time: str | None
    document_type: str


@dataclass(frozen=True)
class ReviewDraft:
    review_id: str
    document_name: str
    source_path: str
    raw_document_dir: str
    page_count: int
    pages: list[CorrectedPage]
    metadata: DocumentMetadata
    status: str = "pending_review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "document_name": self.document_name,
            "source_path": self.source_path,
            "raw_document_dir": self.raw_document_dir,
            "page_count": self.page_count,
            "pages": [asdict(page) for page in self.pages],
            "metadata": asdict(self.metadata),
            "status": self.status,
        }


def parse_object(content: str, required: set[str]) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise LLMResponseError(f"Model response is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMResponseError("Model response must be a JSON object")
    missing = required - value.keys()
    if missing:
        raise LLMResponseError(
            "Model response is missing fields: " + ", ".join(sorted(missing))
        )
    return value


def parse_corrected_text(content: str) -> str:
    data = parse_object(content, {"corrected_text"})
    corrected = data["corrected_text"]
    if not isinstance(corrected, str):
        raise LLMResponseError("corrected_text must be a string")
    return corrected


def parse_metadata(content: str, labels: dict[str, str]) -> DocumentMetadata:
    required = {
        "label_code",
        "label_name",
        "sender",
        "recipient",
        "date_time",
        "document_type",
    }
    data = parse_object(content, required)
    code = data["label_code"]
    name = data["label_name"]
    if not isinstance(code, str) or code not in labels:
        raise LLMResponseError(f"Unknown label code: {code!r}")
    if name != labels[code]:
        raise LLMResponseError(
            f"Label name {name!r} does not match code {code!r} ({labels[code]!r})"
        )
    for field in ("sender", "recipient", "date_time"):
        if data[field] is not None and not isinstance(data[field], str):
            raise LLMResponseError(f"{field} must be a string or null")
    document_type = data["document_type"]
    if not isinstance(document_type, str) or not document_type.strip():
        raise LLMResponseError("document_type must be a non-empty string")
    return DocumentMetadata(
        label_code=code,
        label_name=name,
        sender=data["sender"],
        recipient=data["recipient"],
        date_time=data["date_time"],
        document_type=document_type.strip(),
    )
