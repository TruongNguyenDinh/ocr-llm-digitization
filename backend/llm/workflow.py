import json
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from .client import ChatClient, LLMClientError
from .correction_guard import constrain_corrections
from .ollama_client import OllamaClient
from .markdown_review import preserve_protected_content
from .prompts import CLASSIFICATION_SYSTEM_PROMPT, CORRECTION_SYSTEM_PROMPT
from .schemas import (
    CorrectedPage,
    LLMResponseError,
    PageText,
    ReviewDraft,
    parse_corrected_text,
    parse_metadata,
)


class LLMWorkflowError(RuntimeError):
    """Raised when local LLM processing fails for a document or page."""


def load_labels(path: str | Path | None = None) -> dict[str, str]:
    label_path = Path(path) if path is not None else Path(__file__).with_name("labels.json")
    try:
        data = json.loads(label_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LLMWorkflowError(f"Could not load label registry {label_path}: {exc}") from exc
    if not isinstance(data, dict) or not data:
        raise LLMWorkflowError("Label registry must be a non-empty JSON object")
    labels = {str(code): str(name) for code, name in data.items()}
    if "0" not in labels:
        raise LLMWorkflowError("Label registry must define code '0' as fallback")
    return labels


class LocalLLMWorkflow:
    def __init__(
        self,
        client: ChatClient | None = None,
        labels: dict[str, str] | None = None,
        provider: str = "qwen",
    ) -> None:
        if provider != "qwen":
            raise ValueError(f"Unsupported LLM provider: {provider}")
        self.provider = provider
        if client is None:
            client = OllamaClient()
        self.client = client
        self.model = getattr(client, "model", "unknown")
        self.labels = labels if labels is not None else load_labels()

    def process_pages(
        self,
        pages: Iterable[PageText | dict[str, Any]],
        *,
        document_name: str = "document",
        source_path: str = "",
        raw_document_dir: str = "",
    ) -> ReviewDraft:
        normalized_pages: list[PageText] = []
        for page in pages:
            if isinstance(page, PageText):
                normalized_pages.append(page)
            elif isinstance(page, dict):
                normalized_pages.append(PageText(str(page["page_id"]), str(page["text"])))
            else:
                raise TypeError("Each page must be PageText or a page mapping")
        if not normalized_pages:
            raise LLMWorkflowError("Cannot process a document with no OCR pages")
        page_ids = [page.page_id for page in normalized_pages]
        if len(page_ids) != len(set(page_ids)):
            raise LLMWorkflowError("OCR page IDs must be unique")

        try:
            self.client.ensure_model_available()
        except LLMClientError as exc:
            raise LLMWorkflowError(
                f"{self.provider.title()} is unavailable for {document_name}: {exc}"
            ) from exc

        corrected_pages: list[CorrectedPage] = []
        for page in normalized_pages:
            try:
                response = self.client.chat(
                    [
                        {"role": "system", "content": CORRECTION_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"Trang {page.page_id}. Sửa lỗi OCR trong phần dữ liệu sau.\n"
                                f"<document_page>\n{page.text}\n</document_page>"
                            ),
                        },
                    ],
                    response_format={
                        "type": "object",
                        "properties": {"corrected_text": {"type": "string"}},
                        "required": ["corrected_text"],
                    },
                )
                corrected_text = preserve_protected_content(
                    page.text, constrain_corrections(page.text, parse_corrected_text(response))
                )
            except (LLMClientError, LLMResponseError, KeyError, TypeError) as exc:
                raise LLMWorkflowError(
                    f"Could not correct page {page.page_id} of {document_name}: {exc}"
                ) from exc
            corrected_pages.append(
                CorrectedPage(
                    page_id=page.page_id,
                    raw_text=page.text,
                    corrected_text=corrected_text,
                )
            )

        corrected_document = "\n\n".join(
            f"[{page.page_id}]\n{page.corrected_text}" for page in corrected_pages
        )
        label_list = "\n".join(
            f"- {code}: {name}" for code, name in sorted(self.labels.items())
        )
        try:
            metadata_response = self.client.chat(
                [
                    {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Danh sách nhãn:\n{label_list}\n\n"
                            "Trích xuất thông tin từ toàn bộ văn bản theo trang:\n"
                            f"<document>\n{corrected_document}\n</document>"
                        ),
                    },
                ],
                response_format={
                    "type": "object",
                    "properties": {
                        "label_code": {
                            "type": "string",
                            "enum": sorted(self.labels),
                        },
                        "sender": {"type": ["string", "null"]},
                        "recipient": {"type": ["string", "null"]},
                        "date_time": {"type": ["string", "null"]},
                        "document_type": {"type": "string"},
                    },
                    "required": [
                        "label_code",
                        "sender",
                        "recipient",
                        "date_time",
                        "document_type",
                    ],
                },
            )
            metadata = parse_metadata(metadata_response, self.labels)
        except (LLMClientError, LLMResponseError) as exc:
            raise LLMWorkflowError(
                f"Could not classify/extract metadata for {document_name}: {exc}"
            ) from exc

        return ReviewDraft(
            review_id=uuid4().hex,
            document_name=document_name,
            source_path=source_path,
            raw_document_dir=raw_document_dir,
            page_count=len(corrected_pages),
            pages=corrected_pages,
            metadata=metadata,
            provider=self.provider,
            model=self.model,
        )
