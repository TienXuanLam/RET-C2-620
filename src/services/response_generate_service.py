"""AgentCore Platform v1.0 — step 6: ResponseGenerateNode.

Pure-Python step helper (NOT a BaseNode subclass — see docs/02_design.md
"Architecture Overview"). Invoked from
src/nodes/main_node.py::MainNode.execute(), AFTER APPIDisclosureGateNode
and ConsumerContractActCheckNode (steps 4-5) have already gated the context.
"""

from __future__ import annotations

from typing import Any

_UNAVAILABLE_INVENTORY_NOTE = "Live inventory status unavailable."


class ResponseGenerateNode:
    """Step 6 — LLM Q&A generation constrained by the gated (safe) chunk set
    from step 4. When ConsumerContractActCheckNode (step 5) has escalated the
    query, this step returns the escalation notice instead of attempting an
    answer to the legal question (advisory_only guarantee).
    """

    def __init__(self, llm: Any = None) -> None:
        self._llm = llm

    def execute(
        self,
        query: str,
        safe_chunks: list[dict[str, Any]],
        inventory_status: dict[str, Any] | None,
        trust_level: str,
        appi_blocked: bool,
        escalation_flag: bool,
        cca_note: str | None,
    ) -> dict[str, Any]:
        if escalation_flag and cca_note:
            # Step 5 already escalated — never attempt a legal ruling.
            return {"answer": cca_note}

        context_text = "\n".join(c.get("chunk", "") for c in safe_chunks)
        inventory_line = (
            _format_inventory(inventory_status) if inventory_status is not None else _UNAVAILABLE_INVENTORY_NOTE
        )

        if self._llm is not None:
            prompt = _build_prompt(query, context_text, inventory_line, trust_level, appi_blocked)
            try:
                response = self._llm.complete([{"role": "user", "content": prompt}])
                answer = response.get("content", "") if isinstance(response, dict) else str(response)
                if answer:
                    return {"answer": answer}
            except Exception:
                pass

        # Deterministic fallback when no LLM is configured (or it fails):
        # ground the answer directly in retrieved KB chunks / inventory line.
        answer = context_text.strip() or "No relevant policy information was found for this question."
        answer = f"{answer}\n\n{inventory_line}"
        if appi_blocked:
            answer += "\n\nRegistrant contact details cannot be shared without consent " "verification for this caller."
        return {"answer": answer}


def _format_inventory(status: dict[str, Any]) -> str:
    if status.get("in_stock"):
        return "Item is in stock."
    if status.get("on_order"):
        return f"Item is on order. Estimated restock: {status.get('estimated_restock', 'unknown')}."
    if status.get("discontinued"):
        return "Item is discontinued."
    return "Item is currently out of stock."


def _build_prompt(query: str, context_text: str, inventory_line: str, trust_level: str, appi_blocked: bool) -> str:
    pii_instruction = (
        "Do NOT include the registrant's address, phone number, or other contact "
        "details in your answer. If the question requires that information, "
        "explain that consent verification is required instead."
        if appi_blocked
        else "You may include registrant contact details only if directly supported " "by the retrieved policy context."
    )
    return (
        "You are a retail gift registry policy assistant. Answer the question "
        "using ONLY the retrieved policy context below. Do not speculate.\n\n"
        f"Caller trust level: {trust_level}\n"
        f"{pii_instruction}\n\n"
        f"Retrieved policy context:\n{context_text}\n\n"
        f"Inventory status: {inventory_line}\n\n"
        f"Question: {query}\n\nAnswer:"
    )
