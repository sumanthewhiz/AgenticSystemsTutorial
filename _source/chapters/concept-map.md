Use this appendix when you want to jump from an idea to the exact SwarmPipe implementation. Paths and identifiers were checked against the project source.

## Part 0 - Start here

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| First run and scenarios | `swarmpipe/scenarios.py` `SCENARIOS` | `sp scenarios list` | [Chapter 0](00-welcome.html) |
| Dashboard tabs | `swarmpipe/web/static/app.js` | open `http://127.0.0.1:8765` | [Chapter 0](00-welcome.html) |
| Reset and clean slate | `swarmpipe/cli.py` `reset` | `sp reset --yes` | [Chapter 0](00-welcome.html) |

## Part I - Foundations

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Agent base class | `swarmpipe/agents/base.py` `Agent` | dashboard **Agents & Tools** | [Chapter 1](01-llm-to-agent.html) |
| ReAct loop | `swarmpipe/agents/base.py` `react` | `sp trace <ident>` after an incident | [Chapter 1](01-llm-to-agent.html) |
| Deterministic fallbacks | `swarmpipe/agents/base.py` `DEGRADE_ERRORS` | `sp scenarios drop llm_outage --process` | [Chapter 1](01-llm-to-agent.html) |
| Composition root | `swarmpipe/app.py` `build_services` | `sp init` | [Chapter 2](02-architecture-tour.html) |
| Workflows | `swarmpipe/runtime/workflows.py` `build_workflows` | `sp runs list` | [Chapter 2](02-architecture-tour.html) |
| Agent registry | `swarmpipe/agents/registry.py` `AgentRegistry` | dashboard **Agents & Tools** | [Chapter 2](02-architecture-tour.html) |
| Model gateway | `swarmpipe/llm/gateway.py` `ModelGateway` | `sp llm status` | [Chapter 3](03-prompts-models-gateway.html) |
| Prompt registry | `swarmpipe/llm/prompts.py` `PromptRegistry` | `sp prompts list` | [Chapter 3](03-prompts-models-gateway.html) |
| Prompt lock | `prompts/prompts.lock.json` | `sp evals gate --update-lock` | [Chapter 3](03-prompts-models-gateway.html) |
| Tool gateway | `swarmpipe/tools/gateway.py` `ToolGateway` | dashboard **Agents & Tools** | [Chapter 4](04-tools-and-gateway.html) |
| Tool catalog | `swarmpipe/tools/catalog.py` `READ_TOOLS` | `sp trace <ident>` | [Chapter 4](04-tools-and-gateway.html) |
| Rogue-agent suspension | `swarmpipe/tools/gateway.py` `call` | `sp killswitch on --scope agent:<id>` | [Chapter 4](04-tools-and-gateway.html) |

## Part II - Data pipeline backbone

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Watched folder polling | `swarmpipe/runtime/watcher.py` `FolderWatcher` | `sp scenarios drop clean_day --process` | [Chapter 5](05-ingestion.html) |
| File admission | `swarmpipe/runtime/workflows.py` `f_stage` | `sp runs show <run_id>` | [Chapter 5](05-ingestion.html) |
| Readers and sniffing | `swarmpipe/data/readers.py` `sniff` | `sp scenarios drop pipe_txt --process` | [Chapter 5](05-ingestion.html) |
| DLQ | `swarmpipe/cli.py` `dlq_list` | `sp dlq list` | [Chapter 5](05-ingestion.html) |
| Contract store | `swarmpipe/data/contracts.py` `ContractStore` | dashboard **Datasets & Lineage** | [Chapter 6](06-contracts-and-quality.html) |
| Sales contract | `config/contracts/sales_daily.yaml` | `sp scenarios drop volume_drop --process` | [Chapter 6](06-contracts-and-quality.html) |
| Data-quality checks | `swarmpipe/data/quality.py` `run_checks` | `sp runs show <run_id>` | [Chapter 6](06-contracts-and-quality.html) |
| Circuit breaker | `swarmpipe/runtime/workflows.py` `d_quality` | `sp scenarios drop quality_failure --process` | [Chapter 6](06-contracts-and-quality.html) |
| Publishing | `swarmpipe/data/publishing.py` `PublishingService` | dashboard **Datasets & Lineage** | [Chapter 7](07-publishing-lineage.html) |
| Warehouse versions | `swarmpipe/data/warehouse.py` `Warehouse` | `sp scenarios drop clean_day --process` | [Chapter 7](07-publishing-lineage.html) |
| Lineage graph | `swarmpipe/data/lineage.py` `LineageService` | dashboard **Datasets & Lineage** | [Chapter 7](07-publishing-lineage.html) |
| Context graph | `swarmpipe/data/lineage.py` `ContextGraph` | MCP `get_lineage_impact` | [Chapter 7](07-publishing-lineage.html) |

## Part III - The swarm

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Router pattern | `swarmpipe/agents/pipeline_agents.py` `RouterAgent` | `sp scenarios drop encoding --process` | [Chapter 8](08-why-multi-agent.html) |
| Fan-out and fan-in | `swarmpipe/runtime/workflows.py` `f_fanout` | `sp scenarios drop reference --process` | [Chapter 8](08-why-multi-agent.html) |
| Evaluator-optimizer | `swarmpipe/agents/pipeline_agents.py` `CriticAgent` | `sp scenarios drop schema_drift --process` | [Chapter 8](08-why-multi-agent.html) |
| Correlation | `swarmpipe/agents/triage_agents.py` `CorrelatorAgent` | `sp scenarios drop mass_failure --process` | [Chapter 9](09-triage-swarm.html) |
| Supervisor | `swarmpipe/agents/triage_agents.py` `TriageSupervisorAgent` | dashboard **Incidents** | [Chapter 9](09-triage-swarm.html) |
| Planner | `swarmpipe/agents/triage_agents.py` `RemediationPlannerAgent` | incident proposal list | [Chapter 9](09-triage-swarm.html) |
| Verifier | `swarmpipe/agents/triage_agents.py` `VerifierAgent` | proposal verification status | [Chapter 9](09-triage-swarm.html) |
| Message bus | `swarmpipe/agents/messaging.py` `MessageBus` | `sp trace <ident>` | [Chapter 10](10-communication-protocols.html) |
| MCP server | `swarmpipe/mcp_server.py` `McpServer` | `sp mcp --as oncall` | [Chapter 10](10-communication-protocols.html) |
| A2A endpoints | `swarmpipe/web/api.py` `create_app` | `/a2a/agents` | [Chapter 10](10-communication-protocols.html) |
| Knowledge search | `swarmpipe/data/knowledge.py` `KnowledgeBase` | `sp knowledge search "volume drop"` | [Chapter 11](11-context-memory.html) |
| Memory store | `swarmpipe/memory.py` `MemoryStore` | dashboard **Knowledge & Memory** | [Chapter 11](11-context-memory.html) |
| Spotlighting | `swarmpipe/llm/prompts.py` `build_messages` | `sp scenarios drop injection --process` | [Chapter 11](11-context-memory.html) |

## Part IV - Reliability

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Checkpoints | `swarmpipe/runtime/engine.py` `_run_step` | `sp runs show <run_id>` | [Chapter 12](12-durable-execution.html) |
| Leases and reaper | `swarmpipe/runtime/engine.py` `reap_expired_leases` | `sp chaos crash-after --step transform` | [Chapter 12](12-durable-execution.html) |
| Idempotency | `swarmpipe/runtime/engine.py` `StepContext` | `sp scenarios drop duplicate --process` | [Chapter 12](12-durable-execution.html) |
| Saga compensation | `swarmpipe/runtime/workflows.py` `rollback_proposal` | `sp actions rollback <proposal_id> --as oncall` | [Chapter 12](12-durable-execution.html) |
| Model breaker | `swarmpipe/llm/gateway.py` `CircuitBreaker` | `sp scenarios drop llm_outage --process` | [Chapter 13](13-model-resilience.html) |
| Repair loop | `swarmpipe/llm/gateway.py` `extract_json` | `sp chaos set llm_malformed_rate 0.5` | [Chapter 13](13-model-resilience.html) |
| Cost and budget fallback | `swarmpipe/llm/gateway.py` `_check_limits` | dashboard **Cost & Metrics** | [Chapter 13](13-model-resilience.html) |
| Failure scenarios | `swarmpipe/scenarios.py` `s_flaky_llm` | `sp scenarios drop flaky_llm --process` | [Chapter 14](14-failure-modes.html) |
| Loop detection | `swarmpipe/agents/base.py` `react` | `sp chaos set llm_loop_rate 0.7` | [Chapter 14](14-failure-modes.html) |

## Part V - Evaluation

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Eval harness | `swarmpipe/evals/harness.py` `run_suites` | `sp evals run --suite triage --k 1` | [Chapter 15](15-eval-fundamentals.html) |
| Triage dataset | `evals/datasets/triage.v1.jsonl` | `sp evals run --suite triage --cases tri-010-clean-day` | [Chapter 15](15-eval-fundamentals.html) |
| Gate thresholds | `evals/gate.yaml` | `sp evals gate --k 2` | [Chapter 15](15-eval-fundamentals.html) |
| Judge calibration | `swarmpipe/evals/judge.py` `calibrate` | `sp evals calibrate-judge --version v2` | [Chapter 16](16-llm-judge.html) |
| Red-team suite | `evals/datasets/redteam.v1.jsonl` | `sp evals run --suite redteam` | [Chapter 17](17-red-teaming.html) |
| Prompt approval | `swarmpipe/llm/prompts.py` `PromptRegistry` | `sp prompts list` | [Chapter 18](18-ci-gates-certification.html) |
| Model certification | `swarmpipe/evals/harness.py` `certify` | `sp evals certify --model llama3.2 --roles router` | [Chapter 18](18-ci-gates-certification.html) |

## Part VI - Governance

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Prompt injection scan | `swarmpipe/governance/guardrails.py` `scan_text` | `sp scenarios drop injection --process` | [Chapter 19](19-threat-model.html) |
| PII vault | `swarmpipe/data/pii.py` `PiiVault` | `sp ask "emails of customers" --as admin` | [Chapter 20](20-identity-access.html) |
| Identity service | `swarmpipe/governance/identity.py` `IdentityService` | dashboard **Ask the data** | [Chapter 20](20-identity-access.html) |
| Policy engine | `swarmpipe/governance/policy.py` `PolicyEngine` | `sp policy force_publish --dataset sales_daily` | [Chapter 21](21-policy-autonomy.html) |
| Autonomy ladder | `swarmpipe/governance/autonomy.py` `AutonomyManager` | `sp autonomy list` | [Chapter 21](21-policy-autonomy.html) |
| Approvals | `swarmpipe/governance/approvals.py` `ApprovalService` | dashboard **Approvals** | [Chapter 21](21-policy-autonomy.html) |
| Audit chain | `swarmpipe/governance/audit.py` `AuditLog` | `sp audit verify` | [Chapter 22](22-audit-evidence.html) |
| Evidence packs | `swarmpipe/governance/evidence.py` `EvidenceService` | `sp evidence <incident_id>` | [Chapter 22](22-audit-evidence.html) |
| Kill switch | `swarmpipe/governance/killswitch.py` `KillSwitch` | `sp killswitch on --reason "drill" --as oncall` | [Chapter 22](22-audit-evidence.html) |

## Part VII - Operations

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| Tracing | `swarmpipe/observability/tracing.py` `Tracer` | `sp trace <ident>` | [Chapter 23](23-observability.html) |
| Metrics | `swarmpipe/observability/metrics.py` `Metrics` | `sp metrics --prom` | [Chapter 23](23-observability.html) |
| SLO service | `swarmpipe/signals.py` `SLOService` | `sp slo` | [Chapter 23](23-observability.html) |
| Cost attribution | `swarmpipe/llm/gateway.py` `chat` | dashboard **Cost & Metrics** | [Chapter 24](24-cost-capacity.html) |
| Tenant quotas | `config/swarmpipe.yaml` | dashboard **Cost & Metrics** | [Chapter 24](24-cost-capacity.html) |
| LLM profiles | `config/swarmpipe.yaml` | `sp llm use offline` | [Chapter 25](25-model-strategy.html) |
| Health routes | `swarmpipe/web/api.py` `healthz` | `/healthz` | [Chapter 26](26-operations.html) |
| Readiness route | `swarmpipe/web/api.py` `readyz` | `/readyz` | [Chapter 26](26-operations.html) |
| Scheduler monitors | `swarmpipe/runtime/scheduler.py` `Scheduler` | `sp tick --scheduler` | [Chapter 26](26-operations.html) |
| Retention | `swarmpipe/runtime/scheduler.py` `retention` | `sp maintenance retention` | [Chapter 26](26-operations.html) |
| Online backup | `swarmpipe/cli.py` `maintenance` | `sp maintenance backup` | [Chapter 26](26-operations.html) |

## Part VIII - Capstone

| Concept | Where in SwarmPipe | How to see it | Chapter |
|---|---|---|---|
| AI feature PRD | `docs/PRD_AND_EVAL_SPEC.md` | read the PRD before coding | [Chapter 27](27-capstone.html) |
| Scenario extension | `swarmpipe/scenarios.py` `Scenario` | `sp scenarios list` | [Chapter 27](27-capstone.html) |
| Catalog action extension | `swarmpipe/tools/actions.py` `ACTIONS` | dashboard **Agents & Tools** | [Chapter 27](27-capstone.html) |
| Policy entry | `config/policies.yaml` | `sp policy request_resend --dataset sales_daily` | [Chapter 27](27-capstone.html) |
| Final verification | `tests/test_e2e.py` | `python -m pytest` | [Chapter 27](27-capstone.html) |

