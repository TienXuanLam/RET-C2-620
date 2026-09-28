# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `RetailGiftRegistryFulfillmentComplianceQAAgent`
- **L1 Base**: `AgentBaseGraph`
- **Pattern**: Cat 2 — flat backbone (outer `AgentBaseGraph`, no inner subgraph); ChatAgent + VectorRAG
- **Three-Layer Separation**:
  - State: flat TypedDict composition (no Pydantic — msgpack incompatible)
  - Node: L1 inheritance (Template Method: `execute(self, state: dict) -> dict` override only)
  - Graph: composition (`register_nodes()` for node substitution)

## Architecture Overview

`AgentBaseGraph` exposes exactly three domain slots — `pre_process`, `main`, `post_process`
(`compile()` raises `MissingNodeError` if any is absent; there is no mechanism to register a
fourth domain slot). The architect's 8-step spec (source proposal Technical Spec section,
2026-07-04) is implemented as **8 pure-Python step helpers** — plain classes with an
`execute(state)` method (deliberately not named `run()` — see the S-1 invoke-chain gate note
below), not `BaseNode` subclasses — invoked in sequence from inside the three real
`FunctionNode` slots. This keeps every step independently unit-testable while guaranteeing
S-1/S-2/S-3 are the *real* framework gates running on `__call__()`, not a second parallel gate
system that could silently diverge from the enforced one.

> **Naming note — `gate-invoke-chain` (S-1):** step helper methods are named `execute()`, not
> `run()`. The CI gate that blocks `self.<x>.run()` (agent-class calling `.run()` instead of
> `.invoke()` on a sub-agent, bypassing S-1) matches on `self\.[_a-z][_a-z0-9]*\.run(` and does
> not distinguish a real sub-agent call from an unrelated same-named method on a plain
> pure-Python helper. Since `self._retrieve`/`self._generate` are `HybridRetrieveNode`/
> `ResponseGenerateNode` instances (not `BaseNode`/agent instances), calling them is not a
> gated operation — but the method is still named `execute()` to stay clear of the pattern
> entirely rather than rely on the gate's regex not matching.

```
AgentBaseGraph (src/graph/graph.py):
  InitializeNode      [framework default]
  PreProcessNode      [VERIFIED_EXTERNAL — real FunctionNode / real S-1,S-2 gate]
    ├─ InputValidateNode.execute(state)      step 1 — S-1 input validation
    └─ QueryClassifyNode.execute(state)      step 2 — 6-class intent classification
  MainNode            [VERIFIED_EXTERNAL — real FunctionNode]
    ├─ HybridRetrieveNode.execute(state)             step 3 — 3-KB retrieval
    ├─ APPIDisclosureGateNode.execute(state)         step 4 — ⚠️ APPI hard block
    ├─ ConsumerContractActCheckNode.execute(state)   step 5 — ⚠️ CCA escalation-only
    └─ ResponseGenerateNode.execute(state)           step 6 — LLM Q&A generation
  PostProcessNode     [VERIFIED_EXTERNAL — real FunctionNode / real S-3 gate]
    ├─ ComplianceAnnotateNode.execute(state)  step 7 — structured compliance notes
    └─ SecurityGateOutputNode.execute(state)  step 8 — S-3 PII output gate
  FinalizeNode        [framework default]
```

### Node Configuration

| Slot (real `FunctionNode`) | Location | required_trust_level | Step helpers invoked (in order) |
|---|---|---|---|
| `pre_process` | src/nodes/pre_process_node.py | VERIFIED_EXTERNAL | 1. `InputValidateNode` 2. `QueryClassifyNode` |
| `main` | src/nodes/main_node.py | VERIFIED_EXTERNAL | 3. `HybridRetrieveNode` 4. `APPIDisclosureGateNode` 5. `ConsumerContractActCheckNode` 6. `ResponseGenerateNode` |
| `post_process` | src/nodes/post_process_node.py | VERIFIED_EXTERNAL | 7. `ComplianceAnnotateNode` 8. `SecurityGateOutputNode` |

Step helper classes live in `src/services/` (pure domain logic, no `agenticstar`/framework
security-gate imports — they receive and return the same flat `dict` shape as `execute()`
would, so the owning `FunctionNode.execute()` is a thin sequential dispatcher).

### Step Helper Detail

| # | Step helper | Responsibility |
|---|---|---|
| 1 | `InputValidateNode` | Query non-empty, ≤512 tokens; `registry_id` format check when provided; `user_role` ∈ `{customer, staff, ec_support}`; sets `status=ERROR` on failure (S-1 domain-level check, in addition to the framework's node-level S-1 trust gate) |
| 2 | `QueryClassifyNode` | Intent classification, checked in **explicit priority order** — `COMPLIANCE_CCA` and `COMPLIANCE_APPI` are matched before the generic intents (`PRIVACY_SETTINGS`, `FULFILLMENT_ROUTING`, `AVAILABILITY`), so a query mixing a compliance keyword with a generic one (e.g. "cancel this order and check inventory") is never classified as the generic intent — this would otherwise silence the mandatory APPI/CCA annotation in steps 4–5; entity extraction (`registry_id`, `item_id`, `party`); trust-level assignment (`staff→elevated`, `customer/ec_support→standard`); keyword-based `pii_in_scope` flag, OR-combined with step 1's raw-input scan (dual trigger — see Risk #3) |
| 3 | `HybridRetrieveNode` | Queries **3 separate knowledge bases** and merges top-K chunks: (a) registry policy KB (fulfillment SLAs, store pickup rules, OOS handling), (b) APPI 2026 KB (Article 23 consent-scope rules), (c) Consumer Contract Act KB (Article 8 clause definitions) |
| 4 | `APPIDisclosureGateNode` | ⚠️ **Most critical.** Triggered by `intent=COMPLIANCE_APPI` OR `pii_in_scope=true` (dual trigger — Risk #3). Runs the APPI Article 23 consent-scope check. If `trust_level=standard` and disclosure is out-of-scope or unverifiable → **hard block**: sets `appi_blocked=true`, strips any registrant PII from the working answer draft *before* `ResponseGenerateNode` runs — the LLM is never given ungated PII to reason over |
| 5 | `ConsumerContractActCheckNode` | ⚠️ **Escalation-only — never rules.** Triggered by `intent=COMPLIANCE_CCA`. Always sets `escalation_flag=true` and a fixed non-committal notice; does not synthesize any legal conclusion, does not call the LLM for this determination |
| 6 | `ResponseGenerateNode` | LLM Q&A generation from retrieved chunks + (optional) inventory status, constrained by `appi_blocked`/`trust_level` from step 4. If CCA escalation is active, appends the escalation notice instead of attempting an answer to the legal question |
| 7 | `ComplianceAnnotateNode` | Assembles the structured `compliance_notes` list (`{law, note}`) from steps 4–5's findings; resolves `fulfillment_route` when `intent=FULFILLMENT_ROUTING` |
| 8 | `SecurityGateOutputNode` | S-3 belt-and-suspenders: independently scans the final answer text for address/name patterns; redacts and forces `escalation_flag=true` if anything slipped through steps 4–6. This is the same enforcement invoked from `PostProcessNode._extra_security_gate_output()`, not a separate mechanism |

### Data Flow

```
START
  → InitializeNode
  → PreProcessNode (VERIFIED_EXTERNAL, real S-1/S-2 gate)
       1. InputValidateNode  → validated_input flag / ERROR short-circuit
       2. QueryClassifyNode  → intent, entities (JSON-str), trust_level, pii_in_scope
  → MainNode (VERIFIED_EXTERNAL)
       3. HybridRetrieveNode        → retrieved_chunks (JSON-str) from 3 KBs
       4. APPIDisclosureGateNode    → appi_blocked, appi_note
       5. ConsumerContractActCheckNode → escalation_flag (forced true on COMPLIANCE_CCA), cca_note
       6. ResponseGenerateNode      → answer
  → PostProcessNode (VERIFIED_EXTERNAL, real S-3 gate)
       7. ComplianceAnnotateNode    → compliance_notes (JSON-str), fulfillment_route
       8. SecurityGateOutputNode    → answer (final, PII-scanned), escalation_flag (final)
       S-4 audit log: query_intent, registry_id hash, user_role, pii_in_scope,
         appi_blocked, escalation_flag, timestamp, invocation_id
       → result (JSON-str), formatted_output (str)
  → FinalizeNode
END
```

> **Scope boundary** (proposal §4): registry creation/modification, direct POS/inventory write
> operations, multi-turn conversation history persistence, payment processing, and definitive
> legal rulings on Consumer Contract Act applicability are explicitly out of scope. Each
> invocation is stateless across calls.

> **`advisory_only` guarantee** (architect spec): this agent never issues a binding legal
> determination. Every compliance-adjacent output (`appi_note`, `cca_note`, `compliance_notes`)
> is phrased as guidance for human review, not a ruling. `ConsumerContractActCheckNode` always
> escalates rather than concluding. `config/agent.yaml` declares `advisory_only: true` as a
> documented runtime contract flag consumed by the calling orchestrator (informational —
> enforcement is the deterministic escalation-only behavior of step 5, not a framework switch).

## State Definition

File: `src/schemas/state.py` — extends `AgentState` (flat TypedDict, ADR-005).

| Field | Type | Producer (step) | Consumer | ADR-005 note |
|---|---|---|---|---|
| `intent` | `Optional[str]` | 2. QueryClassifyNode | 4,5,6,7 | one of the 6 intent classes |
| `entities` | `Optional[str]` | 2. QueryClassifyNode | 3,6 | **JSON-str** — `{registry_id, item_id, party}` |
| `trust_level` | `Optional[str]` | 2. QueryClassifyNode | 4,6,8 | `"elevated"` (staff) / `"standard"` (customer, ec_support) — domain gating flag, distinct from framework `caller_trust_level` |
| `pii_in_scope` | `Optional[bool]` | 2. QueryClassifyNode | 4 | keyword-based risk flag; independent second trigger for step 4 (Risk #3) |
| `retrieved_chunks` | `Optional[str]` | 3. HybridRetrieveNode | 6 | **JSON-str** — merged top-K chunks tagged by source KB (`registry`\|`appi`\|`cca`) |
| `appi_blocked` | `Optional[bool]` | 4. APPIDisclosureGateNode | 6,7,8 | true when the APPI consent-scope check hard-blocks registrant PII disclosure |
| `appi_note` | `Optional[str]` | 4. APPIDisclosureGateNode | 7 | APPI Article 23 consent-scope finding (advisory wording only) |
| `cca_note` | `Optional[str]` | 5. ConsumerContractActCheckNode | 7 | fixed non-committal Consumer Contract Act Article 8 notice |
| `answer` | `Optional[str]` | 6. ResponseGenerateNode (draft) → 8. SecurityGateOutputNode (final) | PostProcessNode output | LLM-generated Q&A answer text, PII-scanned at step 8 |
| `compliance_notes` | `Optional[str]` | 7. ComplianceAnnotateNode | PostProcessNode output | **JSON-str** — list of `{law, note}` merged from `appi_note`/`cca_note` |
| `escalation_flag` | `Optional[bool]` | 5. ConsumerContractActCheckNode (may be forced by 8) | PostProcessNode output | true when a Consumer Contract Act question or an S-3 catch requires human review |
| `fulfillment_route` | `Optional[str]` | 7. ComplianceAnnotateNode | PostProcessNode output | `online_direct_ship` \| `instore_pickup` \| `cross_store_transfer` \| `not_available` \| `None` |
| `result` | `Optional[str]` | PostProcessNode | FinalizeNode / caller | **JSON-str** — full structured response |
| `formatted_output` | `Optional[str]` | PostProcessNode | caller | human-readable answer + compliance notes |

> **State Constraints (mandatory):**
> - Flat TypedDict only — no Pydantic, dataclass, or arbitrary objects (msgpack incompatible)
> - No credentials/JWT/API keys in state (checkpoint DB leakage risk)
> - InvocationContext via `config["configurable"]` only — never stored in state
> - Dict/list fields (`entities`, `retrieved_chunks`, `compliance_notes`): `Optional[str]` +
>   `json.dumps` (producer) / `json.loads` (consumer) [ADR-005]
> - **Registrant PII (address, contact, name) is never stored as a discrete state field.** It
>   may transiently appear inside the `answer` draft between steps 6 and 8; the audit log
>   persists only a `registry_id` **hash**, never plaintext registrant data (S-2).

## Security Design

| Gate | Location | Level | Implementation |
|---|---|---|---|
| S-1 | PreProcessNode (real gate) + step 1 `InputValidateNode` (domain check) | VERIFIED_EXTERNAL | Framework S-1 trust gate on `__call__()`; domain-level check inside `execute()`: query non-empty/≤512 tokens, `registry_id` format, `user_role` allowlist |
| S-2 | PreProcessNode | VERIFIED_EXTERNAL | `_extra_security_gate_input()` scans raw `user_input` for PII keywords *before* step 1 validation runs; sets `state["_pii_keyword_detected"]`, which `execute()` OR-combines with step 2's own keyword scan on the validated query into the single `pii_in_scope` flag (dual trigger — neither scan alone is authoritative). Audit log persists only a `registry_id` hash — never plaintext registrant data |
| S-3 | PostProcessNode (real gate) + step 8 `SecurityGateOutputNode` | VERIFIED_EXTERNAL | `_extra_security_gate_output()` invokes the same PII pattern scan as step 8; redacts and forces `escalation_flag=true` if registrant PII is found in the final answer — belt-and-suspenders on top of step 4's proactive block |
| S-4 | All domain nodes | — | `emit_trace_event()` in every `execute()`: `input_validated`/`intent_classified` (PreProcessNode), `kb_retrieved`/`appi_gate_evaluated`/`cca_escalated`/`response_generated` (MainNode), `response_assembled` (PostProcessNode) — payload includes `registry_id` hash, never plaintext PII |

> **S-2/S-3 hook rule (ADR-017):** All three real slot nodes are `FunctionNode` subclasses.
> Framework `@final` gates run automatically. Extend via `_extra_security_gate_input()` /
> `_extra_security_gate_output()` only. **MUST NOT override `_security_gate_input()` or
> `_security_gate_output()` directly** — raises `TypeError` at class definition.

> **S-4 emit rule:** Do NOT emit `node_start` / `node_complete` / `node_error` —
> `BaseNode.__call__()` emits these automatically. Custom events only.

### PII risk — design decisions (proposal §11, Risks #1–#3)

1. **Risk #1 (High) — registrant PII leaked to a standard-trust caller.** Mitigated at two
   independent layers, both real: (a) step 4 `APPIDisclosureGateNode` proactively strips/blocks
   registrant PII from the working draft *before* `ResponseGenerateNode` (step 6) ever runs —
   the LLM is not trusted to withhold PII on prompt instruction alone; (b) step 8
   `SecurityGateOutputNode`, invoked from the real `PostProcessNode._extra_security_gate_output()`,
   independently re-scans the final answer and redacts + escalates if anything slipped through.
   **Mandatory PoB test**: standard-trust caller asks for the registrant's address → assert no
   PII in `answer`, `appi_blocked=true`, and a consent-verification instruction is present.
2. **Risk #2 (Medium) — inventory tool leaks registrant metadata.** Step 3 `HybridRetrieveNode`
   (and the optional inventory tool call inside step 6) applies a strict field allowlist
   (`in_stock`, `out_of_stock`, `on_order`, `discontinued`, `estimated_restock`); any
   non-allowlisted field is stripped before `ResponseGenerateNode` sees it.
3. **Risk #3 (Medium) — intent misclassification silences the APPI annotation.** Step 4 triggers
   on `intent=COMPLIANCE_APPI` **OR** `pii_in_scope=true` (set independently by step 2's keyword
   scan) — a dual trigger, so misclassification alone cannot suppress the APPI gate.
4. **Consumer Contract Act — escalation is unconditional.** Step 5 never attempts to resolve a
   CCA question; `intent=COMPLIANCE_CCA` always yields `escalation_flag=true` and the fixed
   non-committal notice, satisfying the `advisory_only` guarantee.

## Framework Utilization

### Shared Components Used
- [x] InvocationContext (correlation_id, session_id, permissions, credential handle) — via `config["configurable"]`
- [x] ConnectionPolicy (retry/timeout strategy) — for LLM calls and optional inventory tool call in MainNode
- [x] SecurityViolationError — raised by framework S-1 trust gate on insufficient `caller_trust_level`
- [x] S-2: `_extra_security_gate_input()` — PII/consent keyword scan in PreProcessNode
- [x] S-3: `_extra_security_gate_output()` — delegates to step 8 `SecurityGateOutputNode` logic
- [x] S-4: `emit_trace_event()` — at least one domain-specific event in each `execute()`

> **S-2/S-3 gate behaviour by node type (ADR-017):**
> - `FunctionNode` subclass → framework `@final` gate always runs automatically;
>   extend via `_extra_security_gate_input()` / `_extra_security_gate_output()` only
> - `GraphNode` / `RemoteAgentNode` → deliberate no-op (upstream or remote node's gate already applied)
> - Custom `BaseNode` subclass → must implement `_security_gate_input()` and
>   `_security_gate_output()` directly (`@abstractmethod` — omission raises `TypeError` at instantiation)

### Composition Pattern

- **Pattern**: Standalone (no GraphNode/RemoteAgentNode) — 8 step helpers are pure-Python
  classes in `src/services/`, not LangGraph nodes; only 3 real `FunctionNode`s are registered
- **L1 Base**: `AgentBaseGraph`
- **Error propagation strategy**: propagate — node failures surface to the framework backbone;
  the optional inventory tool call inside step 6 degrades gracefully in-node, it does not raise

## Import Isolation Confirmation

- [x] Template does NOT import `agenticstar-platform` SDK (Level 0)
- [x] Import targets: `framework/` and `shared/` only
- [x] No `agents/base/` imports (L1 direct inheritance — no L2)

## Class Name Consistency

| Artifact | Value |
|---|---|
| `src/graph/graph.py` | `class RetailGiftRegistryFulfillmentComplianceQAAgent(AgentBaseGraph)` |
| `config/agent.yaml` | `class: "RetailGiftRegistryFulfillmentComplianceQAAgent"` |
| `src/api/server.py` | `from src.graph.graph import RetailGiftRegistryFulfillmentComplianceQAAgent` |

## Design Decision Record

| Decision | Option A | Option B | Chosen | Rationale |
|---|---|---|---|---|
| L1 base type | AgentBaseGraph | AutonomousBaseGraph | AgentBaseGraph | Cat 2 fixed pipeline; no autonomous loop needed |
| 8-step realization | 8 real `BaseNode`s (extra LangGraph nodes) | 8 pure-Python step helpers inside 3 real `FunctionNode`s | Pure-Python step helpers | `AgentBaseGraph` only exposes 3 domain slots; a parallel node system running outside `__call__()` would not be covered by the real S-1/S-2/S-3 gates and would misrepresent security coverage |
| Composition pattern | Standalone (flat backbone) | GraphNode + inner BaseGraph | Standalone | Pipeline is linear; nested graph adds complexity without benefit given only 3 real nodes |
| Intent classification | Rule-based only | LLM zero-shot | Deterministic rule + LLM assist | Compliance triggers must be deterministic for legal defensibility; LLM assists only on ambiguous phrasing |
| APPI/CCA annotation | LLM-generated | Deterministic rule application | Deterministic rule application | Rule parameters sourced directly from statute; CCA is escalation-only by design (`advisory_only`) |
| PII gating strategy | Prompt-only | Proactive block (step 4) + independent output scan (step 8) | Both, independent | Risk #1 is High; prompt constraints alone are insufficient |
| Inventory tool call | Required | Optional with graceful fallback | Optional | Agent must answer from KB policy alone when the inventory tool is not configured |
| Error propagation | Propagate | Handle + partial output | Propagate | Partial outputs risk silently incorrect compliance guidance |
