---
objectives:
  - "Distinguish workload identity, user identity and tool or server identity in an agentic system"
  - "Explain delegation with `on_behalf_of` and why SwarmPipe intersects scopes instead of unioning them"
  - "Describe short-lived credentials, `secret://` references and why secrets never belong in prompts"
  - "Run the Analyst with different users and observe PII tokenization, detokenization and tenant denial"
  - "Explain the controls behind safe natural-language-to-SQL"
---

An agent is not a person, but it still needs an identity. It needs to prove which workload is acting, which user it is
acting for and which tool or server it is calling. Without that separation, a helpful "ask your data" agent becomes a
privilege escalation machine: a low-privilege user asks a high-privilege agent for raw PII, and the system has no idea
whose permissions should win.

SwarmPipe uses the stricter answer: delegated actions get the **intersection** of the agent's permissions and the
user's permissions. The agent can only do what both are allowed to do.

## Three identities, not one

:::concept Workload identity
The identity of the running agent or service, such as `agent:analyst` or `agent:executor`. It limits what that
software component can do even when no human is present.
:::

:::concept User identity
The authenticated human or configured service user the agent acts for, such as `user:analyst`, `user:oncall` or
`user:admin`.
:::

:::concept Tool or server identity
The identity and version of the thing being called: a tool contract, MCP server, model provider or external service.
It is part of the supply chain and audit trail.
:::

:::flow Identity on one delegated action
User asks | `user:oncall` approves or requests work
Agent acts | `agent:executor` performs the catalog action
Tool executes | `act_hold_downstream` runs through the tool gateway
Audit records | executed_by plus on_behalf_of plus policy and approval
:::

In `config\swarmpipe.yaml`, users carry scopes, tenants and PII rights:

```yaml
users:
  admin:   {roles: [admin, approver, operator], scopes: ["*"], pii_access: true, tenants: ["*"]}
  oncall:  {roles: [approver, operator], scopes: ["data:read", "incident", "approval:decide", "knowledge:read", "action"], pii_access: false, tenants: ["*"]}
  analyst: {roles: [viewer], scopes: ["data:read:published", "knowledge:read"], pii_access: false, tenants: ["default"]}
```

The Analyst agent has the *capability* to handle PII, but that capability is effective only when the user also has
PII access. That is the difference between "this code path can detokenize" and "this request may detokenize."

`swarmpipe\governance\identity.py` makes the intersection explicit:

```python
def can(self, scope: str) -> bool:
    ok = _scope_match(self.scopes, scope)
    if self.on_behalf_of is not None:
        ok = ok and self.on_behalf_of.can(scope)
    return ok

@property
def pii_allowed(self) -> bool:
    return self.pii_access and (self.on_behalf_of.pii_allowed if self.on_behalf_of else True)
```

:::analogy Two-key safe
Delegation is a two-key safe. The agent key proves the workload is allowed to use a capability. The user key proves
this person is allowed to request it. Opening the safe requires both.
:::

## Secrets and short-lived credentials

Agents should never see raw provider keys, database passwords or webhook secrets. SwarmPipe configuration uses
`secret://` references for hosted providers:

```yaml
openai: {type: openai_compat, base_url: "https://api.openai.com/v1", api_key: "secret://OPENAI_API_KEY", json_mode: true}
azure:  {type: azure_openai, endpoint: "secret://AZURE_OPENAI_ENDPOINT", api_key: "secret://AZURE_OPENAI_API_KEY", ...}
```

`SecretsBroker` resolves those references from environment variables or `.secrets.json` only at the provider/tool
edge. The model prompt receives neither the reference's value nor a copy of the key. The same module issues
short-lived HMAC-signed tokens with an expiry (`ttl_s` defaults to 300 seconds), so a delegated credential is scoped
and temporary.

:::warning Never hard-code credentials into prompts, tools or examples
Prompt text is logged, cached, evaluated, repaired and sometimes exported as evidence. Use `secret://` references,
resolve them at the boundary and rely on the secret-leak guardrail to block known secret values before a model call.
:::

## Tenant isolation and least privilege

Tenants in SwarmPipe are simple but realistic. Files at the inbox root belong to `default`; files under
`data\inbox\acme` belong to `acme`. Published views are tenant-prefixed, quotas are per tenant and autonomy levels are
per tenant plus action class.

Least privilege is also per agent. Investigators have read-only tools. The Planner can propose, but cannot execute.
Only the Executor has `act_*` write tools. The Analyst has one read-only tool, `query_warehouse`.

:::swarmpipe Identity and access code map
- `swarmpipe\governance\identity.py`: identities, `acting_for`, scope intersection, tenant checks, short-lived tokens and `SecretsBroker`.
- `config\swarmpipe.yaml`: users, tenants, provider `secret://` references and guardrails.
- `swarmpipe\data\pii.py`: deterministic PII detection, tokenization vault and detokenization.
- `swarmpipe\agents\service_agents.py`: Analyst agent, `pii_access = True` capability and NL-to-SQL flow.
- `swarmpipe\data\warehouse.py`: read-only SQLite connection, authorizer, tenant temp views, row limit and VM-step budget.
:::

## PII: classify, tokenize, detokenize only when authorized

SwarmPipe detects PII deterministically with regexes and validators such as Luhn checks. Publishing replaces raw values
with deterministic typed tokens such as `tok_email_<hash>`. The raw value is stored in the `pii_vault` table and is
detokenized only when the effective delegated identity has PII access. Detokenization is audited.

This means tokens still support joins and repeat analysis, but casual access does not reveal personal data.

:::layers Governed data access
Published data | PII columns are tokenized before they reach consumer-facing views
Semantic layer | `config\glossary.yaml` maps business questions to metrics and dimensions
Analyst prompt | model proposes one read-only SQL statement over allowed tables
Static checks | only a single `SELECT` or `WITH` statement is accepted
Tool gateway | `query_warehouse` runs under `agent:analyst acting for user:<name>`
Warehouse authorizer | denies writes, cross-tenant reads and unsafe functions
Result shaping | row limits, truncation flag, PII detokenization only when allowed
:::

`swarmpipe\data\warehouse.py` is the last line of defense if a model writes unsafe SQL:

```python
if action == sqlite3.SQLITE_READ:
    t = arg1 or ""
    if t in allowed or t.startswith(prefix_t) or t.startswith(prefix_v):
        return sqlite3.SQLITE_OK
    denied.append(f"read {t}")
    return sqlite3.SQLITE_DENY
...
con.set_progress_handler(progress, 1000)
rows = cur.fetchmany(max_rows + 1)
```

The model is useful for translation. Authorization is still deterministic code.

## Lab: ask the data as analyst and admin

:::lab Analyst identity and PII access
1. Start from a clean baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   ```

2. Ask a normal governed metric:

   ```powershell
   sp ask "total revenue by region" --as analyst
   ```

   ```output
   4 row(s): region=South, total_revenue=3286293.16; region=West, total_revenue=2923620.95; ...
   SQL: SELECT region AS region, ROUND(SUM(amount), 2) AS total_revenue FROM sales_enriched GROUP BY region ORDER BY total_revenue DESC
   acting as: agent:analyst acting for user:analyst | tables: ['customers', 'inventory', 'regions', 'sales_daily', 'sales_enriched'] | PII detokenized: 0 | evidence: ev_...
   ```

3. Ask for customer emails as a non-PII user:

   ```powershell
   sp ask "emails of customers" --as analyst
   ```

   ```output
   20 row(s): customer_id=C0001, name=tok_person_name_92f5957d48b7, email=tok_email_afbfea10b616, phone=tok_phone_a5fbb5547760; ...
   SQL: SELECT customer_id, name, email, phone FROM customers LIMIT 20
   acting as: agent:analyst acting for user:analyst | ... | PII detokenized: 0 | evidence: ev_...
   ```

4. Ask the same question as admin:

   ```powershell
   sp ask "emails of customers" --as admin
   ```

   ```output
   20 row(s): customer_id=C0001, name=Kabir Iyer, email=kabir.iyer1@example.com, phone=+91 9792966160; ...
   SQL: SELECT customer_id, name, email, phone FROM customers LIMIT 20
   acting as: agent:analyst acting for user:admin | ... | PII detokenized: 60 | evidence: ev_...
   ```

   The agent did not change. The user did. The effective delegated identity changed from no PII access to PII access.
:::

:::lab Tenant, destructive and off-topic refusals
Run three requests that production systems must refuse:

```powershell
sp ask "total revenue by region" --as analyst --tenant acme
sp ask "delete all sales rows" --as analyst
sp ask "what is the weather in Pune today" --as analyst
```

```output
refused: user:analyst may not read published data of tenant acme
refused: I can only read data; changes must go through the pipeline
refused: The question does not map to a governed metric or dataset in the semantic layer
```

Open **Ask the data** in the dashboard and compare the same behavior there. Open **Governance** or `sp audit tail`
afterward to see that denied and answered requests are recorded with the acting identity.
:::

## Lab: PII leak scenario

:::lab Where leaked PII goes
1. Drop a customer file with card numbers typed into the free-text `notes` column:

   ```powershell
   sp scenarios drop pii_leak --process
   sp incidents list --limit 3
   ```

   ```output
   dropped ['customers_2026-09-29.csv'] into <your-SwarmPipe-folder>\data\inbox
   admitted 1 file(s); processed in 6.6s
   ...
   | id      | status    | severity | dataset   | root_cause  | title |
   | inc_... | mitigated | high     | customers | pii_exposure | customers: pii undeclared ... |
   ```

2. Ask for emails again as `analyst`:

   ```powershell
   sp ask "emails of customers" --as analyst
   ```

   ```output
   email=tok_email_afbfea10b616 ... | PII detokenized: 0
   ```

   The leaked embedded PII is masked or tokenized before publication, the privacy incident is flagged, and the
   Analyst still returns tokens for a user without PII rights.
:::

## Break it: try cross-tenant or write access

:::breakit Make the Analyst misbehave
Try to force the Analyst to write data:

```powershell
sp ask "run UPDATE default__sales_daily SET amount=0" --as analyst
```

```output
refused: I can only read data; changes must go through the pipeline
```

Then try to move the user across a tenant boundary:

```powershell
sp ask "total revenue by region" --as analyst --tenant acme
```

```output
refused: user:analyst may not read published data of tenant acme
```

There are two different controls here. The delegated identity fails `can_access_tenant("acme")`, so the query is not
even attempted. For writes, the Analyst's prompt and single-statement check refuse the request; if that failed, the
warehouse authorizer would still deny non-`SELECT` operations on the read-only connection.
:::

:::warning Natural-language-to-SQL is not a database firewall
The model should help choose a metric and produce SQL, not decide who may read which rows. In a larger deployment,
use the same pattern with your real warehouse: semantic layer, read-only role, row and time limits, tenant filters,
audited detokenization and a database-native authorizer or policy engine.
:::

## A2A with identity

Chapter 10 covers A2A in depth. The security point here is simple: an A2A task does not remove server-side identity.
The Analyst's Agent Card is exposed at `/a2a/agents/analyst`, and tasks can be posted to
`/a2a/agents/analyst/tasks`, but the server still applies the configured user, tenant and tool policies. Protocol
metadata is not permission.

## Quiz

:::quiz
Q: When `agent:analyst` acts for `user:analyst`, whose permissions apply?
- [ ] Only the agent's permissions
- [ ] Only the user's permissions
- [x] The intersection of agent and user permissions
> SwarmPipe's `acting_for` delegation requires both identities to allow the scope and tenant.

Q: Why can `--as admin` see raw emails while `--as analyst` sees tokens?
- [x] The Analyst has PII capability, but effective PII access also requires the user to have PII rights
- [ ] Admin uses a different warehouse
- [ ] Tokens are randomly decoded in the CLI
> `pii_allowed` is intersected across the agent and the user.

Q: Where are provider secrets resolved?
- [ ] In the prompt body
- [x] At the provider or tool boundary by `SecretsBroker`
- [ ] In the dashboard JavaScript
> Configuration uses `secret://` references; raw values are not sent to the model.

Q: What blocks a write statement generated by the Analyst?
- [ ] The Critic agent
- [x] Single-`SELECT` validation plus the read-only warehouse authorizer
- [ ] The file watcher
> The model proposes SQL; deterministic checks and SQLite authorization enforce read-only behavior.

Q: What does tenant isolation protect in the lab?
- [ ] Only the dashboard tabs
- [x] Inbox paths, published views, quotas, autonomy and data-access checks
- [ ] Only PII columns
> SwarmPipe models tenancy across ingestion, storage, quotas, policy and identity.
:::

:::takeaways
- Production agents need workload identity, user identity and tool/server identity in the audit trail.
- Delegation must intersect permissions; union semantics are privilege escalation.
- SwarmPipe uses `secret://` references, short-lived HMAC tokens and secret-leak checks so secrets do not enter prompts.
- PII is detected deterministically, tokenized before publication and detokenized only for authorized delegated identities.
- Safe NL-to-SQL requires semantic grounding, read-only execution, tenant scoping, row limits and a database authorizer.
:::
