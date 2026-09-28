# RET-C2-620 — Unit Tests: MainNode (dispatches steps 3-6)

import inspect
import json

from framework.schemas.trust_level import TrustLevel

from src.nodes.main_node import MainNode


class _FakeKB:
    def __init__(self, chunks):
        self._chunks = chunks

    def similarity_search(self, query, k):
        return self._chunks[:k]


def _base_state(**kwargs) -> dict:
    return {
        "user_input": "",
        "validated_input": "Is item X in stock?",
        "intent": "AVAILABILITY",
        "entities": json.dumps({"registry_id": "REG-1", "item_id": "ITEM-1", "party": "registrant"}),
        "trust_level": "standard",
        "pii_in_scope": False,
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "node_history": [],
        "error_log": [],
        **kwargs,
    }


class TestMainNodeSuccessPath:
    def test_returns_success_with_valid_state(self):
        node = MainNode(registry_kb=_FakeKB([{"chunk": "Pickup window is 7 days."}]))
        result = node.execute(_base_state())
        assert result["status"] == "success"
        assert "answer" in result

    def test_retrieved_chunks_is_json_str(self):
        node = MainNode(registry_kb=_FakeKB([{"chunk": "policy text"}]))
        result = node.execute(_base_state())
        chunks = json.loads(result["retrieved_chunks"])
        assert isinstance(chunks, list)

    def test_appi_gate_blocks_pii_intent_for_standard_trust(self):
        node = MainNode(appi_kb=_FakeKB([{"chunk": "registrant address 東京都千代田区1-1-1"}]))
        state = _base_state(intent="COMPLIANCE_APPI", pii_in_scope=True, trust_level="standard")
        result = node.execute(state)
        assert result["appi_blocked"] is True

    def test_cca_intent_sets_escalation_flag(self):
        node = MainNode()
        state = _base_state(intent="COMPLIANCE_CCA")
        result = node.execute(state)
        assert result["escalation_flag"] is True

    def test_non_appi_non_cca_intent_does_not_trigger_gates(self):
        node = MainNode()
        state = _base_state(intent="AVAILABILITY", pii_in_scope=False)
        result = node.execute(state)
        assert result["appi_blocked"] is False
        assert result["escalation_flag"] is False


class TestMainNodeSecurity:
    def test_required_trust_level_is_verified_external(self):
        assert MainNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_trust_gate_blocks_anonymous(self):
        # TC-02: exercise the real __call__() gate entry point, not execute().
        node = MainNode()
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = node(state)
        assert result["status"] == "error"

    def test_trust_gate_allows_verified_external(self):
        node = MainNode()
        state = _base_state(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL.value)
        result = node(state)
        assert result["status"] == "success"


class TestMainNodeContract:
    def test_execute_method_signature(self):
        sig = inspect.signature(MainNode.execute)
        params = list(sig.parameters.keys())
        assert params[1] == "state"
        assert "_invoke_impl" not in MainNode.__dict__
