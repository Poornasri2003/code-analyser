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


def _get_orchestrator():
    from code_analyser.llm.factory import get_client
    from code_analyser.orchestrator import Orchestrator

    client = get_client()
    workdir = Path(os.getenv("ANALYSER_WORKDIR", "/tmp/code_analyser_work"))
    return Orchestrator(client=client, store=_get_store(), workdir=workdir)


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


@app.get("/", response_class=HTMLResponse)
async def index():
    """Landing page with simple UI."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Code Analyser — IBM Bob 2.0 Hackathon</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
           background: #0f1117; color: #e6edf3; min-height: 100vh; }
    .header { background: linear-gradient(135deg, #1f2937 0%, #111827 100%);
              border-bottom: 1px solid #30363d; padding: 24px 32px;
              display: flex; align-items: center; gap: 16px; }
    .header h1 { font-size: 1.5rem; font-weight: 700; color: #58a6ff; }
    .header p { color: #8b949e; font-size: 0.875rem; margin-top: 4px; }
    .badge { background: #1d4ed8; color: #93c5fd; padding: 2px 10px;
             border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
    .container { max-width: 960px; margin: 0 auto; padding: 32px 24px; }
    .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px;
            padding: 28px; margin-bottom: 24px; }
    .card h2 { font-size: 1.1rem; font-weight: 600; margin-bottom: 16px;
               color: #f0f6fc; display: flex; align-items: center; gap: 8px; }
    label { display: block; font-size: 0.875rem; color: #8b949e;
            margin-bottom: 6px; margin-top: 14px; }
    input, textarea { width: 100%; background: #0d1117; border: 1px solid #30363d;
             border-radius: 8px; padding: 10px 14px; color: #e6edf3;
             font-size: 0.9rem; outline: none; transition: border-color 0.2s; }
    input:focus, textarea:focus { border-color: #58a6ff; }
    button { background: #1f6feb; color: #fff; border: none; border-radius: 8px;
             padding: 10px 22px; font-size: 0.9rem; font-weight: 600;
             cursor: pointer; margin-top: 16px; transition: background 0.2s; }
    button:hover { background: #388bfd; }
    button.secondary { background: #21262d; color: #e6edf3;
                       border: 1px solid #30363d; }
    button.secondary:hover { background: #30363d; }
    .result { background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
              padding: 16px; margin-top: 16px; white-space: pre-wrap;
              font-family: monospace; font-size: 0.85rem; color: #7ee787;
              max-height: 400px; overflow-y: auto; display: none; }
    .result.visible { display: block; }
    .grounded-yes { color: #3fb950; }
    .grounded-no { color: #f85149; }
    .tabs { display: flex; gap: 4px; margin-bottom: 24px; }
    .tab { padding: 8px 20px; border-radius: 6px; cursor: pointer;
           font-size: 0.875rem; font-weight: 500; border: 1px solid #30363d;
           background: transparent; color: #8b949e; transition: all 0.2s; }
    .tab.active { background: #1f6feb; color: #fff; border-color: #1f6feb; }
    .section { display: none; }
    .section.active { display: block; }
    .spinner { display: none; width: 20px; height: 20px; border: 2px solid #30363d;
               border-top-color: #58a6ff; border-radius: 50%;
               animation: spin 0.8s linear infinite; margin: 12px auto; }
    .spinner.visible { display: block; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .answer-box { background: #0d1117; border: 1px solid #30363d; border-radius: 8px;
                  padding: 20px; margin-top: 16px; line-height: 1.7; display: none; }
    .answer-box.visible { display: block; }
    .citations { margin-top: 12px; }
    .citation { font-size: 0.8rem; color: #8b949e; font-family: monospace;
                padding: 2px 0; }
    .run-id-display { font-family: monospace; background: #21262d;
                      padding: 4px 10px; border-radius: 4px; font-size: 0.85rem;
                      color: #58a6ff; margin-top: 8px; display: inline-block; }
  </style>
</head>
<body>
  <div class="header">
    <div>
      <h1>⬡ Code Analyser</h1>
      <p>Unstructured code in, structured knowledge graph out</p>
    </div>
    <span class="badge">IBM Bob 2.0 Hackathon</span>
  </div>
  <div class="container">
    <div class="tabs">
      <button class="tab active" onclick="switchTab('analyse')">Analyse</button>
      <button class="tab" onclick="switchTab('ask')">Ask</button>
      <button class="tab" onclick="switchTab('api')">API Docs</button>
    </div>

    <div id="tab-analyse" class="section active">
      <div class="card">
        <h2>🔍 Analyse a Codebase</h2>
        <label>GitHub URL</label>
        <input id="source" type="text" placeholder="https://github.com/owner/repo" />
        <div style="text-align:center;color:#8b949e;margin:10px 0">— or —</div>
        <label>Upload a .zip of your codebase or documents</label>
        <input id="zipfile" type="file" accept=".zip" />
        <label>User ID (for tenant isolation)</label>
        <input id="user_id" type="text" value="demo" />
        <label>Max files (optional)</label>
        <input id="max_files" type="number" placeholder="6" />
        <br/>
        <button onclick="analyse()">Analyse →</button>
        <div class="spinner" id="analyse-spinner"></div>
        <div class="result" id="analyse-result"></div>
        <div id="run-id-holder" style="display:none">
          Run ID: <span class="run-id-display" id="run-id-value"></span>
          <br/><small style="color:#8b949e">Copy this to use in the Ask tab</small>
        </div>
      </div>
    </div>

    <div id="tab-ask" class="section">
      <div class="card">
        <h2>💬 Ask a Question</h2>
        <label>Run ID (from Analyse step)</label>
        <input id="ask-run-id" type="text" placeholder="abc12345" />
        <label>User ID</label>
        <input id="ask-user-id" type="text" value="demo" />
        <label>Question</label>
        <textarea id="question" rows="3"
          placeholder="How does authentication work? What does the parse_token function do?"></textarea>
        <label>Top-k nodes (default 8)</label>
        <input id="k" type="number" value="8" />
        <br/>
        <button onclick="askQuestion()">Ask →</button>
        <div class="spinner" id="ask-spinner"></div>
        <div class="answer-box" id="answer-box">
          <div id="grounded-badge"></div>
          <div id="answer-text" style="margin-top:8px; color:#e6edf3"></div>
          <div class="citations" id="citations"></div>
        </div>
      </div>
    </div>

    <div id="tab-api" class="section">
      <div class="card">
        <h2>📖 API Reference</h2>
        <p style="color:#8b949e; margin-bottom:16px">
          Full OpenAPI docs at <a href="/docs" style="color:#58a6ff">/docs</a>
        </p>
        <pre style="background:#0d1117; border:1px solid #30363d; border-radius:8px;
                    padding:16px; font-size:0.82rem; overflow-x:auto; color:#7ee787">
POST /analyse
{
  "source": "https://github.com/owner/repo",
  "user_id": "demo",
  "run_id": "optional-custom-id",
  "max_files": 200
}

POST /ask
{
  "question": "How does authentication work?",
  "user_id": "demo",
  "run_id": "your-run-id",
  "k": 8
}

GET /jobs/{job_id}          # poll analyse job status
GET /health                 # health check
        </pre>
      </div>
    </div>
  </div>

  <script>
    function switchTab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById('tab-' + name).classList.add('active');
    }

    async function analyse() {
      const source = document.getElementById('source').value.trim();
      const zipInput = document.getElementById('zipfile');
      const zipFile = zipInput && zipInput.files.length ? zipInput.files[0] : null;
      if (!source && !zipFile) { alert('Enter a GitHub URL or choose a .zip file'); return; }
      const user_id = document.getElementById('user_id').value || 'demo';
      const max_files = document.getElementById('max_files').value;

      document.getElementById('analyse-spinner').classList.add('visible');
      document.getElementById('analyse-result').classList.remove('visible');
      document.getElementById('run-id-holder').style.display = 'none';

      const out = document.getElementById('analyse-result');
      const show = (t) => { out.innerHTML = t; out.classList.add('visible'); };

      try {
        let data;
        if (zipFile) {
          const fd = new FormData();
          fd.append('file', zipFile);
          fd.append('user_id', user_id);
          if (max_files) fd.append('max_files', max_files);
          const resp = await fetch('/analyse-upload', { method: 'POST', body: fd });
          data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || 'Upload failed');
        } else {
          const body = { source, user_id };
          if (max_files) body.max_files = parseInt(max_files);
          const resp = await fetch('/analyse', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(body)
          });
          data = await resp.json();
          if (!resp.ok) throw new Error(data.detail || 'Analyse failed');
        }

        const job = data.job_id;
        document.getElementById('run-id-value').textContent = data.run_id;
        document.getElementById('run-id-holder').style.display = 'block';
        document.getElementById('ask-run-id').value = data.run_id;

        // The run happens in the background, so poll until it finishes.
        let report = null;
        for (let i = 0; i < 400; i++) {
          show('Reading files and building the graph… (' + (i * 3) + 's)');
          await new Promise(r => setTimeout(r, 3000));
          const s = await (await fetch('/jobs/' + job)).json();
          if (s.status === 'error') throw new Error(s.error);
          if (s.status === 'done') { report = s.report; break; }
        }
        if (!report) throw new Error('Timed out');

        show('Graph built: <b>' + report.nodes_written + '</b> nodes, <b>' +
             report.edges_written + '</b> relationships from <b>' +
             report.files_processed + '</b> files. Writing the explanation…');

        const ov = await (await fetch('/overview/' + data.run_id +
                                      '?user_id=' + encodeURIComponent(user_id))).json();
        renderOverview(ov, report);
      } catch (e) {
        show('<span style="color:#f85149">Error: ' + e.message + '</span>');
      } finally {
        document.getElementById('analyse-spinner').classList.remove('visible');
      }
    }

    function renderOverview(ov, report) {
      const esc = s => String(s == null ? '' : s)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      let h = '<h3 style="margin-top:0">' +
              (ov.kind === 'codebase' ? 'Codebase explained' : 'Documents explained') +
              '</h3>';
      h += '<p>' + esc(ov.summary) + '</p>';
      if (ov.flow && ov.flow.length) {
        h += '<h4>How it works, step by step</h4><ol>';
        ov.flow.forEach(s => h += '<li>' + esc(s) + '</li>');
        h += '</ol>';
      }
      if (ov.entry_points && ov.entry_points.length) {
        h += '<h4>Entry points</h4><ul>';
        ov.entry_points.forEach(s => h += '<li>' + esc(s) + '</li>');
        h += '</ul>';
      }
      if (ov.components && ov.components.length) {
        h += '<h4>Components</h4>';
        ov.components.forEach(c => {
          h += '<div style="margin:8px 0;padding:8px;background:#0d1117;border-radius:6px">' +
               '<b>' + esc(c.file) + '</b> — ' + esc(c.role);
          if (c.key_symbols && c.key_symbols.length) {
            h += '<ul>';
            c.key_symbols.forEach(k => h += '<li>' + esc(k) + '</li>');
            h += '</ul>';
          }
          h += '</div>';
        });
      }
      if (ov.how_to_explore && ov.how_to_explore.length) {
        h += '<h4>Where to start reading</h4><ul>';
        ov.how_to_explore.forEach(s => h += '<li>' + esc(s) + '</li>');
        h += '</ul>';
      }
      const st = ov.stats || {};
      h += '<p style="color:#8b949e;font-size:13px">' + st.nodes + ' nodes · ' +
           st.edges + ' relationships · ' + st.files + ' files · ' +
           JSON.stringify(st.by_type || {}) + '</p>';
      h += '<p style="color:#8b949e;font-size:13px">Now switch to the ' +
           '<b>Ask</b> tab — the Run ID is already filled in.</p>';
      const out = document.getElementById('analyse-result');
      out.innerHTML = h; out.classList.add('visible');
    }

    async function askQuestion() {
      const question = document.getElementById('question').value.trim();
      const run_id = document.getElementById('ask-run-id').value.trim();
      const user_id = document.getElementById('ask-user-id').value || 'demo';
      const k = parseInt(document.getElementById('k').value) || 8;

      if (!question) { alert('Enter a question'); return; }
      if (!run_id) { alert('Enter a Run ID from the Analyse step'); return; }

      document.getElementById('ask-spinner').classList.add('visible');
      document.getElementById('answer-box').classList.remove('visible');

      try {
        const resp = await fetch('/ask', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ question, user_id, run_id, k })
        });
        const data = await resp.json();

        const badge = document.getElementById('grounded-badge');
        badge.innerHTML = data.grounded
          ? '<span class="grounded-yes">✓ GROUNDED</span>'
          : '<span class="grounded-no">✗ NOT GROUNDED</span>';

        document.getElementById('answer-text').textContent = data.answer || '';

        const citsEl = document.getElementById('citations');
        citsEl.innerHTML = '';
        if (data.citations && data.citations.length > 0) {
          citsEl.innerHTML = '<div style="margin-top:12px; font-size:0.8rem; color:#8b949e; font-weight:600">Citations:</div>';
          data.citations.forEach(c => {
            const d = document.createElement('div');
            d.className = 'citation';
            d.textContent = `${c.node_id} — ${c.path}:${c.line_start || '?'}-${c.line_end || '?'}`;
            citsEl.appendChild(d);
          });
        }

        document.getElementById('answer-box').classList.add('visible');
      } catch (e) {
        document.getElementById('answer-box').innerHTML = 'Error: ' + e.message;
        document.getElementById('answer-box').classList.add('visible');
      } finally {
        document.getElementById('ask-spinner').classList.remove('visible');
      }
    }
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "code-analyser"}


@app.post("/analyse")
async def analyse(req: AnalyseRequest, background_tasks: BackgroundTasks):
    """Start an analysis run. Returns run_id immediately, processes in background."""
    import threading
    run_id = req.run_id or str(uuid.uuid4())[:8]
    job_id = run_id

    _jobs[job_id] = {"status": "running", "run_id": run_id, "report": None, "error": None}

    def _run():
        try:
            orch = _get_orchestrator()
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
    _jobs[run_id] = {"status": "running", "run_id": run_id, "report": None, "error": None}

    def _run():
        try:
            orch = _get_orchestrator()
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
    return _jobs[job_id]


def _collect_graph(user_id: str, run_id: str):
    store = _get_store()
    nodes = store.query_nodes(user_id, run_id, limit=500)
    if hasattr(store, "_edges"):
        edges = [
            e for e in store._edges
            if e.get("user_id") == user_id and e.get("run_id") == run_id
        ]
    else:
        edges = []
    return nodes, edges


@app.get("/overview/{run_id}")
async def overview(run_id: str, user_id: str = "demo"):
    """A written walkthrough of whatever was just analysed, built from the
    whole graph rather than a retrieved slice."""
    nodes, edges = _collect_graph(user_id, run_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="No graph for this run")

    by_id = {n["id"]: n for n in nodes}
    kinds = {}
    for n in nodes:
        kinds.setdefault(n.get("type", "?"), []).append(n)

    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        by_file.setdefault(n.get("path") or "(no file)", []).append(n)

    lines = []
    for path, members in sorted(by_file.items()):
        lines.append(f"FILE {path}")
        for m in sorted(members, key=lambda x: x.get("line_start") or 0):
            sig = (m.get("props") or {}).get("signature") if isinstance(m.get("props"), dict) else None
            lines.append(
                f"  - [{m.get('type')}] {m.get('name')}"
                f"{' ' + sig if sig else ''}"
                f" (lines {m.get('line_start')}-{m.get('line_end')}): {m.get('description')}"
            )
    for e in edges:
        s = by_id.get(e.get("source_id"), {}).get("name")
        t = by_id.get(e.get("target_id"), {}).get("name")
        if s and t:
            lines.append(f"EDGE {s} -{e.get('type')}-> {t}: {e.get('description') or ''}")

    is_code = any(
        n.get("type") in {"Function", "Method", "Class", "Module"} for n in nodes
    )
    if is_code:
        system = (
            "You explain unfamiliar codebases to a new engineer. Using ONLY the "
            "graph below, write json with these keys:\n"
            '{"summary": "3-4 sentences on what this project is and does",\n'
            ' "flow": ["ordered steps describing how control moves through the '
            'system, naming the real functions and files"],\n'
            ' "components": [{"file": "path", "role": "what this file is for", '
            '"key_symbols": ["name — what it does"]}],\n'
            ' "entry_points": ["where execution starts"],\n'
            ' "how_to_explore": ["what a newcomer should read first, and why"]}\n'
            "Name only files and symbols that appear in the graph. Never invent."
        )
    else:
        system = (
            "You explain documents to someone who has not read them. Using ONLY "
            "the graph below, write json with these keys:\n"
            '{"summary": "3-4 sentences on what these documents cover",\n'
            ' "flow": ["the main points in the order they are presented"],\n'
            ' "components": [{"file": "path", "role": "what this document covers", '
            '"key_symbols": ["topic — what it says"]}],\n'
            ' "entry_points": ["which document to read first"],\n'
            ' "how_to_explore": ["what to read next, and why"]}\n'
            "Name only documents and topics present in the graph. Never invent."
        )

    from code_analyser.llm.factory import get_client
    try:
        raw, _ = get_client().complete_json(
            system, "GRAPH:\n" + "\n".join(lines)[:14000], max_tokens=2000
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Overview failed: {e}")

    raw["kind"] = "codebase" if is_code else "documents"
    raw["stats"] = {
        "nodes": len(nodes),
        "edges": len(edges),
        "files": len([p for p in by_file if p != "(no file)"]),
        "by_type": {k: len(v) for k, v in sorted(kinds.items())},
    }
    return raw


@app.get("/symbols/{run_id}")
async def symbols(run_id: str, user_id: str = "demo", name: Optional[str] = None):
    """Every function/class in the graph, with what calls it and what it calls.
    Answers "list all functions and their calls" exactly, without an LLM."""
    nodes, edges = _collect_graph(user_id, run_id)
    if not nodes:
        raise HTTPException(status_code=404, detail="No graph for this run")
    by_id = {n["id"]: n for n in nodes}

    wanted = {"Function", "Method", "Class", "Module"}
    out = []
    for n in nodes:
        if n.get("type") not in wanted:
            continue
        if name and name.lower() not in (n.get("name") or "").lower():
            continue
        calls, called_by = [], []
        for e in edges:
            src, tgt = by_id.get(e.get("source_id")), by_id.get(e.get("target_id"))
            if e.get("source_id") == n["id"] and tgt:
                calls.append({"name": tgt.get("name"), "type": e.get("type"),
                              "path": tgt.get("path")})
            if e.get("target_id") == n["id"] and src:
                called_by.append({"name": src.get("name"), "type": e.get("type"),
                                  "path": src.get("path")})
        props = n.get("props") if isinstance(n.get("props"), dict) else {}
        out.append({
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
async def ask(req: AskRequest):
    """Ask a question about an analysed codebase."""
    try:
        orch = _get_orchestrator()
        result = orch.ask(req.question, user_id=req.user_id, run_id=req.run_id, k=req.k)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def start_api(host: str = "0.0.0.0", port: int = 8000):
    import uvicorn
    uvicorn.run("code_analyser.api:app", host=host, port=port, reload=False)
