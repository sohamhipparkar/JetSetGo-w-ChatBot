"""Gemini client (gemini-2.5-flash) with JSON output, retries and robust parsing."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Protocol


class LLMError(Exception):
    pass


class LLMClient(Protocol):
    def generate_json(self, system: str, prompt: str, schema: dict | None = None) -> dict:
        ...


def parse_json(text: str) -> dict:
    """Parse model output into a dict, tolerating code fences or stray text."""
    if not text:
        raise LLMError("Model returned an empty response.")
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"Model did not return JSON: {cleaned[:200]}")
        data = json.loads(cleaned[start : end + 1])
    if not isinstance(data, dict):
        raise LLMError("Model JSON was not an object.")
    return data


class GeminiLLM:
    """Thin wrapper around the official `google-genai` SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", temperature: float = 0.1):
        if not api_key or api_key.startswith("your_"):
            raise LLMError(
                "GEMINI_API_KEY is missing. Copy .env.example to .env and paste your key "
                "from https://aistudio.google.com/apikey"
            )
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise LLMError("google-genai is not installed. Run: pip install -r requirements.txt") from exc

        self._types = types
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self._schema_supported = True

    def _config(self, system: str, schema: dict | None):
        kwargs: dict[str, Any] = dict(
            system_instruction=system,
            temperature=self.temperature,
            response_mime_type="application/json",
        )
        if schema is not None and self._schema_supported:
            kwargs["response_schema"] = schema
        return self._types.GenerateContentConfig(**kwargs)

    def generate_json(self, system: str, prompt: str, schema: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=prompt, config=self._config(system, schema)
                )
                return parse_json(response.text or "")
            except LLMError as exc:  # bad JSON - retry once more
                last_error = exc
            except Exception as exc:  # network / quota / schema errors
                last_error = exc
                message = str(exc).lower()
                if "schema" in message and self._schema_supported:
                    # Older SDK / API mismatch: retry without a strict schema.
                    self._schema_supported = False
                    continue
                if any(code in message for code in ("api key not valid", "permission_denied", "401", "403")):
                    raise LLMError(f"Gemini rejected the API key: {exc}") from exc
                if not any(code in message for code in ("429", "500", "503", "unavailable", "deadline", "overloaded", "resource_exhausted")):
                    raise LLMError(f"Gemini call failed: {exc}") from exc
            time.sleep(1.5 * (2**attempt))
        raise LLMError(f"Gemini call failed after retries: {last_error}")
