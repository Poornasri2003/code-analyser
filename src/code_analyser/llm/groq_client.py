"""Groq LLM client — free tier, no IBM Cloud account needed."""
from __future__ import annotations
import os
import re
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
        self._max_retries = int(os.getenv("GROQ_MAX_RETRIES", "6"))
        self._retry_wait = float(os.getenv("GROQ_RETRY_WAIT_SECONDS", "15"))
        # Groq counts prompt plus *requested* reply tokens against the
        # per-minute budget, and rejects any single request above it.
        self._request_cap = int(os.getenv("GROQ_REQUEST_TOKEN_CAP", "7400"))
        self._reasoning = os.getenv("GROQ_REASONING_EFFORT", "low")
        # Each model has its own daily token allowance, so when one runs out
        # the next can carry on instead of stalling the run for hours.
        fallbacks = os.getenv("GROQ_FALLBACK_MODELS", "openai/gpt-oss-20b,qwen/qwen3.8-27b")
        self._models = [self._model] + [
            m.strip() for m in fallbacks.split(",") if m.strip() and m.strip() != self._model
        ]
        self._exhausted: set = set()

    @property
    def model(self) -> str:
        return self._model

    def _next_model(self) -> bool:
        self._exhausted.add(self._model)
        for m in self._models:
            if m not in self._exhausted:
                self._model = m
                return True
        return False

    def _create(self, messages, max_tokens: int, json_mode: bool, reasoning: bool):
        kwargs = dict(model=self._model, messages=messages,
                      max_tokens=max_tokens, temperature=0)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if reasoning:
            kwargs["reasoning_effort"] = self._reasoning
        return self._client.chat.completions.create(**kwargs)

    def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> Tuple[dict, int]:
        # JSON mode is the only reliable way to stop the model answering in
        # Markdown prose. It requires the literal word "json" in the prompt.
        messages = [
            {"role": "system", "content": system + "\n\nRespond with a single json object and nothing else."},
            {"role": "user", "content": user},
        ]
        prompt_est = _estimate_tokens(system) + _estimate_tokens(user) + 40
        budget = max(_MIN_REPLY, min(max_tokens, self._request_cap - prompt_est))
        json_mode = True
        # gpt-oss thinks before answering; low effort is ample for structured
        # extraction and leaves far more of the budget for the reply itself.
        reasoning = self._model.startswith("openai/gpt-oss") and bool(self._reasoning)
        last_err = None
        for attempt in range(self._max_retries):
            try:
                response = self._create(messages, budget, json_mode, reasoning)
                text = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else 0
                return extract_json(text), tokens
            except LLMFormatError:
                raise
            except Exception as e:
                last_err = e
                msg = str(e)
                if "reasoning_effort" in msg:
                    reasoning = False
                    continue
                if "response_format" in msg or "json_object" in msg:
                    # This model has no JSON mode; retry free-form.
                    json_mode = False
                    continue
                if "too large" in msg.lower():
                    # The request alone exceeds the cap, so waiting cannot help.
                    # Shrink the reply budget by the overshoot and go again now.
                    over = _overshoot(msg)
                    budget = budget - (over or 1000) - 200
                    if budget < _MIN_REPLY:
                        raise LLMFormatError(f"Prompt too large for this provider: {msg[:200]}")
                    continue
                if "per day" in msg.lower() or "(TPD)" in msg or "(RPD)" in msg:
                    # The daily allowance is gone; waiting means hours. Move to
                    # the next model, or fail now with a message a person can act on.
                    if self._next_model():
                        reasoning = self._model.startswith("openai/gpt-oss") and bool(self._reasoning)
                        json_mode = True
                        continue
                    raise LLMFormatError(
                        "Groq's free daily token allowance is used up on every configured "
                        f"model. It resets in {_wait_text(msg)}. Use watsonx or another key meanwhile."
                    )
                if "429" in msg or "rate" in msg.lower():
                    # The per-minute budget is spent. Groq says exactly how long
                    # until it refills, which is usually seconds, not a minute.
                    time.sleep(_retry_after(msg, self._retry_wait * (attempt + 1)))
                    continue
                raise
        raise LLMFormatError(f"Groq call failed after {self._max_retries} attempts: {last_err}")


_MIN_REPLY = 900
_WAIT_RE = re.compile(r"try again in (?:(\d+)m)?([\d.]+)s", re.I)
_REQ_RE = re.compile(r"Limit (\d+), Requested (\d+)", re.I)


def _estimate_tokens(text: str) -> int:
    # Code and JSON tokenise densely; 3.2 characters per token errs high,
    # which is the safe direction for staying under the cap.
    return int(len(text) / 3.2)


def _retry_after(msg: str, default: float) -> float:
    m = _WAIT_RE.search(msg)
    if not m:
        return default
    return min(int(m.group(1) or 0) * 60 + float(m.group(2)) + 0.5, 65.0)


def _wait_text(msg: str) -> str:
    m = re.search(r"try again in ([\dhms.]+)", msg)
    return m.group(1) if m else "a few hours"


def _overshoot(msg: str) -> int:
    m = _REQ_RE.search(msg)
    return max(int(m.group(2)) - int(m.group(1)), 0) if m else 0
