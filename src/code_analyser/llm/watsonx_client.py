"""IBM watsonx.ai LLM client."""
from __future__ import annotations

import time
from typing import Any, Dict, Tuple

from code_analyser import config
from code_analyser.llm.protocol import LLMFormatError, extract_json

_JSON_NOTE = "\n\nRespond with a single json object and nothing else."


class WatsonxClient:
    """Chat completions through the ibm-watsonx-ai SDK, temperature 0."""

    def __init__(self) -> None:
        from ibm_watsonx_ai import Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        missing = [name for name, val in (
            ("WATSONX_API_KEY", config.WATSONX_API_KEY),
            ("WATSONX_PROJECT_ID", config.WATSONX_PROJECT_ID),
        ) if not val]
        if missing:
            raise ValueError(f"watsonx is selected but {', '.join(missing)} is not set")

        self._model = ModelInference(
            model_id=config.WATSONX_MODEL_ID,
            credentials=Credentials(url=config.WATSONX_URL, api_key=config.WATSONX_API_KEY),
            project_id=config.WATSONX_PROJECT_ID,
        )
        self._json_mode = True
        self._max_retries = 5

    def _chat(self, system: str, user: str, max_tokens: int) -> Dict[str, Any]:
        # The chat API takes max_tokens; max_new_tokens belongs to generate_text.
        params: Dict[str, Any] = {"temperature": 0, "max_tokens": max_tokens}
        if self._json_mode:
            params["response_format"] = {"type": "json_object"}
        return self._model.chat(
            messages=[{"role": "system", "content": system + _JSON_NOTE},
                      {"role": "user", "content": user}],
            params=params,
        )

    def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> Tuple[dict, int]:
        last_err: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                response = self._chat(system, user, max_tokens)
                text = response["choices"][0]["message"].get("content") or ""
                tokens = (response.get("usage") or {}).get("total_tokens", 0)
                return extract_json(text), tokens
            except LLMFormatError:
                raise
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if self._json_mode and ("response_format" in msg or "json" in msg):
                    # Not every watsonx model supports JSON mode; extract_json
                    # can still recover the object from free-form output.
                    self._json_mode = False
                    continue
                if "429" in msg or "rate" in msg or "too many" in msg:
                    time.sleep(min(5 * (attempt + 1), 30))
                    continue
                raise
        raise LLMFormatError(f"watsonx call failed after {self._max_retries} attempts: {last_err}")
