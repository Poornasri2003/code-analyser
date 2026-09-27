"""Fake LLM client for offline testing."""
from __future__ import annotations
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

from code_analyser.llm.protocol import LLMFormatError


class FakeLLMClient:
    """Returns pre-queued responses in FIFO order. No network calls."""

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None) -> None:
        self._queue: deque = deque(responses or [])

    def queue(self, response: Dict[str, Any]) -> None:
        """Enqueue an additional canned response."""
        self._queue.append(response)

    def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> Tuple[Dict[str, Any], int]:
        """Pop and return the next queued response, or raise LLMFormatError."""
        if not self._queue:
            raise LLMFormatError("FakeLLMClient: response queue is empty")
        return self._queue.popleft(), 0
