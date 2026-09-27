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


def _get_orchestrator():
    from code_analyser.llm.factory import get_client
    from code_analyser.orchestrator import Orchestrator

    store_type = os.getenv("STORE_TYPE", "neo4j")
    from code_analyser.store.factory import get_store
    store = get_store(store_type)
    client = get_client()
    workdir = Path(os.getenv("ANALYSER_WORKDIR", "/tmp/code_analyser_work"))
    return Orchestrator(client=client, store=store, workdir=workdir)


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
        <label>GitHub URL or local path</label>
        <input id="source" type="text" placeholder="https://github.com/owner/repo" />
        <label>User ID (for tenant isolation)</label>
        <input id="user_id" type="text" value="demo" />
        <label>Max files (optional)</label>
        <input id="max_files" type="number" placeholder="500" />
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
      if (!source) { alert('Enter a source URL or path'); return; }
      const user_id = document.getElementById('user_id').value || 'demo';
      const max_files = document.getElementById('max_files').value;

      document.getElementById('analyse-spinner').classList.add('visible');
      document.getElementById('analyse-result').classList.remove('visible');
      document.getElementById('run-id-holder').style.display = 'none';

      const body = { source, user_id };
      if (max_files) body.max_files = parseInt(max_files);

      try {
        const resp = await fetch('/analyse', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body)
        });
        const data = await resp.json();
        document.getElementById('analyse-result').textContent = JSON.stringify(data, null, 2);
        document.getElementById('analyse-result').classList.add('visible');
        if (data.run_id) {
          document.getElementById('run-id-value').textContent = data.run_id;
          document.getElementById('run-id-holder').style.display = 'block';
        }
      } catch (e) {
        document.getElementById('analyse-result').textContent = 'Error: ' + e.message;
        document.getElementById('analyse-result').classList.add('visible');
      } finally {
        document.getElementById('analyse-spinner').classList.remove('visible');
      }
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


@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


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
