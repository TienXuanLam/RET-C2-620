"""AgentCore Platform v1.0"""

# Node contract: extend FunctionNode; implement
# execute(state) -> dict; return ONLY changed fields; use AgentStatus enum.
#
# Real S-3 gate slot. Dispatches steps 7-8 of the architect's 8-step spec:
# ComplianceAnnotateNode, SecurityGateOutputNode.
# See docs/02_design.md "Architecture Overview".

import hashlib
import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.compliance_annotate_service import ComplianceAnnotateNode, SecurityGateOutputNode


class PostProcessNode(FunctionNode):
    """Step 7-8 dispatcher: compliance annotation + S-3 PII output gate."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        # S-3: independent re-scan is already applied inside execute() via
        # step 8 SecurityGateOutputNode.execute(); this hook is the framework's
        # real enforcement point confirming the gate ran (ADR-017).
        return result

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        entities = json.loads(state.get("entities") or "{}")
        inventory_status = json.loads(state.get("inventory_status") or "null")
        intent = state.get("intent", "GENERAL_POLICY")
        trust_level = state.get("trust_level", "standard")

        step7 = ComplianceAnnotateNode.execute(
            appi_note=state.get("appi_note"),
            cca_note=state.get("cca_note"),
            intent=intent,
            inventory_status=inventory_status,
        )

        step8 = SecurityGateOutputNode.execute(
            answer=state.get("answer", ""),
            trust_level=trust_level,
            escalation_flag=bool(state.get("escalation_flag", False)),
        )

        registry_id_hash = _hash_registry_id(entities.get("registry_id"))
        escalation_flag = step8["escalation_flag"]

        # escalation_flag is a first-class State field (returned below) — do
        # not also embed it inside `response`/`result`, to avoid two copies
        # of the same value that could silently diverge on a future edit.
        response: dict[str, Any] = {
            "answer": step8["answer"],
            "compliance_notes": step7["compliance_notes"],
            "fulfillment_route": step7["fulfillment_route"],
            "audit_ref": registry_id_hash,
        }
        if escalation_flag:
            response["escalation_instruction"] = (
                "This question requires review by store privacy officer or legal "
                "team before answering. Do not respond directly."
            )

        emit_trace_event(
            "response_assembled",
            {
                "query_intent": intent,
                "registry_id_hash": registry_id_hash,
                "pii_in_scope": state.get("pii_in_scope", False),
                "appi_blocked": state.get("appi_blocked", False),
                "escalation_flag": escalation_flag,
            },
            state,
        )

        return {
            "result": json.dumps(response),
            "formatted_output": _format_markdown(response),
            "compliance_notes": json.dumps(step7["compliance_notes"]),
            "fulfillment_route": step7["fulfillment_route"],
            "escalation_flag": escalation_flag,
            "status": AgentStatus.SUCCESS.value,
        }


def _hash_registry_id(registry_id: str | None) -> str:
    if not registry_id:
        return ""
    return hashlib.sha256(registry_id.encode("utf-8")).hexdigest()[:16]


def _format_markdown(response: dict[str, Any]) -> str:
    lines = [response["answer"], ""]
    if response["compliance_notes"]:
        lines.append("**Compliance Notes:**")
        for note in response["compliance_notes"]:
            lines.append(f"- [{note['law']}] {note['note']}")
        lines.append("")
    if response.get("fulfillment_route"):
        lines.append(f"**Fulfillment Route:** {response['fulfillment_route']}")
    if response.get("escalation_instruction"):
        lines.append(f"\n**⚠️ {response['escalation_instruction']}**")
    return "\n".join(lines)
