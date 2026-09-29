---
objectives:
  - "Compare simulated, local self-hosted, hosted SaaS and bring-your-own model strategies"
  - "Read SwarmPipe LLM profiles and explain per-role routing choices"
  - "Run one local Ollama request and switch safely back to the offline profile"
  - "Explain per-role model certification and the `llm.require_certification` gate"
  - "Describe how real models fail differently from simulated test doubles"
---

A model strategy is not "which model is best?" It is "which model is trustworthy enough for this role, at this cost and latency, under these data-residency and operational constraints?" A router, a diagnoser and a judge do different jobs. Treating them as one generic "LLM" is how teams overspend on easy calls and under-test risky ones.

SwarmPipe starts offline with simulated models because every lab must be reproducible and private. It can also route to a local Ollama model or to hosted OpenAI-compatible providers. The architecture lesson is the same in all profiles: one gateway, per-role routes, certification before trust, and graceful degradation when a model is not available.

## Model options and trade-offs

:::cards Model strategies
Simulated models | deterministic local test doubles; free and failure-injectable; not intelligent
Self-hosted open models | local control and data residency; you operate latency, memory, upgrades and quality
Hosted SaaS APIs | strong capability and managed operations; data leaves the machine and provider limits apply
Bring your own model | enterprise-selected endpoint behind the same gateway; quality and ops vary by owner
:::

The trade-offs are practical:

| Strategy | Quality | Cost | Latency | Data residency | Operations |
|---|---|---|---|---|---|
| `offline` simulated | deterministic heuristics | illustrative only | milliseconds | local | easiest |
| `ollama` local | real but model-dependent | no per-token API fee | 15-45s on this CPU | local | you run it |
| `azure` / `openai` | hosted model quality | metered provider cost | network + provider | off-machine | provider + secrets |
| BYOM | endpoint-specific | contract-specific | endpoint-specific | policy-specific | shared ownership |

SwarmPipe's README is explicit: hosted profiles can send data off-machine. That is why the tutorial uses `offline` unless a lab intentionally asks for one local real call.

:::analogy Model strategy as a fleet
You do not use a cargo truck for a letter or a bicycle for a refrigerator. A production agent platform needs a fleet: cheap vehicles for simple trips, stronger ones for risky work, maintenance records for each, and rules for when a vehicle is not allowed on the road.
:::

## Profiles and per-role routing

Profiles live in `config\swarmpipe.yaml`. They map roles to ordered fallback chains:

```yaml
profiles:
  offline:
    default:   [sim-small]
    steward:   [sim-large, sim-small]
    diagnoser: [sim-large, sim-small]
    planner:   [sim-large, sim-small]
    analyst:   [sim-large, sim-small]
    judge:     [sim-large]
  ollama:
    default:   [llama3.2, sim-small]
    diagnoser: [llama3.2, sim-large]
```

`secret://` values configure hosted providers without putting keys in source. `openai` uses `secret://OPENAI_API_KEY`; `azure` uses `secret://AZURE_OPENAI_ENDPOINT` and `secret://AZURE_OPENAI_API_KEY`. Chapter 20 owns identity and secret handling; here the key point is that hosted providers go through the same gateway controls as local ones.

:::swarmpipe Routing implementation
`ModelGateway.active_profile` reads `llm.active_profile`; `ModelGateway.route(role)` returns the chain for that role. If `llm.require_certification` is true, it filters the chain to models with a `model_certifications` row where `status='certified'`.
:::

Choosing a model per role starts with task shape:

| Role | What it needs | Why route differently |
|---|---|---|
| `router` | classify file type from sniffer evidence | cheap, low-risk, easy to evaluate |
| `profiler` / `steward` | semantic typing and mappings | needs more reasoning but still checked by deterministic evidence |
| `diagnoser` | merge specialist findings and cite evidence | high consequence; certify carefully |
| `planner` | propose allowed actions | high safety impact; critic and policy still constrain it |
| `analyst` | NL to governed SQL | needs refusal and PII behavior, not just SQL fluency |
| `judge` | evaluate explanations | must be calibrated before being trusted |

## Certification before trust

Certification is not a vibe check. `sp evals certify --model llama3.2 --roles router` runs the same eval suite with that model serving the role and no fallback, then records the result in `model_certifications`. For `router`, the metric is accuracy against `evals\datasets\router.v1.jsonl`. The model must meet the threshold in `evals\gate.yaml`.

```python
# swarmpipe/core/db.py
CREATE TABLE IF NOT EXISTS model_certifications (
  model TEXT, role TEXT, status TEXT, scores TEXT, eval_run_id TEXT,
  certified_at TEXT, PRIMARY KEY (model, role));
```

When `llm.require_certification` is false, profiles route normally. When it is true, uncertified models are removed from the route. If no certified model remains for a role, the gateway raises `LLMUnavailable` with `no routable (certified) model for role ...`. That is exactly what you want: fail closed instead of silently using an uncertified model.

## What real models do that simulators do not

The simulated models are test doubles. They are fast, deterministic and chaos-controllable. Real models add operational texture:

- CPU latency can be 15-30 seconds per call, and in one verification run a single Ollama router call took 45.93 seconds.
- Real models can drift in output format, requiring JSON extraction and repair.
- Real models can be confidently wrong. SwarmPipe's `docs\LABS.md` Lab 12 documents a development observation where `llama3.2` misdiagnosed the `unit_change` scenario as `referential_integrity_break`.
- Provider errors, timeouts and rate limits become real transport failures rather than simulated knobs.

Do not conclude that a model is "good" because it answered one prompt. Certify the role, keep fallbacks, and monitor production feedback.

:::warning Passing one role says nothing about another
A verification run certified `llama3.2` for `router`. That does not certify it for `diagnoser`, `planner`, `analyst` or `judge`. Role-specific certification is the point.
:::

## Fallbacks and graceful degradation

Fallbacks are taught in [Chapter 13](13-model-resilience.html), but model strategy depends on them. A route can fall from a hosted or local model to a simulated model; if every model fails, agents catch `LLMUnavailable`, `BudgetExceeded`, `QuotaExceeded`, `KillSwitchEngaged` and `GuardrailViolation` and use deterministic fallback where safe.

The fallback is not pretending everything is fine. A degraded diagnosis may lower confidence or abstain. A deterministic router may use sniffer output. An analyst may refuse because the model layer is unavailable. This is better than partial hidden success.

:::flow Model decision path
role request | `router`, `diagnoser`, `planner`, ...
active profile | `offline`, `ollama`, `azure`, `openai`
certification filter | optional `llm.require_certification`
route chain | first model, then fallback models
gateway controls | quotas, budgets, guardrails, cache, breaker, repair
agent fallback | deterministic safe behavior or abstention
:::

## Hands-on: one real local request

:::lab Try Ollama, then switch back
1. From a baseline workspace, send one router request through the local Ollama profile:

   ```powershell
   sp llm test --profile ollama
   ```

   ```output
   served by llama3.2 (ollama) in 45.93s, tokens 443/28, repairs 0, chain ['llama3.2']
   {
     "kind": "tabular",
     "confidence": 0.99,
     "reason": "consistent comma delimiter and a header row"
   }
   ```

   Your time may be lower or higher. Local CPU inference is slow.

2. Switch back immediately:

   ```powershell
   sp llm use offline
   sp llm status
   ```

   ```output
   active LLM profile -> offline
   {
     "active_profile": "offline",
     "routes": {
       "default": ["sim-small"],
       "diagnoser": ["sim-large", "sim-small"],
       "planner": ["sim-large", "sim-small"]
     },
     "breakers": {}
   }
   ```

3. Dashboard check: **Cost & Metrics** shows the model call row; **Evals** is where certification results appear.
:::

:::lab Certify a model for one role
1. Run the router certification:

   ```powershell
   sp evals certify --model llama3.2 --roles router
   ```

   ```output
   router suite
     rt-001 sales_2026-09-29.csv: expected tabular got tabular (llm) PASS
     rt-002 inventory_2026-09-29.txt: expected tabular got tabular (llm) PASS
     ...
   router: cases=9, accuracy=1.0
   llama3.2 for role router: accuracy=1.0 (bar 0.9) -> certified
   {
     "router": {
       "suite": "router",
       "metric": "accuracy",
       "value": 1.0,
       "bar": 0.9,
       "status": "certified"
     }
   }
   ```

2. Inspect **Evals** -> certifications. The row is persisted in `model_certifications`.

3. Do not run `--roles diagnoser` casually in a short lab. `docs\LABS.md` says it is slow, around 20 minutes, and expected to be rejected for this machine/model combination.
:::

:::lab Require certification
1. Before certifying a planner model, turn on the certification gate:

   ```powershell
   sp chaos set llm.require_certification true
   sp llm test --role planner
   ```

   ```output
   llm.require_certification = true
   LLMUnavailable: no routable (certified) model for role planner
   ```

2. Turn it off for the rest of the tutorial:

   ```powershell
   sp chaos set llm.require_certification false
   sp llm use offline
   ```

3. What happened? The `offline` profile normally routes `planner` to `sim-large, sim-small`, but with `llm.require_certification` enabled, the gateway filtered out models that were not certified for `planner`. The route became empty and failed closed.
:::

:::breakit Uncertified role fails closed
Repeat the certification gate with any role you have not certified:

```powershell
sp chaos set llm.require_certification true
sp llm test --role analyst
sp chaos set llm.require_certification false
```

You should see the same `no routable (certified) model for role analyst` shape unless you previously certified that model/role pair. This is a safe break: it changes routing, not data. In a production deployment, keep this flag on only after your required roles have certifications recorded.
:::

## Simulated models as test doubles

The `offline` profile is not a toy; it is a test strategy. Simulated models let SwarmPipe reproduce timeouts, rate limits, malformed JSON, hallucinated citations, loops and wrong answers with runtime flags. That makes Chapter 14 failure modes, Chapter 15 evals and Chapter 17 red teams repeatable on a laptop.

The trick is to remember what a test double can and cannot prove. It can prove that the gateway retries, repairs, meters, falls back and records evidence. It cannot prove that a real model will choose the right root cause, obey formatting under pressure or handle unfamiliar language. For that, run role certification and controlled canaries.

## Production notes

At scale, model strategy becomes a portfolio. Maintain a model inventory, role certifications, owner contacts, data-residency classification, cost rates, latency SLOs and rollback plans. Version hosted deployments and local weights explicitly. Re-run certification when a provider changes a model alias, when prompts change, when tools change or when production feedback reveals a new failure mode.

:::quiz
Q: Why does SwarmPipe default to `offline`?
- [ ] Hosted models are impossible to use
- [x] Labs stay local, deterministic and reproducible by default
- [ ] Simulated models are always more accurate
> Offline is a privacy and learning default, not a quality claim.

Q: What does an LLM profile define?
- [ ] Dashboard colors
- [x] Role-to-model fallback chains
- [ ] Data contracts
> Profiles map roles such as `router` and `diagnoser` to ordered model lists.

Q: What does `sp evals certify --model llama3.2 --roles router` prove?
- [x] `llama3.2` met the router certification bar on the router eval suite
- [ ] `llama3.2` is certified for every role
- [ ] Hosted providers are disabled
> Certification is per model and per role.

Q: What happens when `llm.require_certification` leaves no certified model in a route?
- [ ] The gateway silently uses the first model anyway
- [x] The gateway raises `LLMUnavailable`
- [ ] The audit log is deleted
> The route fails closed with `no routable (certified) model for role ...`.

Q: Why keep simulated models after adding real models?
- [ ] To hide production failures
- [x] To provide fast deterministic tests and reproducible chaos cases
- [ ] To bypass schema validation
> Simulators are test doubles for system behavior; real models still need certification.
:::

:::takeaways
- Model strategy is per role, not one global "best model" choice.
- `offline`, `ollama`, `azure` and `openai` profiles all go through the same SwarmPipe gateway.
- Hosted profiles require `secret://` keys and can send data off-machine; the tutorial stays offline by default.
- Real local models add latency, format drift and wrong-answer risk that simulators cannot fully predict.
- Certification records model/role trust in `model_certifications`; `llm.require_certification` fails closed when a role has no certified route.
- Simulated models remain valuable as deterministic test doubles for failure modes and CI.
:::
