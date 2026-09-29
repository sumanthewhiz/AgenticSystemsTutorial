---
objectives:
  - "Choose plain code, one agent or many agents for a production workflow"
  - "Explain the core multi-agent patterns: chaining, routing, fan-out/fan-in, supervisor-workers, critic loops and blackboards"
  - "Map each pattern to the SwarmPipe files and dashboard views that implement it"
  - "Measure the token and cost multiplier of a swarm, then decide whether the extra agents earned their keep"
  - "Use a critic ablation to see why independent review and a single decision owner matter"
---

A multi-agent system is not automatically more advanced than a single agent. It is just more moving parts. You use it
when the work naturally has different jobs, different privileges, different evidence sources or different reviewers.
You avoid it when one deterministic function or one bounded agent can do the work with less cost and fewer failure
modes.

SwarmPipe gives you a concrete decision point. Ingesting a normal sales file needs a little model help for routing,
profiling and contract interpretation. Diagnosing a bad file is different: the system must correlate signals, inspect
evidence, reason about root cause, plan actions, critique the plan, apply policy, execute, verify and learn. That is
where a swarm starts to pay for itself.

## Start with the smallest thing that works

:::concept Plain code
Deterministic software whose next step is defined by code, not by model reasoning. Use it for stable rules, arithmetic,
authorization, policy evaluation, signatures, idempotency and verification.
:::

:::concept Agent
A component that uses a model to make a bounded decision: classify, choose a tool, summarize evidence, diagnose,
propose an action or critique someone else's proposal. Deterministic agents count too: the Correlator, Impact Analyzer,
Executor and Verifier are agents because they own a production responsibility, even though they do not call an LLM.
:::

:::concept Multi-agent system
Several agents cooperate on one outcome. The point is not "more brains"; it is separation of duties: specialists see
scoped evidence, an orchestrator owns the decision, reviewers check proposals, and write privileges stay with a narrow
executor.
:::

Use this rule of thumb:

| Shape | Use it when | SwarmPipe example |
|---|---|---|
| Plain code | The rule is stable and must be exact | `DataAssuranceAgent`, policy evaluation, HMAC verification |
| One agent | One bounded judgment is enough | `RouterAgent` classifies a file as tabular, document or unsupported |
| Many agents | The task needs independent specialists, reviewers, least privilege or durable human waits | the `triage` workflow |

:::warning Extra agents are a cost multiplier
Every agent adds prompt tokens, tool results, traces, retries and coordination. Anthropic publicly reported that its
multi-agent research system used about **15x** the tokens of a comparable chat interaction. That does not mean "never
use swarms"; it means the swarm must buy you accuracy, safety, auditability or speed that a simpler design cannot.
:::

## The core patterns

:::flow-v Multi-agent patterns in SwarmPipe
Route | pick the right workflow or specialist
Chain | pass work step by step with typed outputs
Fan out | split independent evidence gathering
Fan in | merge findings under one owner
Critique | independently review a proposal
Blackboard | share a durable case file
:::

### Prompt chaining / sequential handoff

Sequential handoff means one step produces typed output that the next step consumes. The pipeline does not ask one
large prompt to "do ingestion". It runs durable steps: privacy scan, profile, contract check, transform, quality and
publish.

:::swarmpipe Sequential handoff
Look at `swarmpipe/runtime/workflows.py`. The `ingest_dataset` workflow is
`load -> privacy -> profile -> onboard -> contract_check -> transform -> quality -> publish -> lineage`. Each step
records output in the run context before the next step starts, so a crash can resume from the last checkpoint. Durable
execution itself is covered in [Chapter 12](12-durable-execution.html).
:::

### Routing

Routing sends work to the right path. The Router picks tabular, document or unsupported. The Triage Supervisor maps
signal types to specialists.

```python
# swarmpipe/agents/triage_agents.py
SPECIALISTS_BY_SIGNAL = {
    "schema_drift": ["schema"],
    "volume_anomaly": ["volume", "quality"],
    "pii_undeclared": ["privacy"],
    "injection_attempt": ["security"],
    "out_of_band_change": ["integrity"],
}
```

Routing is useful only when the router has a narrow decision and a safe fallback. If a signal is unknown, SwarmPipe
routes to `quality` rather than granting the model every tool.

### Parallelization: fan-out and fan-in

Fan-out runs independent work concurrently. Fan-in joins it back into one decision. SwarmPipe uses this twice. A
spreadsheet file fans out into one child run per sheet. During incident triage, the Supervisor fans out to up to five
specialist investigators, then fans their findings back into one diagnosis.

:::swarmpipe Fan-out/fan-in
`TriageSupervisorAgent.investigate` sends signed tasks to specialists, runs them in a `ThreadPoolExecutor`, receives
their findings and writes each finding to the blackboard. The Supervisor, not the specialists, owns the diagnosis.
:::

### Orchestrator-workers

The orchestrator-worker pattern gives one agent the plan and many agents the subtasks. In SwarmPipe the Supervisor
decides which specialists are needed. The specialist agents are deliberately narrow: the Volume Investigator has volume
history and checks; the Security Investigator has signal details and runbooks; none of them can execute actions.

:::analogy Hospital triage
A triage doctor does not personally run every lab test. They order blood work, imaging and specialist consults, then
make the diagnosis. The lab does not prescribe treatment. SwarmPipe follows the same boundary.
:::

### Evaluator-optimizer

An evaluator-optimizer loop asks one agent to propose and another to review. The Contract Steward proposes mappings
for schema drift. The Critic checks the evidence. The Planner proposes remediation actions. The Critic checks that the
actions exist in the catalog, cite evidence and do not publish bad data.

```python
# swarmpipe/agents/pipeline_agents.py
if self.svc.flags.get("feature.critic_review", True) is False:
    return {
        "verdict": "skipped",
        "reason": "critic disabled (ablation)",
    }
```

This is not bureaucracy for its own sake. It catches plausible model output before it reaches policy and execution.

### Blackboard / shared case file

A blackboard is shared state for a case. Instead of passing a giant chat transcript between agents, each agent posts a
typed entry with author, version and evidence ids.

:::swarmpipe Blackboard
`swarmpipe/agents/messaging.py` defines `Blackboard`. The **Incidents** tab shows the case file: `case_opened`, the
Supervisor's `plan`, investigator `finding` entries, the final `diagnosis` and the Planner's `plan`.
:::

## Why specialization and least privilege matter

Specialists make better prompts because the task is smaller. More importantly, specialists make safer systems because
their tools are smaller. SwarmPipe's investigators have read-only tools such as `get_volume_history`,
`get_schema_diff`, `search_knowledge` and `recall_similar_incidents`. Only the Executor has `act_*` tools, and even
then it can run them only after policy or approval.

:::cards Agent privilege in the triage swarm
Supervisor | chooses specialists and owns the diagnosis; no write tools
Investigators | read-only evidence gathering with scoped tools
Planner | proposes catalog actions; cannot execute
Critic | reviews proposals; cannot execute
Policy engine | deterministic decision, not a model opinion
Executor | only holder of write tools, with idempotency keys
Verifier | checks ground truth after execution
:::

The other design rule is a **single decision owner**. Specialists can disagree. The Supervisor records alternatives,
calibrates confidence, removes bad citations and may abstain. Without one owner, the system can average conflicting
opinions into a confident mush.

## When not to use multiple agents

Do not use a swarm for a deterministic check, a single schema conversion, a short classification or a workflow where
one model call plus validation is enough. Do not use it when you cannot afford the token multiplier. Do not use it to
hide vague ownership: if nobody owns the final answer, adding agents makes accountability worse.

SwarmPipe is intentionally mixed. The Correlator clusters signals before any model reasons. The Impact Analyzer walks
lineage deterministically. The Policy Engine decides autonomy levels with rules. The Verifier checks ground truth. The
LLM agents are reserved for interpretation, diagnosis, planning and explanation.

:::lab Compare ingest cost with incident cost
1. Start clean and load the baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp status
   ```

   ```output
   LLM: 13 calls, $0.0029, 14340 tokens | profile offline | kill switches: none | inbox: C:\...\SwarmPipe\data\inbox
   ```

2. Open the **Cost & Metrics** tab and look at **By agent**. Baseline ingest spends mostly on `router`,
   `profiler`, `steward` and `critic`.

3. Now create an incident:

   ```powershell
   sp scenarios drop volume_drop --process
   sp incidents list --limit 5
   ```

   ```output
   | id                 | status    | severity | dataset     | signal_count | root_cause       | cost_usd |
   | inc_...            | mitigated | critical | sales_daily | 1            | truncated_extract| 0.011965 |
   ```

4. Return to **Cost & Metrics**. In a verification run, the incident added `planner`, `supervisor`,
   the quality investigator, the volume investigator, `learner` and `critic` calls:

   ```output
   {'agent': 'agent:planner', 'calls': 1, 'usd': 0.00694}
   {'agent': 'agent:supervisor', 'calls': 1, 'usd': 0.002875}
   {'agent': 'agent:investigator_quality', 'calls': 4, 'usd': 0.001095}
   {'agent': 'agent:investigator_volume', 'calls': 3, 'usd': 0.000732}
   ```

   Your ids, dates and costs vary. The point is the shape: incident triage costs several times a clean ingest because
   the system buys grounded diagnosis, safe action planning and verification.
:::

:::lab Trace the fan-out tree
1. Use the incident id from the previous lab:

   ```powershell
   sp trace inc_...
   ```

   ```output
   trace ...
   `-- workflow triage
       +-- step investigate
       |   `-- invoke_agent supervisor.fan_out
       |       +-- invoke_agent investigator_volume.investigate
       |       |   +-- execute_tool get_volume_history evidence_id=ev_...
       |       |   `-- execute_tool search_knowledge evidence_id=ev_...
       |       `-- invoke_agent investigator_quality.investigate
       |           +-- execute_tool get_check_results evidence_id=ev_...
       |           `-- execute_tool get_profile_comparison evidence_id=ev_...
       +-- step diagnose
       +-- step plan
       |   `-- invoke_agent critic.review
       +-- step execute
       `-- step verify
   ```

2. Open the **Incidents** tab, select the same incident and compare the trace with the blackboard entries. The trace
   explains *when* agents ran. The blackboard explains *what* they contributed.
:::

:::breakit Disable the critic
1. Turn the critic off and rerun an incident:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp chaos set feature.critic_review false
   sp scenarios drop volume_drop --process
   sp chaos clear
   ```

2. Open the incident blackboard. The Planner entry still appears, but the critique says it was skipped:

   ```output
   {"proposals":["request_resend","hold_downstream","notify_owner"],
    "invalid":[],
    "critique":{"verdict":"skipped","reason":"critic disabled (ablation)"},
    "rounds":1}
   ```

3. In this scenario the plan is still safe because catalog validation, policy and verification remain active. That is
   the lesson: one missing reviewer should not be catastrophic. In harder cases, especially prompt-injection and
   poisoned-memory cases, the critic is one of the layers that prevents a bad proposal from moving forward.
:::

:::warning What changes at larger scale
At scale, the hard part is not spawning agents; it is bounding them. Set a per-run budget across the whole swarm,
cluster before reasoning, cap specialist count, keep write tools out of investigators, and record the single decision
owner for every business outcome.
:::

:::quiz
Q: When should you prefer plain code over an agent?
- [x] When the decision is stable, exact and must be reproducible
- [ ] When the task has many possible interpretations
- [ ] When you need natural-language explanation
> Exact checks, policy evaluation, signatures and idempotency should be deterministic.

Q: Why does SwarmPipe fan out to specialists?
- [ ] To give every agent write access
- [x] To gather independent scoped evidence before one Supervisor diagnoses
- [ ] To avoid recording a final owner
> Specialists gather evidence; the Supervisor owns the final diagnosis.

Q: What is the main cost risk of multi-agent design?
- [ ] Agents cannot use tools
- [x] Token, latency and coordination costs multiply
- [ ] Deterministic code becomes impossible
> More agents mean more prompts, tool results, retries and traces.

Q: What did the critic-off ablation show?
- [ ] Disabling the critic disables all policy checks
- [x] The plan records `critic disabled (ablation)`, while other safety layers still apply
- [ ] SwarmPipe stops routing files
> Defense in depth means one disabled reviewer should not remove catalog validation, policy or verification.
:::

:::takeaways
- Multi-agent is a design trade-off, not a maturity badge.
- SwarmPipe uses plain code for exact controls and agents for bounded judgment.
- The main patterns are routing, chaining, fan-out/fan-in, supervisor-workers, evaluator-optimizer and blackboard.
- Least privilege matters more than agent count: investigators read, the Planner proposes and only the Executor writes.
- A single decision owner keeps disagreement accountable.
- Measure cost by agent before deciding that a swarm earned its token multiplier.
:::
