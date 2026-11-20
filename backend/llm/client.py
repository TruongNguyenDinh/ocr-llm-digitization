from __future__ import annotations

from typing import Any, Protocol, Sequence


class LLMClientError(RuntimeError):
    """Raised when an LLM provider cannot complete a request."""


class ChatClient(Protocol):
    model: str

    def ensure_model_available(self) -> None: ...

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        response_format: str | dict[str, Any] | None = None,
    ) -> str: ...
