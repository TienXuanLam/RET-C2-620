"""AgentCore Platform v1.0 — steps 1-2: InputValidateNode, QueryClassifyNode.

Pure-Python step helpers (NOT BaseNode subclasses — see docs/02_design.md
"Architecture Overview"). Invoked in sequence from
src/nodes/pre_process_node.py::PreProcessNode.execute(), which is the real
FunctionNode that runs the actual S-1/S-2 framework gates on __call__().
"""

from __future__ import annotations

import re
from typing import Any

_ALLOWED_ROLES = {"customer", "staff", "ec_support"}
_MAX_QUERY_TOKENS = 512

# Iteration order is a deliberate priority ranking, checked first-match
# (see QueryClassifyNode.execute below): compliance-shaped intents
# (COMPLIANCE_CCA, COMPLIANCE_APPI) are listed BEFORE the generic
# operational intents (PRIVACY_SETTINGS, FULFILLMENT_ROUTING, AVAILABILITY).
# This guarantees a query that mixes a compliance keyword with a generic
# one (e.g. "cancel this order and check inventory") is never silently
# classified as the generic intent, which would suppress the mandatory
# APPI/CCA annotation in MainNode steps 4-5. Do NOT reorder this dict
# without also updating test_intent_classify_service.py::TestIntentPriorityOrdering.
_INTENT_KEYWORDS = {
    "COMPLIANCE_CCA": ["解除", "取消", "キャンセル", "代替品", "強制", "消費者契約法"],
    "COMPLIANCE_APPI": ["個人情報保護法", "appi", "第三者提供", "同意範囲"],
    "PRIVACY_SETTINGS": ["プライバシー設定", "非公開", "公開設定"],
    "FULFILLMENT_ROUTING": ["配送", "店舗受取", "取り寄せ", "在庫移動", "pickup", "cross-store"],
    "AVAILABILITY": ["在庫", "availability", "入荷", "取り扱い", "in stock", "out of stock"],
}
_COMPLIANCE_INTENTS_FIRST = ("COMPLIANCE_CCA", "COMPLIANCE_APPI")
_DEFAULT_INTENT = "GENERAL_POLICY"

_PII_RISK_KEYWORDS = ["住所", "address", "個人情報", "連絡先", "氏名", "名前"]

_REGISTRY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")


class InputValidateNode:
    """Step 1 — S-1 domain-level input validation (query/registry_id/user_role)."""

    @staticmethod
    def execute(state: dict[str, Any]) -> dict[str, Any]:
        query = (state.get("user_input") or "").strip()
        registry_id = state.get("registry_id")
        user_role = state.get("user_role", "customer")

        if not query:
            return {"_step1_error": "query is empty — a registry question is required"}

        if len(query.split()) > _MAX_QUERY_TOKENS:
            return {"_step1_error": f"query exceeds {_MAX_QUERY_TOKENS} token limit"}

        if registry_id and not _REGISTRY_ID_RE.match(registry_id):
            return {"_step1_error": f"registry_id format invalid: {registry_id!r}"}

        if user_role not in _ALLOWED_ROLES:
            return {"_step1_error": f"user_role must be one of {_ALLOWED_ROLES}, got {user_role!r}"}

        return {"_step1_validated_query": query}


class QueryClassifyNode:
    """Step 2 — intent classification, entity extraction, trust-level assignment,
    keyword-based pii_in_scope flag (independent 2nd trigger for step 4 — Risk #3).
    """

    @staticmethod
    def execute(state: dict[str, Any], query: str) -> dict[str, Any]:
        lowered = query.lower()

        # Explicit priority, not implicit dict-order reliance (Risk #3):
        # compliance intents are matched first so a query mixing a
        # compliance keyword with a generic one (e.g. "cancel + inventory")
        # is never classified as the generic intent.
        ordered_intents = list(_COMPLIANCE_INTENTS_FIRST) + [
            name for name in _INTENT_KEYWORDS if name not in _COMPLIANCE_INTENTS_FIRST
        ]

        intent = _DEFAULT_INTENT
        for candidate_intent in ordered_intents:
            keywords = _INTENT_KEYWORDS[candidate_intent]
            if any(kw.lower() in lowered for kw in keywords):
                intent = candidate_intent
                break

        entities = {
            "registry_id": state.get("registry_id"),
            "item_id": state.get("item_id"),
            "party": _extract_party(lowered),
        }

        user_role = state.get("user_role", "customer")
        trust_level = "elevated" if user_role == "staff" else "standard"

        pii_in_scope = any(kw.lower() in lowered for kw in _PII_RISK_KEYWORDS)

        return {
            "intent": intent,
            "entities": entities,
            "trust_level": trust_level,
            "pii_in_scope": pii_in_scope,
        }


def _extract_party(lowered_query: str) -> str:
    if "purchaser" in lowered_query or "購入者" in lowered_query:
        return "purchaser"
    if "staff" in lowered_query or "店員" in lowered_query:
        return "staff"
    return "registrant"
