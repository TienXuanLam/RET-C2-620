"""AgentCore Platform v1.0 — steps 4-5: APPIDisclosureGateNode, ConsumerContractActCheckNode.

⚠️ Most security-critical module in this template (proposal §11 Risk #1 — High).

Pure-Python step helpers (NOT BaseNode subclasses — see docs/02_design.md
"Architecture Overview"). Invoked from
src/nodes/main_node.py::MainNode.execute(), BEFORE ResponseGenerateNode runs.
The LLM must never be handed ungated registrant PII to reason over — these
gates run proactively, not just as a post-hoc filter.
"""

from __future__ import annotations

import re
from typing import Any

# Registrant address / personal-name patterns (JP + generic). Kept in sync
# with src/nodes/post_process_node.py step 8 SecurityGateOutputNode, which
# re-applies the same scan as an independent belt-and-suspenders check.
PII_PATTERNS = [
    re.compile(r"〒?\d{3}-?\d{4}[^\n]{0,40}(都|道|府|県)"),  # JP postal + prefecture
    re.compile(r"\d{1,5}\s+[A-Za-z].{0,30}(Street|St\.|Avenue|Ave\.|Road|Rd\.)", re.IGNORECASE),
    re.compile(r"(氏名|名前)[:：]\s*\S+"),
]

_APPI_ADVISORY_NOTE = (
    "APPI 2026 Article 23: this question involves registrant personal data "
    "disclosure to a third party. The requested disclosure falls outside the "
    "original registry consent scope for a standard-trust caller, or could "
    "not be verified as in-scope. Registrant PII has been withheld; consent "
    "verification is required before this information may be shared. "
    "This is guidance for human review, not a final compliance ruling."
)
_APPI_IN_SCOPE_NOTE = (
    "APPI 2026 Article 23: registrant data used for the stated purpose (e.g. "
    "delivery to the registrant) falls within the original registry consent "
    "scope. No additional consent is required for this specific use. This is "
    "guidance for human review, not a final compliance ruling."
)

_CCA_ESCALATION_NOTE = (
    "Consumer Contract Act Article 8: this question concerns contract "
    "enforceability (cancellation rights, forced substitution, or clause "
    "validity). This agent does not provide legal rulings on contract "
    "enforceability. This question has been escalated for review by store "
    "privacy officer or legal team."
)


class APPIDisclosureGateNode:
    """Step 4 — ⚠️ most critical gate. Dual-triggered by intent=COMPLIANCE_APPI
    OR pii_in_scope=true (Risk #3: prevents intent misclassification from
    silencing this gate). Hard-blocks registrant PII disclosure to
    standard-trust callers by stripping it from the retrieved-chunk context
    BEFORE ResponseGenerateNode runs (Risk #1).
    """

    @staticmethod
    def execute(
        intent: str, pii_in_scope: bool, trust_level: str, retrieved_chunks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        triggered = intent == "COMPLIANCE_APPI" or pii_in_scope
        if not triggered:
            return {"appi_blocked": False, "appi_note": None, "safe_chunks": retrieved_chunks}

        if trust_level == "elevated":
            # Staff may receive registrant contact info per proposal §4.
            return {"appi_blocked": False, "appi_note": _APPI_IN_SCOPE_NOTE, "safe_chunks": retrieved_chunks}

        # Standard trust: strip any chunk content matching PII patterns before
        # it ever reaches the LLM prompt in step 6.
        safe_chunks = [chunk for chunk in retrieved_chunks if not contains_pii(chunk.get("chunk", ""))]
        return {"appi_blocked": True, "appi_note": _APPI_ADVISORY_NOTE, "safe_chunks": safe_chunks}


class ConsumerContractActCheckNode:
    """Step 5 — ⚠️ escalation-only. Never issues a legal ruling: intent=
    COMPLIANCE_CCA always and unconditionally sets escalation_flag=true with a
    fixed non-committal notice (advisory_only guarantee).
    """

    @staticmethod
    def execute(intent: str) -> dict[str, Any]:
        if intent != "COMPLIANCE_CCA":
            return {"escalation_flag": False, "cca_note": None}
        return {"escalation_flag": True, "cca_note": _CCA_ESCALATION_NOTE}


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for pattern in PII_PATTERNS)
