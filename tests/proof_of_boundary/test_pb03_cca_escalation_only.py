# PB-03: Consumer Contract Act escalation-only boundary (proposal §11 Risk #5;
# advisory_only guarantee). intent=COMPLIANCE_CCA must ALWAYS escalate and
# must NEVER produce a legal ruling / enforceability assertion — across the
# full step 5 -> step 6 -> step 7 chain.
# See docs/02_design.md "advisory_only guarantee".

from src.services.compliance_annotate_service import ComplianceAnnotateNode
from src.services.compliance_gate_service import ConsumerContractActCheckNode
from src.services.response_generate_service import ResponseGenerateNode

_RULING_LANGUAGE = ["unenforceable", "you are entitled to", "you are not entitled to", "this clause is void"]


class TestPB03ConsumerContractActEscalationOnly:
    def test_cca_intent_unconditionally_escalates(self):
        result = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        assert result["escalation_flag"] is True

    def test_end_to_end_response_never_asserts_enforceability(self):
        cca = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        generated = ResponseGenerateNode(llm=None).execute(
            query="Can the store force a substitute item without my consent?",
            safe_chunks=[{"chunk": "OOS substitution policy details."}],
            inventory_status=None,
            trust_level="standard",
            appi_blocked=False,
            escalation_flag=cca["escalation_flag"],
            cca_note=cca["cca_note"],
        )
        lowered = generated["answer"].lower()
        for phrase in _RULING_LANGUAGE:
            assert phrase not in lowered, f"response must not contain ruling language: {phrase!r}"
        assert "escalated" in lowered

    def test_llm_is_never_invoked_for_cca_determination(self):
        calls = []

        class _SpyLLM:
            def complete(self, messages, **kwargs):
                calls.append(messages)
                return {"content": "This clause is unenforceable."}  # would be a ruling if ever reached

        cca = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        result = ResponseGenerateNode(llm=_SpyLLM()).execute(
            query="Is this cancellation clause enforceable?",
            safe_chunks=[],
            inventory_status=None,
            trust_level="standard",
            appi_blocked=False,
            escalation_flag=cca["escalation_flag"],
            cca_note=cca["cca_note"],
        )
        assert calls == [], "LLM must not be called when a CCA escalation is active"
        assert result["answer"] == cca["cca_note"]

    def test_escalation_instruction_present_in_final_compliance_notes(self):
        cca = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        annotated = ComplianceAnnotateNode.execute(
            appi_note=None, cca_note=cca["cca_note"], intent="COMPLIANCE_CCA", inventory_status=None,
        )
        laws = [n["law"] for n in annotated["compliance_notes"]]
        assert "Consumer Contract Act Article 8" in laws

    def test_routine_oos_availability_question_does_not_escalate(self):
        # Risk #5 (Low): general availability questions must not over-trigger CCA.
        result = ConsumerContractActCheckNode.execute(intent="AVAILABILITY")
        assert result["escalation_flag"] is False
