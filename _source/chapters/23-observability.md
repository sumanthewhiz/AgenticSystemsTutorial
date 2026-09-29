---
objectives:
  - "Explain why agent observability needs traces across decisions, tools, models and cost"
  - "Read a SwarmPipe trace waterfall from workflow step to agent, model call and tool call"
  - "Use `sp metrics`, `sp metrics --prom`, `/metrics` and **Cost & Metrics** to inspect platform health"
  - "Connect structured JSON logs, traces and audit without confusing their purposes"
  - "Evaluate pipeline SLOs and choose which signals should alert a human"
---

A normal batch pipeline can often be debugged from one failed job and one stack trace. An agentic pipeline is different. The failure may be a slow model call, a repair loop, a tool that returned thin evidence, a specialist that abstained, a quota that forced deterministic fallback, or a policy decision that intentionally stopped an action. You need to see the whole chain, not just the final status.

SwarmPipe's answer is deliberately simple and local: spans in SQLite and `data\traces\*.jsonl`, metrics in SQLite and Prometheus text, JSON logs in `data\logs\swarmpipe.jsonl`, and audit in a separate hash-chained log. The goal is not to imitate a cloud observability stack. The goal is to teach what you must preserve when you move to one.

## Why agent observability is different

:::concept Agent observability
The ability to reconstruct what an agentic system did, why it did it, what evidence it used, which model/tool calls were involved, how long each step took and what each step cost.
:::

Three things make this harder than ordinary service telemetry. First, non-determinism: even with the same input, a real model can vary. Second, fan-out: one incident can involve a supervisor, specialists, a planner, a critic, an executor, a verifier and a learner. Third, marginal cost: every retry, repair and fallback spends latency and tokens.

:::flow One incident trace
workflow triage | durable run and step checkpoints
invoke_agent supervisor | fan-out and diagnosis orchestration
invoke_agent investigator_* | specialist reasoning
execute_tool search_knowledge | evidence id and tool latency
chat diagnoser | prompt, role and route
llm.call sim-large | model, tokens, cost and latency
policy and execute | deterministic actions and verification
:::

That is why SwarmPipe uses one trace for every agent involved in an incident. `runs.trace_id` records a run trace; `incidents.trace_id` records the incident trace; model calls, tool calls and evidence rows carry enough ids to join back.

## Traces and GenAI span attributes

SwarmPipe's tracing code lives in `swarmpipe/observability/tracing.py`. It uses OpenTelemetry GenAI semantic-convention names where they fit:

```python
# swarmpipe/observability/tracing.py
GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_PROVIDER = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID = "gen_ai.tool.call.id"
```

Agent spans come from `Agent.invoke` in `swarmpipe/agents/base.py`, model spans from `ModelGateway.chat` and `_try_model`, and tool spans from `ToolGateway.call`. SwarmPipe adds its own attributes such as `swarmpipe.run_id`, `swarmpipe.incident_id`, `swarmpipe.cost_usd`, `swarmpipe.evidence_id`, `swarmpipe.route` and `swarmpipe.root_cause`.

:::swarmpipe Trace implementation
`Tracer.span` buffers spans by execution segment. It writes to the `spans` table and, when `tracing.export_jsonl` is true, appends OpenTelemetry-shaped JSON lines to `data\traces\spans-YYYYMMDD.jsonl`.
:::

Sampling has two parts. `tracing.sample_rate` is head sampling for successful traces; the default in `config\swarmpipe.yaml` is `1.0`, so local labs keep every successful trace. `tracing.always_keep_errors: true` is the tail rule: traces with error spans are kept even when head sampling would drop them. This is industry practice beyond SwarmPipe too: sample success aggressively at scale, but keep errors, high latency and safety-relevant traces.

## Metrics, logs and SLOs

Metrics are not traces. A metric tells you the system changed shape: model latency rose, cache hits stopped, queue depth grew, SLO burn increased. A trace tells you what happened in one execution.

SwarmPipe's `Metrics` class supports counters (`inc`), gauges (`gauge`) and summaries/histograms (`observe`). The CLI command `sp metrics` summarizes the last 24 hours. `sp metrics --prom` and the `/metrics` route expose Prometheus text. The dashboard **Cost & Metrics** tab shows model usage by agent/model, tenant quotas, per-incident cost, SLOs and metric summaries.

:::cards Signals you should alert on
Page now | `slo_breach`, sustained `queue_depth`, repeated `llm_unavailable_total`, DLQ growth, breaker opens, audit verification failure
Ticket soon | cache-hit regression, moderate p95 latency drift, cost trend, repair-rate increase
Record only | individual successful model calls, normal tool calls, routine published versions
:::

SLOs are for the pipeline itself, not for a business dashboard. `config\swarmpipe.yaml` defines `ingest-latency`, `ingest-success` and `triage-latency`. `SLOService.evaluate` computes SLI, burn rate and remaining error budget. `Scheduler.slo` raises a `slo_breach` signal when a configured SLO is breached; in a verification run, a slow baseline run produced an `ingest-latency` warning incident.

Structured logs are implemented in `swarmpipe/observability/logging.py`. The JSON formatter injects `trace_id` and `span_id` from the active span and can carry `run_id`, `incident_id`, `tenant` and `agent` when code logs inside `log_context`. Today, most INFO rows are runtime and watcher events; `--process` CLI runs are intentionally quiet and may produce an empty JSON log. Use logs for coarse runtime breadcrumbs, traces for incident reconstruction, and [Chapter 22](22-audit-evidence.html) for audit-grade evidence.

:::warning Telemetry is not audit
Spans and metrics are sampled, short-lived and optimized for debugging. Audit is complete, hash-chained and optimized for accountability. Do not use a sampled trace as proof that no action happened; use the audit log and evidence pack.
:::

## Hands-on: trace one incident

:::lab Read the trace waterfall
1. Start from the standard lab state:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop volume_drop --process
   sp incidents list
   ```

   ```output
   | id                 | status    | severity | tenant  | dataset     | signal_count | root_cause        | cost_usd |
   | inc_mumhq8or17b7fb | mitigated | critical | default | sales_daily | 1            | truncated_extract | 0.011965 |
   ...
   ```

   Ids, dates, timings and costs vary.

2. Show the incident trace:

   ```powershell
   sp trace inc_mumhq8or17b7fb
   ```

   ```output
   trace fcd46ce15ddb50d4d76c47b3d175356c
   `-- workflow triage +0ms 988ms
       +-- step investigate +1ms 628ms
       |   `-- invoke_agent supervisor.fan_out +215ms 415ms
       |       `-- invoke_agent investigator_quality.investigate +271ms 314ms
       |           +-- chat investigator ... input_tokens=1087 output_tokens=49 cost_usd=0.00019245
       |           +-- execute_tool search_knowledge ... name=search_knowledge evidence_id=ev_mumhqdjk2c0510
       +-- step diagnose +629ms 234ms
       |   `-- chat diagnoser ... input_tokens=712 output_tokens=63 cost_usd=0.00241
       `-- step close +935ms 52ms
   ```

3. Read it from left to right: the workflow step is the durable skeleton, `invoke_agent` is agent work, `chat` is the gateway call, `llm.call` is the provider attempt, and `execute_tool` records an evidence id.

4. Dashboard check: open **Incidents**, select the incident, then inspect the trace waterfall at the bottom. Open **Runs** for the triage run to compare checkpoints and model calls.
:::

:::lab Metrics and Prometheus exposition
1. Summarize metrics:

   ```powershell
   sp metrics
   ```

   ```output
   | metric                  | count | sum      | p50    | p95    | max     |
   | llm_calls_total         | 30    | 30.0     | 1.0    | 1.0    | 1.0     |
   | llm_cost_usd_total      | 30    | 0.018405 | ...    | ...    | 0.00694 |
   | llm_latency_ms          | 30    | 477.1182 | 12.50  | 33.37  | 34.97   |
   | triage_diagnosis_seconds| 2     | 10.825   | 4.236  | 6.589  | 6.589   |
   ```

2. Show Prometheus text:

   ```powershell
   sp metrics --prom
   ```

   ```output
   # TYPE swarmpipe_actions_executed_total counter
   swarmpipe_actions_executed_total{action="request_resend",ok="true"} 1.0
   # TYPE swarmpipe_agent_invocation_ms summary
   swarmpipe_agent_invocation_ms{agent="investigator_quality",op="investigate",quantile="0.95"} 466.1919000209309
   swarmpipe_agent_invocation_ms_count{agent="investigator_quality",op="investigate"} 2
   ```

3. With a server already running, the same exposition is available at:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/metrics
   ```

4. Dashboard check: open **Cost & Metrics**. Compare **By agent**, **By model / status**, **Tenant quotas**, **Per incident** and **Metrics (last 24h)**.
:::

:::lab SLOs and JSON logs
1. Evaluate SLOs:

   ```powershell
   sp slo
   ```

   ```output
   | id             | objective | total | bad | sli    | burn_rate | error_budget_remaining | status   |
   | ingest-latency | 0.95      | 7     | 1   | 0.8571 | 2.8571    | 0.0                    | breached |
   | ingest-success | 0.99      | 7.0   | 0   | 1.0    | 0.0       | 1.0                    | ok       |
   | triage-latency | 0.95      | 2     | 0   | 1.0    | 0.0       | 1.0                    | ok       |
   ```

2. Inspect JSON logs. In `--process` labs this file may be empty; with `sp run --no-web` it contains runtime and watcher INFO rows:

   ```powershell
   Get-Content .\data\logs\swarmpipe.jsonl |
     ConvertFrom-Json |
     Select-Object -First 8 ts,level,msg,trace_id,run_id,incident_id,tenant,agent |
     Format-Table -AutoSize
   ```

   ```output
   ts                     level msg
   --                     ----- ---
   29-09-2026 03:23:56 PM INFO  runtime started: 1 workers, watching <your-SwarmPipe-folder>\data\inbox
   29-09-2026 03:24:00 PM INFO  admitted customers.xlsx (tenant default) -> run run_mumi1iu622216c
   29-09-2026 03:24:23 PM INFO  admitted sales_2026-09-29.csv (tenant default) -> run run_mumi20xd7d04d0
   ```

3. For one incident, filter the file the same way:

   ```powershell
   $incident = "inc_mumhq8or17b7fb"
   Get-Content .\data\logs\swarmpipe.jsonl |
     ConvertFrom-Json |
     Where-Object { $_.incident_id -eq $incident } |
     Select-Object ts,level,msg,trace_id,run_id,incident_id,tenant,agent
   ```

   In a verification run this returned no rows because current SwarmPipe does not log per-incident INFO events. That is an honest product gap; the trace and audit surfaces carry the incident detail.
:::

:::breakit Make model calls slow
1. Clear previous chaos, inject latency and drop a failure:

   ```powershell
   sp chaos clear
   sp chaos set llm_latency_ms "[400,900]"
   sp scenarios drop volume_drop --process
   sp trace <incident_id>
   sp metrics
   sp slo
   ```

2. In a fresh, non-duplicate run you should see longer `llm.call` spans and higher `llm_latency_ms` p95. If you accidentally re-drop a duplicate file, SwarmPipe may skip it idempotently; reset or use a different scenario.

3. Explain the result: the slow model is visible in the trace, aggregated in metrics and eventually reflected in SLO burn if enough work exceeds thresholds. Do not page on one slow call; page on sustained burn, queue growth or user-visible failure.
:::

## Production notes

At larger scale, ship spans to an OpenTelemetry collector, metrics to a time-series backend, logs to indexed storage and audit to a retention-controlled evidence store. Keep the correlation fields identical: `trace_id`, `span_id`, `run_id`, `incident_id`, `tenant`, `agent`, `model`, `tool` and `evidence_id`. The backend changes; the questions do not.

:::quiz
Q: Why is one trace per incident useful?
- [ ] It replaces the audit log
- [x] It lets you follow workflow steps, agents, tools and model calls in one waterfall
- [ ] It proves the model was correct
> The trace is for debugging causality and latency. Correctness still requires evidence and evals.

Q: Which spans use OpenTelemetry GenAI attributes?
- [ ] Only deterministic data-quality checks
- [x] Agent invocation, model chat/call and tool execution spans
- [ ] Only the web dashboard
> SwarmPipe uses names such as `gen_ai.operation.name`, `gen_ai.agent.name`, `gen_ai.request.model` and `gen_ai.tool.name`.

Q: What does `tracing.always_keep_errors` do?
- [x] Keeps error traces even if head sampling would drop them
- [ ] Deletes successful traces
- [ ] Converts logs into audit rows
> It is a tail rule layered on top of head sampling.

Q: Which signal should usually alert a human?
- [ ] One successful `llm.call`
- [x] Sustained SLO burn or repeated model unavailability
- [ ] A normal cache hit
> Alert on user-visible risk and sustained symptoms, not ordinary telemetry.

Q: Why is the incident JSON-log filter allowed to be empty today?
- [ ] Logs are disabled forever
- [ ] The incident did not happen
- [x] Current SwarmPipe logs mostly runtime/watcher INFO rows; incident detail is in traces and audit
> The logging framework supports correlation fields, but the implemented INFO call sites are sparse.
:::

:::takeaways
- Agent observability must connect decisions, tools, model calls, tokens, cost and latency across many agents.
- SwarmPipe traces use GenAI semantic-convention attributes and export spans to `data\traces` as JSONL.
- Metrics answer "is this getting worse?"; traces answer "what happened in this run?"
- `sp slo` evaluates pipeline SLOs and the scheduler can raise `slo_breach` signals.
- JSON logs are structured but currently sparse for incident detail; use traces for debugging and audit for proof.
- Alert on sustained burn, unavailability, DLQ growth, queue depth and audit failure; record routine successful calls.
:::
