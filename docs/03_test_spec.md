# Test Specification

## Test Strategy
- Coverage target: 100% of domain branches in `src/services/` and `src/nodes/`
- Test types: Unit (per step helper + per node) / Proof-of-Boundary (framework contract + PII/compliance guarantees)

## Framework Compliance Tests (Mandatory)

| TC-ID | Test | Expected Result |
|-------|------|----------------|
| TC-01 | State contract: flat TypedDict, no Pydantic/dataclass | `State` fields are `Optional[str]`/`Optional[bool]` primitives only |
| TC-02 | `required_trust_level` enforced on all 3 real nodes | Declaration: `PreProcessNode`, `MainNode`, `PostProcessNode` all declare `TrustLevel.VERIFIED_EXTERNAL`. Enforcement: each node's `test_trust_gate_blocks_anonymous` calls the real `__call__()` gate entry point (not `execute()`) with `caller_trust_level=ANONYMOUS` and asserts `status=error`; `test_trust_gate_allows_verified_external` asserts the matching-trust case still succeeds. This is what actually proves the framework's S-1 gate — not just the class attribute — is enforced |
| TC-03 | S-2: `_extra_security_gate_input()` non-trivial (PreProcessNode) | Raw PII/consent keyword scan executes on `user_input`; never raises (returns state) |
| TC-04 | S-3: `_extra_security_gate_output()` present and delegates to step 8 (PostProcessNode) | Hook exists; `FunctionNode.@final` gate is not overridden directly |
| TC-05 | S-4: at least one domain `emit_trace_event()` per `execute()` | `PreProcessNode` emits `input_validated`+`intent_classified`; `MainNode` emits `kb_retrieved`+`appi_gate_evaluated`(+`cca_escalated`)+`response_generated`; `PostProcessNode` emits `response_assembled` |
| TC-06 | ⚠️ APPI hard block (step 4) and CCA escalation-only (step 5) — domain business logic | See "Compliance Gate Tests" below — these are the template's core correctness guarantee |

## Compliance Gate Tests (domain business logic — TC-06 detail)

| Case | Input | Expected Result |
|---|---|---|
| APPI dual trigger — intent | `intent=COMPLIANCE_APPI`, `pii_in_scope=False`, `trust_level=standard` | `appi_blocked=True`; PII-pattern chunks stripped from `safe_chunks` |
| APPI dual trigger — keyword flag | `intent=GENERAL_POLICY` (misclassified), `pii_in_scope=True`, `trust_level=standard` | `appi_blocked=True` — Risk #3: misclassification does not silence the gate |
| APPI — elevated trust (staff) | `intent=COMPLIANCE_APPI`, `trust_level=elevated` | `appi_blocked=False`; in-scope advisory note returned, no PII stripped |
| APPI — no trigger | `intent=AVAILABILITY`, `pii_in_scope=False` | `appi_blocked=False`, `appi_note=None`, `safe_chunks` unchanged |
| CCA — always escalates | `intent=COMPLIANCE_CCA` | `escalation_flag=True`; `cca_note` is the fixed non-committal notice; no legal ruling text generated |
| CCA — no trigger | `intent=AVAILABILITY` | `escalation_flag=False`, `cca_note=None` |
| `pii_in_scope` dual trigger — raw scan catches what validated scan misses | Raw `user_input` contains a PII keyword; `QueryClassifyNode.execute()` (mocked) returns `pii_in_scope=False` | `PreProcessNode.execute()` still returns `pii_in_scope=True` — the OR-combination in `execute()` does not depend on both scans agreeing |

## Proof-of-Boundary Tests (Mandatory)

| PB-ID | Boundary | Test | Expected Result |
|-------|----------|------|----------------|
| PB-01 | S-1 trust gate / injection resistance | Standard-trust caller crafts a query attempting to force `trust_level=elevated` or bypass `InputValidateNode` via malformed `user_role`/`registry_id` | Framework S-1 gate + step 1 domain validation both reject; `status=ERROR`; no privilege escalation |
| PB-02 | S-3 PII output block | Standard-trust caller asks directly for the registrant's address/contact (`"What is the registrant's address?"`) | Final `answer` (post step 8) contains no PII pattern match; `appi_blocked=True`; a consent-verification instruction is present instead of the address |
| PB-03 | Consumer Contract Act escalation-only | Query with `intent=COMPLIANCE_CCA` (e.g. cancellation-rights question) | `escalation_flag=True` unconditionally; response never asserts contract enforceability; `escalation_instruction` present in final `result` |
| PB-04 | `advisory_only` enforcement end-to-end | Full pipeline invocation with `intent=COMPLIANCE_APPI` and `intent=COMPLIANCE_CCA` across both `trust_level` values | No code path produces a binding legal ruling; every compliance-adjacent note is advisory-worded; `ConsumerContractActCheckNode` never calls the LLM for a CCA determination |

## Test Execution Summary
- Execution date: _(fill in at CI run)_
- Total tests: _(fill in at CI run)_
- Pass: / Fail: / Skip:
- Coverage: ___%
