"""Groq LLM client — free tier, no IBM Cloud account needed."""
from __future__ import annotations
import os
import time
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
        self._model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
        self._max_retries = int(os.getenv("GROQ_MAX_RETRIES", "4"))
        self._retry_wait = float(os.getenv("GROQ_RETRY_WAIT_SECONDS", "20"))

    def _create(self, messages, max_tokens: int, json_mode: bool):
        kwargs = dict(model=self._model, messages=messages,
                      max_tokens=max_tokens, temperature=0)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self._client.chat.completions.create(**kwargs)

    def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> Tuple[dict, int]:
        # JSON mode is the only reliable way to stop the model answering in
        # Markdown prose. It requires the literal word "json" in the prompt.
        messages = [
            {"role": "system", "content": system + "\n\nRespond with a single json object and nothing else."},
            {"role": "user", "content": user},
        ]
        json_mode = True
        last_err = None
        for attempt in range(self._max_retries):
            try:
                response = self._create(messages, max_tokens, json_mode)
                text = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return extract_json(text), tokens
            except Exception as e:
                last_err = e
                msg = str(e)
                if "response_format" in msg or "json_object" in msg:
                    # This model has no JSON mode; retry free-form once.
                    json_mode = False
                    continue
                if "429" in msg or "413" in msg or "rate" in msg.lower():
                    # Free tiers meter tokens per minute, so the budget refills
                    # on a minute boundary — waiting is the only way through.
                    time.sleep(self._retry_wait * (attempt + 1))
                    continue
                raise
        raise LLMFormatError(f"Groq call failed after {self._max_retries} attempts: {last_err}")
