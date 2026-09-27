We used IBM Bob in two ways: to BUILD Cartograph, and INSIDE Cartograph as a runtime model provider. IBM watsonx.ai is the default provider for every agent in the code.

1. BUILDING CARTOGRAPH IN THE BOB IDE

Bob built Cartograph in one long Agent-mode session. Screenshots are in bob_sessions/.

- Document understanding: we pasted the full hackathon brief and guide into Bob, 3,109 lines of raw page text. Bob produced a Hackathon Requirements Summary covering the deliverables, the 500-word limits, the video rules, and the rule that the repository must contain the files Bob assisted with. We planned the build against that summary.
- Plan: Bob split the work into a tracked phased plan with 17 checklist items: scaffold, domain models, LLM clients, graph stores, agents, orchestrator, API and web UI, tests, deployment config, and commit and push. It worked through them in order and ran to 168k of a 270k-token context without losing track.
- Agent mode: Bob wrote and edited 50 files. These included the Planner, Code, Doc, Linker and Answer agents, the orchestrator, the pluggable LLMClient protocol with its watsonx.ai, Groq, OpenAI-compatible, Bob Shell and fake clients, the Neo4j and in-memory stores, the FastAPI service, and an offline pytest suite.
- Full-repository context: Bob's most valuable catch was a contract mismatch across files. graph_tools.py and inmemory.py were an older version that mutated GraphNode.id directly and exposed upsert_node. The orchestrator expected StoredNode/StoredEdge and a write/query/ensure_schema protocol. Bob found the mismatch, rewrote both modules to match, and fixed a None-unsafe line_end comparison along the way.
- Security: a .bobignore keeps .env, keys, tokens and credential files out of Bob's context, so secrets never reached the assistant.

The session used our full 40-Bobcoin budget. We then hardened the build by hand against a real LLM, adding ZIP upload, priority-ordered file selection, live run tracing and token accounting. The later commits in the repository show this work.

2. BOB INSIDE CARTOGRAPH AT RUNTIME (BOB SHELL)

Every agent talks to the model through one LLMClient interface. Setting LLM_PROVIDER=bobshell routes all Planner, extraction, Linker and Answer calls through Bob Shell (src/code_analyser/llm/bobshell_client.py). Bob receives the system and user prompt and returns JSON, and Cartograph validates that JSON before anything reaches the graph. The assistant that built the analyser can also run it.

3. IBM WATSONX.AI

watsonx.ai is the default LLM_PROVIDER. The WatsonxClient uses the official ibm-watsonx-ai SDK (ModelInference, chat API) with ibm/granite-3-8b-instruct at temperature 0 and reports token usage into each run's trace. The credentials (API key, URL, project ID) are documented in .env.example. Because providers are interchangeable, our hosted demo runs on a free Groq model while watsonx.ai stays the default. Switching between them is one environment variable, with no code changes.
