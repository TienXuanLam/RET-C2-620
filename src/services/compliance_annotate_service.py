"""AgentCore Platform v1.0 — steps 7-8: ComplianceAnnotateNode, SecurityGateOutputNode.

Pure-Python step helpers (NOT BaseNode subclasses — see docs/02_design.md
"Architecture Overview"). Invoked from
src/nodes/post_process_node.py::PostProcessNode.execute() and from
PostProcessNode._extra_security_gate_output() (S-3 real gate hook).
"""

from __future__ import annotations

from typing import Any

from src.services.compliance_gate_service import contains_pii

_ROUTING_RULES = {
    "in_stock": "instore_pickup",
    "on_order": "online_direct_ship",
    "discontinued": "not_available",
}
_DEFAULT_ROUTE_NO_INVENTORY = "online_direct_ship"

_PII_REDACTED_NOTICE = (
    "[This response was withheld because it appeared to contain registrant "
    "personal information. Consent verification is required before this "
    "question can be answered.]"
)


class ComplianceAnnotateNode:
    """Step 7 — assembles structured compliance_notes from steps 4-5's
    findings; resolves fulfillment_route when intent=FULFILLMENT_ROUTING.
    """

    @staticmethod
    def execute(
        appi_note: str | None,
        cca_note: str | None,
        intent: str,
        inventory_status: dict[str, Any] | None,
    ) -> dict[str, Any]:
        compliance_notes: list[dict[str, str]] = []
        if appi_note:
            compliance_notes.append({"law": "APPI 2026 Article 23", "note": appi_note})
        if cca_note:
            compliance_notes.append({"law": "Consumer Contract Act Article 8", "note": cca_note})

        fulfillment_route = None
        if intent == "FULFILLMENT_ROUTING":
            fulfillment_route = _resolve_route(inventory_status)

        return {"compliance_notes": compliance_notes, "fulfillment_route": fulfillment_route}


class SecurityGateOutputNode:
    """Step 8 — S-3 belt-and-suspenders. Independently re-scans the final
    answer for registrant PII patterns (same patterns as step 4) and redacts
    + forces escalation if anything slipped through steps 4-6 (Risk #1).
    """

    @staticmethod
    def execute(answer: str, trust_level: str, escalation_flag: bool) -> dict[str, Any]:
        if trust_level == "elevated":
            return {"answer": answer, "escalation_flag": escalation_flag}

        if contains_pii(answer):
            return {"answer": _PII_REDACTED_NOTICE, "escalation_flag": True}

        return {"answer": answer, "escalation_flag": escalation_flag}


def _resolve_route(inventory_status: dict[str, Any] | None) -> str:
    if inventory_status is None:
        return _DEFAULT_ROUTE_NO_INVENTORY
    for field, route in _ROUTING_RULES.items():
        if inventory_status.get(field):
            return route
    return "cross_store_transfer"
