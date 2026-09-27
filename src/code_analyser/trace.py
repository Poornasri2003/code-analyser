"""Run tracing: what each agent asked the LLM, what came back, how long it took.

The orchestrator does not know about tracing. A run is observed by wrapping its
LLM client, so every model call is recorded wherever it happens.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional


class TraceLog:
    """An ordered list of events for one run."""

    def __init__(self, limit: int = 400) -> None:
        self.events: List[Dict[str, Any]] = []
        self.started = time.time()
        self._limit = limit

    def add(self, stage: str, event: str, **detail: Any) -> Dict[str, Any]:
        rec = {
            "at": round(time.time() - self.started, 2),
            "stage": stage,
            "event": event,
            **detail,
        }
        if len(self.events) < self._limit:
            self.events.append(rec)
        return rec

    @property
    def total_tokens(self) -> int:
        return sum(e.get("tokens") or 0 for e in self.events)

    @property
    def llm_calls(self) -> int:
        return sum(1 for e in self.events if e.get("event") == "llm_call")

    def summary(self) -> Dict[str, Any]:
        by_stage: Dict[str, Dict[str, Any]] = {}
        for e in self.events:
            if e.get("event") != "llm_call":
                continue
            s = by_stage.setdefault(e["stage"], {"calls": 0, "tokens": 0, "seconds": 0.0})
            s["calls"] += 1
            s["tokens"] += e.get("tokens") or 0
            s["seconds"] = round(s["seconds"] + (e.get("seconds") or 0), 2)
        return {
            "llm_calls": self.llm_calls,
            "total_tokens": self.total_tokens,
            "by_stage": by_stage,
        }


class TracingLLMClient:
    """Records every complete_json call against the current stage.

    Wrapping the client is what makes tracing complete: agents call the model
    through this object, so none of them need to know they are being watched.
    """

    def __init__(self, inner: Any, log: TraceLog) -> None:
        self._inner = inner
        self._log = log
        self.stage = "unknown"

    def complete_json(self, system: str, user: str, max_tokens: int = 4096):
        t0 = time.time()
        try:
            out, tokens = self._inner.complete_json(system, user, max_tokens=max_tokens)
        except Exception as e:
            self._log.add(
                self.stage, "llm_call", ok=False,
                seconds=round(time.time() - t0, 2),
                prompt_chars=len(system) + len(user),
                error=str(e)[:300],
            )
            raise
        node_count = len(out.get("nodes") or []) if isinstance(out, dict) else 0
        rel_count = len(out.get("relationships") or []) if isinstance(out, dict) else 0
        self._log.add(
            self.stage, "llm_call", ok=True,
            seconds=round(time.time() - t0, 2),
            tokens=tokens,
            prompt_chars=len(system) + len(user),
            returned_keys=sorted(out.keys())[:8] if isinstance(out, dict) else [],
            nodes=node_count, relationships=rel_count,
        )
        return out, tokens

    def __getattr__(self, item):
        return getattr(self._inner, item)
