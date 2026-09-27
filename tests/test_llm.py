"""Tests for LLM client protocol."""
from __future__ import annotations
import pytest

from code_analyser.llm.protocol import extract_json, LLMFormatError
from code_analyser.llm.fake_client import FakeLLMClient


def test_extract_json_clean():
    raw = '{"key": "value", "num": 42}'
    result = extract_json(raw)
    assert result == {"key": "value", "num": 42}


def test_extract_json_strips_fences():
    raw = '```json\n{"a": 1}\n```'
    assert extract_json(raw) == {"a": 1}


def test_extract_json_extracts_from_chatty():
    raw = "Sure! Here is the result:\n\n{\"answer\": true}\n\nHope that helps!"
    assert extract_json(raw) == {"answer": True}


def test_extract_json_no_json_raises():
    with pytest.raises(LLMFormatError):
        extract_json("This is just text with no JSON")


def test_extract_json_invalid_json_raises():
    with pytest.raises(LLMFormatError):
        extract_json("{invalid json here")


def test_fake_client_returns_queued():
    client = FakeLLMClient([{"result": "ok"}])
    result, tokens = client.complete_json("sys", "user")
    assert result == {"result": "ok"}
    assert tokens == 0


def test_fake_client_empty_queue_raises():
    client = FakeLLMClient([])
    with pytest.raises(LLMFormatError):
        client.complete_json("sys", "user")
