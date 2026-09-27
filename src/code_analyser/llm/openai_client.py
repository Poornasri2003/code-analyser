"""OpenAI-compatible LLM client (works with OpenAI, Together AI, Mistral, etc.)."""
from __future__ import annotations
import os
from typing import Tuple

from code_analyser.llm.protocol import LLMFormatError, extract_json


class OpenAIClient:
    """
    Calls any OpenAI-compatible API.
    Set OPENAI_API_KEY, OPENAI_BASE_URL (optional), OPENAI_MODEL in .env
    Works with:
      - OpenAI (gpt-4o-mini — has free tier via API)
      - Together AI (free credits on signup)
      - Mistral AI (free tier)
      - Ollama (local, no key: OPENAI_BASE_URL=http://localhost:11434/v1 OPENAI_API_KEY=ollama)
    """

    def __init__(self) -> None:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            )
        api_key = os.getenv("OPENAI_API_KEY", "")
        base_url = os.getenv("OPENAI_BASE_URL", None)  # None = default openai
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._client = OpenAI(api_key=api_key, base_url=base_url)

    def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> Tuple[dict, int]:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0,
        )
        text = response.choices[0].message.content or ""
        tokens = response.usage.total_tokens if response.usage else 0
        return extract_json(text), tokens
