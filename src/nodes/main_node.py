"""AgentCore Platform v1.0"""

# Node contract: extend FunctionNode; implement
# execute(state) -> dict; return ONLY changed fields; use AgentStatus enum.
#
# Dispatches steps 3-6 of the architect's 8-step spec:
# HybridRetrieveNode, APPIDisclosureGateNode, ConsumerContractActCheckNode,
# ResponseGenerateNode. Steps 4-5 run BEFORE step 6 — the LLM never sees
# ungated registrant PII (proposal §11 Risk #1). See docs/02_design.md.

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.compliance_gate_service import APPIDisclosureGateNode, ConsumerContractActCheckNode
from src.services.kb_retrieval_service import HybridRetrieveNode
from src.services.response_generate_service import ResponseGenerateNode


class MainNode(FunctionNode):
    """Step 3-6 dispatcher: retrieval, compliance gates, Q&A generation."""

    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(
        self,
        llm: Any = None,
        registry_kb: Any = None,
        appi_kb: Any = None,
        cca_kb: Any = None,
        inventory_tool: Any = None,
    ) -> None:
        self._llm = llm
        self._retrieve = HybridRetrieveNode(
            registry_kb=registry_kb, appi_kb=appi_kb, cca_kb=cca_kb, inventory_tool=inventory_tool
        )
        self._generate = ResponseGenerateNode(llm=llm)

    def execute(self, state: dict[str, Any]) -> dict[str, Any]:
        query = state.get("validated_input", "")
        intent = state.get("intent", "GENERAL_POLICY")
        entities = json.loads(state.get("entities") or "{}")
        trust_level = state.get("trust_level", "standard")
        pii_in_scope = bool(state.get("pii_in_scope", False))

        step3 = self._retrieve.execute(query, intent, entities)
        emit_trace_event(
            "kb_retrieved",
            {"chunk_count": len(step3["retrieved_chunks"]), "intent": intent},
            state,
        )

        step4 = APPIDisclosureGateNode.execute(
            intent=intent,
            pii_in_scope=pii_in_scope,
            trust_level=trust_level,
            retrieved_chunks=step3["retrieved_chunks"],
        )
        emit_trace_event(
            "appi_gate_evaluated",
            {"appi_blocked": step4["appi_blocked"]},
            state,
        )

        step5 = ConsumerContractActCheckNode.execute(intent=intent)
        if step5["escalation_flag"]:
            emit_trace_event("cca_escalated", {"intent": intent}, state)

        step6 = self._generate.execute(
            query=query,
            safe_chunks=step4["safe_chunks"],
            inventory_status=step3["inventory_status"],
            trust_level=trust_level,
            appi_blocked=step4["appi_blocked"],
            escalation_flag=step5["escalation_flag"],
            cca_note=step5["cca_note"],
        )
        emit_trace_event("response_generated", {"escalation_flag": step5["escalation_flag"]}, state)

        return {
            "retrieved_chunks": json.dumps(step3["retrieved_chunks"]),
            "inventory_status": json.dumps(step3["inventory_status"]),
            "appi_blocked": step4["appi_blocked"],
            "appi_note": step4["appi_note"],
            "cca_note": step5["cca_note"],
            "escalation_flag": step5["escalation_flag"],
            "answer": step6["answer"],
            "status": AgentStatus.SUCCESS.value,
        }
