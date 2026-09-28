# RET-C2-620 — Unit Tests: PostProcessNode (dispatches steps 7-8)

import inspect
import json

from framework.schemas.trust_level import TrustLevel

from src.nodes.post_process_node import PostProcessNode


def _base_state(**kwargs) -> dict:
    return {
        "entities": json.dumps({"registry_id": "REG-1", "item_id": "ITEM-1", "party": "registrant"}),
        "inventory_status": json.dumps({"in_stock": True}),
        "intent": "AVAILABILITY",
        "trust_level": "standard",
        "answer": "The item is in stock.",
        "appi_note": None,
        "cca_note": None,
        "escalation_flag": False,
        "appi_blocked": False,
        "pii_in_scope": False,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "node_history": [],
        "error_log": [],
        **kwargs,
    }


class TestPostProcessNodeSuccess:
    def test_returns_success(self):
        node = PostProcessNode()
        result = node.execute(_base_state())
        assert result["status"] == "success"

    def test_result_is_json_str_with_expected_keys(self):
        node = PostProcessNode()
        result = node.execute(_base_state())
        payload = json.loads(result["result"])
        # escalation_flag is intentionally NOT duplicated inside `result` — it
        # is a first-class State field (asserted separately below) to avoid
        # two copies of the same value diverging on a future edit.
        assert set(["answer", "compliance_notes", "fulfillment_route", "audit_ref"]) <= set(payload.keys())
        assert "escalation_flag" not in payload
        assert result["escalation_flag"] is False

    def test_audit_ref_is_hash_not_plaintext_registry_id(self):
        node = PostProcessNode()
        result = node.execute(_base_state())
        payload = json.loads(result["result"])
        assert payload["audit_ref"] != "REG-1"
        assert len(payload["audit_ref"]) == 16

    def test_fulfillment_route_resolved_for_routing_intent(self):
        node = PostProcessNode()
        result = node.execute(_base_state(intent="FULFILLMENT_ROUTING"))
        assert result["fulfillment_route"] == "instore_pickup"

    def test_escalation_instruction_present_when_flagged(self):
        node = PostProcessNode()
        result = node.execute(_base_state(escalation_flag=True, cca_note="Escalation notice."))
        payload = json.loads(result["result"])
        assert "escalation_instruction" in payload


class TestPostProcessNodeS3Gate:
    def test_pii_in_answer_is_redacted_for_standard_trust(self):
        node = PostProcessNode()
        state = _base_state(answer="Registrant address: 〒100-0001 東京都千代田区1-1-1", trust_level="standard")
        result = node.execute(state)
        payload = json.loads(result["result"])
        assert "〒100-0001" not in payload["answer"]
        assert result["escalation_flag"] is True

    def test_elevated_trust_is_not_redacted(self):
        node = PostProcessNode()
        state = _base_state(answer="Registrant address: 〒100-0001 東京都千代田区1-1-1", trust_level="elevated")
        result = node.execute(state)
        payload = json.loads(result["result"])
        assert "〒100-0001" in payload["answer"]


class TestPostProcessNodeContract:
    def test_required_trust_level_is_verified_external(self):
        assert PostProcessNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_trust_gate_blocks_anonymous(self):
        # TC-02: exercise the real __call__() gate entry point, not execute().
        node = PostProcessNode()
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = node(state)
        assert result["status"] == "error"

    def test_trust_gate_allows_verified_external(self):
        node = PostProcessNode()
        state = _base_state(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL.value)
        result = node(state)
        assert result["status"] == "success"

    def test_execute_method_signature(self):
        sig = inspect.signature(PostProcessNode.execute)
        params = list(sig.parameters.keys())
        assert params[1] == "state"
        assert "_invoke_impl" not in PostProcessNode.__dict__
