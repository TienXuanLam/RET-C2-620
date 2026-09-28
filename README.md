# RET-C2-620 — RetailGiftRegistryFulfillmentComplianceQAAgent

> **Category**: Cat 2 (ChatAgent + VectorRAG — gift registry Q&A with APPI 2026 / Consumer Contract Act compliance annotation)
> **Industry**: RET
> **Inherits**: AgentBaseGraph (Level 1 direct)
> **Status**: Draft

## Overview

Conversational Q&A agent for Japanese retail gift registry programs. Classifies a
natural-language question's intent, retrieves relevant policy chunks from a registry
knowledge base (VectorRAG), optionally checks real-time item availability, and returns a
structured answer annotated with APPI 2026 Article 23 (third-party personal-data disclosure)
and Consumer Contract Act Article 8 compliance notes, a fulfillment routing recommendation,
and an escalation flag for questions requiring human legal/privacy review. Automates a task
that today requires store staff to manually cross-reference 2–3 systems and apply APPI 2026
rules (enforced April 2026) that many call-center scripts have not caught up with.

## Why This Template Exists

This template is **one production unit of the Agent 1000 line** — not a standalone
deliverable. The project goal is to make us *capable of producing* 1,000+ templates
per FY26 September capacity. That capability is what unlocks AGENTIC STAR as the
global de facto platform for enterprise agent development.

Of every design decision in this template, ask:

> "Does this make the next template faster, or only this one better?"

If your answer is the latter, reconsider — generalize at Level 2, or refactor the
pattern. A template that is technically beautiful but cannot be replicated quickly
across industries fails the mission. See the project charter for the three-layer
vision and full purpose context.

## Requirements

- Python 3.11+
- Three knowledge-base instances for production go-live: registry policy, APPI 2026,
  Consumer Contract Act (each implementing `similarity_search(query, k) -> list[dict]`)
- Optional: an LLM client for step 6 Q&A generation, and a real-time inventory tool
  implementing `get_status(registry_id, item_id)`

### Behaviour without the platform

Without any of `registry_kb`/`appi_kb`/`cca_kb`/`inventory_tool`/`llm` configured, the
standalone server still boots and every invocation reaches `status=success` — retrieval
returns no chunks, inventory status degrades to "unavailable," and step 6 falls back to a
deterministic, KB-grounded answer (empty context yields a "no relevant policy information"
notice). No secret is required for this template.

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest tests/ -v
```

## Project Structure

```
config/
  agent.yaml          # AgentRegistry manifest
  config.yaml         # runtime parameters
deploy/
  invoke_payload.json # sample /invoke payload
  local-stg.yml       # local STG-equivalent deploy config
src/
  api/server.py       # standalone HTTP entry point
  graph/graph.py       # AgentBaseGraph wiring
  nodes/               # pre_process / main / post_process
  schemas/state.py     # flat TypedDict state
  services/            # pure domain logic (8-step spec helpers)
tests/
  unit/                # per-node/per-service unit tests
  proof_of_boundary/   # framework-contract boundary tests
docs/
  02_design.md         # design specification
  03_test_spec.md      # test specification
cli.py                 # Marketplace Pod entrypoint
```

## Customising

- `config/config.yaml`: `max_retry`, `memory_enabled`, `timeout_s`.
- Pass `registry_kb`/`appi_kb`/`cca_kb`/`inventory_tool`/`llm` instances via
  `RetailGiftRegistryFulfillmentComplianceQAAgent(config={...})` at construction, or wire
  them into `src/api/server.py`'s config for a standalone deployment.

## License

MIT — see [LICENSE](LICENSE).

## Status of this repository

This is a template under active development within the Agent 1000 line. It is
provided as-is, with no warranty, and may change without notice.
