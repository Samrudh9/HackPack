"""Provider-agnostic LLM wrapper with validated structured output.

Design notes
------------
* LiteLLM is the single integration point. Local Ollama is reached through
  ``ollama/<model>``; hosted providers use their normal LiteLLM model string
  plus the provider's API key in the environment.
* Structured output uses ``response_format={"type": "json_object"}`` when the
  provider accepts it. JSON mode is NOT a schema guarantee: every response is
  validated with Pydantic and repaired through a bounded retry loop
  (1 initial attempt + at most ``LLM_MAX_RETRIES`` retries, capped at 2).
* The original prompt is kept separate from retry feedback so the model never
  sees a mutated version of the task.
* Errors never contain API keys or repository text; only exception class names
  and generic guidance are surfaced.
* When generation ultimately fails, callers fall back to the deterministic
  template pitch (see ``hackpack.engine.pitch_builder``) and label the output
  ``generation_mode="fallback"``.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar, Type, Any, Callable, Optional

from pydantic import BaseModel, ValidationError

from config import settings

T = TypeVar("T", bound=BaseModel)

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class LLMConfigurationError(RuntimeError):
    """The configured provider/model could not be reached or is misconfigured."""


class LLMOutputError(RuntimeError):
    """The model responded but could not produce schema-valid JSON in the retry budget."""

    def __init__(self, model_name: str, attempts: int, last_error: str):
        self.model_name = model_name
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"The configured AI model could not produce valid structured output after "
            f"{attempts} attempt(s). Check LLM_MODEL/LLM_API_BASE, or rely on the "
            "deterministic fallback pitch (enabled by default)."
        )


def strip_code_fences(text: str) -> str:
    """Remove Markdown fences and any prose surrounding a JSON object."""
    text = text.strip()
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()
    if text.lower().startswith("json"):
        candidate = text[4:].strip().lstrip(":").strip()
        if candidate.startswith("{"):
            text = candidate
    if text.startswith("{"):
        return text
    # Last resort: return the outermost {...} span, if any.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text


def extract_first_json_object(text: str) -> Optional[str]:
    """Return the first balanced top-level JSON object in ``text``."""
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, end = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return text[idx : idx + end]
        except json.JSONDecodeError:
            pass
        idx = text.find("{", idx + 1)
    return None


class LLMClient:
    def __init__(
        self,
        model: str | None = None,
        api_base: str | None = None,
        temperature: float | None = None,
        max_retries: int | None = None,
        completion_fn: Callable[..., Any] | None = None,
    ):
        """``completion_fn`` exists for tests; production uses LiteLLM."""
        self.model = model or settings.LLM_MODEL
        configured_base = settings.LLM_API_BASE
        self.api_base = api_base if api_base is not None else (configured_base or None)
        self.temperature = settings.LLM_TEMPERATURE if temperature is None else temperature
        self.max_retries = max(0, min(2, settings.LLM_MAX_RETRIES if max_retries is None else max_retries))
        self._completion_fn = completion_fn

    # -- low level ---------------------------------------------------------

    def _completion(self, messages: list[dict], temperature: float, response_format: dict | None = None):
        completion = self._completion_fn
        if completion is None:
            try:
                from litellm import completion  # type: ignore
            except ImportError as exc:
                raise LLMConfigurationError(
                    "LiteLLM is missing. Install dependencies with `pip install -r requirements.txt`."
                ) from exc

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "timeout": settings.LLM_TIMEOUT_SECONDS,
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if response_format:
            kwargs["response_format"] = response_format
        try:
            return completion(**kwargs)
        except LLMConfigurationError:
            raise
        except Exception as exc:  # provider, auth, timeout, network errors
            model_hint = ""
            if self.model.startswith("ollama/"):
                model_hint = (
                    " Make sure Ollama is running and the model is downloaded "
                    "(for example: `ollama pull llama3.1`)."
                )
            # Only the exception class name is surfaced: never str(exc), which
            # could contain request headers or API keys.
            raise LLMConfigurationError(
                f"The configured AI model could not respond ({type(exc).__name__}). "
                f"Check LLM_MODEL/LLM_API_BASE and provider credentials.{model_hint}"
            ) from exc

    @staticmethod
    def _content_of(response: Any) -> str:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        return content.strip() if isinstance(content, str) else ""

    # -- public API --------------------------------------------------------

    def generate(self, system_prompt: str, user_prompt: str, temperature: float | None = None) -> str:
        """Plain-text completion. Raises LLMConfigurationError on empty output."""
        response = self._completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            self.temperature if temperature is None else temperature,
        )
        content = self._content_of(response)
        if not content:
            raise LLMConfigurationError("The AI model returned an empty response. Please retry.")
        return content

    def generate_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float = 0.1,
    ) -> T:
        """Return a validated instance of ``response_model``.

        Attempt 1 uses the original prompt. Each retry appends a separate
        user message containing only repair feedback, keeping the original
        prompt untouched. Raises ``LLMOutputError`` when the budget is
        exhausted; callers should then use the deterministic fallback.
        """
        schema = response_model.model_json_schema()
        original_user_message = (
            f"{user_prompt}\n\n"
            "Return ONLY a JSON object matching this schema. Do not wrap it in Markdown.\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )
        messages_base = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": original_user_message},
        ]

        attempts = self.max_retries + 1
        last_error_text = "unknown"
        for attempt in range(attempts):
            # Try native/json-object mode first; some providers reject the
            # parameter entirely, in which case the provider error surfaces
            # as LLMConfigurationError and the caller falls back.
            response = self._completion(
                [dict(m) for m in messages_base],
                temperature,
                response_format={"type": "json_object"},
            )
            content = self._content_of(response)
            text = strip_code_fences(content)
            candidate = extract_first_json_object(text) if text else None
            try:
                if not candidate:
                    raise ValueError("the response contained no JSON object")
                validated = response_model.model_validate_json(candidate)
                return validated
            except (ValidationError, ValueError) as exc:
                last_error_text = type(exc).__name__
                if attempt < attempts - 1:
                    # Separate repair message; the original task stays intact.
                    messages_base.append(
                        {
                            "role": "user",
                            "content": (
                                "Your previous reply did not validate against the schema "
                                f"({last_error_text}). Reply again with one complete, strict "
                                "JSON object that includes every required field with the "
                                "declared types. No prose, no Markdown fences."
                            ),
                        }
                    )
        raise LLMOutputError(self.model, attempts, last_error_text)
