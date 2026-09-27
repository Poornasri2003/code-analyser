"""IBM watsonx.ai LLM client."""
from __future__ import annotations
import json
from typing import Tuple

from code_analyser.llm.protocol import LLMClient, LLMFormatError, extract_json
from code_analyser import config


class WatsonxClient:
    """Calls ibm-watsonx-ai SDK. temperature=0."""

    def __init__(self) -> None:
        from ibm_watsonx_ai import APIClient, Credentials
        from ibm_watsonx_ai.foundation_models import ModelInference

        credentials = Credentials(
            url=config.WATSONX_URL,
            api_key=config.WATSONX_API_KEY,
        )
        self._model = ModelInference(
            model_id=config.WATSONX_MODEL_ID,
            credentials=credentials,
            project_id=config.WATSONX_PROJECT_ID,
            params={"temperature": 0, "max_new_tokens": 4096},
        )

    def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> Tuple[dict, int]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        response = self._model.chat(messages=messages, params={"max_new_tokens": max_tokens})
        text = response["choices"][0]["message"]["content"]
        tokens = response.get("usage", {}).get("total_tokens", 0)
        return extract_json(text), tokens
