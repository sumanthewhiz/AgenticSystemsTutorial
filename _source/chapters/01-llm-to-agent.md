---
objectives:
  - "Explain what an LLM call does, why it is non-deterministic and how temperature changes behavior"
  - "Describe messages, roles, typed JSON outputs and tool/function calling from first principles"
  - "Trace the observe-think-act-observe loop and recognize the ReAct pattern in SwarmPipe"
  - "Choose between a fixed workflow, router, single agent and multi-agent system"
  - "Show how SwarmPipe wraps probabilistic model steps in deterministic fallbacks"
---

A production agent is not "a model with vibes." It is ordinary software that lets a model make a few bounded
decisions, then validates, records and contains those decisions. That distinction matters when a file lands late,
an upstream schema changes or a model is unavailable: the pipeline must keep moving even when the model is only partly
useful.

This chapter builds the mental model from the smallest piece, one LLM call, to the larger thing you will use through
the rest of the tutorial: an agent running inside a deterministic workflow.

## What an LLM call really is

:::concept Large language model
An LLM predicts the next token in a sequence. A **token** is a chunk of text, often a word fragment. The model receives
messages as context, estimates likely next tokens, emits one, then repeats until it stops.
:::

That sounds mechanical because it is. The useful behavior comes from scale and training: next-token prediction over a
huge corpus learns patterns for summarizing, classifying, extracting JSON and planning. It is still not a database, a
calculator or a promise of truth. It is a probabilistic text engine.

**Temperature** controls sampling. At temperature `0.0`, the model tends to pick the highest-probability token, so
outputs are steadier. Higher temperatures sample from more alternatives, which can help brainstorming but hurts
repeatability. SwarmPipe uses low temperature for operational decisions because production pipelines prefer boring
consistency over creative surprise.

:::concept Message roles
A model call is usually a list of messages. A **system** message contains durable instructions ("You are the Router
agent..."). A **user** message contains the task and data. Assistant messages are prior model outputs; tool-result
messages feed observations back into the loop.
:::

Roles are conventions enforced by the model provider, not a security boundary. SwarmPipe treats any file name, cell,
document or tool result marked untrusted as data, not instructions; Chapter 19 goes deep on prompt injection and
spotlighting.

## From free text to typed output

Free text is hard to operate. If a Router says "this looks like a spreadsheet, probably," the workflow cannot safely
branch. Production agents ask for structured output and validate it.

:::swarmpipe Typed model outputs
SwarmPipe defines model output schemas in `swarmpipe/llm/types.py`. The Router must return `RouterOut`, not prose:

```python
class RouterOut(BaseModel):
    kind: Literal["tabular", "document", "unsupported"]
    confidence: float = Field(ge=0, le=1)
    reason: str = ""
```

The model gateway renders the schema into the prompt, extracts JSON from the response, validates it with Pydantic and
repairs or falls back when validation fails.
:::

Structured output does not make the model correct. It makes the model's answer checkable. SwarmPipe still applies
deterministic guards. For example, a binary file is unsupported even if the model guesses "tabular"; an `.xlsx` file is
tabular even if the model is uncertain.

## Tools and function calling

:::concept Tool / function call
A tool is a typed operation outside the model: read check results, fetch volume history, search a runbook, send a
notification. The model chooses **which** tool to call and with **which JSON arguments**; deterministic code validates
and executes the call.
:::

Tools are how an agent observes the world. The model does not directly query SQLite or send mail. It emits a request
such as `{"action":"call_tool","tool":"get_volume_history","args":{"dataset":"sales_daily"}}`. The tool gateway checks
allowlists, scopes, schemas, rate limits and output size before returning an observation with an evidence id. Chapter 4
teaches the tool gateway in detail.

## The agent loop

An agent is a loop around a model. It observes the current state, thinks about the next step, acts through a tool or
final answer, then observes again. ReAct is the common name for this "reason + act" pattern.

:::loop The ReAct loop
Observe | messages, state, tool results and evidence
Think | choose the next small step
Act | call one tool or produce a final typed answer
Observe again | tool result becomes the next message
Stop | final answer, step budget or loop detector
:::

SwarmPipe implements this in `Agent.react` in `swarmpipe/agents/base.py`. Investigators in the triage swarm use it:
they call read-only tools, collect evidence ids, then return a typed `Finding`. The loop has a step budget, remembers
tool+argument pairs and stops when the same call repeats too often.

:::swarmpipe Deterministic skeleton, probabilistic steps
The docstring in `swarmpipe/agents/base.py` states SwarmPipe's design rule:

```python
Design rule used throughout the swarm: a deterministic skeleton with probabilistic
steps. Every LLM-backed method has a deterministic fallback, so a model outage,
a quota or a budget degrades quality instead of breaking the pipeline.
```

The workflow decides **when** the Router runs. The model only helps decide **how** to route this file, and even that
answer is guarded.
:::

## How much autonomy do you need?

Not every problem needs an agent. Use the least autonomy that solves the problem.

| Pattern | What decides | Use when | SwarmPipe example |
|---|---|---|---|
| Fixed workflow | Code | The steps are known and should not vary | `ingest_dataset`: load -> privacy -> profile -> checks -> publish |
| Router | Model or rules choose a branch | Inputs vary but branches are predefined | Router sends files to tabular, document or unsupported flow |
| Single agent | One loop chooses tools | A bounded task needs iterative evidence gathering | Analyst answers one governed data question |
| Multi-agent | Several specialized agents cooperate | Skills, privileges or verification must be separated | Triage supervisor + investigators + planner + verifier |

Industry practice beyond SwarmPipe is the same: start with deterministic code, add a router when branching is fuzzy,
add one agent when tool selection is genuinely dynamic, and add multiple agents only when separation of concerns earns
its cost.

## Agent kinds in SwarmPipe

SwarmPipe registers 27 agents. They are not all equally "AI." The `kind` field in the registry is deliberate:

:::cards Agent kinds
Deterministic | no model call; examples: `privacy_guard`, `data_assurance`, `publisher`, `executor`, `verifier`
Hybrid | deterministic logic plus one or more model calls; examples: `router`, `profiler`, `steward`, `transformer`
LLM | model-first reasoning, still typed and constrained; examples: `supervisor`, `investigator_volume`, `planner`, `learner`
:::

The Router is a good hybrid example. It asks the `router` role for `RouterOut`, then applies guards from the file
sniffer. If the model is unavailable, it falls back to the sniffer's deterministic `kind_hint`.

:::swarmpipe Router fallback
In `swarmpipe/agents/pipeline_agents.py`, `RouterAgent.run` catches gateway degradation errors and returns:

```python
{"kind": det, "confidence": 0.7,
 "source": "deterministic_fallback",
 "model": None, "degraded": True}
```

That is the production posture: the answer may be less rich, but the pipeline does not collapse.
:::

## Hands-on: follow one file and find the model call

:::lab Trace the Router and fan-out
Run these steps from your SwarmPipe folder with the virtual environment active and
the `sp` shortcut defined. Ids, dates, timings and costs vary.

1. List recent file-level runs:

   ```powershell
   sp runs list --workflow ingest_file --limit 8
   ```

   ```output
   | id                 | workflow    | status    | current_step |
   |--------------------+-------------+-----------+--------------|
   | run_...            | ingest_file | succeeded | finalize     |
   | run_...            | ingest_file | succeeded | finalize     |
   ...
   ```

2. Pick the `customers.xlsx` `ingest_file` run and show it:

   ```powershell
   sp runs show run_mumhlx9730df29
   ```

   ```output
   "workflow": "ingest_file",
   "status": "succeeded",
   "context": {
     "children": [
       "run_mumhlxev0c4a1e",
       "run_mumhlxeva40ea8"
     ],
     "result_status": "succeeded"
   }
   Steps (checkpoints)
   | stage | succeeded | deterministic |
   | route | succeeded | agent         |
   | read  | succeeded | deterministic |
   | fanout| succeeded | deterministic |
   ```

   The model participates in `route`; the two child runs are the Excel sheets `customers` and `regions`.

3. Open the dashboard **Runs** tab, click the same run and find **Model calls**. The Router call shows the role,
   model, prompt and cost. The **Overview** tab should still show no incident for the clean baseline.
:::

:::lab Send one direct model call
1. Ask the gateway to test the Router role:

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

2. Read the simulated model at a conceptual level in `swarmpipe/llm/mock.py`: it dispatches by prompt id, reads the
   rendered `context` block and can be forced to time out, return malformed JSON, cite fake evidence or loop. Do not
   treat it as intelligence; it is a flight simulator for failure modes.
:::

:::breakit Take a model away
1. Drop the outage scenario:

   ```powershell
   sp scenarios drop llm_outage --process
   sp incidents list --limit 3
   ```

   ```output
   | id       | status    | severity | dataset     | root_cause        |
   |----------+-----------+----------+-------------+-------------------|
   | inc_...  | mitigated | critical | sales_daily | truncated_extract |
   ```

2. Inspect the trace of that incident:

   ```powershell
   sp trace inc_mumhpl3ff96a11
   ```

   ```output
   chat diagnoser ... 
     +-- llm.call sim-large ...
     +-- llm.call sim-large ...
     +-- llm.call sim-large ...
     `-- llm.call sim-small ... cost_usd=...
   ```

The scenario takes `sim-large` away. The gateway retries, opens the breaker when needed and falls back to `sim-small`;
agent-level fallbacks are the next line of defense if every routed model is unavailable. Clear lab faults afterward:

```powershell
sp chaos clear
```
:::

:::warning Non-determinism is not a bug you can wish away
Even temperature `0.0` does not turn a model into a deterministic function across providers, versions or hardware.
Production systems constrain the model with typed outputs, tests, evals, fallbacks and policy; they do not assume the
same prompt will always behave the same way.
:::

## Quiz

:::quiz
Q: What is the safest way to use an LLM result inside a workflow?
- [ ] Parse whatever text the model emits and hope the wording stays stable
- [x] Ask for a typed JSON object, validate it and apply deterministic guards
- [ ] Increase temperature so the model explores more answers
> Typed output makes the response checkable; deterministic guards keep unsafe or impossible answers from controlling the workflow.

Q: Why is the Router a hybrid agent?
- [ ] It calls two real hosted models
- [x] It combines a model classification with deterministic sniffer facts and fallback logic
- [ ] It can send notifications
> The Router uses the model for classification, but hard file facts can override or replace that answer.

Q: In the ReAct loop, what happens after a tool returns data?
- [ ] The tool result is automatically trusted as an action
- [x] The result becomes the next observation message, usually with an evidence id
- [ ] The workflow restarts
> Tool output is an observation. The agent may call another tool or finish with a typed answer.

Q: When should you use multiple agents?
- [ ] Whenever a single prompt is long
- [ ] Whenever a model is available
- [x] When specialization, privilege separation or independent verification earns the extra cost
> Multi-agent systems multiply cost and failure modes. SwarmPipe uses them where separation is valuable.
:::

:::takeaways
- An LLM predicts tokens; an agent is a controlled loop that uses model outputs to choose bounded steps.
- System and user roles organize instructions and data, but validation and authorization must live outside the model.
- SwarmPipe validates every model response against typed schemas in `swarmpipe/llm/types.py`.
- The durable workflow is deterministic; model calls are probabilistic steps inside it.
- Hybrid agents such as the Router use models for fuzzy decisions and deterministic fallbacks for resilience.
:::
