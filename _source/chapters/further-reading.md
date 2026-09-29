Every URL in this appendix was fetched successfully before inclusion. The notes say why the reference matters and which chapter it supports.

## Agents and multi-agent patterns

| Reference | Why read it | Supports |
|---|---|---|
| [Anthropic, "Building effective agents"](https://www.anthropic.com/engineering/building-effective-agents) | Practical patterns for agents, workflows and when not to over-agenticize. | [Chapter 1](01-llm-to-agent.html), [Chapter 8](08-why-multi-agent.html) |
| [Anthropic, "How we built our multi-agent research system"](https://www.anthropic.com/engineering/multi-agent-research-system) | Production lessons from a real multi-agent system, including context and token trade-offs. | [Chapter 8](08-why-multi-agent.html), [Chapter 24](24-cost-capacity.html) |
| [Why Do Multi-Agent LLM Systems Fail?](https://arxiv.org/abs/2503.13657) | A failure taxonomy for multi-agent coordination and verification. | [Chapter 14](14-failure-modes.html) |

## Protocols: MCP and A2A

| Reference | Why read it | Supports |
|---|---|---|
| [Model Context Protocol specification](https://modelcontextprotocol.io/specification/2025-06-18) | The protocol behind portable tool and data-source integration for model clients. | [Chapter 10](10-communication-protocols.html) |
| [A2A Protocol documentation](https://a2a-protocol.org/latest/) | The agent-to-agent protocol used for discovery and task exchange. | [Chapter 10](10-communication-protocols.html) |

## Context, retrieval and prompt-injection defense

| Reference | Why read it | Supports |
|---|---|---|
| [Defending Against Indirect Prompt Injection Attacks With Spotlighting](https://arxiv.org/abs/2403.14720) | The paper behind spotlighting untrusted data in prompts. | [Chapter 11](11-context-memory.html), [Chapter 19](19-threat-model.html) |
| [Simon Willison, "The lethal trifecta for AI agents"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) | A crisp way to reason about private data, untrusted content and external communication. | [Chapter 19](19-threat-model.html) |

## Durable execution

| Reference | Why read it | Supports |
|---|---|---|
| [Temporal, "What is Temporal?"](https://docs.temporal.io/temporal) | Production-grade durable execution concepts beyond SwarmPipe's local teaching engine. | [Chapter 12](12-durable-execution.html), [Chapter 26](26-operations.html) |

## Evaluation and judges

| Reference | Why read it | Supports |
|---|---|---|
| [tau-bench: A Benchmark for Tool-Agent-User Interaction](https://arxiv.org/abs/2406.12045) | The benchmark that popularized pass^k reliability framing for tool agents. | [Chapter 15](15-eval-fundamentals.html) |
| [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://arxiv.org/abs/2306.05685) | Background on model judges and why calibration matters. | [Chapter 16](16-llm-judge.html) |

## Security: OWASP, Agentic AI and the lethal trifecta

| Reference | Why read it | Supports |
|---|---|---|
| [OWASP GenAI Security Project](https://genai.owasp.org/) | The umbrella project for LLM and agentic application security guidance. | [Chapter 19](19-threat-model.html) |
| [OWASP Agentic AI Threats and Mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/) | A threat-model-based guide to emerging agentic risks. | [Chapter 19](19-threat-model.html), [Chapter 21](21-policy-autonomy.html) |
| [OWASP Top 10 for Large Language Model Applications](https://owasp.org/projects/top-10-for-large-language-model-applications) | The LLM application risk list that underpins many SwarmPipe controls. | [Chapter 19](19-threat-model.html) |

## Observability, lineage and SRE

| Reference | Why read it | Supports |
|---|---|---|
| [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) | Attribute conventions for GenAI spans, metrics and events. | [Chapter 23](23-observability.html) |
| [OpenTelemetry GenAI semantic conventions repository](https://github.com/open-telemetry/semantic-conventions-genai) | The moved, actively maintained GenAI semantic-convention source. | [Chapter 23](23-observability.html) |
| [OpenLineage documentation](https://openlineage.io/docs/) | The open model for job, run and dataset lineage metadata. | [Chapter 7](07-publishing-lineage.html) |
| [Google SRE Workbook, "Implementing SLOs"](https://sre.google/workbook/implementing-slos/) | A practical SLO process for reliability targets and error budgets. | [Chapter 23](23-observability.html), [Chapter 26](26-operations.html) |
| [Google SRE Book, "Monitoring Distributed Systems"](https://sre.google/sre-book/monitoring-distributed-systems/) | Guidance on what should page a human and what should not. | [Chapter 23](23-observability.html), [Chapter 26](26-operations.html) |
