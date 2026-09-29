---
objectives:
  - "Run daily health and readiness checks for SwarmPipe without confusing liveness with readiness"
  - "Use SLO breaches, traces, metrics and scheduler monitors as operational signals"
  - "Handle dead letters, redrive, retention and online backup safely"
  - "Roll out prompt and model changes through eval, shadow, canary and GA gates"
  - "Respond to incidents caused by an AI action, including freeze windows and rollback"
---

The hard part of an agent platform is not starting it. The hard part is trusting it on a boring Tuesday after a model provider slows down, a malformed file lands, a prompt was edited, and an approval is waiting while the on-call engineer is in another tab. Operations is the discipline that turns all of the architecture you have built into daily habits: check health, watch error budgets, contain bad work, keep audit evidence, and change the system only through gates.

SwarmPipe's operations runbook in `docs/OPERATIONS_RUNBOOK.md` is short on purpose. It names the signals operators actually use, the commands that act on them, and the places where an agentic system differs from a normal data pipeline. This chapter turns that runbook into procedures you can practice.

## The daily operating loop

:::concept Operations runbook
A runbook is the practiced answer to "what do I do now?" It should name the signal, the likely meaning, the first checks, the safe containment action, and the handoff or rollback path.
:::

A useful daily loop starts with the platform, not the model. You want to know whether the system is alive, whether it can do work, whether work is stuck, and whether automatic actions are still inside policy.

:::flow-v Daily SwarmPipe checks
Liveness | `GET /healthz`: is the API process answering?
Readiness | `GET /readyz`: are runtime threads present, and is the schema readable?
Queue and runs | `sp status`, `sp runs list --status running`, `sp runs list --status waiting`
SLOs | `sp slo`, plus `slo_breach` signals from the scheduler
Approvals and actions | `sp approvals list`, dashboard **Approvals**, MCP `list_pending_approvals`
DLQ and audit | `sp dlq list`, `sp audit verify`
Models and cost | `sp llm status`, dashboard **Cost & Metrics**
:::

Health and readiness are deliberately different. `/healthz` returns `{"ok": true}` when the API can answer. It does not prove that watchers, workers, the dispatcher or the scheduler are running. `/readyz` returns a readiness shape with `ready`, `threads` and `schema_version`; with a real runtime it reports the live thread names, and in a TestClient-only check it is ready because there is no separate runtime to inspect.

:::swarmpipe Health and readiness
`/healthz` and `/readyz` live in `swarmpipe/web/api.py`. The scheduler monitors live in `swarmpipe/runtime/scheduler.py`: `reaper`, `freshness`, `out_of_band`, `approvals_expiry`, `autonomy_review`, `slo`, `memory_expiry` and `retention`.
:::

`Scheduler.slo` is the bridge to [Chapter 23](23-observability.html): SLOs are not dashboard decorations. When enough runs exist and an SLI falls below its objective, the scheduler raises a `slo_breach` signal. Treat that as a symptom, not a root cause. Inspect `sp trace <ident>`, model latency, queue depth, breaker state and recent dead letters before changing policy.

```python
# swarmpipe/runtime/scheduler.py
class Scheduler:
    def __init__(self, svc):
        self.svc = svc
        self.tasks = [("reaper", 5, self.reaper), ("freshness", 20, self.freshness),
                      ("out_of_band", 30, self.out_of_band),
                      ("approvals_expiry", 30, self.approvals_expiry),
                      ("autonomy_review", 60, self.autonomy_review),
                      ("slo", 30, self.slo), ("memory_expiry", 3600, self.memory_expiry),
                      ("retention", 3600, self.retention)]
```

## Dead letters and redrive

A dead letter is a file or event that cannot be processed safely after the normal retries. It should stop moving forward, preserve evidence, and become an operational item.

:::concept Dead-letter queue
A dead-letter queue (DLQ) is where SwarmPipe parks work that failed permanently. Redrive means moving that work back to the inbox or queue after the cause has been understood and fixed.
:::

SwarmPipe exposes two redrive paths. `sp dlq redrive <dlq_id>` moves a dead-lettered file from `data/dlq/<tenant>/` back into the watched inbox. `sp runs redrive <run_id>` requeues a failed or dead-lettered durable run. Redrive is not "try random things until it passes". For malformed files, fix the source or ask for a resend first; otherwise you simply re-create the same DLQ entry.

:::swarmpipe DLQ implementation
The file workflow's failure path is in `swarmpipe/runtime/workflows.py`; CLI listing and redrive are in `swarmpipe/cli.py` `dlq_list` and `dlq_redrive`. Durable run redrive is in `swarmpipe/runtime/engine.py` `redrive`.
:::

## Retention, backup and audit

Telemetry is disposable; audit is not. SwarmPipe's retention task deletes old spans, metric points, tool-call rows, stale cache entries, old events and leftover processing directories. It does not purge the hash-chained audit log. That split matters: traces answer "why was this slow?"; audit answers "who or what acted, for whom, under which policy, with what evidence?"

`sp maintenance backup` uses SQLite's online backup API for the state and warehouse databases, so it is safe while the system is running. `sp maintenance retention` runs the same cleanup that the scheduler runs hourly.

:::warning Do not back up only the warehouse
For incident response, the state database is as important as the data tables. It contains runs, steps, evidence ids, approvals, proposals, audit rows and prompt/model versions. A warehouse-only backup cannot prove why an agent acted.
:::

## Safe prompt and model upgrades

A prompt or model change is a production change. It can alter diagnosis, action selection, citations, safety behavior and cost. The safe sequence is:

:::flow Rollout path for model and prompt changes
Eval | `sp evals gate` must pass for the working tree
Lock | prompts require `sp evals gate --update-lock` before runtime accepts new hashes
Shadow | candidate prompt/model runs next to production and records agreement
Canary | limited role, tenant or action class; watch feedback and verification
GA | broaden only after evidence, with rollback and kill switch ready
:::

The prompt lock is the most concrete control from [Chapter 18](18-ci-gates-certification.html). A running server refuses unapproved prompt hashes; approved prompts hot-reload within seconds. A new model should be certified per role with `sp evals certify --model <id> --roles <roles>` before routing real work to it. Industry practice at larger scale is to add automated canary cohorts, model cards, release tickets and post-deploy monitors. SwarmPipe shows the mechanics locally.

## Runtime flags, feature flags and freeze windows

`sp chaos show` lists runtime flags recorded in the state database. Many are chaos knobs such as `chaos.llm_timeout_rate`; some are feature or policy toggles such as `feature.critic_review`, `guardrails.spotlighting`, `llm.active_profile` and `policy.freeze_window`.

Freeze windows are policy, not scheduling. When `policy.freeze_window` is true, medium, high and critical actions are escalated to approval by the `freeze-window` rule in `config/policies.yaml`. Detection and quarantine still run. Low-risk notifications can still proceed. That is exactly what you want during month-end close or an active incident: collect facts and contain damage, but do not let agents mutate important state without a human.

One subtlety: `sp chaos clear` clears `chaos.`, `feature.` and `guardrails.` flags and resets the business clock. It does not clear `policy.freeze_window`. Turn the freeze flag off explicitly with `sp chaos set policy.freeze_window false`.

## If an AI action caused the incident

Agentic operations needs one extra page in the runbook: what if the agent caused the problem? Do not argue with the model. Contain the action path first.

1. Engage the narrowest kill switch that stops more damage: `sp killswitch on --scope action:<class> --reason "..." --as oncall`, or global if the class is unclear.
2. Roll back the proposal with `sp actions rollback <proposal_id> --as oncall` when a compensation exists.
3. Verify ground truth: dataset view target, hold flags, notifications, checksums and incident status.
4. Export evidence with `sp evidence <incident_id>` and keep the audit chain intact.
5. Feed the case into the eval flywheel with `sp evals harvest`, then tighten `config/policies.yaml` or the prompt/model gate.

This is where [Chapter 22](22-audit-evidence.html) and [Chapter 21](21-policy-autonomy.html) pay off. The rollback and verification are deterministic; the autonomy ladder can demote an action class after a rollback or verification failure.

## On-call ergonomics

A good on-call surface lets a tired human make the right decision quickly. SwarmPipe has three equivalent approval surfaces: dashboard **Approvals**, CLI `sp approvals list` / `sp approvals approve`, and MCP `list_pending_approvals` / `decide_approval`. High-risk approvals still require typed confirmation even through MCP, because MCP annotations are hints, not authorization.

Approvals should show the diagnosis, confidence, citations, action parameters, policy reasons and blast radius. They should not require the approver to read raw logs. If the evidence is insufficient, reject or leave the approval pending and let expiry resume the run through the escalation path.

## What changes at real scale

SwarmPipe is intentionally local. At real scale the shape stays the same, but the substrates change.

| Local SwarmPipe | Real-scale replacement | Why |
|---|---|---|
| SQLite state DB | Postgres or another transactional state store | multi-node concurrency, backups, access control |
| SQLite event outbox | Kafka, Service Bus or another broker | durable fan-out and independent consumers |
| Visible Python engine | Temporal, Durable Functions or a similar durable-execution engine | proven retries, timers, history and workers |
| JSONL spans and in-process metrics | OpenTelemetry collector plus metrics backend | fleet-wide sampling, retention and alerting |
| Local HMAC key | KMS or vault, OIDC workload identity | key rotation, identity federation, audit |
| Demo `X-User` header | real OIDC user authentication | trustworthy delegation and tenant access |

:::lab Health and readiness checks
1. Start from a clean slate if needed, then load the baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   ```

2. With a server already running from your SwarmPipe folder, check the routes from a second PowerShell window:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/healthz | ConvertTo-Json -Compress
   Invoke-RestMethod http://127.0.0.1:8765/readyz | ConvertTo-Json -Compress
   ```

   ```output
   {"ok":true}
   {"ready":true,"threads":["dispatcher","scheduler","watcher","worker-1","worker-2","worker-3","worker-4"],"schema_version":1}
   ```

   `threads` lists the runtime threads that are alive. If `/healthz` answers but `/readyz` is false or missing threads, the API is alive but the platform is not ready to process work.

3. Open the dashboard **Overview** and **Cost & Metrics** tabs. Look for queue depth, SLO cards, breaker state and recent signals.
:::

:::lab Backup, retention and the DLQ drill
1. After the baseline, run an online backup and retention task:

   ```powershell
   sp maintenance backup
   sp maintenance retention
   ```

   ```output
   online backup written to C:\...\data\exports\backup-20260929-151547
   {
     "spans": 0,
     "metric_points": 0,
     "tool_calls": 0,
     "llm_cache": 0,
     "events": 0,
     "processing_dirs": 0
   }
   ```

2. Drop malformed inputs:

   ```powershell
   sp scenarios drop malformed --process
   sp dlq list
   ```

   ```output
   dropped ['sales_2026-09-29_corrupt.csv', 'customers_broken.xlsx'] into C:\...\data\inbox
   admitted 2 file(s); processed in 3.8s
   ... ingest_file | dead_lettered | 2 ...
   | dlq_mum... | default | UNSUPPORTED | unsupported content: not a valid xlsx (zip) file | ... |
   | dlq_mum... | default | UNSUPPORTED | unsupported content: NUL bytes in a text file      | ... |
   ```

3. Redrive one entry only after deciding the cause is fixed or after asking for a clean resend:

   ```powershell
   sp dlq redrive <dlq_id>
   sp dlq list
   ```

   ```output
   moved back to C:\...\data\inbox\customers_broken.xlsx
   | dlq_mum... | default | UNSUPPORTED | unsupported content: not a valid xlsx (zip) file | ... | 2026-09-29T09:46:02.694+00:00 |
   ```

   Dashboard check: **Runs** shows dead-lettered runs; **Incidents** shows the malformed-input incident; **Governance** and **Cost & Metrics** show the audit and model cost of the triage.
:::

:::lab Simulate a prompt-upgrade rollout
1. Read the current prompt lock status:

   ```powershell
   sp prompts list
   sp evals gate --k 2
   ```

2. For a real prompt change, work on a branch. The intended rollout is: edit the prompt, run `sp evals gate`, approve the hash with `sp evals gate --update-lock`, then run a shadow or canary period before GA.

3. For a model change, certify the role before routing it:

   ```powershell
   sp evals certify --model llama3.2 --roles router
   ```

   Use Chapter 25's warning here: a model that passes `router` can still be unsafe for `diagnoser`.

4. Watch **Evals**, **Cost & Metrics** and **Incidents** during the rollout. The signals you care about are agreement, false positives, citation validity, safety containment, latency and cost.
:::

:::breakit Freeze window during an incident
1. Turn on a freeze window and drop a failure that would normally produce medium-risk remediation:

   ```powershell
   sp chaos set policy.freeze_window true
   sp scenarios drop schema_drift --process
   sp approvals list
   ```

2. Observe that policy escalates medium, high and critical actions to approval. Detection, diagnosis, quarantine and evidence still happen.

3. Clear it explicitly:

   ```powershell
   sp chaos set policy.freeze_window false
   sp chaos show
   ```

   Do not rely on `sp chaos clear` for this flag; `policy.freeze_window` remains `True` after `sp chaos clear`.
:::

:::quiz
Q: What does `/healthz` prove?
- [x] The API process can answer a liveness request
- [ ] All workers are running and processing files
- [ ] The model provider is healthy
> Liveness is intentionally narrow. Use `/readyz`, `sp status`, `sp runs list` and SLO checks for readiness and work health.

Q: Why is a `slo_breach` signal useful but not enough by itself?
- [ ] It always names the root cause
- [x] It tells you a user-facing objective is burning, then traces and metrics help find why
- [ ] It automatically rolls back every dataset
> SLOs are symptom signals. The cause might be model latency, queue depth, dead letters, approvals or a bug.

Q: Which command uses SQLite's online backup API?
- [ ] `sp reset --yes`
- [x] `sp maintenance backup`
- [ ] `sp audit export`
> Online backup copies the state and warehouse databases safely while the system is running.

Q: What should you do first if an AI action is causing damage?
- [ ] Edit the prompt and hope the next run is better
- [x] Contain the action path with the narrowest kill switch, then roll back and verify
- [ ] Delete audit rows that contain the bad decision
> Containment and evidence come before root-cause debate. Audit must stay intact.

Q: What is the safe order for a prompt upgrade?
- [x] Eval, lock, shadow, canary, GA
- [ ] GA, observe, then write evals if something breaks
- [ ] Edit the prompt and restart the server
> Prompt changes are code changes. The lock ensures unapproved hashes are refused at runtime.
:::

:::takeaways
- `/healthz` is liveness; `/readyz`, SLOs, queues, approvals and DLQs tell you operational readiness.
- SLO breaches are signals from [Chapter 23](23-observability.html), not diagnoses. Follow traces, metrics and run state.
- Dead letters preserve unsafe work until a human understands the cause; redrive only after the cause is fixed.
- Telemetry can expire; audit and evidence packs must not.
- Prompt and model upgrades go through eval, lock or certification, shadow, canary and GA.
- Freeze windows escalate risky actions without disabling detection or quarantine.
- At real scale, keep the semantics but replace local substrates with Postgres, a broker, durable execution, an OTel collector, KMS/vault and OIDC.
:::
