---
objectives:
  - "Explain the difference between telemetry and audit in an agentic system"
  - "Verify SwarmPipe's hash-chained audit log and detect deliberate tampering"
  - "Export and inspect an evidence pack for an incident"
  - "Describe version pinning for models, prompts, tools and agents"
  - "Run a kill-switch drill and observe that deterministic ingestion continues while agent actions stop"
---

Telemetry helps operators debug. Audit helps an investigator, regulator or customer trust what happened. A trace can
be sampled, compacted and deleted after a week. An audit record should be complete, tamper-evident and retained long
enough to answer uncomfortable questions.

Agentic systems need both. When a model proposes an action, you need the trace to understand latency and tool calls.
You need audit and evidence to answer: who did what, on whose behalf, under which policy, with which prompt, model,
tool version and approval?

## Telemetry is not audit

:::concept Telemetry
Operational signals such as traces, metrics and logs. They are optimized for debugging and alerting, often sampled
and retained for a short time.
:::

:::concept Audit
A complete, durable, tamper-evident record of security- and governance-relevant decisions and actions.
:::

| Property | Telemetry | Audit |
|---|---|---|
| Purpose | Debug and operate | Prove and investigate |
| Examples | spans, metrics, JSON logs | approvals, executions, policy decisions, kill switches |
| Retention | short-lived, sampled | long-retained, complete |
| Integrity | useful but disposable | hash-chained and verifiable |
| Reader | engineer on call | auditor, incident commander, regulator |

:::flow Audit chain
Record 1 | hash = sha256(genesis + canonical record)
Record 2 | hash = sha256(record 1 hash + canonical record)
Record 3 | hash = sha256(record 2 hash + canonical record)
Verify | recompute links and find the first broken sequence
Anchor | evidence pack stores the chain head
:::

`swarmpipe\governance\audit.py` is small enough to understand. Every row includes `actor`, `actor_type`,
`on_behalf_of`, `action`, `resource`, `decision`, details and trace id. The hash links to the previous hash:

```python
def _hash(prev: str, row: dict) -> str:
    body = canonical_json({k: row.get(k) for k in _FIELDS})
    return hashlib.sha256((prev + body).encode("utf-8")).hexdigest()
```

If a row is edited, deleted or reordered, `verify()` pinpoints the first bad sequence. If you anchor the current head
outside the database, you can also detect truncation after the anchor.

The audit row also separates `actor` from `on_behalf_of`. For autonomous work, `actor` may be `agent:executor` and
`on_behalf_of` may be empty. For delegated work, the same executor can act on behalf of `user:oncall` after an
approval. That distinction is essential during incident response. "The agent did it" is not enough; you need to know
whether the agent acted under autonomous policy, under a human approval, or under a user request routed through a
tool or protocol server.

## Evidence packs

An evidence pack is not a pretty trace. It is the audit-grade bundle for an incident: triggering signals, data
snapshots, hashes, tool evidence, diagnosis, alternatives, policy decisions, approvals, executions, verification,
versions and cost.

:::swarmpipe Evidence code map
- `swarmpipe\governance\audit.py`: `record`, `verify`, `head` and JSONL export.
- `swarmpipe\governance\evidence.py`: `EvidenceService.build` and HTML export.
- `swarmpipe\governance\killswitch.py`: global, agent, tenant, action and LLM kill-switch scopes.
- `docs\OPERATIONS_RUNBOOK.md`: incident response steps when an AI-proposed action caused the problem.
- Dashboard **Governance**: policies, autonomy history, kill switches and audit.
- Dashboard **Incidents**: evidence, proposals, approvals and the incident trace.
:::

`EvidenceService.build` intentionally pulls from records written during normal operation, not from the model's memory:

```python
return {
    "triggering_signals": signals,
    "data_snapshots": versions,
    "context_and_sources": {"tool_evidence": evidence, "case_file": blackboard},
    "proposed_actions": proposals,
    "approvals": approvals,
    "executed_actions": [p for p in proposals if p["status"] in ("executed", "verified", "verification_failed", "rolled_back")],
    "versions": {"models": models, "prompts": prompts, "tools": sorted({f"{t['tool']}@{t['tool_version']}" for t in tools})},
    "audit_anchor": self.svc.audit.head(),
}
```

:::layers What an evidence pack proves
Signals | which detector fired and when
Data snapshots | dataset versions, row counts and content hashes
Evidence | tool outputs and blackboard entries with citations
Policy | evaluated effect, reasons and matched rules
Human oversight | approvals, rejections, comments and typed confirmation
Execution | action results, `executed_by` and `on_behalf_of`
Verification | ground-truth checks and rollback status
Version pins | model, prompt hash, tool version and agent card hash
Cost and audit anchor | model spend and the audit-chain head
:::

## Version pinning matters

If an incident happened yesterday, today's prompt is not enough to explain it. SwarmPipe records prompt id, prompt
version, prompt hash, model/provider, tool version and agent card hash. Prompt hashes are approved in
`prompts\prompts.lock.json`; unapproved prompt changes are refused until an eval gate approves them. Tool
fingerprints and agent-card hashes play the same supply-chain role for tools and agents.

This matters because "the agent decided" is not a postmortem. Which agent version, with which prompt and which model,
under which policy version, decided?

## Kill switches

When the system is causing harm, you need a brake that does not require editing code. SwarmPipe kill switches have
scopes:

| Scope | Example |
|---|---|
| `global` | stop all agent actions and model calls |
| `agent:<id>` | suspend one rogue agent |
| `tenant:<t>` | stop side effects for one tenant |
| `action:<class>` | block one action class such as `rollback_dataset` |
| `llm` | stop model calls while deterministic work continues |

`swarmpipe\governance\killswitch.py` is checked by the tool gateway, the model gateway and the policy engine.
Deterministic ingestion and quality checks continue, so bad files can still be quarantined and signals can still open
incidents.

:::warning A kill switch is not recovery
Engaging a kill switch contains further harm. Recovery still needs rollback, communication, evidence review,
postmortem, eval updates and policy changes. `docs\OPERATIONS_RUNBOOK.md` lists the response: contain, roll back,
communicate, learn and adjust.
:::

## Lab: verify and tamper with audit

:::lab Hash-chain verification
1. Start from a clean baseline and create an incident:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop volume_drop --process
   ```

2. Verify the audit chain:

   ```powershell
   sp audit verify
   ```

   ```output
   OK {"ok": true, "checked": 25, "head": "50a755e15c38b6d4a8339ddfd4f16a66ccfb53483537eaa0eb7b8f8b25866ed3"}
   ```

3. Deliberately tamper with record 3:

   ```powershell
   sp audit tamper --seq 3
   sp audit verify
   ```

   ```output
   edited audit record 3 - now run `swarmpipe audit verify`
   TAMPERED {"ok": false, "checked": 2, "first_bad_seq": 3, "reason": "record content does not match its hash (modified)"}
   ```

   This is a lab-only command. In a real incident, recover by restoring from a trusted backup or resetting the lab
   workspace if this was only an exercise. Do not "fix" the row by hand; that destroys the point of tamper evidence.
:::

## Lab: export an evidence pack

:::lab Incident evidence pack
1. Find an incident id:

   ```powershell
   sp incidents list --limit 3
   ```

2. Export the pack:

   ```powershell
   sp evidence <incident_id>
   ```

   ```output
   evidence pack: ...\data\exports\evidence\inc_mumi99x6266f6e.html
   ```

3. Open the HTML file from the printed path. You should see the incident summary, diagnosis, actions, versions, cost
   and audit anchor. The JSON file with the same id sits next to it and is the machine-readable artifact.

4. Compare it with:

   ```powershell
   sp trace <incident_id>
   ```

   The trace is for debugging the execution path. The evidence pack is for proving what decisions and records existed.
:::

## Lab: kill-switch drill

:::lab Engage global kill switch during an incident
1. Reset after the tamper exercise, then load the baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   ```

2. Engage the global kill switch:

   ```powershell
   sp killswitch on --scope global --reason "drill" --as admin
   ```

   ```output
   kill switch global -> on
   ```

3. Drop a bad file:

   ```powershell
   sp scenarios drop volume_drop --process
   sp incidents list --limit 3
   ```

   ```output
   admitted 1 file(s); processed in 3.8s
   ...
   | workflow       | status      | n |
   | ingest_dataset | quarantined | 1 |
   | triage         | succeeded   | 2 |
   ...
   | id      | status    | severity | dataset     | root_cause        |
   | inc_... | escalated | critical | sales_daily | truncated_extract |
   ```

4. Inspect state:

   ```output
   PROPOSALS
   VERSIONS
   {'dataset': 'sales_daily', 'status': 'quarantined', 'row_count': 18}
   {'dataset': 'sales_daily', 'status': 'published', 'row_count': 1949}
   ```

   No proposals executed while the kill switch was active, but deterministic ingestion and quarantine still worked.
   The status line also shows `kill switches: ['global']`.

5. Release the switch:

   ```powershell
   sp killswitch off --scope global --reason "drill complete" --as admin
   sp status
   ```

   ```output
   kill switch global -> off
   ...
   LLM: 13 calls, $0.0029, 14340 tokens | profile offline | kill switches: none | inbox: ...\data\inbox
   ```
:::

## Break it: engage the brake mid-incident

:::breakit Global kill switch as incident response
Repeat the kill-switch lab, but engage `global` after an incident opens and before approving any action. Watch the
policy reasons change to denial and confirm no action rows reach `executed` or `verified`. For a narrower drill, use:

```powershell
sp killswitch on --scope action:force_publish --reason "block risky override" --as admin
sp killswitch off --scope action:force_publish --reason "drill complete" --as admin
```

Use action-scoped switches when one class is unsafe, tenant-scoped switches when one customer's environment is affected
and `llm` when model calls are the problem but deterministic ingestion should continue.
:::

:::warning Audit anchors should leave the database
SwarmPipe stores the current audit head in evidence packs. In a larger system, also anchor heads outside the mutable
state database: a ticket, WORM store, object-lock bucket or external ledger. A hash chain detects edits and gaps; an
external anchor also helps detect truncation after the anchored sequence.
:::

## When the AI caused the incident

If an AI-proposed action caused harm, follow the operations runbook:

1. Contain with `sp killswitch on --scope action:<class>` or `--scope global`.
2. Roll back with `sp actions rollback <proposal_id> --as oncall` and verify data state.
3. Export `sp evidence <incident_id>` and share the HTML/JSON with affected owners.
4. Let the Learner draft a postmortem, but have humans review it.
5. Harvest or add the case to evals, tighten policy if needed and run `sp evals gate`.

The rollback itself is evidence for automatic demotion, as shown in [Chapter 21](21-policy-autonomy.html).

## Quiz

:::quiz
Q: Why is telemetry not enough for governance?
- [ ] It is too colorful
- [x] It may be sampled, short-lived and optimized for debugging rather than proof
- [ ] It cannot include model calls
> Audit needs complete, tamper-evident records of decisions and actions.

Q: What does `sp audit verify` recompute?
- [x] The hash chain linking each audit row to the previous row
- [ ] Dataset row counts only
- [ ] Prompt token counts
> The verifier detects modified, deleted or reordered audit records.

Q: What is inside an evidence pack?
- [ ] Only the final diagnosis
- [x] Signals, snapshots, evidence, policy, approvals, executions, verification, versions, cost and audit anchor
- [ ] Only screenshots from the dashboard
> Evidence packs are built from operational records written during the incident.

Q: What continues under a global kill switch?
- [x] Deterministic ingestion and quarantine
- [ ] Arbitrary agent actions
- [ ] Non-allowlisted webhooks
> The switch blocks model calls and side effects, while deterministic controls can still contain bad data.

Q: What should you do after a lab audit tamper?
- [ ] Manually edit the hash until verification passes
- [x] Treat it as a detected break; reset the lab or restore from trusted backup
- [ ] Ignore future audit failures
> Hand-editing a tampered audit chain defeats audit integrity.
:::

:::takeaways
- Telemetry helps operators debug; audit proves who did what, for whom and under which policy.
- SwarmPipe audit rows are hash-chained, and `sp audit verify` pinpoints the first tampered sequence.
- Evidence packs combine signals, snapshots, tool evidence, policy decisions, approvals, execution, verification, versions, cost and the audit anchor.
- Version pinning for prompts, models, tools and agents is necessary for credible postmortems.
- Kill switches contain harm immediately, but recovery still requires rollback, communication, learning, eval updates and policy changes.
:::
