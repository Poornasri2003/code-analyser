"""CLI entry point: analyser analyse | ask | graph-stats"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def _get_orchestrator(provider: str = None):
    from code_analyser import config
    from code_analyser.llm.factory import get_client
    from code_analyser.store.factory import get_store
    from code_analyser.orchestrator import Orchestrator

    if provider:
        os.environ["LLM_PROVIDER"] = provider
        # reload config
        import importlib
        import code_analyser.config as cfg_mod
        importlib.reload(cfg_mod)

    client = get_client()
    store_type = os.getenv("STORE_TYPE", "neo4j")
    store = get_store(store_type)

    workdir = Path(os.getenv("ANALYSER_WORKDIR", "/tmp/code_analyser_work"))
    return Orchestrator(client=client, store=store, workdir=workdir)


@click.group()
def main():
    """Code Analyser — unstructured code in, structured graph out."""
    pass


@main.command("analyse")
@click.argument("source")
@click.option("--user", default="default", help="User ID (tenant isolation)")
@click.option("--run", "run_id", default=None, help="Run ID (auto-generated if omitted)")
@click.option("--max-files", default=None, type=int, help="Override max files limit")
@click.option("--provider", default=None, help="LLM provider: watsonx|bobshell|fake")
def analyse_cmd(source: str, user: str, run_id: str, max_files: int, provider: str):
    """Analyse a GitHub URL, ZIP file, or local directory."""
    orchestrator = _get_orchestrator(provider)

    console.print(f"[bold blue]Analysing[/bold blue]: {source}")
    console.print(f"User: {user}  Run: {run_id or '(auto)'}")

    report = orchestrator.analyse(source, user_id=user, run_id=run_id, max_files=max_files)

    table = Table(title="Run Report", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Run ID", report.run_id)
    table.add_row("Files total", str(report.files_total))
    table.add_row("Files processed", str(report.files_processed))
    table.add_row("Files skipped", str(report.files_skipped))
    table.add_row("Files failed", str(report.files_failed))
    table.add_row("Nodes written", str(report.nodes_written))
    table.add_row("Edges written", str(report.edges_written))
    table.add_row("Nodes dropped", str(report.nodes_dropped))
    table.add_row("Edges dropped", str(report.edges_dropped))
    table.add_row("Elapsed (s)", f"{report.elapsed_seconds:.1f}")

    console.print(table)

    if report.failures:
        console.print(f"[yellow]Failures ({len(report.failures)}):[/yellow]")
        for f in report.failures:
            console.print(f"  {f['label']}: {f['error'][:120]}")


@main.command("ask")
@click.argument("question")
@click.option("--user", default="default", help="User ID")
@click.option("--run", "run_id", required=True, help="Run ID to query")
@click.option("--k", default=8, type=int, help="Number of top nodes to retrieve")
@click.option("--provider", default=None, help="LLM provider")
def ask_cmd(question: str, user: str, run_id: str, k: int, provider: str):
    """Ask a natural-language question about an analysed codebase."""
    orchestrator = _get_orchestrator(provider)

    console.print(f"[bold blue]Question:[/bold blue] {question}")
    result = orchestrator.ask(question, user_id=user, run_id=run_id, k=k)

    grounded = result.get("grounded", False)
    answer = result.get("answer", "")
    citations = result.get("citations", [])

    status = "[green]GROUNDED[/green]" if grounded else "[red]NOT GROUNDED[/red]"
    console.print(Panel(answer, title=f"Answer {status}", border_style="blue"))

    if citations:
        ctable = Table(title="Citations", show_header=True, header_style="bold")
        ctable.add_column("Node ID")
        ctable.add_column("Path")
        ctable.add_column("Lines")
        for c in citations:
            lines = f"{c.get('line_start', '')}-{c.get('line_end', '')}"
            ctable.add_row(c.get("node_id", ""), c.get("path", ""), lines)
        console.print(ctable)


@main.command("graph-stats")
@click.option("--user", default="default", help="User ID")
@click.option("--run", "run_id", default=None, help="Run ID (all runs if omitted)")
def graph_stats_cmd(user: str, run_id: str):
    """Show graph statistics for a user/run."""
    from code_analyser.store.factory import get_store
    store_type = os.getenv("STORE_TYPE", "neo4j")
    store = get_store(store_type)

    # For Neo4j store, query counts
    if hasattr(store, "_driver"):
        with store._driver.session() as session:
            if run_id:
                res = session.run(
                    "MATCH (n:Node {user_id: $u, run_id: $r}) RETURN count(n) AS nc",
                    u=user, r=run_id,
                )
                nc = res.single()["nc"]
                res2 = session.run(
                    """MATCH (a:Node {user_id: $u, run_id: $r})-[e:REL]->(b:Node {user_id: $u, run_id: $r})
                    RETURN count(e) AS ec""",
                    u=user, r=run_id,
                )
                ec = res2.single()["ec"]
                console.print(f"Run [bold]{run_id}[/bold]: {nc} nodes, {ec} edges")
            else:
                res = session.run(
                    "MATCH (n:Node {user_id: $u}) RETURN n.run_id AS rid, count(n) AS nc",
                    u=user,
                )
                for record in res:
                    console.print(f"  Run {record['rid']}: {record['nc']} nodes")
    else:
        # InMemory
        nodes = [n for n in store._nodes.values() if n.get("user_id") == user]
        if run_id:
            nodes = [n for n in nodes if n.get("run_id") == run_id]
        console.print(f"Nodes: {len(nodes)}")


if __name__ == "__main__":
    main()
