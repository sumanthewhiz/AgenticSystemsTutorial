---
objectives:
  - "Recognize common single-agent, multi-agent, data, cost and infrastructure failure modes"
  - "Map each failure mode to a SwarmPipe signal, metric, trace, incident view or chaos scenario"
  - "Explain why valid model output can still be unsafe, ungrounded or operationally wrong"
  - "Run a failure safari that reproduces loops, hallucinated citations, wrong answers, tool errors, outages and crashes"
  - "Reason about combined faults instead of treating failures as isolated incidents"
---

Reliability work gets easier when failures have names. "The agent was bad" is not actionable. "The investigator looped
on the same tool call, the diagnoser cited an evidence id that did not exist, and the planner proposed an invalid
action" gives you a place to look and a control to test.

This chapter is a field guide. It does not re-teach durable execution from [Chapter 12](12-durable-execution.html),
model resilience from [Chapter 13](13-model-resilience.html), or security containment from
[Chapter 19](19-threat-model.html). Instead it names the ways agentic systems fail and shows where SwarmPipe exposes
each one.

## A taxonomy you can operate

:::concept Failure mode
A repeatable way a system can produce an incorrect, unsafe, too expensive or unavailable outcome. A useful failure
mode names the symptom, the detection signal and the control that contains it.
:::

For SwarmPipe, the practical taxonomy has five groups:

:::cards Agent failure families
Single-agent failures | one model-backed component loops, cites fake evidence, picks the wrong tool, returns bad format or overstates confidence
Multi-agent failures | agents disagree, miss handoffs, terminate early or fail to verify another agent's work
Systemic failures | cost runs away, context becomes stale, or one compromised specialist cascades through the swarm
Data failures | a file loads but is wrong, incomplete, stale, private or silently tampered with
Infrastructure failures | crashes, expired leases, poison files, poison events, provider outages and stuck waits
:::

The paper by Cemri et al. describes multi-agent failures in families such as specification and system design,
inter-agent misalignment, weak task verification and bad termination. SwarmPipe's controls line up with that framing:
typed outputs and tool schemas reduce specification drift; signed messages and one decision owner reduce
misalignment; the Critic, Verifier and policy engine address verification; step budgets and loop detection address
termination.

## Field guide table

| Failure | Symptom or signal | Control | Where in SwarmPipe | Reproduce |
|---|---|---|---|---|
| Hallucination or ungrounded claim | diagnosis cites facts not in evidence | evidence ids, groundedness gate, abstention | `TriageSupervisorAgent.diagnose`, `ungrounded_citations_total` | `sp chaos set llm_hallucinated_citation_rate 1` |
| Hallucinated citations | fake `ev_...` ids removed, confidence drops | citation allowlist from tool evidence | **Incidents** evidence, **Runs** `diagnose` output | same as above |
| Wrong tool or bad arguments | `TOOL_ERROR`, invalid proposal, low-quality finding | typed tool contracts, allowlists, stable errors | `swarmpipe/tools/gateway.py` | `sp chaos set tool_error_rate 0.5` |
| Loops and ping-pong | repeated same tool+args, `loop_detected` stop reason | ReAct step budget, loop detector | `Agent.react`, `agent_loops_detected_total` | `sp chaos set llm_loop_rate 0.7` |
| Premature termination | incomplete finding or `unknown` with low evidence | required schemas, Supervisor merge, abstention | triage blackboard and `diagnose` output | raise model outage or tool errors |
| Overconfidence or poor abstention | high confidence with weak evidence | calibrated prompts, evals, abstain path | eval suites and incident diagnosis | `sp chaos set llm_wrong_answer_rate 0.7` |
| Format errors | invalid JSON, schema mismatch | repair loop, schema validation | `llm_repairs_total`, `llm_calls` status | `sp chaos set llm_malformed_rate 0.5` |
| Inter-agent misalignment | specialist findings conflict | Supervisor owns final diagnosis, alternatives retained | triage blackboard | `sp scenarios drop mass_failure --process` |
| Cascading failure | one hijacked specialist biases diagnosis or plan | catalog, policy, approval, egress allowlist | [Chapter 19](19-threat-model.html) | `sp scenarios drop injection --process` |
| Runaway cost | many calls, retries, expensive route | budgets, quotas, cache, clustering | **Cost & Metrics**, `llm_cost_usd_total` | `sp chaos set llm_timeout_rate 0.3` |
| Silent data failure | file "succeeds" but data is wrong | contracts, quality checks, circuit breaker | `Data Assurance`, **Datasets & Lineage** | `sp scenarios drop volume_drop --process` |
| Crash or expired lease | run stuck `running`, then recovered | leases, heartbeat, reaper | `runs_recovered_total` | `sp chaos crash-after --step transform` |
| Poison input or event | DLQ entry or skipped poison event | dead letters, event poison skip after 3 | `sp dlq list`, `core/events.py` | `sp scenarios drop malformed --process` |
| Stale context | old runbook or stale delivery | trust labels, freshness checks, memory review | **Knowledge & Memory**, `stale_resend` | `sp scenarios drop stale_resend --process` |

:::swarmpipe Where the controls live
Agent loop and loop detection: `swarmpipe/agents/base.py`. Triage grounding and degraded fallbacks:
`swarmpipe/agents/triage_agents.py`. Model chaos: `swarmpipe/llm/mock.py`. Tool errors:
`swarmpipe/tools/gateway.py`. Durable crash recovery: `swarmpipe/runtime/engine.py`.
:::

From `swarmpipe/agents/base.py`:

```python
if seen[sig] > 1:
    loops += 1
    self.svc.metrics.inc("agent_loops_detected_total", agent=self.id)
    ...
    if loops >= 2:
        return {"finding": None, "steps": step, "tools_used": tools_used, "evidence_ids": evidence,
                "stop_reason": "loop_detected"}
```

From `swarmpipe/agents/triage_agents.py`, the Supervisor removes fake citations before accepting a diagnosis:

```python
bad = [c for c in d.get("citations", []) if c not in valid]
if bad:
    d["citations"] = [c for c in d.get("citations", []) if c in valid]
    d["confidence"] = max(0.1, float(d.get("confidence", 0.5)) - 0.2)
    d["ungrounded_citations"] = bad
```

## Single-agent failures

Single-agent failures happen inside one agent's loop or one model response. They are often easy to reproduce and hard
to notice without traces. A planner can return a JSON object that validates but proposes a useless action. An
investigator can keep calling the same tool. A diagnoser can cite a fake evidence id because it looks like the evidence ids in
the prompt. A router can classify the file correctly but with unjustified confidence.

SwarmPipe's single-agent controls are layered. The prompt requires a JSON protocol; pydantic validates the shape; the
agent loop has a step budget; repeated tool calls trigger `LOOP_DETECTED`; every tool result receives a real evidence
id; the Supervisor filters citations against the incident's valid evidence ids; and deterministic fallbacks mark
outputs `degraded` when the model layer is unavailable.

:::flow-v Single-agent containment
Model proposes | JSON action or final answer
Schema validates | invalid shape enters repair or fails
Tool gateway checks | allowlist, typed args, stable errors
Loop detector checks | repeated tool+args increments loop metric
Grounding checks | fake citations removed before diagnosis is trusted
Verifier checks | actions are checked against ground truth after execution
:::

## Multi-agent failures

Multi-agent systems add failure modes that do not exist in a single prompt. Two agents can hold inconsistent
assumptions. A specialist can omit a key caveat, and the Supervisor can over-weight it. A team can terminate because
everyone individually did "enough", even though no one verified the shared outcome.

SwarmPipe reduces those risks by assigning one owner for each decision. Specialists investigate; the Supervisor owns
the final diagnosis. The Planner proposes; policy decides; the Executor acts; the Verifier checks. That separation is
also a security boundary. A hijacked specialist can bias a diagnosis, but it cannot write data or send mail. The
cascade risk is real and is covered in [Chapter 19](19-threat-model.html), where prompt injection can fool the model
while the catalog, policy and egress allowlist still contain the outcome.

## Data, cost and infrastructure failures

The most dangerous data failure is silent success: the file loaded, the job ended OK, and the data is wrong. SwarmPipe
turns those into explicit signals with contracts and quality checks. `volume_drop`, `unit_change`, `stale_resend`,
`referential_break` and `pii_leak` all load as files but should not be published as good data.

Runaway cost is a reliability failure because it changes behavior under load. A loop, repeated repair, slow provider
or multi-agent fan-out can multiply calls. SwarmPipe exposes `llm_calls_total`, `llm_cost_usd_total`,
`llm_tokens_total`, `agent_loops_detected_total` and cost by agent in **Cost & Metrics**. Budgets and tenant quotas
are covered in [Chapter 24](24-cost-capacity.html).

Infrastructure failures include crashes and poison messages. Chapter 12 showed `sp chaos crash-after --step transform`
exiting with code 137 and a later `sp tick` recovering the run with `recovered_count: 1`. Poison files go to the DLQ.
Poison events are skipped after three handler failures so one bad event cannot block the event stream forever.

## Hands-on: failure safari

:::lab Lab 1 - Reproduce five agent failures
For each mini-experiment, start from a clean slate unless the step says otherwise:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
```

1. **Looping investigator**:

   ```powershell
   sp chaos set llm_loop_rate 0.7
   sp scenarios drop volume_drop --process
   sp metrics
   sp chaos clear
   ```

   Verified output shape:

   ```output
   chaos.llm_loop_rate = 0.7
   | ingest_dataset | quarantined | 1 |
   | inc_mum...     | mitigated   | critical | sales_daily |
   ...
   | agent_loops_detected_total | ... |
   ```

   In the **Runs** tab, open the triage run. The `investigate` step may show `stop_reason: loop_detected`.

2. **Hallucinated citation**:

   ```powershell
   sp chaos set llm_hallucinated_citation_rate 1
   sp scenarios drop volume_drop --process
   sp chaos clear
   ```

   ```output
   | id          | status            | severity | dataset     | root_cause        |
   | inc_mum...  | awaiting_approval | critical | sales_daily | truncated_extract |
   ```

   The verified `diagnose` output included `ungrounded_citations` and `grounded: false`; the fake ids were removed
   and confidence dropped.

3. **Confidently wrong answer**:

   ```powershell
   sp chaos set llm_wrong_answer_rate 0.7
   sp scenarios drop volume_drop --process
   sp chaos clear
   ```

   ```output
   | id          | status    | severity | dataset     | root_cause              |
   | inc_mum...  | mitigated | critical | sales_daily | data_quality_regression |
   ```

   This is a validly shaped but wrong diagnosis. The file still stayed quarantined because data checks are not
   delegated to the diagnoser.

4. **Tool/backend errors**:

   ```powershell
   sp chaos set tool_error_rate 0.5
   sp scenarios drop volume_drop --process
   sp chaos clear
   ```

   ```output
   | ingest_dataset | quarantined | 1 |
   | inc_mum...     | escalated   | critical | sales_daily |
   ```

   Look in **Runs** for investigator tool results and in **Incidents** for lower-confidence findings or escalation.

5. **Model outage**:

   ```powershell
   sp scenarios drop llm_outage --process
   ```

   ```output
   | ingest_dataset | quarantined | 1 |
   | inc_mum...     | mitigated   | critical | sales_daily |
   ```

   `llm_outage` takes `sim-large` down and drops a volume anomaly. `sim-small` can still serve fallback routes.
:::

:::lab Lab 2 - Infrastructure and poison failures
1. Reproduce a crash and recovery:

   ```powershell
   sp chaos crash-after --step transform
   sp scenarios drop clean_day
   sp tick --timeout 120 --no-scheduler
   Start-Sleep -Seconds 35
   sp tick --timeout 180 --no-scheduler
   sp runs show <recovered-run-id>
   ```

   ```output
   first tick exit=137
   ...
   "status": "succeeded",
   "recovered_count": 1
   | transform | succeeded | 1 | agent |
   | quality   | succeeded | 1 | deterministic |
   ```

2. Reproduce poison input:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop malformed --process
   sp dlq list
   ```

   ```output
   | id         | tenant  | reason      | error                    | run_id     |
   | dlq_mum... | default | UNSUPPORTED | unsupported content: ... | run_mum... |
   ```

3. Open the dashboard:
   - **Runs** shows the failed or dead-lettered workflow.
   - **Incidents** shows the operational incident if one was raised.
   - **Cost & Metrics** shows retries, model calls and loop metrics.
   - **Scenarios & Chaos** shows currently active chaos flags.
:::

:::breakit Combine two faults and reason about the interaction
Run the all-models-down plus bad-data experiment:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --process
sp chaos set llm_outage_models '["sim-large","sim-small"]'
sp scenarios drop volume_drop --process
```

Verified output shape:

```output
| ingest_dataset | quarantined | 1 |
| inc_mum...     | escalated   | critical | sales_daily | truncated_extract |
...
"summary": "(deterministic fallback: LLMUnavailable) majority of specialist findings",
"confidence": 0.45,
"degraded": true
```

The interaction is subtle: model outage weakens diagnosis and lowers confidence, while the volume checks still
quarantine the file. In a weaker design, the same outage might skip diagnosis and accidentally publish; in SwarmPipe,
the data circuit breaker is independent.
:::

## Production notes

:::warning Do not alert on every chaos-visible metric
Some signals deserve pages; others deserve dashboards. A single repaired JSON output may be normal. Sustained
`llm_breaker_open_total`, rising `agent_loops_detected_total`, repeated escalations, cost spikes or quarantined
critical datasets are operational signals. Alert on user or data impact, not every internal correction.
:::

At larger scale, maintain a failure-mode register. Each entry should have a reproduction command or eval case, a
detection signal, an owner, a runbook and an exit criterion. When an incident happens, add it to the register before
you add another generic retry.

## Quiz

:::quiz
Q: Why is "valid JSON" not enough to trust an agent answer?
- [ ] JSON validation proves the facts are true
- [x] JSON validation proves shape, not grounding or correctness
- [ ] SwarmPipe does not use JSON
> A wrong diagnosis can match the schema perfectly. Grounding, verification and evals handle truth.

Q: What metric reveals repeated ReAct tool loops?
- [ ] `llm_cache_hits_total`
- [x] `agent_loops_detected_total`
- [ ] `dataset_publish_total`
> `Agent.react` increments `agent_loops_detected_total` when the same tool and arguments repeat.

Q: Which failure does `sp chaos set llm_hallucinated_citation_rate 1` exercise?
- [x] Fake evidence ids in a model answer
- [ ] Provider 429 rate limits
- [ ] File checksum tampering
> The diagnoser may cite ids that do not exist; the groundedness gate removes them and lowers confidence.

Q: What contains a hijacked specialist before it can change the world?
- [ ] Specialist tools can write data directly
- [ ] The model's confidence score
- [x] Read/write separation, the action catalog, policy, approvals and egress controls
> A specialist can influence the case file, but only the Executor has write tools and every action is governed.

Q: Why is a crash after `transform` not the same as starting over?
- [ ] The file is ignored
- [x] Completed step outputs are checkpoints, so recovery resumes after the recorded step
- [ ] The dashboard remembers the answer
> Durable execution uses persisted steps, not process memory, to decide where to continue.
:::

:::takeaways
- Useful failure analysis names the symptom, the signal, the control and the reproduction path.
- Single-agent failures include loops, fake citations, wrong tools, format errors, premature stops and overconfidence.
- Multi-agent failures include misalignment, weak verification and bad termination; SwarmPipe uses clear ownership and verification boundaries.
- Silent data failures are contained by deterministic contracts, checks and the publish circuit breaker.
- Infrastructure failures are expected: crashes recover through leases and checkpoints; poison files go to the DLQ; poison events are skipped after repeated failures.
- Combined faults matter most. Test interactions such as model outage plus bad data, not only one knob at a time.
:::
