---
objectives:
  - "Classify model-layer failures: timeouts, rate limits, outages, malformed output and wrong answers"
  - "Explain retries, structured-output repairs, circuit breakers, bulkheads, fallback chains and caching"
  - "Use `sp llm status`, `sp metrics`, chaos scenarios and the LLM kill switch to observe resilience controls"
  - "Describe how SwarmPipe degrades to deterministic fallbacks and marks outputs as degraded"
  - "Explain why model resilience is separate from data correctness and policy safety"
---

Models fail differently from databases in production. A database usually returns rows or an error. A model can time out, return a
429, return half a JSON object, confidently cite evidence that does not exist, or be wrong in fluent prose. A
production agentic system must treat the model as a useful but unreliable dependency.

SwarmPipe puts every model call through one gateway. That gateway retries transports, repairs malformed structured
output, opens circuit breakers, falls back across a per-role model chain, caches deterministic calls, enforces budgets
and raises `LLMUnavailable` when no route can answer. Agents then degrade to deterministic fallbacks instead of
breaking the pipeline.

## Model failures are not one thing

:::concept Model-layer resilience
The controls around model calls that keep an agentic application safe and useful when a model is slow, overloaded,
unavailable, malformed or confidently wrong.
:::

The main failure classes are:

| Failure | Symptom | Correct response |
|---|---|---|
| Timeout | no answer before the deadline | retry with backoff; eventually open the breaker |
| 429 rate limit | provider says slow down | honor `retry_after` when present; otherwise back off |
| 5xx or outage | provider unavailable | retry briefly, open breaker, try fallback model |
| Malformed output | invalid JSON or schema mismatch | structured-output repair, then fallback |
| Confidently wrong answer | valid shape, wrong facts | grounding, verification, evals and deterministic circuit breakers |

Retries and repairs are separate. A retry asks the same or next model again after a transport failure. A repair gives
the model its invalid output and asks it to return one JSON object matching the schema. SwarmPipe counts them
separately: `llm_calls_total` for calls, `llm_repairs_total` for schema repairs, `llm_fallbacks_total` for route
fallbacks and `llm_unavailable_total` when every route fails.

:::flow Model gateway path
Agent request | role, prompt, schema, tenant and run id
Limits and guards | kill switch, quotas, run budget, PII and secret checks
Cache and compaction | deterministic cache, context window trimming
Route chain | model A, then model B, per role
Per-model controls | breaker, bulkhead, retries, repair loop
Agent fallback | `LLMUnavailable` becomes deterministic degraded output
:::

## Circuit breakers, bulkheads and fallback chains

A circuit breaker stops hammering a dependency that is already failing. SwarmPipe's `CircuitBreaker` has the standard
states: `closed`, `open` and `half_open`. In `closed`, calls flow. After enough failures, the breaker moves to `open`
and calls are skipped. After a cooldown, one half-open probe is allowed; success closes the breaker, failure opens it
again. Breaker openings increment `llm_breaker_open_total`, and `sp llm status` shows the breaker snapshot.

:::concept Bulkhead
A concurrency boundary that keeps one slow dependency from consuming all worker capacity. SwarmPipe uses
`ModelGateway.bulkhead`, a bounded semaphore sized by `engine.llm_concurrency`.
:::

Fallback chains are per role. In the offline profile, `diagnoser`, `planner`, `steward` and `analyst` route through
`sim-large` then `sim-small`, while the `default` role uses `sim-small`. If `sim-large` is down, the gateway can serve
the call from `sim-small` and increment `llm_fallbacks_total`.

Caching is another resilience lever. Deterministic, cacheable, temperature-zero calls are keyed by normalized
messages, the first model in the route and the schema. Hits increment `llm_cache_hits_total`. The runtime flag
`llm.cache_disabled` disables that cache when you need to study raw model behavior.

:::swarmpipe Where it lives
The gateway is `swarmpipe/llm/gateway.py`. The simulated model and chaos knobs are in `swarmpipe/llm/mock.py`.
Agents catch `DEGRADE_ERRORS` from `swarmpipe/agents/base.py`. The LLM kill switch is implemented by
`swarmpipe/governance/killswitch.py` and checked in `ModelGateway._check_limits`.
:::

From `swarmpipe/llm/gateway.py`:

```python
if not self.breaker.allow(model_id):
    errors.append(f"{model_id}: circuit open")
    span.event("circuit_open_skip", model=model_id)
    continue
...
if repairs >= s.max_repairs:
    errors.append(f"{model_id}: invalid output after {repairs} repairs")
    self.breaker.failure(model_id)
    return None
```

From `swarmpipe/agents/base.py`:

```python
DEGRADE_ERRORS = (LLMUnavailable, BudgetExceeded, QuotaExceeded, KillSwitchEngaged, GuardrailViolation)
```

Each LLM-backed agent catches those errors and returns a deterministic fallback with `degraded: true` where the output
shape supports it.

## Graceful degradation is not pretending nothing happened

Graceful degradation means the system keeps the deterministic safety properties even when advice quality drops.
SwarmPipe's Router falls back to sniffing, the Profiler falls back to deterministic profiling and glossary matching,
the Triage Supervisor can vote over specialist findings, and the Planner can fall back to safe owner notification.
Those outputs carry `degraded` so operators and downstream code know the answer came from a fallback.

The most important boundary is this: model resilience does not replace data quality checks. When all models are down,
the `volume_drop` file is still quarantined because `Data Assurance` is deterministic. The incident diagnosis may
have lower confidence and abstain, but the bad data still does not publish.

Per-run budgets and tenant quotas are covered in [Chapter 24](24-cost-capacity.html). This chapter only needs the
operational consequence: quota and budget failures are part of `DEGRADE_ERRORS`, so agents degrade instead of
spending past the budget.

## Hands-on: read the route and use the LLM kill switch

:::lab Lab 1 - Inspect routes, breakers and the LLM kill switch
1. Start from a baseline:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp llm status
   ```

   ```output
   {
     "active_profile": "offline",
     "routes": {
       "diagnoser": ["sim-large", "sim-small"],
       "planner": ["sim-large", "sim-small"],
       "default": ["sim-small"],
       ...
     },
     "breakers": {},
     "models": {
       "sim-small": {"provider": "mock", "tier": "small", ...},
       "sim-large": {"provider": "mock", "tier": "large", ...}
     }
   }
   ```

2. Engage and release only the model layer:

   ```powershell
   sp killswitch on --scope llm --reason "lab test" --as oncall
   sp status
   sp killswitch off --scope llm --reason "lab done" --as oncall
   ```

   ```output
   kill switch llm -> on
   LLM: 15 calls, $0.00339, 16716 tokens | profile offline | kill switches: ['llm'] | inbox: ...\data\inbox
   kill switch llm -> off
   ```

   The accepted states are `on` and `off`. The exact scope for model calls is `llm`.
:::

:::lab Lab 2 - Flaky model: retries, repairs and fallback counters
1. Use the verified chaos scenario:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop flaky_llm --process
   sp llm status
   sp incidents list --limit 3
   sp metrics
   ```

2. Expected shape:

   ```output
   dropped ['sales_2026-09-29.csv'] into ...\data\inbox
   admitted 1 file(s); processed in 12.3s
   | workflow       | status      | n |
   | ingest_dataset | quarantined | 1 |
   | triage         | succeeded   | 2 |
   ...
   | id                 | status    | severity | dataset     | root_cause            |
   | inc_mum...         | mitigated | high     | sales_daily | unit_or_scale_change  |
   ...
   | llm_fallbacks_total | 1 | 1.0 | ... |
   | llm_repairs_total   | 1 | 1.0 | ... |
   ```

   `flaky_llm` combines timeouts, malformed output and a `unit_change` file. In the verified run, the repair loop and
   a fallback both fired, yet the failed batch stayed quarantined and the incident was mitigated.

3. Clear chaos before the next experiment:

   ```powershell
   sp chaos clear
   ```

   ```output
   cleared 1 flags and reset the clock offset
   ```
:::

## Hands-on: outage and deterministic degradation

:::lab Lab 3 - All models down, bad data still quarantined
1. Reset, create the baseline, then take both simulated models down:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp chaos set llm_outage_models '["sim-large","sim-small"]'
   sp chaos show
   sp scenarios drop volume_drop --process
   ```

   ```output
   chaos.llm_outage_models = ["sim-large","sim-small"]
   | chaos.llm_outage_models | ['sim-large', 'sim-small'] | [] |
   dropped ['sales_2026-09-29.csv'] into ...\data\inbox
   admitted 1 file(s); processed in 11.5s
   | workflow       | status      | n |
   | ingest_dataset | quarantined | 1 |
   | triage         | succeeded   | 2 |
   ```

2. Open the **Runs** tab and the latest `triage` run, or use `sp runs show <triage-run-id>`. In the verified run the
   `diagnose` output contained:

   ```output
   "root_cause_category": "truncated_extract",
   "summary": "(deterministic fallback: LLMUnavailable) majority of specialist findings",
   "confidence": 0.45,
   "model": null,
   "degraded": true,
   "grounded": false
   ```

3. Check the incident and datasets. The diagnosis is lower confidence and escalated, but `sales_daily` did not
   publish the 18-row batch:

   ```output
   | id          | status    | severity | dataset     | root_cause        |
   | inc_mum...  | escalated | critical | sales_daily | truncated_extract |
   ```

   This is the key production lesson: model outage degraded explanation quality, not the data circuit breaker.
:::

:::breakit Combine faults: all models down plus volume drop
The previous lab is the break-it experiment. With both `sim-large` and `sim-small` down, model-backed specialists
produce deterministic degraded findings such as:

```output
"stop_reason": "degraded: LLMUnavailable",
"degraded": true,
"summary": "(deterministic fallback, model unavailable) signal volume_anomaly usually means truncated_extract"
```

Reason about the interaction: the triage swarm has weaker evidence, so it escalates; the data plane still quarantines
because `row_count_min` and `volume_vs_baseline` are deterministic checks. If your production design cannot make that
separation, a model outage can become a data outage.
:::

## Production notes

:::warning A valid JSON answer can still be wrong
The repair loop proves shape, not truth. A wrong but schema-valid diagnosis is handled by grounding, citations,
verification, evals and policy, not by JSON validation. Chapter [15](15-eval-fundamentals.html) covers systematic
measurement of those outcome failures.
:::

At larger scale, use provider-specific retry policies, regional failover and hard cost controls. Keep breakers per
model or deployment, not just per provider. Use bulkheads for model calls so slow hosted models do not starve local
deterministic work. Keep fallback quality visible in the product: a degraded answer must look different from a
normal answer.

## Quiz

:::quiz
Q: What is the difference between an LLM retry and an LLM repair?
- [x] A retry handles transport/provider failure; a repair handles invalid structured output
- [ ] A repair is only for 429 errors
- [ ] A retry validates citations
> SwarmPipe counts repairs with `llm_repairs_total` and fallbacks/retries separately because they indicate different problems.

Q: What does an open circuit breaker do?
- [ ] It makes the model more deterministic
- [x] It skips calls to a failing model until the cooldown allows a half-open probe
- [ ] It disables all workflows
> The breaker protects both the provider and your workers from repeated calls to a dependency that is already failing.

Q: Why did the all-models-down `volume_drop` still quarantine the file?
- [ ] The model guessed correctly
- [x] Data quality checks and the publish circuit breaker are deterministic
- [ ] The dashboard blocked the publish manually
> Model unavailability reduced diagnosis quality, but deterministic checks still protected consumers.

Q: Which command engages only the model-layer kill switch?
- [ ] `sp killswitch on --scope agent:llm`
- [x] `sp killswitch on --scope llm`
- [ ] `sp llm use off`
> The kill switch accepts `on|off` states and `llm` is the model gateway scope.

Q: What does `llm.cache_disabled` affect?
- [ ] Durable step checkpoints
- [ ] The event dispatcher
- [x] The model gateway's deterministic response cache
> Disabling the LLM cache is useful when you want to observe raw model behavior during chaos tests.
:::

:::takeaways
- Model failures include transport failures, malformed output and confidently wrong answers; each needs a different control.
- SwarmPipe's model gateway centralizes kill switches, quotas, budgets, guardrails, cache, breakers, bulkheads, retries, repairs and fallback chains.
- Circuit breakers are `closed -> open -> half_open -> closed/open`; breaker openings increment `llm_breaker_open_total`.
- Agents catch `LLMUnavailable` and related errors and return deterministic degraded outputs instead of crashing workflows.
- Graceful degradation must be visible. `degraded: true` is part of the operational contract.
- Deterministic data checks and policy controls must still work when every model is down.
:::
