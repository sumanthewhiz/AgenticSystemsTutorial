---
objectives:
  - "Walk the SwarmPipe triage workflow from first signal to closed incident"
  - "Explain why SwarmPipe clusters signals before model reasoning"
  - "Trace specialist ReAct loops, evidence ids and the grounded diagnosis gate"
  - "Approve a schema-drift remediation and watch the durable workflow resume"
  - "Break diagnosis with hallucinated citations and explain how the gate responds"
---

An incident is what happens after a pipeline says, "I processed the file," but the data still cannot be trusted.
Production systems need more than a job status. They need to know which detector fired, whether related failures share
one probable cause, what evidence supports the diagnosis, who may act, whether the action worked and what should be
remembered next time.

SwarmPipe's `triage` workflow is a full multi-agent incident system. It starts with deterministic signal correlation,
then uses a supervised swarm for investigation and planning. The model is powerful where interpretation is needed, but
every side effect is catalogued, governed, auditable and verified.

## The workflow in order

:::flow-v The triage workflow
open | create the case file and record signals
investigate | Supervisor fans out to scoped specialists
diagnose | one grounded root cause, alternatives, confidence or abstention
impact | deterministic lineage and blast-radius analysis
plan | catalog-only remediation proposal
govern | policy decision per proposal
execute | write tools run with idempotency keys
await approvals | durable wait for human decisions
verify | check ground truth and compensate failures
learn | postmortem, lesson candidate and eval candidate
close | final status, cost and evidence pack
:::

:::swarmpipe Triage implementation
The step order is registered in `swarmpipe/runtime/workflows.py` as
`open -> investigate -> diagnose -> impact -> plan -> govern -> execute -> await_approvals -> verify -> learn -> close`.
The agents live in `swarmpipe/agents/triage_agents.py`; signals and incidents live in `swarmpipe/signals.py`.
:::

```python
# swarmpipe/runtime/workflows.py
Workflow("triage", [
    Step("open", t_open),
    Step("investigate", t_investigate, kind="agent", retry=agent),
    Step("diagnose", t_diagnose, kind="agent", retry=agent),
    Step("impact", t_impact),
    Step("plan", t_plan, kind="agent", retry=agent, when=_not_abstained),
    Step("govern", t_govern, when=_not_abstained),
    Step("execute", t_execute, when=_not_abstained),
    Step("await_approvals", t_await, when=_not_abstained),
    Step("verify", t_verify, when=_not_abstained),
    Step("learn", t_learn, kind="agent", retry=agent),
    Step("close", t_close),
])
```

## Signals and the Correlator: cluster before you reason

:::concept Signal
One detector firing: a failed quality check, schema drift, overdue freshness SLA, prompt-injection finding,
out-of-band checksum mismatch or pipeline failure.
:::

:::concept Incident
A group of correlated signals that should be investigated as one probable cause.
:::

Correlation happens before any model call. The deterministic `CorrelatorAgent` groups by tenant, probable root dataset,
time window and upstream lineage. This avoids six separate LLM investigations when six files all fail from one upstream
rename.

The `mass_failure` scenario proves the point. It drops six files with the same schema drift. SwarmPipe creates six
`schema_drift` signals, but one `sales_daily` incident:

```output
SIGNALS_TO_INCIDENTS
{'incident_id': 'inc_...', 'signals': 6}
INCIDENTS
{'id': 'inc_...', 'status': 'awaiting_approval', 'dataset': 'sales_daily',
 'signal_count': 6, 'root': 'schema_change_upstream'}
```

The debounce delay gives related signals a chance to arrive before triage starts. In production, that is one of the
cheapest cost controls you can add: cluster first, reason once.

## Investigate: supervisor plus read-only specialists

The Supervisor plans the investigation from signal types. A `volume_anomaly` routes to `volume` and `quality`.
`schema_drift` routes to `schema`. `injection_attempt` routes to `security`. Each specialist has a small read-only
tool allowlist.

| Specialist | Typical tools | Job |
|---|---|---|
| `schema` | `get_schema_diff`, `get_contract`, `recall_similar_incidents`, `search_knowledge` | renamed or missing columns |
| `volume` | `get_volume_history`, `get_check_results`, `search_knowledge` | row-count anomalies |
| `quality` | `get_check_results`, `get_profile_comparison`, `get_sample_rows` | data-quality regressions |
| `security` | `get_signal_details`, `search_knowledge` | prompt injection and blocked egress |
| `lineage` | `get_lineage`, `get_open_incidents` | upstream/downstream relationships |

:::concept ReAct loop
A model loop that alternates reasoning and tool use: think about what evidence is missing, call one tool, observe the
result, then either call another tool or finish with a cited finding.
:::

SwarmPipe constrains that loop. The investigator prompt requires one JSON object per turn, either `call_tool` or
`final`. Tool results arrive with evidence ids such as `ev_...`, and the final finding must cite those ids.

## Diagnose: one grounded answer or abstain

The Supervisor merges findings into one diagnosis. It must choose a `root_cause_category`, write a summary, cite valid
evidence ids, list alternatives, set calibrated confidence and either proceed or abstain. The groundedness gate then
checks citations against evidence rows for this incident.

```python
# swarmpipe/agents/triage_agents.py
bad = [c for c in d.get("citations", []) if c not in valid]
if bad:
    d["citations"] = [c for c in d["citations"] if c in valid]
    d["confidence"] = round(max(0.0, d["confidence"] - 0.2), 3)
    d["ungrounded_citations"] = bad
    svc.metrics.inc("ungrounded_citations_total", agent=self.id)
if d["confidence"] < svc.settings.incidents.diagnosis_min_confidence:
    d["abstain"] = True
```

If confidence is too low, the workflow skips planning and execution, learns from the case and closes as escalated.
That is a feature. A production agent must know when not to act.

## Impact, plan and critic

Impact analysis is deterministic. `ImpactAnalyzerAgent` walks lineage to find downstream datasets, consumers, owners,
regulated outputs and blast radius. Planning is model-assisted but catalog constrained: the Planner can propose only
actions from `swarmpipe/tools/actions.py`, such as `request_resend`, `hold_downstream`, `reprocess_with_mapping`,
`update_contract` or `notify_owner`.

The Critic reviews the plan with independent evidence. Details of policy levels and approvals belong to
[Chapter 21](21-policy-autonomy.html); the key point here is that planning does not execute anything.

## Govern, execute, await approvals, verify

`t_govern` evaluates every proposal independently. Some effects are recommendations; some require approval; low-risk
actions may auto-execute with notification. High-risk or typed-confirmation cases wait durably.

The Executor is the only agent with write tools. It records idempotency keys like `exec:<proposal_id>` so retrying a
workflow does not duplicate side effects. The Verifier then checks ground truth: notification file exists, downstream
hold is set, rollback checksum matches, reprocess child run succeeded. If a write action has a compensator and
verification fails, SwarmPipe rolls it back.

Evidence packs and audit details are covered in [Chapter 22](22-audit-evidence.html). In this chapter, notice the
sequence: no proposal becomes "done" merely because a model claimed success.

## Learn and close

The Learner writes a blameless postmortem, proposes an episodic lesson and proposes a regression eval case. Both are
candidate artifacts. Humans curate lessons through `sp memory promote` or `sp memory reject`; eval harvesting is
covered later in [Chapter 18](18-ci-gates-certification.html). Finally, `close` records status, incident cost and an
evidence pack path.

:::lab Walk a full `volume_drop` incident
1. Start from a clean baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   ```

2. Drop the broken file:

   ```powershell
   sp scenarios drop volume_drop --process
   sp incidents list --limit 5
   ```

   ```output
   | id      | status    | severity | dataset     | signal_count | root_cause        | cost_usd |
   | inc_... | mitigated | critical | sales_daily | 1            | truncated_extract | 0.011965 |
   ```

3. Show the incident:

   ```powershell
   sp incidents show inc_...
   ```

   ```output
   "root_cause_category": "truncated_extract",
   "summary": "Batch has 18 rows vs a baseline of ~490.0 (-96.3%): the extract looks truncated",
   "confidence": 0.86,
   "citations": ["ev_...", "ev_..."],
   "grounded": true

   Blackboard:
   version 2 agent:supervisor plan {"specialists":["volume","quality"], ...}
   version 3 agent:investigator_volume finding {"category":"truncated_extract", ...}
   version 4 agent:investigator_quality finding {"category":"data_quality_regression", ...}
   version 6 agent:planner plan {"proposals":["request_resend","hold_downstream","notify_owner"], ...}
   ```

4. Trace the execution:

   ```powershell
   sp trace inc_...
   sp evidence inc_... --no-html
   ```

   ```output
   +-- step investigate
   |   `-- invoke_agent supervisor.fan_out
   |       +-- invoke_agent investigator_volume.investigate
   |       `-- invoke_agent investigator_quality.investigate
   +-- step plan
   |   `-- invoke_agent critic.review
   +-- step execute
   |   +-- execute_tool act_request_resend evidence_id=ev_...
   |   +-- execute_tool act_hold_downstream evidence_id=ev_...
   |   `-- execute_tool act_notify_owner evidence_id=ev_...
   +-- step verify
   evidence pack: C:\...\SwarmPipe\data\exports\evidence\inc_....json
   ```

5. In the dashboard, open **Incidents** for the case, **Cost & Metrics** for cost by agent, and **Datasets & Lineage**
   to see `sales_enriched` held while the bad batch remains quarantined.
:::

:::lab Approve schema drift and watch the workflow resume
1. Start clean, then drop a file where upstream renamed `customer_id` to `client_code` and `amount` to `net_amount`:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop schema_drift --process
   sp approvals list
   ```

   ```output
   | id      | kind   | status  | subject                           | risk   | requires_confirmation |
   | apr_... | action | pending | reprocess_with_mapping on sales_daily | medium |                       |
   ```

2. Approve as the on-call operator:

   ```powershell
   sp approvals approve apr_... --as oncall --comment "approve mapping in lab"
   sp tick --timeout 60
   sp incidents list --limit 5
   ```

   ```output
   approved reprocess_with_mapping on sales_daily by user:oncall
   | id      | status   | severity | dataset     | root_cause            |
   | inc_... | resolved | critical | sales_daily | schema_change_upstream|
   ```

3. Show the incident:

   ```powershell
   sp incidents show inc_...
   ```

   ```output
   "summary": "Required columns ['customer_id', 'amount'] are missing while new columns
   ['client_code', 'net_amount'] appeared; looks like an upstream rename ..."

   | action                 | status   | policy_effect    | autonomy_level | on_behalf_of |
   | reprocess_with_mapping | verified | require_approval | L2             | user:oncall  |
   | notify_owner           | verified | auto_execute_notify | L3          |              |
   ```

4. In **Approvals**, the item disappears. In **Runs**, a child `ingest_dataset` run appears for the reprocess. In
   **Incidents**, the proposal shows execution by `agent:executor` on behalf of `user:oncall`.
:::

:::lab Prove mass failure becomes one incident
1. Reset and run:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop mass_failure --process
   ```

2. Open **Incidents**. You should see one `sales_daily` incident with six signals, not six independent incidents:

   ```output
   dropped ['sales_..._north.csv', 'sales_..._south.csv', 'sales_..._east.csv',
   'sales_..._west.csv', 'sales_..._online.csv', 'sales_..._partner.csv']
   ...
   | id      | status            | severity | dataset     | title               |
   | inc_... | awaiting_approval | critical | sales_daily | sales_daily: schema drift ... |
   ```

3. The useful dashboard views are **Incidents** for `signal_count`, **Cost & Metrics** for `cluster_ratio`, and
   **Runs** for the six quarantined ingest runs that feed one triage run.
:::

:::breakit Force hallucinated citations
1. Make the simulated model cite a fake evidence id:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp chaos set llm_hallucinated_citation_rate 1.0
   sp scenarios drop volume_drop --process
   sp incidents show inc_...
   sp chaos clear
   ```

2. The groundedness gate removes the fake id, records it and lowers confidence:

   ```output
   "root_cause_category": "truncated_extract",
   "confidence": 0.66,
   "citations": ["ev_...", "ev_..."],
   "ungrounded_citations": ["ev_557b5e7892"],
   "grounded": false
   ```

3. In a verification run, the lower confidence pushed the remediation actions into `require_approval` instead of automatic
   execution. That is the real behavior to look for: fake citations do not survive, and reduced groundedness makes the
   system more conservative.
:::

:::warning Triage is only as good as its detectors
The swarm starts from signals. If a detector never raises a signal, the triage workflow never begins. Production teams
should invest at least as much in data checks, freshness monitors and out-of-band detectors as in better prompts.
:::

:::quiz
Q: Why does SwarmPipe correlate before reasoning?
- [ ] To hide failed signals
- [x] To group related failures into one probable cause and avoid duplicate model work
- [ ] To skip evidence collection
> Correlation is a cheap deterministic control that reduces cost and duplicated action.

Q: Who owns the final diagnosis?
- [ ] The first specialist to finish
- [x] The Triage Supervisor
- [ ] The policy engine
> Specialists provide findings; the Supervisor merges them into one accountable diagnosis.

Q: What happens when the diagnosis confidence is below the threshold?
- [ ] The Executor runs every action anyway
- [x] The diagnosis abstains and planning/execution are skipped
- [ ] The incident is deleted
> Abstention is a safety feature that escalates weak evidence instead of acting on it.

Q: Why does `reprocess_with_mapping` wait for approval in the schema-drift lab?
- [x] It changes pipeline state and policy marks it as an L2 approval action
- [ ] The Executor lacks the tool
- [ ] The schema specialist has write access
> Governed actions are decided by policy, not by the Planner's confidence alone.

Q: What does the hallucinated-citation break-it demonstrate?
- [ ] Fake evidence ids are accepted if the root cause is correct
- [x] The gate removes invalid citations, records them and reduces confidence
- [ ] The Router blocks all future files
> Grounding checks are mechanical: citations must exist for this incident.
:::

:::takeaways
- Triage begins with deterministic signal clustering, not model reasoning.
- Specialists use ReAct loops with scoped read-only tools and cited evidence ids.
- The Supervisor is the single decision owner and may abstain.
- The Planner proposes only catalog actions; policy and approvals decide what may happen.
- Execution is idempotent, verification checks ground truth, and compensation handles failed writes.
- Learning creates candidate memory and eval cases; humans curate them before reuse.
:::
