---
objectives:
  - "Follow one file from the inbox through publish, quarantine and incident triage"
  - "Name the five SwarmPipe workflows and the job each one owns"
  - "Group the 27 agents into pipeline, triage and service teams"
  - "Explain the control-plane / data-plane split and the composition root"
  - "Use the CLI and dashboard to inspect runs, traces and failure isolation"
---

Agentic systems are easier to trust when you can draw the path of one piece of work. In SwarmPipe that piece of work
is a file: it lands in the watched folder, becomes durable runs, may publish a dataset version, may raise signals and
may trigger a triage swarm. The architecture is not "agents everywhere"; it is a data pipeline with agentic decisions
at specific seams.

This tour gives you the map you will reuse for the rest of the tutorial.

## The end-to-end flow

:::flow One file through SwarmPipe
File lands | `data\inbox`, optionally under a tenant folder
Watcher admits it | stable size and mtime, extension allowlist, content hash
`ingest_file` | stage, route, read, fan out sheets
`ingest_dataset` | privacy, profile, contract, transform, quality, publish or quarantine
Signals | failed checks become typed signals
`triage` | investigate, diagnose, plan, govern, act, verify, learn
Publish or isolate | consumers see a good version, bad data goes to quarantine or DLQ
:::

The important production idea is failure isolation. A bad batch can be quarantined while the last good published view
remains available. A malformed file can move to the dead-letter queue while other files keep flowing.

There are two boundaries to notice in that path. First, **admission** is separate from **processing**. The watcher does
not parse a file as soon as it appears; it waits for size and modification time to stay stable, moves the file into
processing and records a content hash. Second, **loading** is separate from **publishing**. A file can be read and typed
successfully, then still fail quality checks and never become the published view. Many production data incidents happen
because teams blur those boundaries and treat "the job completed" as "the data is safe."

## The five workflows

:::swarmpipe Workflow definitions
The workflow skeletons live in `swarmpipe/runtime/workflows.py`.
:::

| Workflow | Steps | What it owns |
|---|---|---|
| `ingest_file` | `stage -> route -> read -> fanout -> finalize` | One physical file, including multi-sheet fan-out |
| `ingest_dataset` | `load -> privacy -> profile -> onboard -> contract_check -> transform -> quality -> publish -> lineage` | One dataset batch or one spreadsheet sheet |
| `document` | `read -> guard -> summarize -> index -> archive` | Free-text documents for the knowledge base |
| `derive` | `check -> build -> publish` | Event-driven derived datasets such as `sales_enriched` |
| `triage` | `open -> investigate -> diagnose -> impact -> plan -> govern -> execute -> await_approvals -> verify -> learn -> close` | Incident investigation and governed remediation |

Workflows are deterministic skeletons. Some steps invoke agents; the engine still checkpoints every step and resumes
from recorded state.

The step names are part of the operating model. When a run fails at `route`, you investigate file classification. When
it fails at `contract_check`, you inspect schema drift and mapping evidence. When it reaches `publish` with status
`quarantined`, the workflow succeeded at protecting consumers even though the batch was bad. That vocabulary is what
lets CLI output, dashboard traces, eval reports and incidents line up.

## The 27 agents, grouped by team

:::cards SwarmPipe agent teams
Pipeline team | `router`, `privacy_guard`, `profiler`, `steward`, `critic`, `transformer`, `data_assurance`, `publisher`
Triage team | `correlator`, `supervisor`, nine `investigator_*` specialists, `impact`, `planner`, `executor`, `verifier`, `learner`
Service team | `analyst`, `librarian`, `judge`
:::

The split is practical. Pipeline agents make ingestion decisions. Triage agents work an incident. Service agents power
interfaces and evaluations. Only the deterministic `executor` owns `act_*` tools, so investigators and planners cannot
touch the outside world directly.

This grouping also controls cost. Clean ingestion uses only a few model calls: routing, profiling and sometimes
contract stewardship or date-format inference. An incident can use many more calls because specialists run ReAct loops,
the Supervisor diagnoses, the Planner drafts actions and the Learner writes a postmortem. You should expect multi-agent
work to cost more and reserve it for cases where independent evidence, specialization or governed action is worth it.

## Control plane and data plane

:::layers Planes in the architecture
Data plane | watcher, engine, workflows, readers, warehouse, knowledge store, event bus and scheduler
Control plane | agent registry, identity, policy, approvals, kill switches, model gateway, tool gateway, evals and prompt registry
Cross-cutting | traces, metrics, SLOs, audit log and evidence packs
:::

`swarmpipe/app.py` is the composition root. It builds `Services` once, wires dependencies by hand and registers tools
and workflows. That's why the eval harness and the test suite can spin up fully isolated instances, each with its own
data folder.

:::swarmpipe Composition root
The `Services` constructor creates the state DB, warehouse, event bus, `PromptRegistry`, `ModelGateway`,
`ToolGateway`, `PolicyEngine`, `AgentRegistry`, `Engine`, `Scheduler` and `FolderWatcher`. In a production deployment
many of these would be separate services; locally they share one process and SQLite for transparency.
:::

## State DB, warehouse, event bus and scheduler

SwarmPipe uses two different stores. The **state database** records control and execution state: `runs`, `steps`,
`events`, `signals`, `incidents`, `evidence`, `proposals`, `approvals`, `llm_calls`, `tool_calls`, metrics and audit.
The **warehouse** stores dataset versions and views: immutable `t__...` tables, quarantined `q__...` tables and the
published view each consumer reads.

The event bus is an outbox in the state DB. Workflows publish events such as `dataset.published` or `signal.raised`;
dispatchers advance offsets only after consumers succeed. Scheduler monitors handle lease recovery, freshness,
out-of-band warehouse changes, approval expiry, autonomy review, SLOs and retention.

Outbox delivery is one of the least glamorous but most important parts of the design. If `dataset.published` were only
an in-memory callback, a crash between publishing and downstream rebuild would lose work. By storing the event next to
the state change, SwarmPipe can replay consumers safely. Consumers track offsets, so a poison event does not erase the
rest of the stream; this is the same pattern you would keep with Kafka, Service Bus or another production broker.

:::flow-v Control loop after a failed check
Quality check fails
Signal raised
Correlator clusters signals into an incident
Triage run submitted
Policy decides each proposal
Executor acts only when allowed
Verifier checks ground truth
:::

## Operator surfaces

SwarmPipe has several interfaces over the same state:

| Surface | Use it for |
|---|---|
| CLI | `sp status`, `sp runs list`, `sp runs show`, `sp trace`, `sp incidents show` |
| Dashboard | 12 tabs: **Overview**, **Scenarios & Chaos**, **Runs**, **Incidents**, **Approvals**, **Datasets & Lineage**, **Agents & Tools**, **Governance**, **Cost & Metrics**, **Evals**, **Ask the data**, **Knowledge & Memory** |
| REST API | routes such as `/api/runs`, `/api/incidents`, `/api/tools`, `/healthz`, `/readyz`, `/metrics` |
| MCP | read status, incidents, datasets, evidence and governed actions from MCP clients |
| A2A | agent cards and task endpoint, including `/a2a/agents/analyst/tasks` |

The dashboard is not a separate source of truth. It reads the same DB and API that the CLI uses.

That is why the tutorial can mix surfaces freely. A file dropped from **Scenarios & Chaos** appears in `sp runs list`.
An approval created by the triage workflow appears in **Approvals**, can be decided by CLI and can also be served to an
MCP client. The important architecture rule is one system of record with multiple operator views, not separate state
per interface.

## Folder layout and honest limitations

The main folders are `config` for contracts and policy, `prompts` for versioned prompt templates, `knowledge` for
trusted runbooks, `evals` for datasets and gates, `swarmpipe` for code, `docs` for reference docs and `data` for
runtime state. The `data` folder is safe to reset; it is created by `sp init`.

The README is intentionally honest: one SQLite file stands in for Postgres, Kafka, Temporal and an OpenTelemetry
collector; one process stands in for distributed services; simulated models are heuristics; local HMAC and `X-User`
headers stand in for enterprise identity; pickle is used for internal step artifacts. Those choices make the system
inspectable on a laptop, not production-hosting advice.

:::deepdive What would change in a hosted system?
The contracts between components would stay more stable than the components themselves. You might replace SQLite state
with Postgres, the event outbox with Kafka or Service Bus, the hand-built durable engine with Temporal or Durable
Functions, and local traces with an OpenTelemetry collector. The data plane would likely move to object storage and a
warehouse format such as Parquet, Delta or Iceberg. The control plane would use enterprise identity, KMS-backed
secrets, WORM audit storage and deployment gates. The tutorial's value is that the same concepts are visible without
those dependencies.
:::

## Hands-on: inspect the architecture from the CLI

:::lab Status, workflows and fan-out
1. Start from the baseline created in Chapter 0:

   ```powershell
   sp status
   ```

   ```output
   Runs
   | workflow       | status    | n |
   | derive         | blocked   | 1 |
   | derive         | succeeded | 1 |
   | ingest_dataset | succeeded | 7 |
   | ingest_file    | succeeded | 6 |
   ...
   LLM: 13 calls, $0.0029, 14340 tokens | profile offline | kill switches: none | inbox: <your-SwarmPipe-folder>\data\inbox
   ```

2. List just file workflows:

   ```powershell
   sp runs list --workflow ingest_file --limit 8
   ```

   ```output
   | id       | workflow    | status    | current_step |
   |----------+-------------+-----------+--------------|
   | run_...  | ingest_file | succeeded | finalize     |
   ...
   ```

3. Show the `customers.xlsx` run:

   ```powershell
   sp runs show run_mumhlx9730df29
   ```

   ```output
   "children": [
     "run_mumhlxev0c4a1e",
     "run_mumhlxeva40ea8"
   ]
   | stage    | succeeded | deterministic |
   | route    | succeeded | agent         |
   | read     | succeeded | deterministic |
   | fanout   | succeeded | deterministic |
   | finalize | succeeded | deterministic |
   ```

   This is hierarchical orchestration: one file run waits durably for two child dataset runs.
:::

:::lab Read a trace and use the dashboard
1. Pick a recent `sales_daily` dataset run and trace it:

   ```powershell
   sp trace run_mumhmxb7165532
   ```

   ```output
   workflow ingest_file
     step route
       invoke_agent router.route
         chat router
           llm.call sim-small
   workflow ingest_dataset
     step privacy
     step profile
       chat profiler
     step quality
     step publish
     step lineage
   ```

2. Open the dashboard if a server is already running, or start one only in your normal SwarmPipe terminal:

   ```powershell
   sp run
   ```

   Use **Overview** for health and recent work. Use **Runs** to click a run, inspect checkpoints, model calls,
   OpenLineage events and the trace. Do not start a second server if port `8765` is already in use.

3. Switch to **Datasets & Lineage**. Confirm that `sales_daily` has immutable versions and `sales_enriched` is derived
   from it. Then switch to **Cost & Metrics** and look for the model calls used by routing and profiling. You are
   seeing the same execution path from three angles: data state, trace state and cost state.
:::

:::breakit Malformed files are isolated
1. Drop two malformed files:

   ```powershell
   sp scenarios drop malformed --process
   sp dlq list
   sp incidents list --limit 5
   ```

   ```output
   dropped ['sales_2026-09-29_corrupt.csv', 'customers_broken.xlsx'] into <your-SwarmPipe-folder>\data\inbox
   admitted 2 file(s); processed in 3.6s

   | id       | tenant  | reason      | error                         | run_id  |
   |----------+---------+-------------+-------------------------------+---------|
   | dlq_...  | default | UNSUPPORTED | unsupported content: NUL ...  | run_... |
   | dlq_...  | default | UNSUPPORTED | unsupported content: not ...  | run_... |

   | id      | status    | severity | root_cause      | title                    |
   |---------+-----------+----------+-----------------+--------------------------|
   | inc_... | mitigated | high     | malformed_input | customers_broken.xlsx... |
   ```

The bad files go to the DLQ, an incident is opened and the already-published datasets stay available. That is failure
isolation: malformed input is contained instead of poisoning the whole pipeline.
:::

:::warning Local architecture is a teaching architecture
Do not confuse "all in one process" with "how to host it at scale." The semantics matter: durable steps, idempotent
side effects, event offsets, policy decisions, evidence ids and audit records. At larger scale you would likely keep
those semantics and replace local SQLite/runtime pieces with managed stores, queues and workflow engines.
:::

## Quiz

:::quiz
Q: Which workflow owns one physical file and creates child runs for sheets?
- [x] `ingest_file`
- [ ] `ingest_dataset`
- [ ] `triage`
> `ingest_file` routes and reads the file, then fans out one `ingest_dataset` child per dataset or sheet.

Q: What is the difference between the state DB and the warehouse?
- [ ] They are two names for the same tables
- [x] The state DB records execution/control state; the warehouse stores dataset versions and published views
- [ ] The warehouse stores only logs
> Runs, incidents and calls live in state; data versions and consumer views live in the warehouse.

Q: Why is `app.py` called the composition root?
- [ ] It contains all business logic
- [x] It constructs and wires the services once, then passes dependencies explicitly
- [ ] It renders the dashboard
> Explicit wiring avoids hidden globals and makes isolated eval/sandbox instances possible.

Q: What happens to malformed input in the break-it lab?
- [ ] It overwrites the last published version
- [x] It moves to the DLQ and opens an incident while other data remains available
- [ ] It is silently ignored
> Isolation is the point: bad files are visible and recoverable, not allowed to poison consumers.
:::

:::takeaways
- SwarmPipe is organized around five durable workflows, not free-floating agents.
- The 27 agents are grouped into pipeline, triage and service teams with different privileges.
- Control-plane services decide identity, policy, models, tools and approvals; data-plane services move and store work.
- The state DB and warehouse serve different purposes.
- The CLI, dashboard, REST API, MCP and A2A surfaces all inspect the same underlying system.
:::
