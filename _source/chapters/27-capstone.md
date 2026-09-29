---
objectives:
  - "Read an AI feature PRD and identify the linked evaluation spec"
  - "Use a production-readiness checklist before shipping an agent feature"
  - "Extend SwarmPipe with a scenario, triage eval case, data-quality rule and governed catalog action"
  - "Verify changes with `sp evals gate` and `python -m pytest`"
  - "Undo capstone work safely by switching back to the main branch"
---

You now have the pieces: agents, tools, workflows, data contracts, lineage, durable execution, evals, policy, audit, cost, models and operations. The capstone is where you stop treating them as separate topics and ship one small agentic feature end to end. The feature itself matters less than the discipline: write the PRD, define the eval, touch the deterministic skeleton, add the agent-facing affordance, gate it, and leave a rollback path.

Work in your own SwarmPipe project, on a branch. The tutorial gives hints and pointers, not full solutions, because production engineering is the act of connecting requirements to code with evidence.

:::flow The capstone path
Specify | PRD + eval spec
Branch | `git switch -c capstone`
Build | scenario, rule, action, policy
Evaluate | eval cases, then `sp evals gate`
Test | `python -m pytest`
Ship or roll back | merge, or `git switch main`
:::

## The PRD is part of the system

`docs/PRD_AND_EVAL_SPEC.md` is the model. It describes the data-aware failure triage feature that SwarmPipe already implements, and it pairs product intent with measurable gates.

:::concept AI feature PRD
An AI feature PRD is a product requirements document that treats model behavior, tool use, safety boundaries and evaluation thresholds as first-class requirements, not implementation details.
:::

A useful AI PRD answers five questions:

| Question | Where the SwarmPipe PRD answers it |
|---|---|
| What user pain exists? | pipelines end OK while delivering bad data |
| Who needs what job done? | on-call, source owner, approver, analyst, platform admin |
| What is in and out of scope? | five file formats, nine action classes, no arbitrary SQL writes |
| What can the system do autonomously? | autonomy table tied to `config/policies.yaml` |
| How do we prove it works? | eval datasets, metrics, thresholds and rollout gates |

The eval spec is not an appendix you write after launch. It is the acceptance test for the PRD. The triage feature's primary metrics include root-cause accuracy, pass^k, citation validity, safety violations, false-positive incidents and average cost. The component metrics cover router, analyst and judge calibration. The safety suite covers prompt injection and poisoned knowledge. The rollout plan says offline replay, shadow, propose-and-approve, autonomy promotion, and kill-switch drills.

:::swarmpipe PRD and eval surfaces
The PRD is `docs/PRD_AND_EVAL_SPEC.md`. Gate thresholds are in `evals/gate.yaml`. Cases live in `evals/datasets/triage.v1.jsonl`, `evals/datasets/redteam.v1.jsonl`, `evals/datasets/router.v1.jsonl`, `evals/datasets/analyst.v1.jsonl` and `evals/datasets/judge_calibration.v1.jsonl`. The harness is `swarmpipe/evals/harness.py`.
:::

## A production-readiness checklist

Before you ship an agent feature, walk this list. Each item links back to the chapter that taught the idea.

| Check | Chapter |
|---|---|
| 1. The user job and non-goals are explicit. | [Chapter 27](27-capstone.html) |
| 2. Probabilistic steps sit inside a deterministic workflow skeleton. | [Chapter 1](01-llm-to-agent.html) |
| 3. Control plane and data plane ownership are clear. | [Chapter 2](02-architecture-tour.html) |
| 4. Prompt templates are versioned and locked. | [Chapter 3](03-prompts-models-gateway.html) |
| 5. Model output has a typed schema and repair/fallback behavior. | [Chapter 3](03-prompts-models-gateway.html) |
| 6. Tool contracts have typed args, scopes, bounded output and stable errors. | [Chapter 4](04-tools-and-gateway.html) |
| 7. File admission is idempotent and rejects unsupported inputs safely. | [Chapter 5](05-ingestion.html) |
| 8. Data contracts express schema, freshness, quality and business rules. | [Chapter 6](06-contracts-and-quality.html) |
| 9. Bad data trips a circuit breaker before publish. | [Chapter 6](06-contracts-and-quality.html) |
| 10. Versions, snapshots and rollback are defined. | [Chapter 7](07-publishing-lineage.html) |
| 11. Lineage and downstream impact are available before action. | [Chapter 7](07-publishing-lineage.html) |
| 12. Multi-agent decomposition earns its cost. | [Chapter 8](08-why-multi-agent.html) |
| 13. There is one final decision owner for diagnosis or action. | [Chapter 9](09-triage-swarm.html) |
| 14. Agent messages are typed, signed or otherwise authenticated. | [Chapter 10](10-communication-protocols.html) |
| 15. MCP or A2A surfaces enforce authorization server-side. | [Chapter 10](10-communication-protocols.html) |
| 16. Retrieved context carries trust and citations. | [Chapter 11](11-context-memory.html) |
| 17. Memory and runbook promotion require human curation. | [Chapter 11](11-context-memory.html) |
| 18. Steps checkpoint, retry with backoff and resume after crash. | [Chapter 12](12-durable-execution.html) |
| 19. Side effects are idempotent and compensatable. | [Chapter 12](12-durable-execution.html) |
| 20. Model timeouts, breakers, bulkheads, cache and budgets exist. | [Chapter 13](13-model-resilience.html) |
| 21. Known failure modes have reproduction drills. | [Chapter 14](14-failure-modes.html) |
| 22. Offline eval datasets cover normal, edge and false-positive cases. | [Chapter 15](15-eval-fundamentals.html) |
| 23. Non-determinism is measured with pass@k and pass^k. | [Chapter 15](15-eval-fundamentals.html) |
| 24. LLM judges are calibrated before their scores are trusted. | [Chapter 16](16-llm-judge.html) |
| 25. Red-team cases prove containment even when the model is fooled. | [Chapter 17](17-red-teaming.html) |
| 26. CI gates block unsafe prompt, policy, tool and model changes. | [Chapter 18](18-ci-gates-certification.html) |
| 27. Prompt injection, lethal-trifecta and egress risks are contained. | [Chapter 19](19-threat-model.html) |
| 28. User, agent and tool identities are separated. | [Chapter 20](20-identity-access.html) |
| 29. Policy-as-code decides every action outside the model. | [Chapter 21](21-policy-autonomy.html) |
| 30. Audit, evidence packs and kill switches are present. | [Chapter 22](22-audit-evidence.html) |
| 31. Traces, metrics, logs and SLOs are wired from day one. | [Chapter 23](23-observability.html) |
| 32. Cost is attributed by run, agent, tenant and model. | [Chapter 24](24-cost-capacity.html) |
| 33. Models are certified per role before trust. | [Chapter 25](25-model-strategy.html) |
| 34. Operations procedures cover DLQ, backup, retention and AI-caused incidents. | [Chapter 26](26-operations.html) |

## Capstone setup

Create a branch in your SwarmPipe project. Do not do this in the tutorial source. Run these from your SwarmPipe folder:

```powershell
git switch -c capstone
.\.venv\Scripts\Activate.ps1
function sp { python -m swarmpipe @args }
sp reset --yes
sp init
sp scenarios drop baseline --process
```

To abandon your work and return to the starting point:

```powershell
git switch main
```

If your branch has uncommitted changes, Git may ask you to commit, stash or discard them. Choose deliberately.

:::warning Keep the capstone small
A capstone feature should touch several surfaces, but it should not rewrite the system. One new scenario, one eval case, one rule and one governed action is enough to prove you understand the lifecycle.
:::

## Exercise 1: add a scenario and matching triage eval case

Your goal is to add a reproducible failure. Pick a data issue that is not already identical to `volume_drop`, `schema_drift`, `unit_change`, `quality_failure`, `referential_break`, `stale_resend`, `pii_leak`, `malformed`, `freshness` or `oob_tamper`. A good example is "sales file with a small but systematic negative quantity pattern" or "inventory report with impossible stock for one warehouse".

Touch these places:

| File | What to add |
|---|---|
| `swarmpipe/scenarios.py` | a `s_<name>` function plus a `Scenario(...)` entry in `SCENARIOS` |
| `evals/datasets/triage.v1.jsonl` | one disabled or active case with `id`, `drops`, `approver`, `expect` and `lineage` |
| `docs/PRD_AND_EVAL_SPEC.md` | if this were a real product change, update scope or the eval table |

Acceptance criteria:

- `sp scenarios list` shows the new scenario.
- `sp scenarios drop <name> --process` creates either a clean publish or an intended incident.
- The eval case names the expected signal, root cause and forbidden actions.
- `sp evals run --suite triage --cases <case_id> --k 1` reports `PASS` after you finish the rest of the feature.

Hints: search `s_quality_failure` and `s_unit_change` in `swarmpipe/scenarios.py` for patterns. Keep filenames compatible with the existing contract match rules.

## Exercise 2: add a quality rule and see it trip

Data contracts are executable product requirements. Add or extend one rule in `config/contracts/sales_daily.yaml`, then create data that violates it.

Touch these places:

| File | What to inspect or change |
|---|---|
| `config/contracts/sales_daily.yaml` | `rules`, `columns`, `accepted_values`, `min`, `max`, `references`, `drift` |
| `swarmpipe/data/quality.py` | `run_checks` to understand how rules become `CheckResult` rows |
| `swarmpipe/runtime/workflows.py` | `CHECK_SIGNAL` to see how check types become incident signals |

Acceptance criteria:

- A clean baseline still publishes.
- Your scenario trips the intended rule.
- The failed batch is quarantined, not published.
- `sp runs show <run_id>` shows the failed check.
- `sp incidents list` shows an incident only when the violation exceeds the contract threshold.

Hints: the existing `amount_equals_qty_x_price` rule is evaluated by `data/safe_expr.py`. Prefer changing thresholds or adding a simple expression over adding new Python code first.

## Exercise 3: add or extend a governed catalog action

This is the highest-risk exercise. Agents must never invent side effects; they choose from the action catalog, and deterministic code executes, compensates and verifies.

Feasible extension points, verified in code:

| File or function | Purpose |
|---|---|
| `swarmpipe/tools/actions.py` `ActionSpec` | declares the action name, description, params, execute, compensate and verify functions |
| `swarmpipe/tools/actions.py` `ACTIONS` | catalog entries exposed as `act_*` tools |
| `config/policies.yaml` | risk, reversibility, default and max autonomy level |
| `swarmpipe/agents/triage_agents.py` | planner simulation and validation behavior if the offline model needs to propose it |
| `evals/datasets/triage.v1.jsonl` | case expectations such as `must_propose`, `must_execute_any`, `forbidden_executed` |

A low-risk capstone action could be a more specific notification or a reversible hold-style action. Avoid external network calls. Do not add an action that writes arbitrary SQL, disables checks or bypasses policy.

Acceptance criteria:

- The new action has a typed Pydantic params model.
- `ACTIONS` includes execute, compensation if reversible, and verification.
- `config/policies.yaml` includes the action class with a conservative starting level.
- The Executor is the only agent that can execute the write tool.
- The eval case proves the action is proposed or forbidden as intended.

Hints: copy the shape of `request_resend`, `hold_downstream` or `release_hold`. Read `v_hold`, `v_release` and `v_notify` before writing your verifier. If verification cannot observe ground truth, the action is not ready for autonomy.

## Exercise 4: ship through the gate

When the feature works locally, ship it like a production change.

```powershell
sp evals run --suite triage --cases <case_id> --k 1
sp evals gate --k 2
python -m pytest
```

The clean triage eval path was verified with:

```output
triage suite: 1 cases x 1 trial(s)
  tri-010-clean-day trial 1/1: PASS
triage: cases=1, trials=1, pass_at_k=1.0, pass_hat_k=1.0, pass_rate=1.0,
false_positive_incidents=0, avg_cost_usd=0.0034, avg_llm_calls=15.0,
p95_latency_s=60.26
```

Your numbers will vary. What matters is that your new case passes, the full gate passes, and tests do not fail because of your changes.

:::lab Capstone lab 1: scenario plus eval
1. Create the branch and clean slate from the setup section.
2. Add a scenario in `swarmpipe/scenarios.py`.
3. Run it:

   ```powershell
   sp scenarios drop <name> --process
   sp incidents list
   ```

4. Add one case to `evals/datasets/triage.v1.jsonl`.
5. Run just that case:

   ```powershell
   sp evals run --suite triage --cases <case_id> --k 1
   ```

Acceptance: the case fails before the feature is complete for a meaningful reason, then passes after the rule/action work is done.
:::

:::lab Capstone lab 2: contract rule and catalog action
1. Add or modify a rule in `config/contracts/sales_daily.yaml`.
2. Re-run the baseline to prove clean data still passes.
3. Drop your scenario and inspect the run:

   ```powershell
   sp runs list --workflow ingest_dataset --limit 5
   sp runs show <run_id>
   ```

4. Add or extend the action in `swarmpipe/tools/actions.py` and policy in `config/policies.yaml`.
5. Run the scenario again and inspect **Incidents**, **Approvals** and **Governance**.

Acceptance: policy decides the action outside the model, and verification records either success or a clear failure.
:::

:::lab Capstone lab 3: final gate
1. Run the targeted eval.
2. Run the full gate and tests:

   ```powershell
   sp evals gate --k 2
   python -m pytest
   ```

3. If you changed a prompt, approve it only through:

   ```powershell
   sp evals gate --update-lock
   ```

Acceptance: targeted eval, full gate and tests pass. If they do not, fix the code or lower the feature scope; do not weaken the gate to make the report green.
:::

:::breakit Poison your own capstone
Turn off one defense and prove containment still holds.

```powershell
sp chaos set feature.critic_review false
sp scenarios drop <name> --process
sp chaos clear
```

Watch whether the planner proposes a riskier action. If it does, the action catalog, policy, approvals and verifier should still prevent unsafe state changes. If turning off one defense makes bad data publish, add a red-team case before you fix it.
:::

## What a good capstone PR says

A good capstone pull request is small but complete. It says:

- Problem: what production failure or operator pain it covers.
- Design: which workflow step, contract rule, scenario and action changed.
- Eval: which case was added and what metric it protects.
- Safety: what the forbidden action is, what policy level applies, and how rollback works.
- Verification: targeted eval, full gate and tests.
- Operations: which dashboard tab or command an on-call should use when it fires.

:::quiz
Q: Why does the capstone start with `docs/PRD_AND_EVAL_SPEC.md` instead of code?
- [ ] Documentation is more important than working software
- [x] It ties user value, autonomy, safety and measurable acceptance criteria together before implementation
- [ ] The eval harness cannot run without a PRD file
> Agent features fail when product intent and evaluation are separated. The PRD makes the gate meaningful.

Q: Where should a new synthetic failure scenario be registered?
- [ ] `swarmpipe/runtime/scheduler.py`
- [x] `swarmpipe/scenarios.py` in `SCENARIOS`
- [ ] `prompts/router.v1.md`
> Scenarios are generated in `swarmpipe/scenarios.py`; eval cases then refer to them by name.

Q: What makes a catalog action production-ready?
- [ ] The planner can describe it in natural language
- [x] Typed params, policy entry, deterministic execution, compensation where possible and ground-truth verification
- [ ] It auto-executes at L4 immediately
> Agents propose from a catalog; deterministic code authorizes, executes and verifies.

Q: Which command ships the whole change through the CI-style eval gate?
- [x] `sp evals gate --k 2`
- [ ] `sp scenarios drop baseline --process`
- [ ] `sp chaos show`
> Baseline and chaos are useful checks, but the gate runs the versioned suites and thresholds.

Q: If a new feature passes its targeted case but fails red-team containment, what should you do?
- [ ] Mark the red-team case flaky and remove it
- [x] Treat the failure as a blocker and fix the design or policy
- [ ] Ship behind a comment in the PR
> Safety containment is a release gate, not a nice-to-have metric.
:::

:::takeaways
- An AI PRD must include an eval spec, autonomy boundaries, rollout gates and non-goals.
- Production readiness is a checklist across workflow, tools, data, security, evals, policy, audit, cost and operations.
- Extend SwarmPipe through scenarios, contracts, catalog actions and eval cases together, not as isolated edits.
- A catalog action is not safe until it has typed parameters, policy, verification and rollback thinking.
- Ship through targeted evals, the full gate and tests; never weaken the gate to fit the feature.
:::
