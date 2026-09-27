"""Factory: get_client(config) -> LLMClient instance."""
from __future__ import annotations
from code_analyser import config as cfg


def get_client():
    provider = cfg.LLM_PROVIDER.lower()
    if provider == "watsonx":
        from code_analyser.llm.watsonx_client import WatsonxClient
        return WatsonxClient()
    elif provider == "bobshell":
        from code_analyser.llm.bobshell_client import BobShellClient
        return BobShellClient()
    elif provider == "fake":
        from code_analyser.llm.fake_client import FakeLLMClient
        return FakeLLMClient()
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}. Choose watsonx, bobshell, or fake.")
