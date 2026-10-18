"""LLM client tests. All provider calls are mocked; no network or key needed."""
import json
from types import SimpleNamespace
from typing import Optional

import pytest
from pydantic import BaseModel, Field, ValidationError

from hackpack.llm_client import (
    LLMClient,
    LLMConfigurationError,
    LLMOutputError,
    extract_first_json_object,
    strip_code_fences,
)


class TinyModel(BaseModel):
    name: str
    count: int = Field(default=0)


def fake_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def collector(responses, exceptions=None):
    """Return (fn, calls): fn replays responses or raises from exceptions."""
    calls: list[dict] = []

    def fn(**kwargs):
        calls.append(kwargs)
        index = len(calls) - 1
        if exceptions and index < len(exceptions) and exceptions[index] is not None:
            raise exceptions[index]
        return fake_response(responses[min(index, len(responses) - 1)])

    return fn, calls


VALID_JSON = json.dumps({"name": "hack", "count": 3})


def test_generate_structured_valid_first_attempt():
    fn, calls = collector([VALID_JSON])
    client = LLMClient(completion_fn=fn)
    result = client.generate_structured("system", "user", TinyModel)
    assert result.name == "hack" and result.count == 3
    assert len(calls) == 1
    assert calls[0]["response_format"] == {"type": "json_object"}


def test_generate_structured_strips_markdown_fences():
    fenced = "```json\n" + VALID_JSON + "\n```"
    fn, _ = collector([fenced])
    client = LLMClient(completion_fn=fn)
    assert client.generate_structured("s", "u", TinyModel).name == "hack"


def test_generate_structured_repairs_after_invalid_json():
    fn, calls = collector(["this is not json at all", VALID_JSON])
    client = LLMClient(completion_fn=fn)
    result = client.generate_structured("s", "u", TinyModel)
    assert result.count == 3
    assert len(calls) == 2
    # Retry messages are appended after the original user prompt, which is untouched.
    retry_messages = calls[1]["messages"]
    assert retry_messages[1]["content"] == calls[0]["messages"][1]["content"]
    assert "did not validate" in retry_messages[2]["content"]


def test_generate_structured_repairs_after_schema_violation():
    bad = json.dumps({"name": "hack", "count": "not-a-number"})
    fn, _ = collector([bad, VALID_JSON])
    client = LLMClient(completion_fn=fn)
    assert client.generate_structured("s", "u", TinyModel).count == 3


def test_generate_structured_extracts_embedded_json():
    wrapped = 'Sure! Here is the JSON you asked for:\n{"name": "embedded", "count": 1}\nHope that helps.'
    fn, _ = collector([wrapped])
    client = LLMClient(completion_fn=fn)
    assert client.generate_structured("s", "u", TinyModel).name == "embedded"


def test_generate_structured_retry_exhaustion():
    fn, calls = collector(["garbage"])
    client = LLMClient(completion_fn=fn, max_retries=2)
    with pytest.raises(LLMOutputError) as excinfo:
        client.generate_structured("s", "u", TinyModel)
    assert len(calls) == 3  # 1 initial + 2 retries
    assert excinfo.value.attempts == 3


def test_max_retries_capped_at_two():
    fn, calls = collector(["garbage"])
    client = LLMClient(completion_fn=fn, max_retries=99)
    with pytest.raises(LLMOutputError):
        client.generate_structured("s", "u", TinyModel)
    assert len(calls) == 3


def test_provider_error_is_sanitized():
    def broken(**kwargs):
        raise RuntimeError("401 Unauthorized: api_key=sk-secret-value-12345")

    client = LLMClient(completion_fn=broken)
    with pytest.raises(LLMConfigurationError) as excinfo:
        client.generate_structured("s", "u", TinyModel)
    message = str(excinfo.value)
    assert "sk-secret-value" not in message
    assert "RuntimeError" in message


def test_generate_rejects_empty_response():
    fn, _ = collector([""])
    client = LLMClient(completion_fn=fn)
    with pytest.raises(LLMConfigurationError):
        client.generate("s", "u")


def test_strip_code_fences_variants():
    assert strip_code_fences("```json\n{}\n```") == "{}"
    assert strip_code_fences("```{}\n```") == "{}"
    assert strip_code_fences('prose {"a": 1} tail') == '{"a": 1}'


def test_extract_first_json_object_nested():
    text = 'noise {"outer": {"inner": 2}} more'
    extracted = extract_first_json_object(text)
    assert json.loads(extracted) == {"outer": {"inner": 2}}


def test_extract_first_json_object_none_when_absent():
    assert extract_first_json_object("no json here") is None
