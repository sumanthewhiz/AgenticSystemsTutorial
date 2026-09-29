---
objectives:
  - "Explain why production agents act through an action catalog instead of free-form tool use"
  - "Read a SwarmPipe policy decision and connect it to risk tier, autonomy level and escalation rules"
  - "Run policy what-if commands for confidence, injection, blast radius, regulated consumers and freeze windows"
  - "Approve a durable action, observe execution and use one-click rollback"
  - "Explain how autonomy is earned with evidence and withdrawn automatically"
---

Once an agent can recommend a fix, the next question is not "can the model do it?" The question is "under what policy
may this system act, for this tenant, on this dataset, with this evidence?" If that answer lives in a prompt, the
model is governing itself. That is not production governance.

SwarmPipe separates planning from authorization. The Planner proposes actions from a catalog. A deterministic policy
engine decides whether each action is denied, shown as information, recommended, sent for approval or executed
automatically. The autonomy ladder is earned from real outcomes and capped by risk.

## Action catalog, not free-form actions

:::concept Action catalog
A typed list of actions an agent may propose or execute. Each action has a name, parameter schema, risk tier,
verification function and optional compensation.
:::

Free-form actions sound flexible: "do whatever is needed." In production, they are how a model invents
`disable_checks`, emails a URL or publishes data that failed validation. SwarmPipe's actions live in
`swarmpipe\tools\actions.py`: `notify_owner`, `request_resend`, `hold_downstream`, `release_hold`,
`rollback_dataset`, `reprocess_with_mapping`, `update_contract` and `force_publish`.

The catalog is not just a list. Each action has:

| Property | Why it matters |
|---|---|
| Pydantic params | invalid arguments fail before execution |
| Risk tier | policy can treat low, medium, high and critical actions differently |
| Reversibility | rollback and compensation are part of the action contract |
| Verification | the Verifier checks ground truth after execution |
| Tool spec | only the Executor gets `act_*` write tools |

:::flow Governed action path
Diagnosis | grounded root cause and confidence
Planner | proposes catalog actions only
Critic | reviews plan against evidence
Policy | evaluates risk, autonomy and escalations
Approval | durable wait when required
Executor | runs typed action through the tool gateway
Verifier | checks ground truth and compensates on failure
Autonomy | records evidence for promotion or demotion
:::

## Policy-as-code

`config\policies.yaml` is the contract between the business and the agent platform. It defines the ladder effects:

```yaml
level_effects:
  L0: inform_only
  L1: recommend
  L2: require_approval
  L3: auto_execute_notify
  L4: auto_execute
```

It also defines risk and caps per action. For example, `request_resend` starts at L3 and may reach L4, while
`force_publish` starts at L1 and is capped at L2 with typed confirmation and annotation required.

:::concept Autonomy ladder
The allowed effect for an action class in a tenant: L0 inform only, L1 recommend, L2 require approval, L3 auto-execute
with notification and rollback, L4 auto-execute within policy.
:::

`swarmpipe\governance\policy.py` describes the decision order in code:

```python
EFFECTS = ["auto_execute", "auto_execute_notify", "require_approval", "recommend", "inform_only", "deny"]
AUTO_EFFECTS = {"auto_execute", "auto_execute_notify"}

def stricter(a: str, b: str) -> str:
    return a if EFFECTS.index(a) >= EFFECTS.index(b) else b
```

Escalations only move decisions stricter. Denials win. The model cannot talk policy into becoming looser.

:::swarmpipe Policy code map
- `config\policies.yaml`: ladder effects, action risk, defaults, max levels, escalations, denials, freeze windows and autonomy rules.
- `swarmpipe\governance\policy.py`: `PolicyEngine.evaluate`, `ActionContext` and `PolicyDecision`.
- `swarmpipe\governance\approvals.py`: durable approvals and typed confirmation.
- `swarmpipe\governance\autonomy.py`: evidence counters, promotion review and automatic demotion.
- `swarmpipe\tools\actions.py`: catalog execution, verification and compensation.
:::

## Escalations and denials

Escalations are context-sensitive brakes:

| Rule | Effect |
|---|---|
| `low-confidence` | confidence below 0.75 requires approval |
| `injection-suspected` | suspected prompt injection requires approval |
| `blast-radius` | high or critical actions affecting more than 3 consumers require approval |
| `regulated-consumer` | high or critical actions touching regulated consumers require approval |
| `freeze-window` | medium or higher risk changes require approval during a freeze |
| `global-auto-cap` | too many automatic actions in one hour require approval |

The denial rule is stricter: `cooldown` refuses repeated state-changing actions on the same target within five minutes
from another incident. It prevents remediation flapping.

:::analogy Railway signals
The Planner can suggest a route, but policy is the signaling system. A green signal may become amber because of a
freeze window, red because of a kill switch, or stay red forever because the track is not allowed for that train.
:::

## Durable approvals and typed confirmation

Approvals are not chat messages. They are durable rows tied to a run, incident, proposal, risk and user decision. When
a triage run needs approval, it waits. If the process restarts, the wait remains. Approval records include
`requires_confirmation` for high-risk actions, and the CLI supports:

```powershell
sp approvals approve <approval_id> --as oncall --comment "reviewed" --confirm <required-text>
```

`force_publish` is the canonical "be careful" action: critical risk, typed confirmation, annotation required and
hard-capped below full autonomy.

The approval surface also matters. The dashboard **Approvals** tab, the CLI and MCP all operate on the same durable
approval rows. That means a workflow does not care whether a human clicks a dashboard button or runs a command; it
resumes from the same recorded decision. This is different from asking a model, "should I proceed?" A model answer is
another artifact to evaluate. An approval is an authorization event with a user, timestamp, comment, optional
confirmation text and policy context. If the operator is unavailable, the run stays waiting rather than guessing.

## Lab: policy what-if matrix

:::lab Read policy decisions
Start from any initialized SwarmPipe workspace with the baseline loaded, then run:

```powershell
sp policy request_resend --dataset sales_daily --tenant default --confidence 0.93 --blast 1 --no-injection --no-regulated
sp policy request_resend --dataset sales_daily --tenant default --confidence 0.60 --blast 1 --no-injection --no-regulated
sp policy force_publish --dataset sales_daily --tenant default --confidence 0.93 --blast 6 --injection --regulated
```

```output
{
  "effect": "auto_execute_notify",
  "action": "request_resend",
  "level": "L3",
  "risk": "low",
  "reasons": ["autonomy level L3 for 'request_resend' (tenant default) -> auto_execute_notify"]
}
{
  "effect": "require_approval",
  "action": "request_resend",
  "reasons": [
    "autonomy level L3 for 'request_resend' (tenant default) -> auto_execute_notify",
    "Diagnosis confidence is below 0.75"
  ],
  "matched_rules": ["level:L3", "low-confidence"]
}
{
  "effect": "recommend",
  "action": "force_publish",
  "level": "L1",
  "risk": "critical",
  "typed_confirmation": true,
  "annotation_required": true
}
```

The third decision is important: even with `--injection`, `--regulated` and high blast radius, the result is
`recommend` because `force_publish` starts at L1. Escalations cannot make a decision looser, and a recommend-only
critical action is already stricter than approval.

Now test the freeze-window flag:

```powershell
sp chaos set policy.freeze_window true
sp policy rollback_dataset --dataset sales_daily --tenant default --confidence 0.93 --blast 1 --no-injection --no-regulated
sp chaos set policy.freeze_window false
```

```output
policy.freeze_window = true
{
  "effect": "require_approval",
  "action": "rollback_dataset",
  "level": "L2",
  "risk": "medium",
  "matched_rules": ["level:L2"]
}
policy.freeze_window = false
```

Because `rollback_dataset` is already L2, the freeze window does not visibly change the effect in this example. It
would stop a medium-risk L3 action from auto-executing.
:::

## Lab: schema drift approval flow

:::lab Approve a medium-risk action
1. Start clean and load the baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   ```

2. Drop schema drift:

   ```powershell
   sp scenarios drop schema_drift --process
   sp approvals list --status pending
   ```

   ```output
   dropped ['sales_2026-09-29.csv'] into <your-SwarmPipe-folder>\data\inbox
   admitted 1 file(s); processed in 10.8s
   ...
   | id      | kind   | status  | subject                           | risk   |
   | apr_... | action | pending | reprocess_with_mapping on sales_daily | medium |
   ```

3. Approve the mapping after reviewing the incident evidence:

   ```powershell
   sp approvals approve <approval_id> --as oncall --comment "mapping reviewed"
   sp tick --timeout 90
   sp incidents list --limit 3
   ```

   ```output
   approved reprocess_with_mapping on sales_daily by user:oncall
   admitted 0 file(s); processed in 0.0s
   ...
   | id      | status   | severity | dataset     | root_cause             |
   | inc_... | resolved | critical | sales_daily | schema_change_upstream |
   ```

   No `--confirm` was required because this approval was medium risk. Use `--confirm` when `requires_confirmation`
   is populated, especially for critical actions such as `force_publish`.
:::

## Autonomy is earned and withdrawn

`swarmpipe\governance\autonomy.py` records proposals, approvals, rejections, executions, verification results,
rollbacks and human agreement. Promotion needs evidence and a human approval by default:

```yaml
autonomy_rules:
  promote: {min_samples: 5, min_approval_rate: 0.9, min_verification_rate: 1.0, max_rollbacks: 0, auto_promote: false}
  demote:  {max_verification_failures: 1, max_rollbacks: 1}
```

Demotion is automatic because safety should not wait for a committee. If a human rolls back an L3 action, that is
evidence that the action class was too autonomous for current conditions.

:::lab Roll back an auto-executed action
1. List autonomy levels:

   ```powershell
   sp autonomy list --tenant default
   ```

   ```output
   | tenant  | action          | level | max_level | risk   | executed | verified_ok |
   | default | hold_downstream | L3    | L3        | medium | 0        | 0           |
   | default | force_publish   | L1    | L2        | critical | 0      | 0           |
   ```

2. Drop a volume drop. `hold_downstream` auto-executes at L3:

   ```powershell
   sp scenarios drop volume_drop --process
   ```

   ```output
   | id      | status    | severity | dataset     | root_cause        |
   | inc_... | mitigated | critical | sales_daily | truncated_extract |
   ...
   EXECUTED_PROPOSALS
   {'id': 'prp_...', 'action': 'hold_downstream', 'status': 'verified', 'policy_effect': 'auto_execute_notify'}
   ```

3. Roll it back:

   ```powershell
   sp actions rollback <proposal_id> --as oncall
   sp autonomy list --tenant default
   ```

   ```output
   {
     "rolled_back": "prp_...",
     "result": {"released": ["sales_enriched"]}
   }
   ...
   | tenant  | action          | level | max_level | risk   |
   | default | hold_downstream | L2    | L3        | medium |
   ```

   The rollback released the hold and automatically demoted `hold_downstream` from L3 to L2.
:::

:::breakit Set a dangerous action to L4
Try to over-promote `force_publish`:

```powershell
sp autonomy set force_publish L4 --tenant default --reason "lab cap test" --as admin
```

```output
{
  "tenant": "default",
  "action": "force_publish",
  "from": "L1",
  "to": "L2"
}
```

The request asked for L4, but the policy cap forced L2. Some actions should never be fully autonomous: publishing data
that failed checks is a business-risk decision, not a model-confidence decision.
:::

:::warning The human can be the weak link
Approvals reduce excessive agency, but humans can approve bad requests. Show policy reasons, evidence ids, impact,
blast radius and typed confirmation text. Then keep downstream controls: verification, compensation, egress allowlists,
audit and automatic demotion.
:::

## Quiz

:::quiz
Q: Why does SwarmPipe use an action catalog?
- [ ] To make prompts shorter only
- [x] To prevent agents from inventing arbitrary side effects
- [ ] To avoid human approvals entirely
> Unknown actions such as `disable_checks` are invalid before policy evaluation can approve them.

Q: What does L3 mean in SwarmPipe?
- [ ] Inform only
- [ ] Recommend only
- [x] Auto-execute with notification and one-click rollback
> L3 is useful for reversible, low-blast-radius actions with verification evidence.

Q: Can an escalation make a policy decision looser?
- [ ] Yes, if the model is confident
- [x] No, escalations only make effects stricter
- [ ] Yes, during a freeze window
> `stricter()` chooses the stricter effect; denials win over all effects.

Q: Why did `force_publish` not become L4?
- [x] Its `max_level` caps it at L2
- [ ] It was missing from the catalog
- [ ] The dataset had no owner
> Critical actions can be permanently capped regardless of evidence.

Q: What happens after a rollback or verification failure?
- [ ] The action is automatically promoted
- [x] The autonomy manager can demote the action class immediately
- [ ] The audit log is deleted
> Safety withdrawals are automatic; promotions require evidence and usually human approval.
:::

:::takeaways
- Production agents should propose from a typed catalog, not invent side effects.
- Policy-as-code combines action risk, tenant autonomy, context and escalations outside the model.
- Durable approvals let workflows wait safely across restarts and require typed confirmation for high-risk actions.
- Autonomy is per tenant and action class; it is earned from approvals and verification, then capped by policy.
- Rollbacks and verification failures are evidence, so SwarmPipe demotes autonomy automatically.
:::
