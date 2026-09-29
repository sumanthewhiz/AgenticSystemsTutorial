---
objectives:
  - "Explain token economics and where SwarmPipe records cost per model call"
  - "Attribute model spend by run, incident, agent, model and tenant"
  - "Use routing, caching, budgets and quotas to control the multi-agent cost multiplier"
  - "Interpret latency and concurrency controls such as p95, bulkheads and backpressure"
  - "Run quota, cache and cost-comparison labs safely"
---

Multi-agent systems make cost feel nonlinear. A single bad file can call a router, profiler, supervisor, investigators, diagnoser, planner, critic and learner. Add retries, repairs and fallbacks, and one incident can cost ten times more than a clean ingest. That does not make multi-agent designs wrong; it means cost and capacity are first-class production signals.

SwarmPipe makes that visible. Every model call writes input tokens, output tokens, model, role, tenant, run, incident, latency and cost to `llm_calls`. The **Cost & Metrics** tab, `sp status`, `sp metrics`, quotas and SLOs all read from that same ground truth.

## Token economics

:::concept Token economics
The practice of treating model context and output as metered resources: input tokens cost money and latency, output tokens usually cost more, and every retry multiplies both.
:::

Prices live in `config\swarmpipe.yaml`. The offline simulated prices are illustrative, but the accounting path is the same as a hosted provider:

```yaml
sim-small:
  usd_per_1k_in: 0.00015
  usd_per_1k_out: 0.0006
sim-large:
  usd_per_1k_in: 0.0025
  usd_per_1k_out: 0.01
```

`ModelGateway._record` writes the call row and increments the metrics:

```python
# swarmpipe/llm/gateway.py
self.svc.metrics.inc("llm_calls_total", model=model_id, status=status, role=req.role)
self.svc.metrics.observe("llm_latency_ms", latency, model=model_id)
self.svc.metrics.inc("llm_tokens_total", tin, model=model_id, direction="input")
self.svc.metrics.inc("llm_tokens_total", tout, model=model_id, direction="output")
self.svc.metrics.inc("llm_cost_usd_total", cost, tenant=req.tenant, agent=req.agent)
```

The useful unit is not just cost per call. For an agent platform, ask for cost per clean ingest, cost per incident, cost per resolved incident, cost by tenant and cost by role. Chapter 8 explains when multiple agents are worth the multiplier; this chapter shows how to measure it.

:::flow Cost attribution path
llm.call | tokens, latency and cost
llm_calls table | run_id, incident_id, agent, role, model, tenant
metrics | `llm_cost_usd_total`, `llm_latency_ms`, `llm_cache_hits_total`
Cost & Metrics | by agent, model, tenant, incident
SLOs and budgets | control spend and latency before runaway
:::

## Routing, caching and budgets

Not every role deserves the same model. In the default `offline` profile, `router` uses `sim-small`, while reasoning-heavy roles such as `diagnoser`, `planner`, `steward`, `analyst` and `judge` use `sim-large` first. The `ollama`, `azure` and `openai` profiles keep the same idea: cheap/small models for classification and formatting; stronger models where the quality delta justifies the spend.

Caching is the second lever. `llm.cache_enabled: true` caches deterministic, cacheable, temperature-zero calls. The runtime flag `llm.cache_disabled` disables it for experiments. Cache hits increment `llm_cache_hits_total` and are recorded in `llm_calls` with provider `cache`, zero tokens and zero cost. Cache keys normalize random spotlighting boundaries so otherwise-identical prompts still hit.

Per-run budgets are the hard stop. `budgets.per_run_usd: 0.25` and `budgets.per_run_tokens: 150000` apply across every agent in a run. When exceeded, the gateway raises `BudgetExceeded`; agents that catch gateway degradation errors use deterministic fallback behavior where possible. That is the right failure mode: finish safely with lower confidence, or abstain, rather than quietly overspending.

:::swarmpipe Cost controls
Routing and budgets are in `swarmpipe/llm/gateway.py`; prices, profiles, `llm.cache_enabled`, `budgets.per_run_usd`, tenant quotas and `engine.llm_concurrency` are in `config\swarmpipe.yaml`.
:::

## Tenant quotas and graceful degradation

SwarmPipe tenants are inbox subfolders and separate published views. The default tenant has a daily LLM request limit of 2000; `acme` has 40. You can override the request quota at runtime with:

```powershell
$quotaFlag = "quota.acme.daily_llm_requests"
sp chaos set $quotaFlag 1
```

The gateway checks quota before a model call. When the tenant has reached its daily limit, it raises `QuotaExceeded`. Pipeline agents and triage agents catch that as a degradation signal. Some work can continue deterministically: files can still be staged, checks can still run, circuit breakers can still quarantine bad data, and the system can abstain or use lower-confidence fallback diagnosis. The default tenant is unaffected.

In a verification run, setting `acme` to one request after baseline caused the volume-drop incident to escalate with zero incident model spend; the quota table still showed the earlier baseline calls. The diagnosis included an abstention shape rather than a confident model answer:

```output
quotas
{'tenant': 'acme', 'day': '2026-09-29', 'llm_requests': 13, 'cost_usd': 0.00290295}
diagnosis {"root_cause_category": "unknown", "summary": "Evidence is insufficient to name a root cause", ...}
```

## Latency, concurrency and capacity

Capacity is not just dollars. A model call can be cheap and slow. SwarmPipe tracks `llm_latency_ms`, `agent_invocation_ms`, `step_duration_ms`, `run_duration_seconds`, `ingest_e2e_seconds` and `triage_diagnosis_seconds`. `sp metrics` reports p50, p95, p99 and max for summary metrics.

:::concept p95 latency
The value below which 95% of observed requests completed. It is usually more useful than average latency because users and SLOs feel the slow tail.
:::

Concurrency controls live in deterministic code. `engine.workers` controls worker threads. `engine.llm_concurrency` is a bulkhead semaphore around model calls, so slow Ollama or hosted calls do not consume the whole runtime. `watcher.backpressure_high_watermark` stops admitting more files when queued/running work is too deep. These are boring controls, and boring is good.

:::layers Capacity controls
Admission | watcher stability checks and backpressure
Execution | worker count, durable leases and retries
Model bulkhead | `engine.llm_concurrency`
Budgets | per-run dollars/tokens and tenant daily quotas
SLOs | p95-oriented ingest and triage objectives
:::

## Hands-on: compare ingest and incident cost

:::lab Cost of clean ingest vs incident
1. Start clean and run baseline plus one incident:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --process
   sp scenarios drop volume_drop --process
   sp status
   sp incidents list
   ```

   ```output
   LLM: 30 calls, $0.0184, 36582 tokens | profile offline | kill switches: none | inbox: C:\...\data\inbox
   | inc_mumhq8or17b7fb | mitigated | critical | default | sales_daily | 1 | truncated_extract | 0.011965 |
   ```

2. Open **Cost & Metrics**. Compare **By agent** and **Per incident**. A verification run showed:

   ```output
   by_agent
   {'agent': 'agent:planner', 'model': 'sim-large', 'calls': 1, 'usd': 0.00694, ...}
   {'agent': 'agent:supervisor', 'model': 'sim-large', 'calls': 2, 'usd': 0.005285, ...}
   {'agent': 'agent:profiler', 'model': 'sim-small', 'calls': 8, 'usd': 0.002558, ...}
   per_incident
   {'incident_id': 'inc_mumhq8or17b7fb', 'calls': 11, 'usd': 0.011965}
   ```

3. Interpret it: clean ingestion used router/profiler calls; the incident added specialist, diagnoser, planner and learner calls. That is the multi-agent multiplier from [Chapter 8](08-why-multi-agent.html), made measurable.
:::

:::lab Tenant quota trip
1. Reset and create `acme` data:

   ```powershell
   sp reset --yes
   sp init
   sp scenarios drop baseline --tenant acme --process
   ```

2. Lower the tenant quota and drop a failure:

   ```powershell
   $quotaFlag = "quota.acme.daily_llm_requests"
   sp chaos set $quotaFlag 1
   sp scenarios drop volume_drop --tenant acme --process
   sp incidents list
   ```

   ```output
   quota.acme.daily_llm_requests = 1
   | inc_mumhu7fk052412 | escalated | critical | acme | sales_daily | 1 | truncated_extract | 0.0 | ...
   ```

3. Open **Cost & Metrics** -> **Tenant quotas**. You should see `acme` request counts for the day. The important behavior is isolation: `acme` degrades, but the default tenant's quota and data remain separate.

4. Clear the override when done:

   ```powershell
   $quotaFlag = "quota.acme.daily_llm_requests"
   sp chaos set $quotaFlag 40
   ```

   Runtime flags persist in the state database. A reset clears them because it moves the whole `data` folder aside.
:::

:::lab Cache experiment
1. In a baseline workspace, run a deterministic workload twice:

   ```powershell
   sp scenarios drop clean_day --process
   sp scenarios drop clean_day --process
   sp metrics
   ```

   In a verification run, the second identical file was idempotently skipped, so model-call counts did not rise:

   ```output
   | ingest_file | skipped | 1 |
   | llm_calls_total | 32 | 32.0 | ...
   ```

2. Disable the cache and repeat an equivalent deterministic workload:

   ```powershell
   sp chaos set llm.cache_disabled true
   sp scenarios drop clean_day --process
   sp metrics
   ```

   ```output
   llm.cache_disabled = true
   | ingest_file | skipped | 2 |
   | llm_calls_total | 32 | 32.0 | ...
   ```

3. The skipped duplicate shows a second cost control: idempotency can save more than cache. To see `llm_cache_hits_total`, use a workload that repeats the same cacheable call without triggering file-level duplicate skipping, such as repeated eval trials or repeated model tests inside one process.
:::

:::breakit Quota equals one
Set a tenant's quota to one, then observe what still works:

```powershell
sp reset --yes
sp init
sp scenarios drop baseline --tenant acme --process
$quotaFlag = "quota.acme.daily_llm_requests"
sp chaos set $quotaFlag 1
sp scenarios drop volume_drop --tenant acme --process
sp incidents show <incident_id>
```

You will still get deterministic admission, checks and quarantine. Model-heavy diagnosis may abstain or degrade. That is the production lesson: cost controls should reduce quality or autonomy before they reduce safety.
:::

## Cost SLOs and what to alert on

SwarmPipe's configured SLOs cover latency and success, not a separate dollar SLO. The cost SLO is still visible operationally: track `llm_cost_usd_total`, `cost_per_resolved_incident`, quota burn and p95 latency in **Cost & Metrics**. Industry practice beyond SwarmPipe is to define budget alerts such as "projected daily model spend > 80% of budget" and efficiency SLOs such as "p95 diagnosis latency under 180 seconds while average incident cost stays below X."

Alert on budget exhaustion, quota exhaustion for important tenants, sustained p95 latency, DLQ growth and breaker opens. Record individual high-cost calls for review unless they threaten a budget.

:::warning Do not optimize cost by hiding evidence
The most dangerous cost reduction is removing grounding, critics or verification and calling it "efficiency." Optimize routing, retrieval, caching and clustering first. If you remove an agent or check, prove with evals that quality and safety remain acceptable.
:::

## Production notes

At real scale, put costs into showback/chargeback by tenant and feature. Separate hard limits from soft budgets. Use queue length and p95 latency to autoscale workers, but scale model concurrency carefully; increasing `engine.llm_concurrency` can move the bottleneck to a provider rate limit. Keep "cluster before you reason" as a design rule: six related signals should become one incident and one diagnosis, not six expensive swarms.

:::quiz
Q: Where does SwarmPipe record cost per model call?
- [ ] Only in the dashboard DOM
- [x] In the `llm_calls` table and related metrics
- [ ] Only in audit rows
> `llm_calls` is the source for run, incident, agent, model and tenant attribution.

Q: Why are output tokens important?
- [ ] They are always free
- [x] They often cost more and increase latency
- [ ] They are not recorded
> SwarmPipe records input and output tokens separately.

Q: What does `llm.cache_disabled` do?
- [x] Stops the gateway from serving deterministic cache hits
- [ ] Deletes published datasets
- [ ] Disables tenant quotas
> It is an efficiency experiment flag, not a correctness flag.

Q: What should happen when a tenant quota is exceeded?
- [ ] The system should silently bypass the quota
- [x] Model-heavy work should degrade or abstain while deterministic safety still runs
- [ ] The default tenant should also stop
> Quotas are per tenant, and safe deterministic controls should remain available.

Q: Which capacity control protects model calls from consuming all runtime concurrency?
- [ ] `watcher.extensions`
- [x] `engine.llm_concurrency`
- [ ] `prompts.enforce_lock`
> The model gateway uses a bulkhead semaphore from `engine.llm_concurrency`.
:::

:::takeaways
- Multi-agent cost is measurable only if every model call records tokens, cost, role, agent, tenant, run and incident.
- Route small models to simple roles and stronger models to roles where evals justify the quality/cost trade-off.
- Cache, idempotency, clustering and bounded retrieval reduce spend before you remove safety agents.
- Per-run budgets and tenant quotas intentionally cause graceful degradation or abstention.
- Watch p95 latency, queue depth, breaker opens and SLO burn alongside dollars.
- Cost SLOs are operational policy even when the local config focuses on latency and success SLOs.
:::
