# lablab.ai submission — copy/paste sheet

## Submission Title (≤50 chars)
Cartograph: Codebase Knowledge Graph with IBM Bob

## Short Description (≤255 chars)
Cartograph maps any codebase into a knowledge graph using five AI agents built with IBM Bob, then answers questions from the graph with citations, and flags any answer it cannot ground. It reads the repo once so every question after that is cheap.

## Long Description (≤500 words)
Paste the whole of `problem-solution.md`.

## IBM Bob Usage Statement (≤500 words)
Paste the whole of `bob-usage-statement.md`.

## Categories
Choose the developer-onboarding / developer-productivity option if the form offers one.

## Technologies Used
IBM Bob · IBM watsonx.ai · IBM Granite · Python · FastAPI · Neo4j
(Do NOT list ChatGPT or Codex; they are not used in this project.)

## Public Code Repository
https://github.com/Poornasri2003/code-analyser

## IBM Bob Task Session Summary Screenshots
Upload from `bob_sessions/`:
- bob-session-02-build-phases.png
- bob-session-03-requirements-summary.png
(Leave out bob-session-01-recent-tasks.png. It shows the Culprit workspace, not this project.)

## Demo Application Platform / Application URL
Platform: Hugging Face Spaces (Docker). The README front-matter is already set up for a Space.
URL: fill in after deploying. If there is no time, give the GitHub URL and the run command from the README.

## Cover Image
`submission/screenshots/cover.png` (1920×1080)

## Slide Presentation
`submission/slide-presentation.pdf` (editable source: `submission/Cartograph.pptx`, with speaker notes)

## Video (≤3 min, ≥90 s of live demo): script
| Time | On screen | Say |
|---|---|---|
| 0:00–0:25 | Slides 2–3 | "Before you change unfamiliar code you have to learn it, and everyone learns it again from scratch. Chat assistants re-read the files for every question and can't show where an answer came from." |
| 0:25–0:40 | Slide 5 (architecture) | "Cartograph builds a knowledge graph once: a Planner, Code and Doc agents, a validator and a Linker. Then it answers from the graph." |
| 0:40–1:10 | Web UI: paste a Git URL, start | "I paste a public repo. The live trace shows the Planner routing files by priority, then each file being extracted, with the tokens spent." |
| 1:10–1:50 | Graph, overview, call graph | "This is the graph it built: modules, functions and the edges between them, linked across files." |
| 1:50–2:30 | Ask 2–3 questions | "Where is authentication enforced? The answer cites the exact nodes. If the model cites something it wasn't given, the answer is marked ungrounded instead of being shown as fact." |
| 2:30–2:55 | Bob IDE screenshots, slide 10 | "IBM Bob built this: it read our 3,000-line brief, planned 17 phases and wrote 50 files in Agent mode. Bob Shell can also be the model that runs it, and watsonx.ai Granite is the default." |
| 2:55–3:00 | Cover | "Cartograph. Read once, answer from the graph." |
