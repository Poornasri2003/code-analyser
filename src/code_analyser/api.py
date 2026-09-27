"""FastAPI web application for Code Analyser — public deployment interface."""
from __future__ import annotations
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="Code Analyser",
    description="Unstructured code in, structured knowledge graph out. Powered by IBM Bob 2.0.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store for demo
_jobs: Dict[str, Dict[str, Any]] = {}

MAX_UPLOAD_BYTES = int(os.getenv("ANALYSER_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


_store = None


def _get_store():
    # The in-memory store holds the graph in the instance itself, so a fresh
    # one per request would lose everything /analyse just wrote.
    global _store
    if _store is None:
        from code_analyser.store.factory import get_store
        _store = get_store(os.getenv("STORE_TYPE", "neo4j"))
    return _store


def _get_orchestrator(trace=None):
    from code_analyser.llm.factory import get_client
    from code_analyser.orchestrator import Orchestrator
    from code_analyser.trace import TracingLLMClient

    client = get_client()
    if trace is not None:
        client = TracingLLMClient(client, trace)
    workdir = Path(os.getenv("ANALYSER_WORKDIR", "/tmp/code_analyser_work"))
    orch = Orchestrator(client=client, store=_get_store(), workdir=workdir)
    orch.trace = trace
    return orch


class AnalyseRequest(BaseModel):
    source: str
    user_id: str = "demo"
    run_id: Optional[str] = None
    max_files: Optional[int] = None


class AskRequest(BaseModel):
    question: str
    user_id: str = "demo"
    run_id: str
    k: int = 8
    # Earlier turns, so a follow-up like "and what calls that?" can be resolved.
    history: List[Dict[str, str]] = []


_WEB_DIR = Path(__file__).parent / "web"


@app.get("/", response_class=HTMLResponse)
async def index():
    # Read per request so a redeploy never serves a stale page from memory.
    page = _WEB_DIR / "index.html"
    if not page.exists():
        return HTMLResponse("<h1>Code Analyser</h1><p>UI file missing.</p>", status_code=500)
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    provider = os.getenv("LLM_PROVIDER", "watsonx").lower()
    model = {
        "groq": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        "watsonx": os.getenv("WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct"),
        "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }.get(provider, provider)
    return {"status": "ok", "service": "code-analyser",
            "llm_provider": provider, "model": model,
            "store": os.getenv("STORE_TYPE", "neo4j")}


@app.post("/analyse")
async def analyse(req: AnalyseRequest, background_tasks: BackgroundTasks):
    """Start an analysis run. Returns run_id immediately, processes in background."""
    import threading
    run_id = req.run_id or str(uuid.uuid4())[:8]
    job_id = run_id

    from code_analyser.trace import TraceLog
    trace = TraceLog()
    _jobs[job_id] = {"status": "running", "run_id": run_id, "report": None,
                     "error": None, "_trace": trace}

    def _run():
        try:
            orch = _get_orchestrator(trace)
            report = orch.analyse(
                req.source,
                user_id=req.user_id,
                run_id=run_id,
                max_files=req.max_files,
            )
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["report"] = report.model_dump()
        except Exception as e:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {"job_id": job_id, "run_id": run_id, "status": "running"}


@app.post("/analyse-upload")
async def analyse_upload(
    file: UploadFile = File(...),
    user_id: str = Form("demo"),
    max_files: Optional[int] = Form(None),
):
    """Analyse an uploaded .zip. A local path means nothing to a remote server,
    so uploads are the only way to analyse a non-public codebase."""
    import threading
    import tempfile

    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported")

    upload_root = Path(tempfile.mkdtemp(prefix="ca_upload_"))
    saved = upload_root / "upload.zip"
    size = 0
    with saved.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Upload exceeds {MAX_UPLOAD_BYTES // (1024*1024)}MB limit",
                )
            fh.write(chunk)

    run_id = str(uuid.uuid4())[:8]
    from code_analyser.trace import TraceLog
    trace = TraceLog()
    _jobs[run_id] = {"status": "running", "run_id": run_id, "report": None,
                     "error": None, "_trace": trace}

    def _run():
        try:
            orch = _get_orchestrator(trace)
            report = orch.analyse(
                str(saved), user_id=user_id, run_id=run_id, max_files=max_files
            )
            _jobs[run_id]["status"] = "done"
            _jobs[run_id]["report"] = report.model_dump()
        except Exception as e:
            _jobs[run_id]["status"] = "error"
            _jobs[run_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"job_id": run_id, "run_id": run_id, "status": "running"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    trace = job.get("_trace")
    out = {k: v for k, v in job.items() if not k.startswith("_")}
    if trace is not None:
        # Live: the UI polls this while the run is still going.
        out["trace"] = trace.events
        out["trace_summary"] = trace.summary()
        last = trace.events[-1] if trace.events else None
        out["current"] = last["stage"] if last else "starting"
    return out


@app.get("/trace/{job_id}")
async def get_trace(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    trace = _jobs[job_id].get("_trace")
    if trace is None:
        raise HTTPException(status_code=404, detail="No trace for this run")
    return {"run_id": job_id, "summary": trace.summary(), "events": trace.events}


@app.get("/graph/{run_id}")
async def graph(run_id: str, user_id: str = "demo"):
    """Nodes and edges for the graph view."""
    nodes, edges = _collect_graph(user_id, run_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="No graph for this run")
    ids = {n["id"] for n in nodes}
    return {
        "nodes": [
            {"id": n["id"], "name": n.get("name"), "type": n.get("type"),
             "path": n.get("path"), "description": n.get("description"),
             "line_start": n.get("line_start"), "line_end": n.get("line_end")}
            for n in nodes
        ],
        "edges": [
            {"source": e.get("source_id"), "target": e.get("target_id"),
             "type": e.get("type"), "description": e.get("description")}
            for e in edges
            if e.get("source_id") in ids and e.get("target_id") in ids
        ],
    }


def _collect_graph(user_id: str, run_id: str):
    store = _get_store()
    if hasattr(store, "query_all"):
        return store.query_all(user_id, run_id)
    return store.query_nodes(user_id, run_id, limit=500), []


# One overview per run: it reads the whole graph, so it is worth reusing.
_overviews: Dict[str, Dict[str, Any]] = {}

_OVERVIEW_CODE = """You are Code Analyser, an onboarding assistant. A developer has just \
joined this project and must become productive in the codebase quickly, without \
reading every file. Using ONLY the graph below, which was extracted from the \
repository, write the briefing they need. Nodes have an [id], type, name, location \
and description; RELATIONSHIPS show who CALLS, IMPORTS, READS, WRITES or CONTAINS whom.

Return ONE json object with exactly these keys:
{
  "title": "what this project is, in 3-8 words",
  "summary": "What the project is, what problem it solves and who uses it. 3-5 plain sentences.",
  "architecture": "How it is organised: the main layers or modules and how they depend on each other. 2-4 sentences.",
  "flow": [{"step": "what happens at this point, in plain language", "where": "path::symbol"}],
  "components": [{"file": "path", "role": "what this file is responsible for",
                  "key_symbols": [{"name": "symbol", "does": "what it does",
                                   "inputs": "what it takes", "outputs": "what it returns or changes"}]}],
  "key_concepts": [{"term": "a project-specific name or idea", "meaning": "what it means here"}],
  "data": ["what data the project holds or passes around, and where it lives"],
  "entry_points": [{"where": "path::symbol", "why": "how execution or usage starts here"}],
  "extend": [{"task": "a realistic change a newcomer might be asked to make",
              "where": "path::symbol to change", "impact": "what else that touches"}],
  "reading_order": [{"target": "path", "why": "why read it at this point"}],
  "gotchas": ["surprising behaviour, hidden coupling or missing pieces a newcomer should know"],
  "suggested_questions": ["questions a newcomer should ask next, naming real functions"]
}

Rules:
- Name only files and symbols that appear in the graph. Never invent anything.
- flow: 4-10 steps that follow the RELATIONSHIPS from an entry point to where the work
  is done. Walk the edges; do not simply list files.
- components: most important file first, at most 8 files and 5 symbols each.
- extend: 3-5 entries based on where the graph shows the code is built to grow.
- key_concepts at most 8, reading_order at most 6, gotchas at most 5,
  suggested_questions exactly 4.
- Write for someone who has never seen the project: plain words, short sentences."""

_OVERVIEW_DOCS = """You are Code Analyser, an onboarding assistant. Someone has been \
handed these documents and must understand them quickly without reading them end to \
end. Using ONLY the graph below, which was extracted from the documents, write the \
briefing they need. Nodes have an [id], type, name, location and description; \
RELATIONSHIPS show how sections, concepts and entities connect.

Return ONE json object with exactly these keys:
{
  "title": "what these documents are, in 3-8 words",
  "summary": "What the documents cover, why they exist and who they are for. 3-5 plain sentences.",
  "architecture": "How the material is organised and how the documents relate. 2-4 sentences.",
  "flow": [{"step": "a main point, in the order it is presented", "where": "document#section"}],
  "components": [{"file": "document", "role": "what this document is for",
                  "key_symbols": [{"name": "topic or section", "does": "what it says"}]}],
  "key_concepts": [{"term": "a defined term, role or idea", "meaning": "what it means here"}],
  "data": ["key facts, figures, dates, obligations or rules"],
  "entry_points": [{"where": "document#section", "why": "why start reading here"}],
  "extend": [{"task": "a situation where a reader would need to act on this material",
              "where": "document#section to consult", "impact": "what else in the material it affects"}],
  "reading_order": [{"target": "document", "why": "why read it at this point"}],
  "gotchas": ["exceptions, conditions, contradictions or gaps a reader could miss"],
  "suggested_questions": ["questions a reader should ask next about this material"]
}

Rules:
- Name only documents, sections and terms that appear in the graph. Never invent.
- flow 4-10 items, components at most 8, key_concepts at most 8, extend 3-5,
  reading_order at most 6, gotchas at most 5, suggested_questions exactly 4.
- Plain words, short sentences."""


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


@app.get("/overview/{run_id}")
def overview(run_id: str, user_id: str = "demo", refresh: bool = False):
    """An onboarding briefing built from the whole graph, not a retrieved slice."""
    from code_analyser import config
    from code_analyser.graph_context import looks_like_code, render_context
    from code_analyser.llm.factory import get_client
    from code_analyser.llm.protocol import LLMFormatError

    key = f"{user_id}|{run_id}"
    if key in _overviews and not refresh:
        return _overviews[key]

    nodes, edges = _collect_graph(user_id, run_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="No graph for this run")

    is_code = looks_like_code(nodes)
    context, shown = render_context(
        nodes, edges, config.OVERVIEW_CONTEXT_CHARS, group_by_file=True
    )
    system = _OVERVIEW_CODE if is_code else _OVERVIEW_DOCS
    user = "GRAPH:\n" + context

    client = get_client()
    raw = None
    for extra in ("", "\n\nBe concise: at most 4 items in every list, under 25 words per item."):
        try:
            raw, _ = client.complete_json(system + extra, user,
                                          max_tokens=config.OVERVIEW_MAX_TOKENS)
            break
        except LLMFormatError:
            continue  # usually a reply cut off at the token limit; ask for less
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Overview failed: {e}")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=502, detail="The model did not return a usable overview")

    result: Dict[str, Any] = {
        "title": str(raw.get("title") or ""),
        "summary": str(raw.get("summary") or ""),
        "architecture": str(raw.get("architecture") or ""),
    }
    for k in ("flow", "components", "key_concepts", "data", "entry_points",
              "extend", "reading_order", "gotchas", "suggested_questions"):
        result[k] = _as_list(raw.get(k))

    files = {n.get("path") for n in nodes if n.get("path")}
    by_type: Dict[str, int] = {}
    for n in nodes:
        by_type[n.get("type", "?")] = by_type.get(n.get("type", "?"), 0) + 1
    result["kind"] = "codebase" if is_code else "documents"
    result["stats"] = {"nodes": len(nodes), "edges": len(edges),
                       "files": len(files), "by_type": by_type}
    # Tells the reader when a large graph had to be trimmed to fit the model.
    result["coverage"] = {"nodes_shown": len(shown), "nodes_total": len(nodes)}
    _overviews[key] = result
    return result


@app.get("/symbols/{run_id}")
async def symbols(run_id: str, user_id: str = "demo", name: Optional[str] = None):
    """Every function and class with its signature, callers and callees, read
    straight from the graph with no LLM call."""
    from code_analyser.graph_context import CODE_TYPES, node_props

    nodes, edges = _collect_graph(user_id, run_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="No graph for this run")
    by_id = {n["id"]: n for n in nodes}

    out = []
    for n in nodes:
        if n.get("type") not in CODE_TYPES:
            continue
        if name and name.lower() not in (n.get("name") or "").lower():
            continue
        calls, called_by = [], []
        for e in edges:
            src, tgt = by_id.get(e.get("source_id")), by_id.get(e.get("target_id"))
            if e.get("source_id") == n["id"] and tgt and e.get("type") != "CONTAINS":
                calls.append({"id": tgt["id"], "name": tgt.get("name"),
                              "type": e.get("type"), "path": tgt.get("path")})
            if e.get("target_id") == n["id"] and src and e.get("type") != "CONTAINS":
                called_by.append({"id": src["id"], "name": src.get("name"),
                                  "type": e.get("type"), "path": src.get("path")})
        props = node_props(n)
        out.append({
            "id": n["id"],
            "name": n.get("name"),
            "type": n.get("type"),
            "path": n.get("path"),
            "lines": [n.get("line_start"), n.get("line_end")],
            "description": n.get("description"),
            "signature": props.get("signature"),
            "inputs": props.get("inputs"),
            "outputs": props.get("outputs"),
            "calls": calls,
            "called_by": called_by,
        })
    out.sort(key=lambda s: ((s["path"] or ""), s["lines"][0] or 0))
    return {"run_id": run_id, "count": len(out), "symbols": out}


@app.post("/ask")
def ask(req: AskRequest):
    """Ask about an analysed codebase. Plain def: the LLM call blocks, and FastAPI
    runs sync handlers in a thread pool so polling stays responsive meanwhile."""
    try:
        orch = _get_orchestrator()
        return orch.ask(req.question, user_id=req.user_id, run_id=req.run_id,
                        k=req.k, history=req.history)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def start_api(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("code_analyser.api:app", host=host, port=port, reload=False)
