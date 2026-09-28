# PB-02: S-3 PII output block — mandatory (proposal §11 Risk #1, High).
# A standard-trust caller who directly asks for the registrant's address must
# receive an answer with NO PII, plus a consent-verification instruction, and
# appi_blocked=True. Verified end-to-end across step 4 (proactive block) and
# step 8 (independent belt-and-suspenders re-scan).
# See docs/02_design.md "PII risk — design decisions" Risk #1.

from src.services.compliance_annotate_service import SecurityGateOutputNode
from src.services.compliance_gate_service import APPIDisclosureGateNode, contains_pii
from src.services.response_generate_service import ResponseGenerateNode

_REGISTRANT_ADDRESS_CHUNK = {
    "chunk": "Registrant address on file: 〒100-0001 東京都千代田区1-1-1",
    "source_kb": "registry",
}


class TestPB02StandardTrustCallerCannotObtainRegistrantPii:
    def test_step4_strips_pii_chunk_for_standard_trust(self):
        result = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=True, trust_level="standard",
            retrieved_chunks=[_REGISTRANT_ADDRESS_CHUNK],
        )
        assert result["appi_blocked"] is True
        assert result["safe_chunks"] == []

    def test_end_to_end_no_llm_answer_contains_no_pii_and_has_consent_instruction(self):
        gate = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=True, trust_level="standard",
            retrieved_chunks=[_REGISTRANT_ADDRESS_CHUNK],
        )
        generated = ResponseGenerateNode(llm=None).execute(
            query="What is the registrant's address?",
            safe_chunks=gate["safe_chunks"],
            inventory_status=None,
            trust_level="standard",
            appi_blocked=gate["appi_blocked"],
            escalation_flag=False,
            cca_note=None,
        )
        final = SecurityGateOutputNode.execute(
            answer=generated["answer"], trust_level="standard", escalation_flag=False,
        )

        assert not contains_pii(final["answer"])
        assert "consent verification" in final["answer"].lower()
        assert gate["appi_blocked"] is True

    def test_step8_catches_pii_even_if_step4_is_bypassed(self):
        # Belt-and-suspenders: simulate a hypothetical draft that leaked PII
        # despite step 4 (e.g. a future regression in step 6's prompt logic).
        leaked_draft = f"Sure, here it is: {_REGISTRANT_ADDRESS_CHUNK['chunk']}"
        final = SecurityGateOutputNode.execute(
            answer=leaked_draft, trust_level="standard", escalation_flag=False,
        )
        assert not contains_pii(final["answer"])
        assert final["escalation_flag"] is True

    def test_elevated_trust_staff_may_receive_registrant_contact_info(self):
        gate = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=True, trust_level="elevated",
            retrieved_chunks=[_REGISTRANT_ADDRESS_CHUNK],
        )
        assert gate["appi_blocked"] is False
        assert gate["safe_chunks"] == [_REGISTRANT_ADDRESS_CHUNK]

        final = SecurityGateOutputNode.execute(
            answer=_REGISTRANT_ADDRESS_CHUNK["chunk"], trust_level="elevated", escalation_flag=False,
        )
        assert contains_pii(final["answer"])  # staff is allowed to see it
        assert final["escalation_flag"] is False
