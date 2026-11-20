from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .client import LLMClientError


try:
    from .gemini_local_settings import GEMINI_API_KEY
except ImportError:
    GEMINI_API_KEY = ""


class GeminiError(LLMClientError):
    """Raised when Gemini cannot complete a text generation request."""


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        configured_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        self.api_key = (configured_key or GEMINI_API_KEY).strip()
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        self.timeout = timeout if timeout is not None else float(
            os.environ.get("GEMINI_TIMEOUT_SECONDS", "300")
        )

    def ensure_model_available(self) -> None:
        if not self.api_key.strip():
            raise GeminiError(
                "Gemini API key is not configured. Set GEMINI_API_KEY in the backend environment "
                "or in backend/llm/gemini_local_settings.py."
            )

    def chat(
        self,
        messages: Sequence[dict[str, str]],
        response_format: str | dict[str, Any] | None = None,
    ) -> str:
        self.ensure_model_available()
        system_parts = [
            {"text": message["content"]}
            for message in messages
            if message.get("role") == "system" and message.get("content")
        ]
        contents = [
            {
                "role": "model" if message.get("role") == "assistant" else "user",
                "parts": [{"text": message.get("content", "")}],
            }
            for message in messages
            if message.get("role") != "system"
        ]
        if not contents:
            raise GeminiError("Gemini request requires at least one user message.")

        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}
        if response_format is not None:
            schema = response_format
            if isinstance(schema, str):
                try:
                    schema = json.loads(schema)
                except ValueError as exc:
                    raise GeminiError("Gemini response schema must be valid JSON.") from exc
            if isinstance(schema, dict) and schema.get("type") == "json":
                schema = schema.get("schema")
            if isinstance(schema, dict):
                payload["generationConfig"] = {
                    "responseMimeType": "application/json",
                    "responseJsonSchema": schema,
                    "thinkingConfig": {
                        "thinkingLevel": os.environ.get("GEMINI_THINKING_LEVEL", "low"),
                    },
                }

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='')}:generateContent"
        )
        request = Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        retryable_statuses = {429, 500, 502, 503, 504}
        retry_count = 0
        while True:
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                detail = re.sub(r"(?i)(key\s*[=:]\s*)[^\s,\"}]+", r"\1[redacted]", detail)
                if self.api_key:
                    detail = detail.replace(self.api_key, "[redacted]")
                if exc.code in retryable_statuses and retry_count < 3:
                    retry_after = exc.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2 ** retry_count
                    except ValueError:
                        delay = 2 ** retry_count
                    time.sleep(max(0.0, min(delay, 15.0)))
                    retry_count += 1
                    continue
                raise GeminiError(f"Gemini returned HTTP {exc.code}: {detail[:1000]}") from exc
            except TimeoutError as exc:
                raise GeminiError(
                    f"Gemini did not return a response within {self.timeout:g} seconds. "
                    "The service may be overloaded; wait briefly and retry."
                ) from exc
            except (URLError, json.JSONDecodeError) as exc:
                raise GeminiError(f"Could not communicate with Gemini: {exc}") from exc

        try:
            candidates = result["candidates"]
            parts = candidates[0]["content"]["parts"]
            content = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
        except (KeyError, IndexError, TypeError) as exc:
            prompt_feedback = result.get("promptFeedback") if isinstance(result, dict) else None
            if prompt_feedback:
                raise GeminiError(f"Gemini did not return a candidate: {prompt_feedback}") from exc
            raise GeminiError("Gemini response did not contain generated text.") from exc
        if not isinstance(content, str) or not content:
            raise GeminiError("Gemini response did not contain generated text.")
        return content
