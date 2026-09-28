"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict — never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects
# cause silent corruption.  Extend AgentState with agent-specific
# fields only.  Do NOT add credentials, secrets, or Pydantic models.
#
# Registrant PII (address, contact, name) is never stored as a discrete
# field here. It may transiently appear inside `answer` between
# ResponseGenerateNode and SecurityGateOutputNode; it is never persisted
# to the audit log (see src/nodes/post_process_node.py S-2 handling).

from typing import Optional

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """RetailGiftRegistryFulfillmentComplianceQAAgent state.

    All shared fields (user_input, status, session_id, node_history,
    error_log, hitl_*, etc.) are inherited from AgentState.
    """

    # --- PreProcessNode (steps 1-2: InputValidateNode, QueryClassifyNode) ---
    intent: Optional[str]
    entities: Optional[str]  # JSON-str: {registry_id, item_id, party}
    trust_level: Optional[str]  # "elevated" | "standard" — domain gating flag
    pii_in_scope: Optional[bool]

    # --- MainNode (steps 3-6: HybridRetrieveNode, APPIDisclosureGateNode,
    #     ConsumerContractActCheckNode, ResponseGenerateNode) ---
    retrieved_chunks: Optional[str]  # JSON-str: chunks tagged by source KB
    inventory_status: Optional[str]  # JSON-str: allowlisted fields only (Risk #2)
    appi_blocked: Optional[bool]
    appi_note: Optional[str]
    cca_note: Optional[str]
    answer: Optional[str]

    # --- PostProcessNode (steps 7-8: ComplianceAnnotateNode, SecurityGateOutputNode) ---
    compliance_notes: Optional[str]  # JSON-str: list of {law, note}
    escalation_flag: Optional[bool]
    fulfillment_route: Optional[str]
