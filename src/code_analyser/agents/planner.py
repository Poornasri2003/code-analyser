"""Planner agent — routes files to code/doc/skip."""
from __future__ import annotations
from pathlib import Path
from typing import List

from code_analyser.models import ManifestEntry, PlannerOutput, RouteEntry
from code_analyser.llm.fake_client import FakeLLMClient


def run_planner(
    root: Path,
    manifest: List[ManifestEntry],
    client,
) -> PlannerOutput:
    """Call the LLM planner and return a PlannerOutput.

    The LLM is expected to return a dict matching PlannerOutput schema.
    If any manifest path is missing from the LLM routes, it is added as 'skip'.
    """
    system = "You are a code analysis planner. Route each file to code, doc, or skip."
    user = f"Files: {[e.path for e in manifest]}"

    raw, _ = client.complete_json(system, user)

    # Parse routes
    routes_raw = raw.get("routes", [])
    plan = PlannerOutput(
        kind=raw.get("kind", "code"),
        reasoning=raw.get("reasoning", ""),
        project_summary=raw.get("project_summary", ""),
        routes=[RouteEntry.model_validate(r) for r in routes_raw],
    )

    # Ensure every manifest path appears exactly once
    routed = {r.path for r in plan.routes}
    for entry in manifest:
        if entry.path not in routed:
            plan.routes.append(RouteEntry(path=entry.path, route="skip", priority=3, reason="not routed by planner"))

    return plan
