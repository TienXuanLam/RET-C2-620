# RET-C2-620 — Unit Tests: PreProcessNode (dispatches steps 1-2)

import inspect
import json
from unittest import mock

from framework.schemas.trust_level import TrustLevel

from src.nodes.pre_process_node import PreProcessNode


def _base_state(**kwargs) -> dict:
    return {
        "user_input": "Is item X in stock?",
        "user_role": "customer",
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "node_history": [],
        "error_log": [],
        **kwargs,
    }


class TestPreProcessNodeSuccess:
    def test_valid_query_returns_success(self):
        node = PreProcessNode()
        result = node.execute(_base_state())
        assert result["status"] == "success"

    def test_returns_intent_and_trust_level(self):
        node = PreProcessNode()
        result = node.execute(_base_state())
        assert result["intent"] == "AVAILABILITY"
        assert result["trust_level"] == "standard"

    def test_entities_is_json_str(self):
        node = PreProcessNode()
        result = node.execute(_base_state())
        entities = json.loads(result["entities"])
        assert "registry_id" in entities

    def test_staff_role_gets_elevated_trust(self):
        node = PreProcessNode()
        result = node.execute(_base_state(user_role="staff"))
        assert result["trust_level"] == "elevated"


class TestPreProcessNodeErrors:
    def test_empty_query_returns_error(self):
        node = PreProcessNode()
        result = node.execute(_base_state(user_input=""))
        assert result["status"] == "error"

    def test_invalid_user_role_returns_error(self):
        node = PreProcessNode()
        result = node.execute(_base_state(user_role="admin"))
        assert result["status"] == "error"

    def test_invalid_registry_id_format_returns_error(self):
        node = PreProcessNode()
        result = node.execute(_base_state(registry_id="!!bad!!"))
        assert result["status"] == "error"


class TestPreProcessNodeSecurity:
    def test_required_trust_level_is_verified_external(self):
        assert PreProcessNode.required_trust_level == TrustLevel.VERIFIED_EXTERNAL

    def test_trust_gate_blocks_anonymous(self):
        # TC-02: verify enforcement, not just the declaration above — calls
        # the real __call__() gate entry point (not execute()) so a shadowed
        # __call__() or a misconfigured trust check would be caught here.
        node = PreProcessNode()
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = node(state)
        assert result["status"] == "error"

    def test_trust_gate_allows_verified_external(self):
        node = PreProcessNode()
        state = _base_state(caller_trust_level=TrustLevel.VERIFIED_EXTERNAL.value)
        result = node(state)
        assert result["status"] == "success"

    def test_s2_flags_pii_keyword_without_raising(self):
        node = PreProcessNode()
        state = _base_state(user_input="Please share the registrant's 住所")
        result = node._extra_security_gate_input(state)
        assert result.get("_pii_keyword_detected") is True

    def test_s2_passes_clean_input_through(self):
        node = PreProcessNode()
        state = _base_state()
        result = node._extra_security_gate_input(state)
        assert "_pii_keyword_detected" not in result

    def test_dual_trigger_or_branch_raw_scan_catches_what_validated_scan_misses(self):
        # Risk #3 dual-trigger: pii_in_scope must end up True even when
        # QueryClassifyNode's own scan (on the validated/lowercased query)
        # misses a PII keyword that the raw-input S-2 scan already caught —
        # this is precisely the gap the OR-logic was added to close.
        node = PreProcessNode()
        state = _base_state(user_input="Please share the registrant's 住所")

        with mock.patch(
            "src.nodes.pre_process_node.QueryClassifyNode.execute",
            return_value={
                "intent": "GENERAL_POLICY",
                "entities": {"registry_id": None, "item_id": None, "party": "registrant"},
                "trust_level": "standard",
                "pii_in_scope": False,  # simulated miss on the validated-query scan
            },
        ):
            gated_state = node._extra_security_gate_input(state)
            result = node.execute(gated_state)

        assert result["pii_in_scope"] is True

    def test_execute_method_signature(self):
        sig = inspect.signature(PreProcessNode.execute)
        params = list(sig.parameters.keys())
        assert params[1] == "state"
        assert "_invoke_impl" not in PreProcessNode.__dict__
