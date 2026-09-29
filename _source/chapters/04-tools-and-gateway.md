---
objectives:
  - "Define a tool contract and explain why annotations are hints, not security"
  - "Show how scopes, per-agent allowlists and read/write separation limit agents"
  - "Follow a tool call through validation, rate limiting, evidence capture and stable errors"
  - "Inspect evidence ids in incidents and traces"
  - "Reproduce tool failures and observe how the swarm degrades"
---

Models can talk; tools let them touch the world. That is where agentic systems become useful and dangerous. A model
that can only classify text may be wrong; a model that can send mail, publish data or update contracts can create an
incident. Production systems put every tool behind a deterministic gateway.

SwarmPipe's rule is simple: agents never call Python functions directly. They call named, typed tools through
`ToolGateway.call`, and the gateway decides whether the call is allowed.

## What a tool contract contains

:::concept Tool contract
A tool contract is a stable interface: name, version, description, argument schema, required scope, side-effect
metadata, trust label, output limit and rate limit. It lets a model choose a tool without letting the model define the
tool.
:::

In `swarmpipe/tools/gateway.py`, `ToolSpec` contains:

```python
name: str
version: str
description: str
args_model: type[BaseModel]
scope: str
read_only: bool = True
destructive: bool = False
idempotent: bool = True
open_world: bool = False
trust: str = "trusted"
max_output_chars: int = 4000
rate_limit_per_min: int = 120
```

The argument model becomes JSON Schema for prompts, MCP clients and validation. If an agent supplies invalid JSON or
wrong fields, the gateway returns `INVALID_ARGUMENTS`; the handler never runs.

That contract is also documentation for the model. The investigator prompt includes only the tools the current agent
may use, and each tool includes its JSON schema. This keeps the tool menu small. A volume specialist does not need to
see every action in the remediation catalog; it needs the few read tools that can prove or disprove a volume problem.

## Annotations are not security

Tool annotations such as `readOnlyHint`, `destructiveHint`, `idempotentHint` and `openWorldHint` help user interfaces
present risk. They are not authorization. A malicious or confused client can ignore them.

:::swarmpipe Annotations plus enforcement
`ToolSpec.annotations` exposes hints. `ToolGateway.call` enforces the real controls: kill switch, approved
fingerprint, agent allowlist, identity scope, tenant access, rate limit, argument validation, output bound, evidence id
and audit for side effects.
:::

That distinction is also why MCP tools in SwarmPipe are safe to expose: the server enforces identity and policy even
when a client only displays hints.

For example, an MCP client may label `decide_approval` as destructive, but the server still checks the acting user,
typed confirmation and approval status. Conversely, a read-only annotation does not grant data access; `query_warehouse`
still runs through identity and the warehouse authorizer.

## Allowlists, scopes and privilege separation

Each agent has `Agent.tools` and `Agent.scopes`. Investigators can call only read tools relevant to their specialty.
The Analyst can call `query_warehouse`. The Executor is the only agent with write tools.

:::cards Tool privilege model
Read tools | `get_check_results`, `get_volume_history`, `get_signal_details`, `search_knowledge`, `query_warehouse`
Action tools | executor-only `act_*` tools such as notify owner, request resend, hold downstream, reprocess with mapping and force publish
Executor-only writes | only `executor` has the `act_*` tools and `action` scopes
Policy before action | planner proposes; policy and approvals decide; executor acts
:::

This is defense in depth. Even if the Planner is tricked into proposing `force_publish`, it cannot execute it. The
proposal must pass catalog validation, policy and possibly human approval; then the Executor calls the action tool.

Read tools also differ in trust. `get_contract` and `get_volume_history` return system-owned metadata and are trusted.
`get_signal_details` and `get_sample_rows` may contain attacker-controlled file content, so their tool specs or returned
payloads mark them untrusted. The prompt builder preserves that label when the result is fed back to an agent.

## The tool gateway pipeline

:::flow-v `ToolGateway.call`
Kill switch check
Tool exists and fingerprint matches approval
Agent allowlist check
Identity scope and tenant check
Per-agent rate limit
Pydantic argument validation
Handler execution
Output truncation and trust label
Evidence id inserted
Tool call logged and metrics updated
Audit side effects
:::

Stable error codes come from `swarmpipe/core/errors.py` and gateway errors: `TOOL_NOT_FOUND`, `TOOL_NOT_APPROVED`,
`TOOL_FORBIDDEN`, `FORBIDDEN`, `RATE_LIMITED`, `INVALID_ARGUMENTS`, `NOT_FOUND`, `TOOL_ERROR_TRANSIENT`,
`TOOL_ERROR` and `KILL_SWITCH`. Stable codes are important because agents and operators can react to categories
instead of parsing prose.

The gateway also bounds success. A successful handler can produce too much data, so `max_output_chars` truncates the
serialized result and records that truncation. Truncation is not silent: the `ToolResult` carries `truncated=True`, the
tool-call row records output size and the trace span includes tool metadata. Large output should push you toward a
more specific tool, not a larger prompt.

## Untrusted output and evidence ids

Some read tools intentionally surface content that came from files or users. `get_signal_details` may include
injection snippets. `get_sample_rows` returns quarantined row samples. These tools mark output as untrusted so prompt
building can spotlight it. Chapter 11 teaches grounding and citations; here you only need the mechanism: every
successful tool result becomes an evidence row with an `ev_...` id.

:::swarmpipe Evidence as the citation substrate
The gateway inserts into `evidence` with `incident_id`, `run_id`, tool name, arguments, bounded content, trust label
and creator. Investigators cite those ids; the Supervisor's groundedness gate removes citations that do not exist.
:::

Tool fingerprints provide a supply-chain check. If a tool's name, version, description, schema or scope changes after
approval, the gateway returns `TOOL_NOT_APPROVED`. Repeated forbidden or unknown tool calls trigger
`ToolGateway._suspicion`; after the threshold, SwarmPipe engages an agent-scoped kill switch and raises a
`rogue_agent` signal.

:::analogy Tools are power tools in a shared workshop
Labels matter, but they do not stop the saw. A real workshop uses locked cabinets, guards, training and logs. SwarmPipe
does the same for agent tools: descriptions help the model choose, while allowlists, scopes, policy and audit enforce
what is actually allowed.
:::

## Read tools versus action tools

Read tools are designed to return evidence, not change state. `get_check_results` summarizes failed checks for one
run. `get_profile_comparison` compares the quarantined batch to the previous baseline. `search_knowledge` returns
runbook snippets with trust labels. `query_warehouse` is read-only SQL over published datasets and uses an authorizer
to reject writes even if a model produces one.

Action tools are catalog actions with compensations and verifiers. The request-resend action writes a notification; its
verifier checks the notification row and outbox file. The hold-downstream action sets holds; its compensation releases
them. The reprocess-with-mapping action starts a child run and waits for it. The force-publish action exists to teach
why "set it to OK" is high risk; policy keeps it tightly constrained.

The Planner may propose action names and parameters, but it still does not call tools. Policy converts each proposal
into deny, recommend, require approval or auto-execute. Only after that decision does the Executor call `act_*`.

At larger scale, teams usually add another boundary: a tool registry owned by the platform team. New tools go through
review, get risk-classified, receive owners and SLOs, and are certified against regression tests before agents can see
them. SwarmPipe's approved fingerprints are the local version of that process. They do not prove a handler is perfect,
but they make silent drift visible: a changed schema or scope is refused until somebody intentionally approves it.

Tool design should also stay narrow. A tempting shortcut is a generic "run SQL" or "call HTTP" tool with broad
permissions. SwarmPipe uses `query_warehouse` only for read-only published data, and notifications resolve recipient
handles through deterministic code. Narrow tools make prompts shorter, errors clearer and policies enforceable.

## Hands-on: inspect tool contracts and evidence

:::lab Use the dashboard and an incident evidence table
1. Open the dashboard and go to **Agents & Tools**. Inspect the Volume Investigator. Its tool
   list is short: `get_volume_history`, `get_check_results`, `search_knowledge`, `recall_similar_incidents`.

2. Drop a volume incident if you do not already have one:

   ```powershell
   sp scenarios drop volume_drop --process
   sp incidents list --limit 3
   ```

   ```output
   | id      | status    | severity | dataset     | root_cause        |
   |---------+-----------+----------+-------------+-------------------|
   | inc_... | mitigated | critical | sales_daily | truncated_extract |
   ```

3. Open **Incidents**, click the incident and find the **Evidence** table. Each investigator tool result has an
   evidence id such as `ev_...`, a tool name, a trust label and bounded content.
:::

:::lab Trace tool calls
1. Trace the same incident:

   ```powershell
   sp trace inc_mumhq18z99025a
   ```

   ```output
   invoke_agent investigator_intake.investigate
     chat investigator
     execute_tool get_run_failure name=get_run_failure evidence_id=ev_mumhq18z99025a
     chat investigator
     execute_tool search_knowledge name=search_knowledge evidence_id=ev_mumhq19d26e8d3
   ...
   invoke_agent executor.execute
     execute_tool act_request_resend name=act_request_resend evidence_id=ev_...
   ```

2. Notice the separation: investigators gather read-only evidence; later, if policy allows it, the Executor performs
   `act_*` tools. The trace shows both as spans, but the identities and allowlists differ.
:::

:::breakit Force tool failures
1. Start from a clean baseline, then force every tool handler to fail transiently:

   ```powershell
   sp chaos set tool_error_rate 1
   sp scenarios drop volume_drop --process
   sp incidents list --limit 3
   sp trace inc_mumhtb4faaf1b2
   sp chaos clear
   ```

   ```output
   chaos.tool_error_rate = 1
   | id      | status    | severity | dataset     | root_cause |
   |---------+-----------+----------+-------------+------------|
   | inc_... | escalated | critical | sales_daily | unknown    |

   execute_tool get_volume_history name=get_volume_history
   execute_tool get_check_results name=get_check_results
   execute_tool get_profile_comparison name=get_profile_comparison
   ```

With tool results unavailable, investigators have weak evidence and the Supervisor may abstain or escalate instead of
pretending. That is the correct failure mode: no evidence, no confident action.
:::

:::warning Open-world tools need extra suspicion
Tools with `open_world=True`, such as notifications, can reach outside the system if not constrained. SwarmPipe keeps
recipients as handles (`owner`, `source_owner`, `security`, `oncall`) and resolves them in the Executor; URL egress is
allowlisted. Tool annotations alone would not be enough.
:::

## Quiz

:::quiz
Q: What actually prevents an investigator from calling `act_force_publish`?
- [ ] The model probably knows not to
- [x] The gateway checks the agent's tool allowlist and identity scope
- [ ] The dashboard hides the button
> Security is enforced server-side in `ToolGateway.call`, not by model intent or UI hints.

Q: Why does every successful tool result get an evidence id?
- [ ] To make ids longer
- [x] To give agents and auditors a stable citation target
- [ ] To bypass schema validation
> Evidence ids are the basis for grounded findings, diagnoses and evidence packs.

Q: What are `readOnlyHint` and `destructiveHint`?
- [ ] Security controls
- [x] UI/client annotations that describe expected behavior
- [ ] Database permissions
> Annotations help clients, but authorization is enforced separately.

Q: What should happen when tool failures remove the evidence needed for a diagnosis?
- [ ] The model should guess
- [x] The system should degrade, abstain or escalate
- [ ] The batch should be force-published
> Production systems must prefer uncertainty over unsupported action.

Q: What does a tool fingerprint protect against?
- [ ] Slow model calls
- [x] Silent drift in a tool contract after approval
- [ ] Duplicate files
> If the approved schema or scope changes, the gateway returns `TOOL_NOT_APPROVED`.
:::

:::takeaways
- Tools are typed contracts, not arbitrary functions exposed to a model.
- Tool annotations are helpful hints; allowlists, scopes, policy and gateway checks are security.
- Read tools and action tools are separated, and only the Executor holds `act_*` tools.
- Untrusted tool output stays labeled untrusted and receives evidence ids for grounding.
- Stable error codes, tool fingerprints and rogue-agent suspension make tool failure and drift operable.
:::
