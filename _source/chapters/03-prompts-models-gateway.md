---
objectives:
  - "Treat prompts as versioned, approved code rather than ad hoc strings"
  - "Explain message construction, untrusted data blocks, token estimates and cost"
  - "Follow a model call through routing, guardrails, cache, retries, repair and fallback"
  - "Use LLM profiles and simulated models safely in local labs"
  - "Observe malformed-output repair and model-gateway metrics"
---

Prompts are executable instructions for a probabilistic dependency. If they change silently, your agent changed
silently. If they mix trusted instructions with untrusted data, your agent can be steered by a spreadsheet cell. If
their outputs are not validated, your workflow is parsing wishes.

SwarmPipe treats prompt and model access as a controlled gateway problem: prompts are versioned and hash-locked, model
calls are routed by role, and every response is validated before it can affect a workflow.

## Prompts are code

SwarmPipe prompt templates live in `prompts\<id>.<version>.md` with front matter. The approved hashes live in
`prompts\prompts.lock.json`. `PromptRegistry` loads templates, hot-reloads changed files and refuses an edited prompt
unless its hash is approved.

:::swarmpipe Prompt change control
`swarmpipe/llm/prompts.py` implements `PromptRegistry.get`. When `prompts.enforce_lock` is true, an unapproved prompt
raises `PROMPT_NOT_APPROVED`. The full eval-and-lock workflow belongs to [Chapter 18](18-ci-gates-certification.html);
for now, remember that prompt edits are code changes.
:::

Prompt versioning matters because many agents share a role. `diagnoser.v1` and `diagnoser.v2` can both exist; one can
run in shadow while the approved version serves production traffic.

Think of this as the prompt equivalent of a dependency lock. The source file is human-readable, the lock records the
exact approved body hash, and the runtime checks that the file on disk still matches. If someone edits the prompt in a
running workspace, hot reload notices within a few seconds. The new text is visible to the registry, but it is not
usable until the lock approves it. That is intentionally inconvenient: prompt changes can alter tool choices,
citations, refusal behavior and cost, so they need the same discipline as code changes.

## Building messages safely

Model messages have two jobs: durable instructions and task data. SwarmPipe puts the prompt body in the system message
and data blocks in the user message. Each data block has a trust label.

:::concept Untrusted data block
Any content that came from a file, user, document or untrusted tool result is data to inspect, not instructions to
obey. SwarmPipe can wrap it in randomized `<<<DATA ...>>>` boundaries, a preview of spotlighting. Chapter 19 explains
the threat model and defense in depth.
:::

The prompt builder also bounds untrusted text with `guardrails.max_untrusted_chars`, redacts PII before model calls and
checks prompts for known secret values. These are gateway controls, not model behavior.

The separation of instructions and data also improves debugging. When you inspect a model-call row in **Runs**, you can
ask: did the system instructions say the right thing, did the task include the right facts, and which data blocks were
untrusted? Without that separation, teams end up with giant string-concatenated prompts where a cell value, a runbook
quote and a developer instruction are indistinguishable.

## Tokens, context windows and cost

Models bill and fail around tokens, not characters. SwarmPipe's simulated models use `swarmpipe/llm/tokens.py`, a
simple `chars / 4` heuristic unless `SWARMPIPE_TOKENIZER=tiktoken` is set. Real providers report usage directly.

Model prices and context windows live in `config/swarmpipe.yaml`:

```yaml
sim-small:
  usd_per_1k_in: 0.00015
  usd_per_1k_out: 0.0006
  context_window: 16000
sim-large:
  usd_per_1k_in: 0.0025
  usd_per_1k_out: 0.01
  context_window: 128000
```

The numbers for simulated models are illustrative, but the accounting is real: `llm_calls`, `llm_tokens_total` and
`llm_cost_usd_total` are recorded per call, role, agent, tenant and run.

Context windows are a second budget. A model with a 16,000-token context cannot safely accept an unlimited incident
history, row sample and runbook corpus. `ModelGateway._compact` trims the longest message when estimated context would
overflow. That is a last-resort safety valve, not a context strategy; better agent design retrieves bounded evidence
with tools instead of stuffing whole datasets into prompts.

## Typed outputs and repair

Every operational model call has a schema. The gateway first tries tolerant JSON extraction: raw JSON, fenced JSON or
the first `{...}` span. Then it validates against the requested Pydantic model. If parsing or validation fails, the
gateway appends a repair instruction and asks again. If repairs fail, it tries the next model in the route chain. If
all models fail, the calling agent degrades.

:::swarmpipe Gateway pipeline
The docstring in `swarmpipe/llm/gateway.py` lists the per-call order:

```text
kill switch -> tenant quota -> run budget -> guardrails -> context-window
compaction -> cache -> route chain -> circuit breaker -> bulkhead ->
transport retries -> JSON extraction + schema validation -> repair loop
```
:::

This order is important. For example, a kill switch and quota are checked before spending tokens; schema validation
happens before the response can control a workflow.

Every attempt is recorded, including failed validation. That history lets you answer questions operators actually ask:
which model served this role, did it use a fallback, how many repairs happened, what did it cost, and which prompt hash
was active? When the answer is bad, you can separate model behavior from system behavior. A wrong diagnosis is different
from a schema-validation failure, which is different from a quota refusal.

## Routing, profiles and simulated models

Model routes are per role. In the default `offline` profile, most roles use `sim-small`, while expensive reasoning
roles such as `diagnoser`, `planner`, `steward`, `analyst` and `judge` route to `sim-large` first, with fallbacks where
configured.

:::cards LLM profiles
`offline` | simulated `sim-small` and `sim-large`; default, local and deterministic
`ollama` | local `llama3.2:latest` with simulated fallback
`azure` | Azure OpenAI-compatible hosted route, configured with secrets
`openai` | OpenAI-compatible hosted route, configured with secrets
:::

Switch profiles with `sp llm use <profile>`. The README is explicit: hosted profiles can send data off-machine, so the
tutorial stays offline by default. Simulated models exist so failures are reproducible: latency, timeout, outage,
malformed JSON, wrong answer, hallucinated citation and loop behavior are all chaos knobs.

:::analogy Model gateway as an electrical panel
You do not wire every room directly to the power plant. You route circuits through a panel with breakers, labels and
limits. The model gateway is that panel for agents: one place to switch profiles, trip breakers, meter usage and shut
off unsafe traffic.
:::

## What the gateway does not solve

The gateway makes a call safer and observable; it does not make a model omniscient. It cannot infer missing evidence,
certify a new model by itself or decide that a risky action is acceptable. Those responsibilities live in other layers:
tool retrieval and grounding in [Chapter 11](11-context-memory.html), eval gates in [Chapter 18](18-ci-gates-certification.html),
policy in [Chapter 21](21-policy-autonomy.html) and operations/cost management in [Chapter 24](24-cost-capacity.html).

This separation keeps the architecture understandable. The prompt registry controls prompt integrity. The gateway
controls model access. Agents own task-specific fallback behavior. Workflows own durable progress. Policy owns action
risk. If you put all of those decisions inside one prompt, you get a demo; if you split them, you get an operable
system.

## Hands-on: inspect prompts and routes

:::lab Prompt registry and model status
1. List prompts:

   ```powershell
   sp prompts list
   ```

   ```output
   | key             | role         | approved | hash         | description                  |
   |-----------------+--------------+----------+--------------+------------------------------|
   | analyst_sql.v1  | analyst      | True     | ae60f1eacd56 | Natural language to...       |
   | critic.v1       | critic       | True     | 41b24ed99c1d | Evaluator in an...           |
   | diagnoser.v1    | diagnoser    | True     | 49cc44b8836c | Supervisor that merges...    |
   | router.v1       | router       | True     | cba7d3cdeca4 | Classify an arriving file... |
   ...
   ```

2. Open `prompts\router.v1.md` in your editor. Notice the prompt asks for a JSON object matching the schema and uses
   deterministic sniffer results as strong evidence.

3. Show active routing:

   ```powershell
   sp llm status
   ```

   ```output
   {
     "active_profile": "offline",
     "routes": {
       "default": ["sim-small"],
       "diagnoser": ["sim-large", "sim-small"],
       "planner": ["sim-large", "sim-small"],
       "steward": ["sim-large", "sim-small"]
     },
     "breakers": {}
   }
   ```
:::

:::lab Test a role and observe repair
1. Send one Router call:

   ```powershell
   sp llm test --role router
   ```

   ```output
   served by sim-small (mock) in 0.02s, tokens 425/22, repairs 0, chain ['sim-small']
   {
     "kind": "tabular",
     "confidence": 0.96,
     "reason": "sniffer: consistent comma delimiter"
   }
   ```

2. Force malformed model output and repeat:

   ```powershell
   sp chaos set llm_malformed_rate 1
   sp llm test --role router
   ```

   ```output
   chaos.llm_malformed_rate = 1
   served by sim-small (mock) in 0.02s, tokens 490/22, repairs 1, chain ['sim-small']
   {
     "kind": "tabular",
     "confidence": 0.96,
     "reason": "sniffer: consistent comma delimiter"
   }
   ```

3. Drop a scenario while the flag is on, then inspect **Runs** -> **Model calls** or **Cost & Metrics**:

   ```powershell
   sp scenarios drop volume_drop --process
   sp metrics
   sp chaos clear
   ```

   ```output
   | metric            | count | sum  |
   |-------------------+-------+------|
   | llm_calls_total   | ...   | ...  |
   | llm_repairs_total | ...   | ...  |
   ```

   The metric may be absent until at least one repair occurs. In the dashboard, model-call rows with
   `status=invalid_output` are followed by repair attempts.

4. Open the **Runs** tab for the scenario run. In **Model calls**, compare the original invalid-output attempt with
   the repair attempt. The important field is not the exact token count; it is the fact that repair is explicit,
   counted and visible instead of hidden inside agent code.
:::

:::breakit Disable the cache and compare
The cache is useful only for deterministic, cacheable calls. Disable it with a runtime flag, run a repeated scenario
or role test that normally reuses stable prompts, then compare **Cost & Metrics** before and after:

```powershell
sp chaos set llm.cache_disabled true
sp scenarios drop clean_day --process
sp metrics
sp chaos clear
```

With the cache disabled, `llm_cache_hits_total` stops increasing and repeated model calls cost tokens again. This is a
safe break-it experiment: it changes efficiency, not data correctness.

If you are using a fresh workspace, you may need to run the same deterministic workload twice before cache behavior is
visible. Cache keys normalize spotlight boundary ids, so randomized data markers do not defeat caching for otherwise
identical deterministic prompts.
:::

:::warning Prompt quality is not the same as system safety
A better prompt may reduce mistakes, but the gateway still needs quotas, budgets, circuit breakers, schema validation,
fallbacks and policy checks. Prompt changes should improve eval scores; they should not be trusted to replace
deterministic controls.
:::

## Quiz

:::quiz
Q: Why does SwarmPipe keep `prompts.lock.json`?
- [ ] To make prompts shorter
- [x] To approve exact prompt hashes and refuse unapproved prompt edits
- [ ] To store model outputs
> Prompt text is code. A lockfile prevents silent behavior changes.

Q: What happens when a model returns fenced JSON or prose plus JSON?
- [ ] The gateway always fails immediately
- [x] The gateway attempts tolerant JSON extraction, then schema validation
- [ ] The workflow accepts the prose
> SwarmPipe can extract JSON from common wrappers, but the extracted object still must validate.

Q: What is the purpose of an LLM profile?
- [ ] It stores user passwords
- [x] It maps roles to ordered model fallback chains
- [ ] It changes the dashboard theme
> `offline`, `ollama`, `azure` and `openai` profiles define which model serves each role.

Q: Why use simulated models in this tutorial?
- [ ] They are more capable than hosted models
- [x] They are local, deterministic by default and can reproduce failure modes on demand
- [ ] They bypass validation
> The simulator is a training and CI tool, not a claim of intelligence.

Q: Which chapter owns the full prompt change-control workflow?
- [ ] Chapter 4
- [x] Chapter 18
- [ ] Chapter 24
> This chapter introduces prompt locks; Chapter 18 teaches the eval gate and approval workflow.
:::

:::takeaways
- Prompts are versioned code with approved hashes, not casual strings.
- Message construction separates durable instructions from trusted and untrusted data blocks.
- Token estimates, context windows and per-model prices feed cost and budget controls.
- The model gateway applies kill switches, quotas, budgets, guardrails, cache, retries, repair, fallback and metering.
- Simulated models keep labs offline while making real failure modes reproducible.
:::
