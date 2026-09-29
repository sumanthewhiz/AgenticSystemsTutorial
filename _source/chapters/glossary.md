## A

**A2A (Agent2Agent)** - An open protocol for agent-to-agent discovery and task exchange. See [Chapter 10](10-communication-protocols.html).

**Abstention** - A model or agent choosing not to decide when evidence is weak or contradictory. See [Chapter 9](09-triage-swarm.html).

**Action catalog** - The allowlist of state-changing operations an agent may propose, each with typed parameters and verification. See [Chapter 21](21-policy-autonomy.html).

**Agent** - A component that uses a model, tools and state to decide part of a task. See [Chapter 1](01-llm-to-agent.html).

**Agent card** - A machine-readable description of an agent's identity, skills and endpoints. See [Chapter 10](10-communication-protocols.html).

**Agent loop** - The repeated observe, think, act and observe cycle often called ReAct. See [Chapter 1](01-llm-to-agent.html).

**Analyst agent** - SwarmPipe's governed natural-language-to-SQL agent for published data. See [Chapter 20](20-identity-access.html).

**Approval** - A durable human decision that lets a prepared action continue, often with typed confirmation. See [Chapter 21](21-policy-autonomy.html).

**Audit log** - A durable, tamper-evident record of decisions and side effects. See [Chapter 22](22-audit-evidence.html).

**Autonomy ladder** - SwarmPipe's L0-L4 scale from inform-only to autonomous execution, earned with evidence and withdrawn after failures. See [Chapter 21](21-policy-autonomy.html).

## B

**Backpressure** - Admission control that slows or stops new work when queues are too deep. See [Chapter 5](05-ingestion.html).

**Blackboard** - Shared case state where agents append findings, evidence and decisions. See [Chapter 8](08-why-multi-agent.html).

**Blast radius** - The downstream consumers, datasets or reports affected by an action or bad batch. See [Chapter 7](07-publishing-lineage.html).

**Blue/green publish** - Publishing by staging a new immutable version and then repointing a stable view. See [Chapter 7](07-publishing-lineage.html).

**Bulkhead** - A concurrency boundary that keeps a slow dependency from starving unrelated work. See [Chapter 13](13-model-resilience.html).

## C

**Canary** - A limited rollout to a small cohort before general availability. See [Chapter 18](18-ci-gates-certification.html).

**Checkpoint** - A persisted step result that lets a workflow resume without replaying earlier work. See [Chapter 12](12-durable-execution.html).

**Circuit breaker** - A control that stops publishing or dependency calls when failures cross a threshold. See [Chapter 6](06-contracts-and-quality.html).

**Compensation** - A saga rollback action that semantically undoes a side effect. See [Chapter 12](12-durable-execution.html).

**Context engineering** - Selecting, labeling and compressing the right information for a model call. See [Chapter 11](11-context-memory.html).

**Control plane** - The governance, identity, policy, model, tool and eval machinery that controls agents. See [Chapter 2](02-architecture-tour.html).

**Critic** - An evaluator agent that reviews another agent's proposal using independent evidence. See [Chapter 8](08-why-multi-agent.html).

## D

**Data contract** - A versioned agreement for schema, semantics, freshness and quality. See [Chapter 6](06-contracts-and-quality.html).

**Data plane** - The workflows, watcher, event bus, warehouse and files that move and transform data. See [Chapter 2](02-architecture-tour.html).

**Dead-letter queue (DLQ)** - Storage for work that failed permanently and needs operator attention. See [Chapter 5](05-ingestion.html).

**Delegation** - Acting on behalf of a user while intersecting user and agent permissions. See [Chapter 20](20-identity-access.html).

**Deterministic fallback** - Non-model logic used when the model is unavailable or untrusted. See [Chapter 1](01-llm-to-agent.html).

**Durable execution** - Running workflows so crashes, retries and waits do not lose progress. See [Chapter 12](12-durable-execution.html).

## E

**Egress allowlist** - A control that permits outbound communication only to approved destinations. See [Chapter 19](19-threat-model.html).

**Embedding** - A vector representation used for semantic retrieval; SwarmPipe uses BM25 locally instead. See [Chapter 11](11-context-memory.html).

**Error budget** - The allowed amount of unreliability before a team slows feature changes. See [Chapter 23](23-observability.html).

**Eval case** - A versioned input, expectation and scoring rule for measuring behavior. See [Chapter 15](15-eval-fundamentals.html).

**Eval flywheel** - The loop of production feedback becoming new regression cases. See [Chapter 18](18-ci-gates-certification.html).

**Evidence id** - A stable citation id attached to a tool result or observation. See [Chapter 11](11-context-memory.html).

**Evidence pack** - An export containing signals, data snapshots, evidence, policy, approvals, actions, verification and audit anchors. See [Chapter 22](22-audit-evidence.html).

## F

**Fan-in** - Merging parallel work back into one decision or output. See [Chapter 8](08-why-multi-agent.html).

**Fan-out** - Splitting work into parallel child tasks or specialist investigations. See [Chapter 8](08-why-multi-agent.html).

**Feature flag** - A runtime switch that changes behavior without editing code. See [Chapter 26](26-operations.html).

**Fencing** - Preventing a worker with a lost lease from continuing side effects. See [Chapter 12](12-durable-execution.html).

**Freeze window** - A policy period where risky actions are escalated to approval. See [Chapter 26](26-operations.html).

## G

**GA (General availability)** - The broad rollout stage after evals, shadow and canary evidence. See [Chapter 18](18-ci-gates-certification.html).

**GenAI semantic conventions** - OpenTelemetry attribute names for model, agent and tool spans. See [Chapter 23](23-observability.html).

**Groundedness** - The degree to which a claim is supported by cited evidence. See [Chapter 11](11-context-memory.html).

**Guardrail** - A deterministic or model-assisted control that reduces unsafe behavior. See [Chapter 19](19-threat-model.html).

## H

**Hallucinated citation** - A citation id or source reference that does not exist in the provided evidence. See [Chapter 11](11-context-memory.html).

**Hash chain** - A sequence where each audit row includes the previous hash, making tampering evident. See [Chapter 22](22-audit-evidence.html).

**Health check** - A liveness probe that tells whether the service can answer. See [Chapter 26](26-operations.html).

**Human-in-the-loop** - A design where a human approves, rejects or supplies judgment for risky steps. See [Chapter 21](21-policy-autonomy.html).

## I

**Idempotency key** - A key that makes repeated side-effect attempts execute at most once. See [Chapter 12](12-durable-execution.html).

**Immutable version** - A dataset version that is never edited after creation. See [Chapter 7](07-publishing-lineage.html).

**Incident** - A correlated set of signals that needs diagnosis and possibly remediation. See [Chapter 9](09-triage-swarm.html).

**Indirect prompt injection** - Malicious instructions hidden in data, documents or tool results. See [Chapter 19](19-threat-model.html).

**Ingestion** - Turning files in the watched folder into durable workflow runs. See [Chapter 5](05-ingestion.html).

**Investigator** - A read-only specialist agent that gathers cited evidence for one failure family. See [Chapter 9](09-triage-swarm.html).

## J

**Judge** - A model used to score open-ended output against a rubric. See [Chapter 16](16-llm-judge.html).

**Judge calibration** - Measuring judge agreement with human labels and bias before trusting scores. See [Chapter 16](16-llm-judge.html).

## K

**Kill switch** - A scoped control that stops model calls or actions immediately. See [Chapter 22](22-audit-evidence.html).

**Knowledge poisoning** - Corrupting retrieved documents or memory so future agents receive bad guidance. See [Chapter 11](11-context-memory.html).

## L

**Lease** - A time-limited claim on a run that expires if a worker dies. See [Chapter 12](12-durable-execution.html).

**Lethal trifecta** - The risky combination of private data access, untrusted content and external communication. See [Chapter 19](19-threat-model.html).

**Lineage** - Metadata describing datasets, jobs, versions and dependencies. See [Chapter 7](07-publishing-lineage.html).

**LLM gateway** - The shared path for model routing, budgets, cache, breakers, validation and fallback. See [Chapter 3](03-prompts-models-gateway.html).

## M

**MCP (Model Context Protocol)** - A protocol for exposing tools and data sources to model clients. See [Chapter 10](10-communication-protocols.html).

**Memory** - Stored knowledge from runs, lessons or curated documents. See [Chapter 11](11-context-memory.html).

**Model certification** - Running role-specific evals before trusting a model in that role. See [Chapter 25](25-model-strategy.html).

**Model profile** - A configured model routing chain such as offline, Ollama, Azure or OpenAI. See [Chapter 25](25-model-strategy.html).

**Multi-agent system** - A system where multiple agents cooperate through routing, handoff, fan-out or shared state. See [Chapter 8](08-why-multi-agent.html).

## N

**Natural-language-to-SQL** - Translating a user question into read-only governed SQL. See [Chapter 20](20-identity-access.html).

**Non-determinism** - Variation in model output across attempts, measured rather than ignored. See [Chapter 15](15-eval-fundamentals.html).

## O

**OIDC** - OpenID Connect, the production identity mechanism that replaces demo headers. See [Chapter 20](20-identity-access.html).

**On-call ergonomics** - Designing alerts, approvals and runbooks so tired humans can act safely. See [Chapter 26](26-operations.html).

**OpenLineage** - An open specification for job and dataset lineage events. See [Chapter 7](07-publishing-lineage.html).

**OpenTelemetry** - A standard for traces, metrics and logs across services. See [Chapter 23](23-observability.html).

**Out-of-band change** - A direct data edit that bypasses the pipeline. See [Chapter 7](07-publishing-lineage.html).

## P

**pass@k** - The probability that at least one of k attempts succeeds. See [Chapter 15](15-eval-fundamentals.html).

**pass^k** - The probability that all k attempts succeed, a stricter reliability view. See [Chapter 15](15-eval-fundamentals.html).

**PII tokenization** - Replacing personal data with stable tokens unless an authorized identity detokenizes it. See [Chapter 20](20-identity-access.html).

**Policy-as-code** - Deterministic authorization rules stored and reviewed as code. See [Chapter 21](21-policy-autonomy.html).

**Poison file** - An input crafted to crash parsing, mislead a model or carry malicious instructions. See [Chapter 14](14-failure-modes.html).

**Postmortem** - A blameless explanation of what happened and how to prevent recurrence. See [Chapter 9](09-triage-swarm.html).

**PRD** - Product requirements document; for AI features it must include eval and safety requirements. See [Chapter 27](27-capstone.html).

**Prompt lock** - A lockfile of approved prompt hashes enforced at runtime. See [Chapter 18](18-ci-gates-certification.html).

**PSI (Population Stability Index)** - A drift metric comparing current and baseline distributions. See [Chapter 6](06-contracts-and-quality.html).

## Q

**Quality check** - A data-health assertion such as row count, schema, accepted values, freshness or drift. See [Chapter 6](06-contracts-and-quality.html).

**Quarantine** - Storing bad or suspicious data without publishing it to consumers. See [Chapter 6](06-contracts-and-quality.html).

## R

**Readiness check** - A probe that tells whether the platform is ready to process work. See [Chapter 26](26-operations.html).

**ReAct** - An agent pattern that interleaves reasoning and tool actions. See [Chapter 1](01-llm-to-agent.html).

**Red team** - Purposefully attacking the system to measure containment. See [Chapter 17](17-red-teaming.html).

**Redrive** - Requeueing dead-lettered work after the cause is understood. See [Chapter 26](26-operations.html).

**Rollback** - Reverting a state change by repointing versions, restoring snapshots or running compensation. See [Chapter 12](12-durable-execution.html).

**Router agent** - The agent that classifies arriving files as tabular, document or unsupported. See [Chapter 2](02-architecture-tour.html).

**Run** - A durable workflow execution with steps, state, attempts and trace id. See [Chapter 12](12-durable-execution.html).

**Runbook** - A documented procedure for diagnosing and responding to an operational condition. See [Chapter 26](26-operations.html).

## S

**Saga** - A sequence of side effects paired with compensations. See [Chapter 12](12-durable-execution.html).

**Scenario** - A SwarmPipe synthetic input or fault you can drop into the inbox. See [Chapter 0](00-welcome.html).

**Shadow mode** - Running a candidate prompt or model beside production without acting on it. See [Chapter 18](18-ci-gates-certification.html).

**Signal** - A deterministic observation such as schema drift, freshness overdue or SLO breach. See [Chapter 9](09-triage-swarm.html).

**SLO** - Service level objective, a target for reliability measured by an SLI. See [Chapter 23](23-observability.html).

**Spotlighting** - Marking untrusted data boundaries in prompts so the model treats content as data, not instructions. See [Chapter 19](19-threat-model.html).

**Structured output** - Model output validated against a schema. See [Chapter 3](03-prompts-models-gateway.html).

**Supervisor** - The triage agent that plans investigations and owns the final diagnosis. See [Chapter 9](09-triage-swarm.html).

**SwarmPipe** - The local, offline-by-default multi-agent data pipeline used throughout the tutorial. See [Chapter 0](00-welcome.html).

## T

**Tenant isolation** - Keeping data, quotas, autonomy and permissions separated by tenant. See [Chapter 20](20-identity-access.html).

**Telemetry** - Operational traces, metrics and logs used for debugging and SLOs. See [Chapter 23](23-observability.html).

**Tool gateway** - The shared path that validates tool calls, scopes, evidence ids and fingerprints. See [Chapter 4](04-tools-and-gateway.html).

**Trace** - A tree of spans showing one request, run or incident across agents and tools. See [Chapter 23](23-observability.html).

**Trust label** - A marker such as trusted, unverified or untrusted attached to retrieved context. See [Chapter 11](11-context-memory.html).

## V

**Verifier** - The deterministic agent that checks ground truth after an action. See [Chapter 9](09-triage-swarm.html).

**Version pinning** - Recording the prompt, model, tool and agent versions used for a decision. See [Chapter 22](22-audit-evidence.html).

## W

**Watched folder** - The local inbox where files arrive for ingestion. See [Chapter 5](05-ingestion.html).

**Workflow** - A deterministic sequence of durable steps. See [Chapter 12](12-durable-execution.html).

**Workload identity** - A service identity used by software rather than a human. See [Chapter 20](20-identity-access.html).
