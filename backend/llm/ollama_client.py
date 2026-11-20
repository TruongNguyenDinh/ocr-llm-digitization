import json
import os
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .client import LLMClientError


class OllamaError(LLMClientError):
    """Raised when the local Ollama service cannot complete a request."""


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        configured_timeout = os.environ.get("OLLAMA_TIMEOUT_SECONDS")
        if timeout is not None:
            if timeout < 0:
                raise ValueError("Ollama timeout must be zero or positive")
            self.timeout = timeout or None
        elif configured_timeout:
            parsed_timeout = float(configured_timeout)
            if parsed_timeout < 0:
                raise ValueError("OLLAMA_TIMEOUT_SECONDS must be zero or positive")
            self.timeout = parsed_timeout or None
        else:
            # Ollama may need several minutes to load Qwen or generate a long page.
            # Leave the request open until the service responds or the caller cancels.
            self.timeout = None

    def _request(self, endpoint: str, payload: dict[str, Any] | None = None) -> Any:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.base_url}{endpoint}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(
                f"Ollama returned HTTP {exc.code}: {detail[:1000]}"
            ) from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Could not communicate with Ollama: {exc}") from exc

    def ensure_model_available(self) -> None:
        response = self._request("/api/tags")
        model_names = {
            item.get("name")
            for item in response.get("models", [])
            if isinstance(item, dict)
        }
        if self.model not in model_names:
            raise OllamaError(
                f"Ollama model '{self.model}' is not installed. "
                f"Run `ollama pull {self.model}` first."
            )

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        response_format: str | dict[str, Any] | None = None,
        *, num_ctx: int | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "stream": False,
            "think": False,
        }
        if response_format is not None:
            payload["format"] = response_format
        if num_ctx is not None:
            payload["options"] = {"num_ctx": num_ctx}
        response = self._request("/api/chat", payload)
        if isinstance(response, dict) and response.get("done_reason") in {
            "length",
            "max_tokens",
        }:
            raise OllamaError(
                "Ollama stopped before completing its response because the output token limit was reached."
            )
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise OllamaError("Ollama response did not contain message content") from exc
        if not isinstance(content, str):
            raise OllamaError("Ollama message content was not text")
        return content
