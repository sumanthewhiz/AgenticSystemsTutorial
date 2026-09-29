---
objectives:
  - "Say precisely what makes an agentic application **production-grade**, not just a clever demo"
  - "Recognise the building blocks every chapter uses: concepts, labs, *break it* experiments and quizzes"
  - "Get SwarmPipe running, push your first files through it and watch the swarm open an incident"
  - "Find your way around the 12 dashboard tabs and reset the system safely whenever you want a clean slate"
---

Most agent tutorials stop at "call a model in a loop with some tools". This one starts there and keeps going:
evaluations, failure modes, durable execution, security, governance, cost, observability, operations. That's everything
you need to trust an agent with real work. You won't just read about these ideas. Each one is implemented in a working
application sitting on your machine, and every chapter asks you to **run it, watch it, break it and fix it**.

## What "production-grade agentic" actually means

A demo agent has to be impressive once. A production agent has to be right, safe and affordable thousands of times,
while models misbehave, files arrive corrupted, dependencies time out and someone tries to trick it.

:::concept Agentic application
Software in which one or more **language-model-driven components (agents)** decide some of the steps: which tool to call,
what the data means, what went wrong, what to do next. The rest is ordinary deterministic code, which **constrains**,
**checks** and **records** every one of those decisions.
:::

"Production-grade" is the collection of properties that let you trust that software. Each part of this tutorial
builds one layer of this stack:

:::layers The layers of a production agentic system (and the part that teaches each)
Agents and patterns | what agents are, how many to use, how they cooperate (Parts I and III)
Data and tools | clean inputs, contracts, tool contracts, grounded context (Parts I–III)
Reliability | surviving crashes, retries, flaky models, known failure modes (Part IV)
Evaluation | proving quality before and after every change (Part V)
Security and governance | assume the model will be fooled, then contain it (Part VI)
Observability, cost and operations | seeing, paying for and running it day to day (Part VII)
:::

## Meet SwarmPipe, your living lab

**SwarmPipe** is a data pipeline run by a swarm of 27 agents. You drop `.csv`, `.txt`, `.xls` or `.xlsx` files into
a watched folder, and the system takes it from there:

:::flow What happens to one file
File lands | in the watched folder
Router agent | what kind of file is this?
Ingest workflow | read, profile, check the contract
Quality checks | is the data *correct*, not just present?
Publish or quarantine | a circuit breaker protects consumers
Triage swarm | investigate, diagnose, plan
Policy and approval | may the agent act?
Act, verify, learn | and record everything
:::

It runs **offline by default**. Two *simulated* models (`sim-small` and `sim-large`) stand in for real LLMs. They're
free, fast and deterministic, and on request they misbehave in exactly the ways real models do: time out, return
broken JSON, hallucinate citations or fall for prompt injection. That makes every failure mode in this tutorial
reproducible on demand. When you want the real thing, one command switches to a local Ollama model or a hosted one
([Chapter 25](25-model-strategy.html)).

:::analogy A flight simulator for agent engineering
Pilots don't learn engine failures by waiting for one. They train in a simulator that can fail any system at any
moment. SwarmPipe's simulated models and chaos flags do the same for agent failures.
:::

## How every chapter works

Chapters follow the same rhythm: a concept explained from first principles, then where it lives in SwarmPipe, then
your hands on the keyboard. These are the building blocks you'll meet (each one below is a live example):

:::swarmpipe Where to look
Boxes like this point at the exact files, functions, dashboard tabs and commands that implement the concept, for
example `swarmpipe/runtime/engine.py` for durable execution.
:::

:::lab Example lab
Numbered steps with commands you can copy (hover a code block and press **Copy**):

```powershell
sp status
```

...followed by what you should see:

```output
LLM: 26 calls, $0.01536, 32232 tokens | profile offline | kill switches: none | inbox: ...\SwarmPipe\data\inbox
```
:::

:::breakit Example experiment
Each concept is easiest to understand when it's missing. These boxes switch a defense off or inject a fault, then ask
you to predict, observe and explain what happens.
:::

:::warning Example gotcha
Mistakes real teams make in production, and how to avoid them.
:::

:::deepdive Optional deeper material
Click to expand. Skip these on a first pass. They hold the "why exactly" details and the edge cases.
:::

Each chapter ends with a short **quiz** (click an answer to check it) and **key takeaways**, and each has a
**Mark this chapter as complete** button. Your progress is stored in your browser and shown in the top bar and
on the home page.

## Set up SwarmPipe

You need a local copy of the SwarmPipe project. All commands in this tutorial are PowerShell and are run from your
SwarmPipe folder.

:::lab Get a working environment
1. Open **PowerShell**, get the project (skip the clone if you already have a copy) and activate its virtual environment:

   ```powershell
   git clone https://github.com/sumanthewhiz/SwarmPipe.git
   cd SwarmPipe
   .\.venv\Scripts\Activate.ps1
   ```

   On a fresh clone the environment doesn't exist yet. Create it once with `python -m venv .venv`, activate it and run
   `pip install -r requirements.txt` (Python 3.11 or newer).

2. Initialise the state database, data contracts, knowledge base, agent registry and prompt lock:

   ```powershell
   python -m swarmpipe init
   ```

   ```output
   SwarmPipe initialised - state C:\...\SwarmPipe\data\state\swarmpipe.db
   Watched folder (drop files here): C:\...\SwarmPipe\data\inbox
   {
     "contracts_imported": ["customers@v1", "inventory@v1", "regions@v1", "sales_daily@v1"],
     "static_lineage_edges": 12,
     "knowledge_docs_added": 10,
     "agents_registered": 27,
     "unapproved_prompts": []
   }
   ```

   Running `init` again is harmless. On an already-initialised system the lists are simply empty or zero, because
   nothing new needed importing.
:::

### Make `sp` a shortcut

You'll type `python -m swarmpipe` hundreds of times, so this tutorial writes it as **`sp`**. Define the shortcut in
every new PowerShell window after activating the environment (or add the line to your PowerShell `$PROFILE`):

```powershell
function sp { python -m swarmpipe @args }
sp --help
```

`sp --help` lists every command group: `scenarios`, `runs`, `incidents`, `approvals`, `evals`, `chaos` and more. The
[command cheat sheet](cheatsheet.html) has all of them on one page.

## Your first files, and your first incident

SwarmPipe ships with 28 **scenarios**: synthetic deliveries and faults you can drop into the watched folder with one
command. With `--process` they're handled synchronously, without a server, which is ideal for a first look.

:::lab Push data through the pipeline
1. Load the reference data (a customer master `.xlsx` with two sheets and a legacy inventory `.xls`) and four days
   of sales history, which the checks use as their baseline:

   ```powershell
   sp scenarios drop baseline --process
   ```

   ```output
   dropped ['customers.xlsx', 'inventory_2026-09-28.xls'] into ...\data\inbox
   admitted 2 file(s); processed in 0.8s
   dropped ['sales_2026-09-24.csv', 'sales_2026-09-25.csv', 'sales_2026-09-26.csv', 'sales_2026-09-27.csv'] into ...\data\inbox
   admitted 4 file(s); processed in 5.6s
   ```

   File names carry dates relative to *today*, so yours will differ. A status summary follows, with tables of runs,
   incidents, approvals and datasets.

2. Now deliver a broken file: a truncated extract with 18 rows where about 500 are normal.

   ```powershell
   sp scenarios drop volume_drop --process
   sp incidents list
   ```

   ```output
   | id                 | status    | severity | tenant  | dataset     | signal_count | root_cause        | cost_usd | title                                   |
   | inc_mul9cfnmead9cf | mitigated | critical | default | sales_daily | 1            | truncated_extract | 0.011965 | sales_daily: volume anomaly - row_count_min ... |
   ```

3. Look at what just happened. The file "loaded successfully" as far as any job scheduler could tell. But a quality
   check tripped the **circuit breaker**, so the bad batch was quarantined instead of published. A **swarm** of agents
   then investigated, diagnosed a truncated extract, took low-risk containment actions *within policy* and verified
   them. It cost about one cent of (simulated) model usage. Every chapter from here on unpacks a piece of what you
   just saw.
:::

:::tip Ids and numbers differ on every run
Incident ids, run ids, timings and costs are generated fresh each time. Compare the *shape* of your output with the
examples, not the exact values. Where a command contains a placeholder such as `inc_...`, `run_...` or `apr_...`,
paste the matching id from your own output (for example from `sp incidents list` or `sp approvals list`).
:::

## Tour the dashboard

The same system has a web dashboard. Start the full runtime (watcher, workers, event bus, monitors and web server),
then open <http://127.0.0.1:8765>:

```powershell
sp run
```

Leave that window running and use a **second** PowerShell window for commands (activate the environment and define
`sp` there too). If a server is already running, just open the URL. Starting a second one would fail because the
port is taken.

| Tab | What it shows | Taught in |
|---|---|---|
| **Overview** | health, recent runs and incidents, cost at a glance | [Chapter 2](02-architecture-tour.html) |
| **Scenarios & Chaos** | one-click scenarios and runtime chaos toggles | [Chapter 14](14-failure-modes.html) |
| **Runs** | durable workflow runs, step attempts, checks, model calls, the trace | [Chapter 12](12-durable-execution.html) |
| **Incidents** | signals, diagnosis, proposals → policy → execution → verification, evidence | [Chapter 9](09-triage-swarm.html) |
| **Approvals** | human-in-the-loop decisions waiting for you | [Chapter 21](21-policy-autonomy.html) |
| **Datasets & Lineage** | versions, latest checks, contracts, the lineage graph | [Chapter 7](07-publishing-lineage.html) |
| **Agents & Tools** | the agent registry (agent cards) and tool contracts | [Chapter 4](04-tools-and-gateway.html) |
| **Governance** | policies, autonomy levels and history, kill switches, audit | [Chapter 22](22-audit-evidence.html) |
| **Cost & Metrics** | model usage and cost by agent and model, metrics, SLOs | [Chapter 24](24-cost-capacity.html) |
| **Evals** | eval runs, gate thresholds, shadow and human feedback | [Chapter 15](15-eval-fundamentals.html) |
| **Ask the data** | the Analyst agent: questions in English, governed SQL out | [Chapter 20](20-identity-access.html) |
| **Knowledge & Memory** | runbooks, ingested documents, human-curated lessons | [Chapter 11](11-context-memory.html) |

:::lab Watch it live
1. Open the **Scenarios & Chaos** tab and drop **clean_day**. Switch to **Runs** and watch the new runs appear and
   finish.
2. Open **Incidents** and click the incident from the previous lab. Scroll through its signals, proposals, evidence
   and the trace at the bottom: one timeline covering every agent that worked on it.
:::

## Reset whenever you like

Many labs ask for a clean slate. Resetting is safe because it *moves* the data aside rather than deleting it:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
```

Stop the server first (Ctrl+C in its window), because a running server holds its database open. `reset` moves the
whole `data` folder to a recoverable `.trash-data-<timestamp>` folder next to it. Runtime chaos settings live in that
database too, so a reset also clears them. Without a reset, `sp chaos clear` returns all chaos flags to their defaults.

:::warning Two terminals, one database
The server and your CLI commands share one state database. That's deliberate: a `sp chaos set ...` in the second
window changes the behavior of the running server immediately. It also means that `--process` commands and a running
server both do work. That's fine, but don't be surprised when the dashboard shows runs you started from the CLI.
:::

## Your learning path

:::flow The nine parts
Start here | set up, first run
Foundations | agents, architecture, gateways
Data backbone | ingestion, contracts, lineage
The swarm | patterns, triage, protocols, memory
Reliability | durability, resilience, failure modes
Evaluation | datasets, judges, red team, gates
Governance | threats, identity, policy, audit
Operations | observability, cost, models, ops
Capstone | build and ship a feature
:::

Reading in order works best, since each part builds on the previous one. If you're short on time, this **core path**
covers the essentials in about seven hours: chapters [1](01-llm-to-agent.html), [2](02-architecture-tour.html),
[6](06-contracts-and-quality.html), [8](08-why-multi-agent.html), [9](09-triage-swarm.html),
[12](12-durable-execution.html), [15](15-eval-fundamentals.html), [19](19-threat-model.html) and
[21](21-policy-autonomy.html).

:::quiz
Q: Why does SwarmPipe use simulated models by default?
- [ ] Real models cannot run inside a data pipeline
- [x] Simulated models are free, deterministic and can fail on demand, so every failure mode is reproducible
- [ ] Simulated models give better answers than real ones
> The simulators exist for learning: you can make them time out, return malformed JSON or obey a prompt injection whenever you choose. You can switch to a real model at any time.

Q: What does `sp scenarios drop volume_drop --process` do?
- [ ] Deletes the sales dataset
- [ ] Only copies a file; nothing is processed until you start the server
- [x] Copies a synthetic file into the watched folder and processes everything synchronously, without a server
> `--process` runs the watcher, workflows, events and monitors in the foreground until the system is quiet, which is ideal for labs.

Q: The truncated file "loaded successfully", yet it was not published. Why?
- [ ] The Router agent rejected the file type
- [x] A data-quality check tripped the circuit breaker, so the batch was quarantined
- [ ] The file was a duplicate
> A job ending OK is not the same as the data being correct. You will study the checks and the circuit breaker in Chapter 6.

Q: What does `sp reset --yes` do to your data?
- [ ] Permanently deletes it
- [x] Moves the data folder to a recoverable `.trash-data-<timestamp>` folder
- [ ] Empties only the inbox
> Nothing is destroyed: you can move the folder back if you need it. Stop the server before resetting.
:::

:::takeaways
- Production-grade means **correct, safe, affordable and accountable** under failure and attack, not just clever once.
- SwarmPipe is a data pipeline run by 27 agents. It's **offline and deterministic by default**, with realistic failures on demand.
- Every chapter follows the same pattern: concept, then where it lives in SwarmPipe, a hands-on lab, a *break it* experiment, a quiz and takeaways.
- `sp` is short for `python -m swarmpipe`. `--process` runs a scenario synchronously, and `sp run` starts the server and dashboard on port 8765.
- `sp reset --yes` gives you a clean slate by moving your data aside, never deleting it.
:::
