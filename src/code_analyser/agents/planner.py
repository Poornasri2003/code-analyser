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
    system = (
        "You are Code Analyser's Planner. You decide how each file in a project "
        "should be analysed. Return ONE json object with exactly these keys:\n"
        "{\n"
        '  "kind": "code" | "docs" | "mixed" | "data",\n'
        '  "reasoning": "two sentences on how you decided",\n'
        '  "project_summary": "what this project appears to be, 2-3 sentences",\n'
        '  "routes": [\n'
        '    {"path": "<exact path from the list>", "route": "code"|"doc"|"skip",\n'
        '     "priority": 1|2|3, "reason": "<only when route is skip>"}\n'
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        '- route "code" for any file containing functions, classes or modules '
        "(.py, .js, .ts, .java, .go, .rs, .rb, .c, .cpp, .cs, Dockerfile, Makefile).\n"
        '- route "doc" for prose, specs, configs and schemas '
        "(.md, .txt, .rst, .yaml, .yml, .json, .toml, .ini, .cfg, LICENSE).\n"
        '- route "skip" ONLY for generated, vendored, minified or lockfile content, '
        "and always give a reason. Never skip a file just because it is small.\n"
        "- priority 1 for entry points and core modules, 2 for normal files, "
        "3 for tests and peripheral files.\n"
        "- EVERY path from the input list must appear exactly once in routes, "
        "copied character for character. Do not invent paths."
    )
    listing = "\n".join(
        f"- {e.path} ({e.line_count} lines, {e.size or e.size_bytes} bytes)"
        for e in manifest
    )
    user = (
        f"Route every one of these {len(manifest)} files. "
        f"Return json with one routes entry per path.\n\n{listing}"
    )

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
