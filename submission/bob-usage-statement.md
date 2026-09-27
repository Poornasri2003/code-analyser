# IBM Bob Usage Statement

> IBM Bob 2.0 Hackathon — Team: Poornasri2003

---

## How We Used IBM Bob 2.0

IBM Bob 2.0 was the main builder of Code Analyser. It took the project from
hackathon brief to a working, tested multi-agent pipeline in one long Agent-mode
session. Screenshots of that session are in [`bob_sessions/`](../bob_sessions/).

### 1. Document understanding: brief to requirements

We began by pasting the full hackathon brief and guide into Bob, 3,109 lines of
raw page text. Bob pulled the real constraints out of it and produced a
**Hackathon Requirements Summary**: the required deliverables, the 500-word
limits, the video rules, and the rule that the repository must contain the
files Bob helped write (see `bob-session-03-requirements-summary.png`). We
planned the rest of the build against that summary instead of re-reading the
page.

### 2. Plan: a phased build

Bob then broke the project into a tracked, phase-by-phase plan (17 checklist
items, visible in `bob-session-02-build-phases.png`) covering scaffolding,
domain models, LLM clients, graph store, agents, orchestrator, API and UI,
tests, deployment config, and finally commit and push. Each phase had a clear
exit point, which kept one very long task coherent. The session ran to
**168k of a 270k-token context** without losing track of where it was.

### 3. Agent mode: multi-file implementation

In Agent mode Bob wrote and edited the code directly. **50 files changed** in
the session, including the Planner, Code, Doc, Linker and Answer agents, the
orchestrator, the pluggable `LLMClient` protocol with watsonx, Groq, OpenAI and
fake clients, the Neo4j and in-memory stores, and an offline pytest suite.

Bob's most useful move was catching a contract mismatch across files. It
noticed that `graph_tools.py` and `inmemory.py` were an older version that
mutated `GraphNode.id` directly and exposed `upsert_node`, while the
orchestrator expected `StoredNode`/`StoredEdge` and a
`write`/`query`/`ensure_schema` protocol. It rewrote both modules to match and
fixed a None-unsafe `line_end` comparison along the way. That kind of
repository-wide consistency check is where full-repo context paid off.

### 4. Security by default

We added a `.bobignore` that keeps `.env`, keys, tokens and credential files
out of Bob's context, so secrets never reached the assistant.

### 5. Bob inside the product

Bob is also a runtime option. `LLM_PROVIDER=bobshell` routes every agent call
through Bob's shell interface (`src/code_analyser/llm/bobshell_client.py`),
so the assistant that built the analyser can also power it.

### Impact and honest limits

Bob delivered in one session what would have taken days by hand: a typed,
validated, tested multi-agent pipeline plus deployment files for Docker,
Render, Railway and Hugging Face. The session used up its **40-Bobcoin
budget**. After that, we hardened the build by hand against a real LLM, which
covered ZIP upload, priority-ordered file selection, live run tracing and
token accounting, as the later commits in the repository show.
