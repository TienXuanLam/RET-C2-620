# RET-C2-620 — Unit Tests: steps 4-5 (APPIDisclosureGateNode, ConsumerContractActCheckNode)
# Most security-critical module — see docs/02_design.md Risks #1 and #3.

from src.services.compliance_gate_service import (
    APPIDisclosureGateNode,
    ConsumerContractActCheckNode,
    contains_pii,
)

_PII_CHUNK = {"chunk": "Registrant address: 〒100-0001 東京都千代田区1-1-1", "source_kb": "registry"}
_CLEAN_CHUNK = {"chunk": "Standard pickup window is 7 business days.", "source_kb": "registry"}


class TestAPPIDisclosureGateNode:
    def test_intent_trigger_blocks_standard_trust(self):
        result = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=False, trust_level="standard",
            retrieved_chunks=[_PII_CHUNK, _CLEAN_CHUNK],
        )
        assert result["appi_blocked"] is True
        assert _CLEAN_CHUNK in result["safe_chunks"]
        assert _PII_CHUNK not in result["safe_chunks"]

    def test_pii_in_scope_trigger_blocks_even_with_misclassified_intent(self):
        # Risk #3: dual trigger — pii_in_scope alone must still gate, regardless of intent.
        result = APPIDisclosureGateNode.execute(
            intent="GENERAL_POLICY", pii_in_scope=True, trust_level="standard",
            retrieved_chunks=[_PII_CHUNK],
        )
        assert result["appi_blocked"] is True

    def test_elevated_trust_is_not_blocked(self):
        result = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=False, trust_level="elevated",
            retrieved_chunks=[_PII_CHUNK],
        )
        assert result["appi_blocked"] is False
        assert result["safe_chunks"] == [_PII_CHUNK]
        assert result["appi_note"] is not None

    def test_no_trigger_passes_through_unblocked(self):
        result = APPIDisclosureGateNode.execute(
            intent="AVAILABILITY", pii_in_scope=False, trust_level="standard",
            retrieved_chunks=[_CLEAN_CHUNK],
        )
        assert result["appi_blocked"] is False
        assert result["appi_note"] is None
        assert result["safe_chunks"] == [_CLEAN_CHUNK]

    def test_advisory_wording_only_no_ruling(self):
        result = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=False, trust_level="standard",
            retrieved_chunks=[],
        )
        assert "guidance for human review" in result["appi_note"]
        assert "not a final compliance ruling" in result["appi_note"]


class TestConsumerContractActCheckNode:
    def test_cca_intent_always_escalates(self):
        result = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        assert result["escalation_flag"] is True
        assert result["cca_note"] is not None

    def test_non_cca_intent_does_not_escalate(self):
        for intent in ("AVAILABILITY", "GENERAL_POLICY", "COMPLIANCE_APPI", "FULFILLMENT_ROUTING"):
            result = ConsumerContractActCheckNode.execute(intent=intent)
            assert result["escalation_flag"] is False
            assert result["cca_note"] is None

    def test_escalation_note_is_advisory_never_a_ruling(self):
        result = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        assert "does not provide legal rulings" in result["cca_note"]
        assert "escalated" in result["cca_note"]


class TestContainsPii:
    def test_detects_jp_address(self):
        assert contains_pii("〒100-0001 東京都千代田区1-1-1") is True

    def test_detects_name_field(self):
        assert contains_pii("氏名：田中太郎") is True

    def test_clean_text_not_flagged(self):
        assert contains_pii("Standard pickup window is 7 business days.") is False
