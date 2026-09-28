"""AgentCore Platform v1.0 — step 3: HybridRetrieveNode.

Pure-Python step helper (NOT a BaseNode subclass — see docs/02_design.md
"Architecture Overview"). Invoked from
src/nodes/main_node.py::MainNode.execute().
"""

from __future__ import annotations

from typing import Any

_TOP_K = 5

# Allowlisted inventory tool response fields (Risk #2 — registrant metadata
# returned alongside item status by some POS/inventory systems must never
# reach ResponseGenerateNode).
_INVENTORY_FIELD_ALLOWLIST = {
    "in_stock",
    "out_of_stock",
    "on_order",
    "discontinued",
    "estimated_restock",
}


class HybridRetrieveNode:
    """Step 3 — retrieves and merges top-K chunks from 3 separate knowledge
    bases: registry policy, APPI 2026, Consumer Contract Act.
    """

    def __init__(
        self, registry_kb: Any = None, appi_kb: Any = None, cca_kb: Any = None, inventory_tool: Any = None
    ) -> None:
        self._registry_kb = registry_kb
        self._appi_kb = appi_kb
        self._cca_kb = cca_kb
        self._inventory_tool = inventory_tool

    def execute(self, query: str, intent: str, entities: dict[str, Any]) -> dict[str, Any]:
        chunks: list[dict[str, Any]] = []
        chunks.extend(_tag_chunks(_query_kb(self._registry_kb, query, _TOP_K), "registry"))
        chunks.extend(_tag_chunks(_query_kb(self._appi_kb, query, _TOP_K), "appi"))
        chunks.extend(_tag_chunks(_query_kb(self._cca_kb, query, _TOP_K), "cca"))

        inventory_status = None
        if intent == "AVAILABILITY" and entities.get("registry_id"):
            inventory_status = self._lookup_inventory(entities)

        return {"retrieved_chunks": chunks, "inventory_status": inventory_status}

    def _lookup_inventory(self, entities: dict[str, Any]) -> dict[str, Any] | None:
        if self._inventory_tool is None:
            return None
        raw = self._inventory_tool.get_status(
            registry_id=entities.get("registry_id"),
            item_id=entities.get("item_id"),
        )
        if not raw:
            return None
        # Risk #2: strict allowlist — strip any registrant metadata the tool
        # may have returned alongside item status.
        return {k: v for k, v in raw.items() if k in _INVENTORY_FIELD_ALLOWLIST}


def _query_kb(kb: Any, query: str, top_k: int) -> list[dict[str, Any]]:
    if kb is None:
        return []
    result: list[dict[str, Any]] = kb.similarity_search(query, k=top_k)
    return result


def _tag_chunks(chunks: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    return [{**chunk, "source_kb": source} for chunk in chunks]
