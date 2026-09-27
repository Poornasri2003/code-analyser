---
title: Code Analyser
emoji: 🕸️
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Code Analyser

Unstructured code in, structured knowledge graph out. Built with IBM Bob 2.0.

Point it at a public Git repository or upload a `.zip`. It reads every file,
asks an LLM to describe each one as nodes and relationships, links those
fragments into one connected graph, and then answers questions about the
codebase from that graph instead of re-reading the files.

## Run it

```bash
pip install -e .
cp .env.example .env     # then fill in the keys
uvicorn code_analyser.api:app --port 8000
```

Open <http://localhost:8000>.

## Configuration

Every value lives in `.env` — see `.env.example` for where to obtain each one.

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `watsonx` (default), `groq`, `openai`, `bobshell` or `fake` |
| `STORE_TYPE` | `neo4j` or `inmemory` (no database required) |
| `ANALYSER_MAX_FILES` | Cap on files analysed per run |
| `ANALYSER_CHUNK_LINES` | Lines per LLM request; lower it for small free-tier token limits |

The LLM sits behind a single `LLMClient` protocol, so providers are
interchangeable — set `LLM_PROVIDER` and nothing else changes.

## Endpoints

| Route | Purpose |
|---|---|
| `GET /` | Web UI |
| `POST /analyse` | Analyse a Git URL or local path |
| `POST /analyse-upload` | Analyse an uploaded `.zip` |
| `GET /jobs/{job_id}` | Poll run progress |
| `POST /ask` | Ask a grounded question, with citations |

## Tests

```bash
pytest
```

All tests run offline against fake clients and an in-memory store — no network,
no database, no API keys.
