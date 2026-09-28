"""AgentCore Platform v1.0"""

# Node contract: extend FunctionNode; implement
# execute(state) -> dict; return ONLY changed fields; use AgentStatus enum.
#
# Real S-1/S-2 gate slot. Dispatches steps 1-2 of the architect's 8-step
# spec: InputValidateNode, QueryClassifyNode.
# See docs/02_design.md "Architecture Overview".

import json
import re
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.intent_classify_service import InputValidateNode, QueryClassifyNode

_PII_KEYWORDS_RAW_INPUT = ["住所", "個人情報", "連絡先", "氏名", "名前"]


class PreProcessNode(FunctionNode):
    """Step 1-2 dispatcher: input validation + intent classification."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_input(self, state: dict[str, Any]) -> dict[str, Any]:
        # S-2: raw PII/consent keyword scan on the unvalidated query text.
        # Must not raise — surface rejection via state.
        # This is the FIRST of two independent pii_in_scope triggers (dual
        # trigger, Risk #3): the flag set here is consumed directly by
        # execute() below and OR-ed with QueryClassifyNode's own keyword scan
        # on the validated query. Neither trigger alone is treated as
        # authoritative — see docs/02_design.md "PII risk — design decisions".
        raw = state.get("user_input", "")
        if any(re.search(kw, raw) for kw in _PII_KEYWORDS_RAW_INPUT):
            state = dict(state)
            state["_pii_keyword_detected"] = True
        return state

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        step1 = InputValidateNode.execute(state)
        if "_step1_error" in step1:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [f"InputValidateNode: {step1['_step1_error']}"],
            }

        emit_trace_event(
            "input_validated",
            {"registry_id_present": bool(state.get("registry_id"))},
            state,
        )

        query = step1["_step1_validated_query"]
        step2 = QueryClassifyNode.execute(state, query)
        pii_in_scope = step2["pii_in_scope"] or bool(state.get("_pii_keyword_detected", False))

        emit_trace_event(
            "intent_classified",
            {"intent": step2["intent"], "pii_in_scope": pii_in_scope},
            state,
        )

        return {
            "validated_input": query,
            "intent": step2["intent"],
            "entities": json.dumps(step2["entities"]),
            "trust_level": step2["trust_level"],
            "pii_in_scope": pii_in_scope,
            "status": AgentStatus.SUCCESS.value,
        }
