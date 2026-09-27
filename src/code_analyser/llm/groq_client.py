"""Groq LLM client — free tier, no IBM Cloud account needed."""
from __future__ import annotations
import os
from typing import Tuple

from code_analyser.llm.protocol import LLMFormatError, extract_json


class GroqClient:
    """
    Calls Groq API (free tier). Get a free key at https://console.groq.com
    Models: llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it
    Set GROQ_API_KEY and GROQ_MODEL in your .env
    """

    def __init__(self) -> None:
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "groq package not installed. Run: pip install groq"
            )
        api_key = os.getenv("GROQ_API_KEY", "")
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment")
        self._client = Groq(api_key=api_key)
        self._model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

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
