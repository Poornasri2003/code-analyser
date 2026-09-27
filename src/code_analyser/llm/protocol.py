"""LLM protocol helpers, shared exceptions, and the LLMClient Protocol."""
from __future__ import annotations
import json
import re
from typing import Protocol, Tuple


class LLMFormatError(Exception):
    """Raised when the LLM response cannot be parsed as valid JSON."""


class LLMClient(Protocol):
    """Protocol for LLM clients used throughout the system."""
    def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> Tuple[dict, int]:
        """Returns (parsed_dict, token_count). Raises LLMFormatError on bad output."""
        ...


def extract_json(raw: str) -> dict:
    """Extract the first JSON object from *raw*, stripping markdown fences etc.

    Raises
    ------
    LLMFormatError
        If no valid JSON object can be found.
    """
    # 1. Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1)

    # 2. Find the first {...} block
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not brace_match:
        raise LLMFormatError(f"No JSON object found in LLM output: {raw[:200]!r}")

    candidate = brace_match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMFormatError(f"Invalid JSON in LLM output: {exc}") from exc
