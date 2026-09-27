"""BobShell local LLM client (subprocess)."""
from __future__ import annotations
import json
import subprocess
from typing import Tuple

from code_analyser.llm.protocol import LLMClient, LLMFormatError, extract_json


class BobShellClient:
    """Calls local bobshell via subprocess for development."""

    def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> Tuple[dict, int]:
        payload = json.dumps({"system": system, "user": user, "max_tokens": max_tokens})
        result = subprocess.run(
            ["bobshell", "complete"],
            input=payload,
            capture_output=True,
            text=True,
            check=True,
        )
        text = result.stdout
        return extract_json(text), 0  # token count not available from bobshell
