# RET-C2-620 — Unit Tests: steps 7-8 (ComplianceAnnotateNode, SecurityGateOutputNode)

from src.services.compliance_annotate_service import ComplianceAnnotateNode, SecurityGateOutputNode


class TestComplianceAnnotateNode:
    def test_merges_appi_and_cca_notes(self):
        result = ComplianceAnnotateNode.execute(
            appi_note="appi finding", cca_note="cca finding", intent="GENERAL_POLICY", inventory_status=None,
        )
        laws = {n["law"] for n in result["compliance_notes"]}
        assert laws == {"APPI 2026 Article 23", "Consumer Contract Act Article 8"}

    def test_no_notes_when_none_triggered(self):
        result = ComplianceAnnotateNode.execute(
            appi_note=None, cca_note=None, intent="AVAILABILITY", inventory_status=None,
        )
        assert result["compliance_notes"] == []

    def test_fulfillment_route_resolved_for_routing_intent(self):
        result = ComplianceAnnotateNode.execute(
            appi_note=None, cca_note=None, intent="FULFILLMENT_ROUTING",
            inventory_status={"in_stock": True},
        )
        assert result["fulfillment_route"] == "instore_pickup"

    def test_fulfillment_route_none_for_non_routing_intent(self):
        result = ComplianceAnnotateNode.execute(
            appi_note=None, cca_note=None, intent="AVAILABILITY", inventory_status={"in_stock": True},
        )
        assert result["fulfillment_route"] is None

    def test_fulfillment_route_defaults_without_inventory(self):
        result = ComplianceAnnotateNode.execute(
            appi_note=None, cca_note=None, intent="FULFILLMENT_ROUTING", inventory_status=None,
        )
        assert result["fulfillment_route"] == "online_direct_ship"

    def test_fulfillment_route_discontinued(self):
        result = ComplianceAnnotateNode.execute(
            appi_note=None, cca_note=None, intent="FULFILLMENT_ROUTING",
            inventory_status={"discontinued": True},
        )
        assert result["fulfillment_route"] == "not_available"


class TestSecurityGateOutputNode:
    def test_clean_answer_passes_through(self):
        result = SecurityGateOutputNode.execute(
            answer="Pickup window is 7 days.", trust_level="standard", escalation_flag=False,
        )
        assert result["answer"] == "Pickup window is 7 days."
        assert result["escalation_flag"] is False

    def test_pii_leak_is_redacted_and_escalated(self):
        # Risk #1 belt-and-suspenders: catches anything that slipped through step 4.
        result = SecurityGateOutputNode.execute(
            answer="Registrant address: 〒100-0001 東京都千代田区1-1-1",
            trust_level="standard", escalation_flag=False,
        )
        assert "〒100-0001" not in result["answer"]
        assert result["escalation_flag"] is True

    def test_elevated_trust_bypasses_redaction(self):
        result = SecurityGateOutputNode.execute(
            answer="Registrant address: 〒100-0001 東京都千代田区1-1-1",
            trust_level="elevated", escalation_flag=False,
        )
        assert "〒100-0001" in result["answer"]
        assert result["escalation_flag"] is False

    def test_preserves_existing_escalation_flag_when_clean(self):
        result = SecurityGateOutputNode.execute(
            answer="clean text", trust_level="standard", escalation_flag=True,
        )
        assert result["escalation_flag"] is True
