"""Factory: get_client(config) -> LLMClient instance."""
from __future__ import annotations
from code_analyser import config as cfg


def get_client():
    """
    Returns an LLM client based on LLM_PROVIDER env var.

    Providers:
      watsonx   — IBM watsonx.ai (needs WATSONX_API_KEY etc.)
      groq      — Groq free tier (needs GROQ_API_KEY, free at console.groq.com)
      openai    — OpenAI-compatible (needs OPENAI_API_KEY, also works with Ollama)
      bobshell  — local bobshell subprocess (dev only)
      fake      — canned responses for tests
    """
    provider = cfg.LLM_PROVIDER.lower()
    if provider == "watsonx":
        from code_analyser.llm.watsonx_client import WatsonxClient
        return WatsonxClient()
    elif provider == "groq":
        from code_analyser.llm.groq_client import GroqClient
        return GroqClient()
    elif provider == "openai":
        from code_analyser.llm.openai_client import OpenAIClient
        return OpenAIClient()
    elif provider == "bobshell":
        from code_analyser.llm.bobshell_client import BobShellClient
        return BobShellClient()
    elif provider == "fake":
        from code_analyser.llm.fake_client import FakeLLMClient
        return FakeLLMClient()
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: {provider!r}. "
            "Choose: watsonx, groq, openai, bobshell, fake"
        )
