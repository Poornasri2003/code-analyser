THE PROBLEM

Before a developer can change unfamiliar code, they have to work out what it is: the entry point, what calls what, where the auth check lives, which files are generated noise. Today that means grep, the file tree, and interrupting whoever knows the system.

This cost recurs at onboarding, when a service is inherited, and whenever a reviewer opens a pull request in an unread module. The result is thrown away. The map one developer builds is never written down, so the next person starts from zero.

Pasting the repository into a chat assistant does not fix this. The model re-reads raw files for every question, runs out of context window on anything bigger than a toy project, and gives a fluent answer with no way to check where it came from.

OUR SOLUTION

Cartograph turns a repository into a queryable knowledge graph once, then answers questions from that graph instead of re-reading the source.

What you give it: a public Git URL or an uploaded .zip.

What it does:
1. Plan: the Planner agent sees the whole file tree, routes every file to code, doc or skip (with a reason), and ranks it by priority. A capped run analyses entry points first, not the alphabetically first files.
2. Extract: the Code and Doc agents describe each file as typed nodes and relationships.
3. Validate: plain Python drops hallucinated line ranges and edges to nodes that do not exist.
4. Link: the Linker resolves references across files into one connected graph, which is embedded and stored in Neo4j or in memory.
5. Answer: a question retrieves the relevant subgraph, and the Answer agent replies with citations. If it cites a node that was not in the retrieved context, the answer comes back grounded=false instead of being shown as fact.

WHO USES IT, AND HOW

New joiners, reviewers working in unfamiliar code, engineers who inherit a service, and leads writing onboarding docs. They paste a URL into the web UI, watch a live trace of every agent call with the tokens spent, browse the resulting graph, overview and call graph, and ask questions in plain English. Teams can also use the REST API (/analyse, /jobs, /ask) or the CLI.

WHAT MAKES IT DIFFERENT

- Read once, answer many times: a chat assistant re-reads the whole repository for each question. Cartograph reads it once, then each question needs only one small retrieval.
- Fails closed: an answer that cannot be traced to the graph is flagged as ungrounded, never presented as fact.
- The LLM reasons, Python decides: the orchestrator owns ordering, retries, validation, ids and storage. Agents only return JSON.
- Durable and shared: the graph outlives the session, so the next teammate does not rebuild the map.
- IBM-first and model-agnostic: IBM watsonx.ai (Granite) is the default provider, and Bob Shell is a selectable provider. Switching models is one environment variable.

Built with IBM Bob 2.0, Python, FastAPI and Neo4j; 34 offline tests.
