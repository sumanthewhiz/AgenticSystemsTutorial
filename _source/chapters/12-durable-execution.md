---
objectives:
  - "Explain why long-running agent workflows need durable state, not just in-memory retries"
  - "Read a SwarmPipe run as persisted steps, recorded outputs, attempts, leases and recovery count"
  - "Use checkpoints, leases, heartbeats and fencing to prevent duplicate work after a crash"
  - "Distinguish retryable errors, permanent errors, deferrals, timeouts and durable waits"
  - "Explain how idempotency keys, sagas, compensation and dead letters make side effects safe"
---

An agentic workflow rarely fits in one request. It reads files, calls models, fans out to specialists, waits for
children, asks a human to approve an action, writes data, emits events and may run for minutes or hours. If that
workflow lives only in process memory, a laptop sleep, deploy, crash or timeout turns "almost done" into "start over
and hope nothing double-sent".

Durable execution is the engineering answer: every run, step output and wait is stored before the next risky action.
After a crash, a new worker resumes from the last checkpoint. The promise is not "nothing ever fails"; it is "failure
does not erase the truth about what already happened."

## The first principle: record before you continue

:::concept Durable execution
A workflow style where progress is persisted outside the worker process. Each completed step becomes a checkpoint, so
recovery can skip work that already succeeded and reuse its recorded output.
:::

For agentic systems this is more important than for ordinary batch jobs. A model call may be nondeterministic, an
outbound notification may be impossible to unsend, and a human approval may arrive while the worker is down. The
runtime therefore treats a step boundary as a transaction boundary:

:::flow-v Durable run lifecycle
Submit run | insert a `runs` row with workflow, input, tenant and trace id
Claim work | worker takes a lease and starts a heartbeat
Run step | call deterministic code, an agent, a child run or a side effect
Checkpoint | insert or update the `steps` row with output and attempt
Resume or finish | skip recorded steps, wait durably, retry, compensate or complete
:::

The important behavior is "resume, do not replay." If SwarmPipe already ran `profile`, `contract_check` and
`transform`, recovery does not ask those agents again. The next worker reconstructs the context from the `steps`
table, then continues at `quality` or whatever step follows the checkpoint.

:::analogy Bank ledger, not sticky note
A sticky note that says "paid invoice?" is not enough. A ledger says who paid, when, with which idempotency key and
what confirmation came back. Durable agent execution uses the same idea for every workflow step.
:::

## Leases, heartbeats and fencing

A durable queue must also prevent two workers from doing the same run at the same time. SwarmPipe solves that with
leases. `Engine.claim` changes a pending run to `running`, writes `lease_owner` and `lease_expires_at`, and returns it
to one worker. A heartbeat thread extends the lease while the worker is alive. If the process dies, the lease stops
moving forward.

:::concept Fencing
A guard that prevents an old worker from continuing after it loses ownership. In SwarmPipe, if the heartbeat update
fails, `LeaseLost` stops the run before the next step or discards a just-finished step result.
:::

The reaper is the other half. `Engine.reap_expired_leases` finds `running` rows whose lease expired, sets them back to
`pending`, increments `recovered_count`, records a `run.recovered` audit row and increments `runs_recovered_total`.
That is why recovery can be automatic: the database, not the dead process, is the source of truth.

:::swarmpipe Where it lives
The durable runtime is `swarmpipe/runtime/engine.py`. Workflows are declared in
`swarmpipe/runtime/workflows.py`. Error types are in `swarmpipe/core/errors.py`, and exponential backoff with full
jitter is `backoff_delay` in `swarmpipe/core/util.py`.
:::

From `swarmpipe/runtime/engine.py`:

```python
for s in self.svc.db.query("SELECT name, status, output FROM steps WHERE run_id=? AND status IN ('succeeded','skipped')", (run["id"],)):
    ctx.outputs[s["name"]] = loads(s["output"], {}) or {}
...
for step in wf.steps:
    if step.name in ctx.outputs:
        continue
```

Those four lines are the resume contract. A succeeded step is not a suggestion; it is recorded history.

## Errors: retry, defer, wait or fail

Production systems should not treat all failures the same. SwarmPipe's `core/errors.py` makes the distinction
explicit:

| Error shape | Runtime behavior | Example in SwarmPipe |
|---|---|---|
| `RetryableError` or `StepTimeout` | retry with exponential backoff and full jitter until the policy is exhausted | transient model or tool failures |
| `PermanentError` | fail the run, run compensations, call the workflow failure hook | unsupported or missing file |
| `Deferred` | reschedule without consuming an attempt | dataset publish lock is busy in `d_publish` |
| `WaitingFor` | park the run durably | `approval:<id>`, `children`, or `run:<id>` |
| `StopWorkflow` | finish early with a terminal status | duplicate file skipped |

Retries use `backoff_delay(attempt, base, cap)`, which implements exponential backoff plus full jitter. Jitter matters
because multiple workers failing at the same dependency should not wake up in lockstep and create a retry storm.

Deferral is not a retry. When `d_publish` cannot acquire the dataset lock, it raises `Deferred(delay_s=0.5)`. The run
moves to `retry_wait`, but the step attempt is not burned. That difference matters for ordinary contention: a busy
lock is not evidence the step is broken.

Agent steps can also time out. `run_with_timeout` runs agent-kind steps under a watchdog thread. If the timeout fires,
the abandoned thread may still finish later, which is exactly why side effects use idempotency keys.

## Idempotency, sagas and side effects

:::concept Idempotency key
A stable key attached to an operation so repeated attempts return the first result instead of performing the side
effect again. SwarmPipe stores these in the `idempotency` table and increments `idempotent_replays_total` on replay.
:::

Publishing a dataset uses `publish:<run_id>`. Document indexing uses `doc:<run_id>`. The Executor uses
`exec:<proposal_id>`. If a crash happens after the side effect but before the worker finishes the surrounding workflow,
recovery calls the same logical operation with the same key and gets the stored result.

Sagas handle the opposite problem: a later step fails after an earlier step changed state. A step can register a
compensation with `ctx.add_compensation`. On permanent failure, `Engine._compensate` runs pending compensations in
reverse order and records `saga.compensate` in audit. For action proposals, `VerifierAgent` uses each action's
compensator when verification fails, and `sp actions rollback <proposal_id>` gives operators the same one-click
rollback path.

:::swarmpipe Side effects with keys
In `swarmpipe/runtime/workflows.py`, `d_publish` wraps publish in `ctx.idempotent(f"publish:{ctx.run_id}", do)`.
In `swarmpipe/agents/triage_agents.py`, `ExecutorAgent.execute` uses `exec:<proposal_id>`.
:::

## Child runs, fan-in and durable waits

SwarmPipe's `ingest_file` workflow reads a workbook and fans out one `ingest_dataset` child run per sheet. The parent
does not poll in memory. `f_fanout` records the child run ids in context, then raises `WaitingFor("children")` until
all children are terminal. The same wait mechanism handles approvals and "wait for another run".

That pattern is what makes human-in-the-loop automation safe. An approval can be created, the worker can exit, and
the approval can be decided later from the dashboard, CLI or MCP. The `approval.decided` event resumes the waiting
run.

:::flow Fan-out and fan-in in `ingest_file`
Parent run | `stage`, `route`, `read`
Child runs | one `ingest_dataset` per sheet
Durable wait | parent status `waiting`, `waiting_on: children`
Fan-in | parent resumes when every child is terminal
Finalize | archive, summarize and emit lineage
:::

## Events are at least once, so handlers must be idempotent

Durable runs are not enough; the event bus must also survive failures. `swarmpipe/core/events.py` stores events in an
outbox table and tracks one offset per consumer. A consumer's offset advances only after its handler succeeds, which
means delivery is at least once. A handler may see the same event again after a crash and must therefore be idempotent.

Poison events are handled deliberately. If a handler fails the same event three times, the dispatcher logs a poison
event and skips it for that consumer so the stream does not block forever. File-level poison input goes to the dead
letter queue: `f_on_failure` moves the file under `data\dlq\<tenant>\`, writes a `.reason.json`, inserts a `dlq` row
and raises a signal. Operators can inspect with `sp dlq list` and, after fixing the cause, redrive with
`sp dlq redrive <dlq_id>`.

## Hands-on: crash after a checkpoint, then recover

:::lab Lab 1 - Crash and resume with `sp tick`
Ids, dates and timings vary. Start from the SwarmPipe project folder with `sp` defined.

1. Reset to a known state and build the baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   ```

2. Tell the next run to crash immediately after the `transform` checkpoint. Drop a clean file without `--process`,
   then process it with `sp tick`:

   ```powershell
   sp chaos crash-after --step transform
   sp scenarios drop clean_day
   sp tick --timeout 120 --no-scheduler
   ```

   ```output
   next run will crash after step 'transform'
   dropped ['sales_2026-09-29.csv'] into ...\data\inbox
   first tick exit=137
   ```

   If you use the `crash` scenario instead, it sets up the same crash-after-transform behavior for the next file.

3. Before the lease expires, the dataset run is still owned by the dead worker:

   ```powershell
   sp runs list --status running --limit 5
   ```

   ```output
   | id              | workflow       | status  | dataset     | current_step | recovered_count |
   | run_mumhn6...   | ingest_dataset | running | sales_daily | transform    | 0               |
   ```

4. Wait about 35 seconds for the lease to expire, then tick again:

   ```powershell
   Start-Sleep -Seconds 35
   sp tick --timeout 180 --no-scheduler
   sp runs show <recovered-run-id>
   ```

   ```output
   admitted 0 file(s); processed in 77.8s
   ...
   "status": "succeeded",
   "recovered_count": 1,
   ...
   Steps (checkpoints)
   | load           | succeeded | 1 | deterministic |
   | privacy        | succeeded | 1 | deterministic |
   | profile        | succeeded | 1 | agent         |
   | contract_check | succeeded | 1 | agent         |
   | transform      | succeeded | 1 | agent         |
   | quality        | succeeded | 1 | deterministic |
   | publish        | succeeded | 1 | deterministic |
   | lineage        | succeeded | 1 | deterministic |
   ```

   The key observation is that `load` through `transform` stayed at attempt `1`. Recovery continued after the
   checkpoint; it did not re-call the model-backed steps.

5. Confirm the recovery metric:

   ```powershell
   sp metrics
   ```

   ```output
   | runs_recovered_total | 1 | 1.0 | ... |
   ```

   In a server-based variant, step 2 uses `sp run`, the process exits with code 137, and restarting `sp run` lets the
   reaper recover the run after the lease expires.
:::

:::lab Lab 2 - Redrive, cancel and dead letters
1. Produce unreadable files:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop malformed --process
   sp dlq list
   ```

   ```output
   | id          | tenant  | reason      | error                         | run_id        |
   | dlq_mum...  | default | UNSUPPORTED | unsupported content: ...      | run_mum...    |
   ```

2. Try the run controls. Redrive only works for failed or dead-lettered runs; cancel only affects pending,
   retry-waiting or waiting runs:

   ```powershell
   sp runs redrive <run_id>
   sp runs cancel <run_id>
   ```

   ```output
   {"redriven": true}
   {"cancelled": false}
   ```

3. After fixing the source file outside this lab, redrive the DLQ entry:

   ```powershell
   sp dlq redrive <dlq_id>
   sp tick --timeout 120 --no-scheduler
   ```

   ```output
   moved back to ...\data\inbox\...
   admitted 1 file(s); processed in ...
   ```

   The important concept is not that malformed data magically becomes valid. It is that poison input is isolated and
   visible instead of blocking the whole pipeline.
:::

:::breakit Duplicate execution is prevented by idempotency
After a baseline, run:

```powershell
sp scenarios drop clean_day --process
sp scenarios drop duplicate --process
sp runs list --status skipped --limit 5
sp metrics
```

Expected shape:

```output
| workflow    | status  | n |
| ingest_file | skipped | 1 |
...
| idempotent_replays_total | ... |
```

`f_stage` detects the byte-identical delivery by content hash and stops the run as `skipped`. If a retry reaches a
side-effect step instead, the idempotency table protects the side effect itself.
:::

## Production notes

:::warning Timeouts do not cancel all work
SwarmPipe's step watchdog raises `StepTimeout`, but Python cannot safely kill arbitrary work already running in the
abandoned thread. The runtime assumes a timed-out side effect may still complete and requires idempotency keys around
side effects. At larger scale, use a worker model that can cancel isolated tasks, but keep idempotency anyway.
:::

At larger scale, SQLite becomes a durable teaching implementation, not the final queue. The same design usually moves
to a transactional database plus a queue, or a workflow engine such as Temporal, Durable Functions or Cadence. The
requirements do not change: persist step outputs, fence leases, make handlers idempotent, separate deferral from
retry, and keep compensations explicit.

## Quiz

:::quiz
Q: Why should a recovered run skip a completed LLM-backed step?
- [ ] LLM calls are always free
- [x] The previous answer is recorded state, and a replay could produce a different answer or duplicate a side effect
- [ ] The model gateway cannot be called twice
> Durable execution treats completed step output as history. Replaying a probabilistic or side-effecting step is not safe by default.

Q: What does `Deferred` mean in SwarmPipe?
- [x] Wait and reschedule without consuming a retry attempt
- [ ] Fail permanently and dead-letter the run
- [ ] Retry immediately with no delay
> Deferral is used for ordinary contention, such as a busy dataset publish lock. It is not counted as a failed attempt.

Q: Which mechanism prevents a dead worker and a new worker from both progressing the same run?
- [ ] The dashboard refresh interval
- [ ] The model cache
- [x] Leases, heartbeats and `LeaseLost` fencing
> The database lease names the owner. The heartbeat renews it, and fencing stops a worker that loses it.

Q: Why are event handlers required to be idempotent?
- [ ] Events are delivered at most once
- [x] Events are delivered at least once, because offsets advance only after handler success
- [ ] Events are never persisted
> At-least-once delivery is reliable but may repeat. Idempotent handlers turn repetition into safe recovery.

Q: What runs when a permanent failure happens after compensations were registered?
- [ ] All steps are retried forever
- [ ] The run is silently deleted
- [x] Pending compensations run in reverse order as a saga
> Compensations are the explicit undo path for side effects that already happened.
:::

:::takeaways
- Durable execution records run and step state in SQLite so crashes do not erase progress.
- Recovery reuses recorded outputs; it does not blindly re-call models or redo side effects.
- Leases, heartbeats, the reaper and `LeaseLost` fencing provide crash recovery without double ownership.
- Retryable errors, permanent errors, deferrals and durable waits are different control-flow paths.
- Idempotency keys and saga compensations make publishing, document indexing and action execution safe under retries.
- The event bus is at least once; idempotent handlers and poison-event handling keep it reliable.
:::
