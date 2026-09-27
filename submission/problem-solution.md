# Problem & Solution Statement

> IBM Bob 2.0 Hackathon — Team: Poornasri2003
> Word count: 468

---

## Problem

Every developer who joins an unfamiliar codebase starts with the same unpaid
task: working out what the thing *is* before changing any part of it. Which
module is the entry point, what calls what, where the auth check actually
lives, which files are generated noise. The available tools are `grep`, the
file tree, and whoever happens to be free to answer questions.

This cost is paid over and over — at onboarding, when inheriting an unowned
service, and every time a reviewer opens a pull request in code they have never
read. It is slow, it interrupts the one person who does know the system, and
its output is disposable: the mental map one developer builds is never written
down, so the next person rebuilds it from scratch.

Pasting a repository into a chat assistant does not solve this. The model
re-reads raw files on every single question, hits the context window on
anything larger than a toy project, and answers with no way to verify where a
claim came from. You get fluent text and no accountability.

## Solution

**Code Analyser turns a repository into a queryable knowledge graph once, then
answers questions from that graph instead of re-reading the source.**

Point it at a public Git URL or upload a `.zip`. A multi-agent pipeline runs:

1. **Planner** sees the whole file manifest and routes every file — `code`,
   `doc`, or `skip` with a stated reason — and ranks it by priority, so a
   budgeted run analyses the files that matter rather than the alphabetically
   first ones.
2. **Code and Doc agents** describe each file as typed nodes and relationships.
3. A **validator** drops hallucinated line numbers and dangling edges.
4. The **Linker** resolves cross-file references into one connected graph.
5. Nodes are embedded and written to Neo4j or an in-memory store.

Asking a question then retrieves a subgraph and answers from it **with
citations**. If the model cites a node that is not in the retrieved context,
the answer is returned `grounded=False` rather than shown as fact — it fails
closed instead of bluffing.

**The impact is a change in cost curve.** Understanding a repository by
grep-and-chat costs a full crawl *per question*. Code Analyser pays that cost
once, then serves every later question from one retrieval. The graph is
durable, shared, and re-usable by the whole team, and the UI shows the live
trace, token spend, and node/edge counts for each run, so the work is auditable
rather than a black box.

IBM Bob 2.0 made this buildable in a weekend — and Bob is wired into the
product itself as a selectable `LLM_PROVIDER`, so the assistant that built the
analyser can also power it.
