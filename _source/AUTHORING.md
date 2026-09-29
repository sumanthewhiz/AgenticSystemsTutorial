# Authoring guide

This folder holds the **source** of the tutorial. `build.py` turns it into the static site one level up
(`index.html`, `chapters/*.html`, `assets/search-index.js`). Edit Markdown here, then rebuild:

```powershell
# run from the tutorial folder; tell the scripts where you installed SwarmPipe (needed once per PowerShell window)
$env:SWARMPIPE_DIR = "<your-SwarmPipe-folder>"
& "$env:SWARMPIPE_DIR\.venv\Scripts\python.exe" _source\build.py --check              # everything
& "$env:SWARMPIPE_DIR\.venv\Scripts\python.exe" _source\build.py --check --only 06-contracts-and-quality
& "$env:SWARMPIPE_DIR\.venv\Scripts\python.exe" _source\extract_facts.py              # after SwarmPipe itself changes
```

Without `SWARMPIPE_DIR` (or `--project`), the scripts look for a `SwarmPipe` folder next to the tutorial folder.

- `outline.yaml` - parts, chapter order, titles, times, summaries and the topics each chapter owns.
- `chapters/<slug>.md` - one file per chapter or appendix. `home.md` - the intro on the home page.
- `facts.md` / `facts.json` - **ground truth extracted from SwarmPipe** (every command, option, scenario, agent, tool,
  workflow, dashboard tab, runtime flag, metric, API route, MCP tool, prompt, eval case and project file).
- `sitegen/` - renderer, templates and the `--check` validator. `../assets/style.css`, `../assets/app.js` - look and behavior.

## Audience and voice

Readers are smart engineers and technical product people who know what an LLM is but have never run a production
agentic system. Teach **why before how**, define every term before using it, prefer concrete examples from SwarmPipe
over abstractions, and explain trade-offs (what it costs, when *not* to do it). Second person ("you"), active voice,
short paragraphs, US spelling. Aim for lucid, not clever. `chapters/00-welcome.md` is the reference for tone and for
how the components are used.

## Chapter anatomy (required, in this order)

1. **Front matter** with 4-6 `objectives` (outcomes the reader can *do* or *explain*).
2. **Opening** (no heading): 1-2 paragraphs with a concrete production problem that motivates the chapter.
3. **Concept sections** (`##` headings, `###` subsections): first principles, `:::concept` definitions, an `:::analogy`
   where it helps, 1-3 diagrams (`:::flow`, `:::flow-v`, `:::loop`, `:::layers`, `:::cards`), comparison tables.
4. **How SwarmPipe implements it**: `:::swarmpipe` boxes naming files, classes and functions; short verbatim code
   excerpts (at most 20 lines, introduced with the file path) where the code itself teaches something.
5. **Hands-on**: at least two `:::lab` boxes. Numbered steps, exact commands in ```` ```powershell ```` fences,
   **real** expected output in ```` ```output ```` fences (captured from your sandbox, trimmed with `...`), and what
   to look for in the dashboard (use the exact tab names).
6. **Break it**: at least one `:::breakit` experiment (chaos flag, toggled defense, bad input). State what to do,
   what you will observe, and why.
7. **Production notes**: at least one `:::warning` (a real-world gotcha) and what changes at larger scale.
8. **Quiz**: one `:::quiz` with 4-6 questions, each with exactly one `[x]` answer and a `>` explanation that teaches.
9. **Key takeaways**: one `:::takeaways` box with 4-7 bullets.

Length: 1,800-3,000 words (the build prints word counts). Link to other chapters with
`[Chapter 12](12-durable-execution.html)` or a section anchor `12-durable-execution.html#some-heading` (anchors are the
heading text lower-cased with spaces turned into hyphens). Don't re-teach a topic another chapter owns (see
`outline.yaml` `covers:`). Summarize it in a sentence or two and link to that chapter.

## Components

````text
:::concept Term          definition box (title = the term)
:::analogy [Title]       everyday analogy
:::note / :::tip / :::warning / :::danger [Title]
:::swarmpipe [Title]     where it lives in SwarmPipe
:::lab Title             hands-on lab (numbered steps, powershell + output fences)
:::breakit Title         break-it experiment
:::deepdive Title        collapsible advanced material
:::flow [Caption]        left-to-right boxes with arrows, one "Title | subtitle" per line
:::flow-v [Caption]      top-to-bottom version        :::loop [Caption]   a cycle (agent loop)
:::layers [Caption]      stacked layers, "Name | description" per line
:::cards [Caption]       grid of cards, "Name | description" per line
:::quiz                  Q: question / - [ ] wrong / - [x] right / > explanation (blank line between questions)
:::takeaways             bullet list
````

Every component ends with a line containing only `:::`. Components can't be nested, but code fences inside them are
fine. Code fence languages: `powershell` (gets a Copy button), `output` (styled as expected output), `python`, `yaml`,
`json`, `sql`, `text`.

## Accuracy rules (non-negotiable)

- Use **only** commands, options, scenario names, flags, file paths, class and function names, metric names, config
  keys, dashboard tab names and API routes that exist. Check `facts.md` first, then read the SwarmPipe source.
  Never guess.
- `sp` means `python -m swarmpipe` (Chapter 0 defines the shortcut). Write commands as `sp ...`.
- Expected output must come from a real run in your sandbox. Trim it, but never invent it. Ids, dates and timings vary
  between runs, so say so where it matters.
- Run `build.py --check --only <your slugs>` and fix **every** warning before you finish. The checker validates commands,
  options, scenarios, chaos flags, profiles, tenants, eval suites, file paths, API routes, identifiers in `inline code`
  and all links and anchors.
- Describe SwarmPipe's real behavior, including its honest limitations (see the README).

## Running SwarmPipe safely (writers)

A SwarmPipe server may be running from `<your-SwarmPipe-folder>` against its own `data` folder. **Never** run commands
in that folder, never run `sp reset` there, never stop Python processes, and never start a server on port 8765. Work in
a private sandbox copy instead:

```powershell
$src = $env:SWARMPIPE_DIR   # your SwarmPipe folder (set above)
$sb = Join-Path $env:TEMP "sp_sandbox_<your-name>"
# exclude the ROOT data folder by full path: a bare "data" would also drop the swarmpipe\data package
robocopy $src $sb /E /XD "$src\.venv" "$src\data" "$src\.git" __pycache__ .pytest_cache /NFL /NDL /NJH /NJS | Out-Null
Set-Location $sb
function sp { & "$src\.venv\Scripts\python.exe" -m swarmpipe @args }
sp init
sp scenarios drop baseline --process
```

Running from the sandbox folder imports the sandbox's copy of the code, so its `data`, `evals/reports` and settings are
all private. Prefer `--process` and `sp tick` over starting a server. If you need HTTP responses, use
`fastapi.testclient.TestClient(create_app(svc, None))` in a Python snippet inside the sandbox. Delete your sandbox when
you're done. Real-model calls (`--profile ollama`) take 15-30 s each, so use them sparingly.

Don't edit SwarmPipe's files, `outline.yaml`, the build scripts or other writers' chapters, and don't use git. Keep
external links for `further-reading.md`, apart from the occasional canonical specification. Never include personal
information, such as local user paths or names.
