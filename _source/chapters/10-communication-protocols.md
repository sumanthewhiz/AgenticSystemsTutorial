---
objectives:
  - "Distinguish shared state, inter-agent messages, A2A tasks and MCP tools"
  - "Explain how SwarmPipe signs and validates internal AgentMessage envelopes"
  - "Inspect agent cards through the registry, dashboard and A2A endpoints"
  - "Run a real MCP JSON-RPC handshake over stdio"
  - "Break a bad inter-agent route and identify the rejection metric"
---

Agents do not just call models. They communicate. A production system must decide which communication is durable state,
which is a point-to-point message, which is an external agent task and which is a tool protocol for an assistant such
as GitHub Copilot CLI. Mixing those surfaces is how teams accidentally give a reasoning agent write access, accept a
forged instruction or lose the evidence trail.

SwarmPipe uses four surfaces: a blackboard for shared incident state, signed internal messages for tightly scoped
tasks, A2A-style HTTP endpoints for agent discovery and task delegation, and MCP over stdio for tools exposed to an
external host.

## Shared state versus messages

:::concept Shared state
Durable data that multiple agents can read: run context, incidents, proposals, evidence rows and blackboard entries.
It is best for facts that must survive crashes and appear in audit/debug views.
:::

:::concept Message
A point-to-point envelope for work assignment or reply. It is best for live coordination: "Supervisor asks Schema
Investigator to investigate this incident" or "Investigator returns a finding."
:::

:::layers SwarmPipe communication layers
Run context | per-run durable inputs and step outputs
Incident blackboard | append-only case file for shared findings
AgentMessage | typed, HMAC-signed internal task and finding messages
A2A HTTP | agent cards and tasks for other agents over REST
MCP stdio | tool protocol for Copilot CLI and other MCP hosts
:::

The blackboard and run context are the default. They make recovery and audit simple. Messages are used only for
internal fan-out/fan-in, where a sender and recipient are known.

This split avoids two common production mistakes. The first is treating a chat transcript as the source of truth. A
transcript is hard to query, hard to resume and easy to over-share. SwarmPipe instead stores structured rows: the
incident, signals, evidence, proposals, approvals and blackboard entries. The second mistake is turning every handoff
into durable global state. A short-lived "please investigate this incident" task is better as a signed message because
it has one sender, one receiver and one allowed reply.

## Signed internal messages

OWASP Agentic AI risk ASI07 covers insecure inter-agent communication. SwarmPipe treats every internal message as
untrusted until verified. `AgentMessage` includes an id, type, sender, recipient, task id, payload, timestamp and
signature. The signature is HMAC-SHA256 over the canonical body, using a key derived from the local master key.

```python
# swarmpipe/agents/messaging.py
ROUTES = {
    ("supervisor", "investigator"): {"task"},
    ("investigator", "supervisor"): {"finding"},
    ("external", "analyst"): {"task"},
    ("analyst", "external"): {"result"},
}
```

On receive, SwarmPipe checks the signature, the addressed recipient and the route allowlist. Rejections are audited,
raise `MESSAGE_REJECTED` and increment `agent_messages_rejected_total`.

:::swarmpipe Message security
The code is in `swarmpipe/agents/messaging.py`. The `MessageBus.receive` method is intentionally deterministic:
message validation is not delegated to a model.
:::

## Agent registry and agent cards

The registry is the inventory of agents: name, description, version, scopes, tools and model route. Each card has a
hash, so silent changes can be detected.

:::swarmpipe Agent cards
`swarmpipe/agents/registry.py` builds all 27 agents and writes their cards to `agent_registry`. The dashboard
**Agents & Tools** tab shows cards, model routes, cost stats and tool counts.
:::

A card is more than documentation. It lets humans and other systems discover what an agent can do before sending work.
SwarmPipe exposes the cards over A2A endpoints:

| Route | Purpose |
|---|---|
| `GET /.well-known/agent-card.json` | the default Analyst card |
| `GET /a2a/agents` | all 27 agent cards |
| `GET /a2a/agents/{agent_id}` | one card, such as `analyst` |
| `POST /a2a/agents/analyst/tasks` | delegate a data question to the Analyst |

## A2A tasks

A2A is useful when another agent wants to delegate a task to SwarmPipe's Analyst. The task body contains message parts.
The response is a task with `status.state`, artifacts and metadata such as acting identity and evidence id.

```python
# swarmpipe/web/api.py
@app.post("/a2a/agents/analyst/tasks")
def a2a_task(body: dict = Body(...), x_user: str | None = Header(None)):
    u = user(x_user or "analyst")
    text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
    res = svc.agents.analyst.ask_question(text, u, body.get("tenant", "default"))
    state = "completed" if not res.get("refused") else "rejected"
```

Notice the identity boundary: the endpoint still resolves a local user and the Analyst still uses governed read-only
SQL. A2A does not bypass the tool gateway.

A2A is intentionally agent-shaped rather than tool-shaped. The caller does not choose `query_warehouse` directly. It
asks the Analyst for an outcome, and the Analyst decides whether the request is answerable, generates safe SQL, runs it
through the read-only tool path and returns an artifact. That is the right abstraction when the remote capability is an
agent with judgment. If you want exact tools and schemas, use MCP instead.

## MCP: tools for external hosts

:::concept MCP
Model Context Protocol is a JSON-RPC protocol that lets a host, such as GitHub Copilot CLI, discover and call tools
and resources exposed by a local or remote server.
:::

SwarmPipe's MCP server runs over stdio with `sp mcp`. It supports `initialize`, `tools/list`, `tools/call`,
`resources/list` and `resources/read`. Tool annotations such as `readOnlyHint` and `destructiveHint` are hints for the
host UI, not security controls. Authorization remains server-side: `sp mcp --as oncall` acts as the configured local
identity; `sp mcp --as analyst` cannot approve actions. The server never forwards client tokens downstream.

MCP resources are read-only context objects. SwarmPipe exposes active contracts as `swarmpipe://contracts/...` and
knowledge documents as `swarmpipe://knowledge/...`. A host can read those resources to explain the pipeline without
calling an action. Tool calls, by contrast, are explicit operations with input schemas and structured results. Keeping
resources and tools separate makes it easier for a host to show safe context without accidentally changing state.
That separation also makes protocol logs easier to review after an incident.

The MCP tools are coarse-grained for an assistant: `pipeline_status`, `list_incidents`, `get_incident`,
`list_datasets`, `get_lineage_impact`, `search_knowledge`, `ask_data_question`, `list_pending_approvals`,
`decide_approval`, `drop_scenario` and `get_evidence_pack`.

:::swarmpipe MCP server
`swarmpipe/mcp_server.py` defines the tool list, annotations, resources and JSON-RPC handler. Tool errors are returned
as `isError: true`; unknown protocol methods return JSON-RPC error `-32601`.
:::

## MCP versus A2A

Use A2A when you are talking to an agent as an agent: discover its card, send it a task and receive an artifact. Use
MCP when a host wants tools and resources: list tool schemas, call a tool and read resources such as contracts and
knowledge documents.

| Need | Prefer |
|---|---|
| "Ask the Analyst agent a question" | A2A task |
| "Let Copilot inspect incidents and datasets" | MCP tools |
| "Expose runbooks and contracts as readable resources" | MCP resources |
| "Coordinate internal specialists in one process" | signed `AgentMessage` plus blackboard |

:::lab Inspect A2A with PowerShell
1. If your SwarmPipe server is already running, use it. Otherwise start it in one terminal:

   ```powershell
   sp run
   ```

2. In a second terminal, request the Analyst card and all cards:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8765/.well-known/agent-card.json
   Invoke-RestMethod http://127.0.0.1:8765/a2a/agents/analyst
   ```

   ```output
   name        : Analyst
   description : Answers natural-language questions with read-only SQL over published datasets, through the semantic layer.
   version     : 1.0.0
   ```

3. Send an A2A task:

   ```powershell
   Invoke-RestMethod -Method Post http://127.0.0.1:8765/a2a/agents/analyst/tasks `
     -ContentType application/json `
     -Body '{"message":{"parts":[{"kind":"text","text":"number of orders by channel"}]}}'
   ```

   ```output
   kind   : task
   status : @{state=completed; timestamp=...}
   artifacts : ...
   metadata  : @{acting_as=agent:analyst acting for user:analyst; evidence_id=ev_...}
   ```

4. Open **Agents & Tools**. Compare the card you fetched with the registry view and its `card_hash`.
:::

:::lab Run an MCP handshake over stdio
1. From the SwarmPipe folder, pipe JSON-RPC lines into `sp mcp`:

   ```powershell
   @'
   {"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"lab","version":"0"}}}
   {"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
   {"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"pipeline_status","arguments":{}}}
   {"jsonrpc":"2.0","id":4,"method":"resources/list","params":{}}
   {"jsonrpc":"2.0","id":5,"method":"no/such-method","params":{}}
   '@ | sp mcp --as oncall
   ```

2. You should see one JSON response per line:

   ```output
   {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",
    "serverInfo":{"name":"swarmpipe","title":"SwarmPipe agentic data pipeline","version":"0.1.0"},
    "instructions":"SwarmPipe control surface. Acting as user:oncall. ..."}}
   {"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"pipeline_status",...},{"name":"list_incidents",...}]}}
   {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"{\"queue_depth\":0,...}"}],
    "isError":false,"structuredContent":{"queue_depth":0,...}}}
   {"jsonrpc":"2.0","id":4,"result":{"resources":[{"uri":"swarmpipe://contracts/customers",...}]}}
   {"jsonrpc":"2.0","id":5,"error":{"code":-32601,"message":"method not found: no/such-method"}}
   ```

3. Tool errors are not protocol errors. Try a missing incident:

   ```powershell
   @'
   {"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_incident","arguments":{"incident_id":"inc_does_not_exist"}}}
   '@ | sp mcp --as oncall
   ```

   ```output
   {"jsonrpc":"2.0","id":1,"result":{"content":[{"type":"text","text":"KeyError: 'incident not found'"}],"isError":true}}
   ```
:::

:::lab Configure GitHub Copilot CLI for MCP
1. Add this block to `~/.copilot/mcp-config.json`, replacing `<repo>` with the absolute path of your SwarmPipe folder
   (with doubled backslashes, for example `C:\\src\\SwarmPipe`):

   ```json
   {
     "mcpServers": {
       "swarmpipe": {
         "type": "local",
         "command": "<repo>\\.venv\\Scripts\\python.exe",
         "args": ["-m", "swarmpipe", "mcp"],
         "cwd": "<repo>",
         "tools": ["*"]
       }
     }
   }
   ```

2. Restart Copilot CLI, then ask it to show pipeline status or explain open incidents. If you need an approval through
   MCP, remember that high-risk approvals still require server-side confirmation text and comments where policy says
   so.
:::

:::breakit Reject a bad internal message
Run this snippet from the SwarmPipe folder. It does not modify project files; it constructs messages in memory and
observes the bus checks.

```powershell
@'
from swarmpipe.app import build_services
svc = build_services(console_logs=False, log_level="WARNING")
msg = svc.bus.send("supervisor", "investigator_schema", "task", {"incident_id": "inc_demo"}, "task_demo")
print("valid receive:", svc.bus.receive(msg, "investigator_schema"))
msg.payload["incident_id"] = "tampered"
try:
    svc.bus.receive(msg, "investigator_schema")
except Exception as exc:
    print(type(exc).__name__, getattr(exc, "code", None), str(exc))
msg2 = svc.bus.send("supervisor", "investigator_schema", "finding", {"bad": True}, "task_demo")
try:
    svc.bus.receive(msg2, "investigator_schema")
except Exception as exc:
    print(type(exc).__name__, getattr(exc, "code", None), str(exc))
print("agent_messages_rejected_total", svc.metrics.summary("agent_messages_rejected_total"))
'@ | python -
```

```output
valid receive: {'incident_id': 'inc_demo'}
SwarmError MESSAGE_REJECTED signature mismatch (message tampered or forged)
SwarmError MESSAGE_REJECTED route supervisor -> investigator_schema (finding) is not allowed
agent_messages_rejected_total {'count': 2, 'sum': 2.0, ...}
```

The receiver did not ask a model whether the message looked safe. It verified the signature and route mechanically.
:::

:::warning Protocols do not replace authorization
MCP annotations and A2A cards help clients behave well, but they are not enforcement. SwarmPipe enforces scopes,
identity, typed confirmations, route allowlists and policy on the server side.
:::

:::quiz
Q: What belongs on the incident blackboard?
- [x] Durable findings, diagnosis, plans and evidence ids that must survive crashes
- [ ] Raw credentials for downstream tools
- [ ] Unverified commands from a spreadsheet cell
> The blackboard is a shared case file with provenance, not a scratchpad for secrets.

Q: What does `agent_messages_rejected_total` measure?
- [ ] Failed LLM calls
- [x] Internal messages rejected for signature, recipient or route problems
- [ ] Dashboard HTTP 404 responses
> Rejected messages are an ASI07 communication-safety signal.

Q: Which protocol is best for Copilot CLI calling SwarmPipe tools?
- [ ] Internal `AgentMessage`
- [ ] A raw blackboard insert
- [x] MCP over stdio
> MCP exposes tool schemas, annotations and resources to external hosts.

Q: Why are MCP annotations not enough?
- [ ] They are encrypted
- [x] They are hints for clients, while authorization must be enforced by the server
- [ ] They disable all write tools
> A malicious or limited client might ignore hints; the server still checks identity and policy.

Q: What does an A2A task return for the Analyst?
- [ ] A Python process id
- [x] A task object with status, artifacts and metadata
- [ ] A raw SQLite connection
> A2A is agent-to-agent task delegation, not database access.
:::

:::takeaways
- Use durable shared state for facts; use signed messages for narrow live coordination.
- SwarmPipe validates internal messages with HMAC signatures, recipient checks and route allowlists.
- Agent cards make capabilities discoverable and card hashes detect silent changes.
- A2A is for agent discovery and task delegation; MCP is for tools and resources exposed to hosts.
- Tool annotations are UX hints, not security boundaries.
- Server-side identity, scope and policy checks are mandatory on every protocol surface.
:::
