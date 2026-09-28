# RET-C2-620 — Unit Tests: step 3 (HybridRetrieveNode)

from src.services.kb_retrieval_service import HybridRetrieveNode


class _FakeKB:
    def __init__(self, chunks):
        self._chunks = chunks

    def similarity_search(self, query, k):
        return self._chunks[:k]


class _FakeInventoryTool:
    def __init__(self, response):
        self._response = response

    def get_status(self, registry_id, item_id):
        return self._response


class TestHybridRetrieveNode:
    def test_merges_chunks_from_three_kbs(self):
        node = HybridRetrieveNode(
            registry_kb=_FakeKB([{"chunk": "registry policy"}]),
            appi_kb=_FakeKB([{"chunk": "appi rule"}]),
            cca_kb=_FakeKB([{"chunk": "cca rule"}]),
        )
        result = node.execute("query", intent="GENERAL_POLICY", entities={})
        sources = {c["source_kb"] for c in result["retrieved_chunks"]}
        assert sources == {"registry", "appi", "cca"}

    def test_no_kb_configured_returns_empty_chunks(self):
        node = HybridRetrieveNode()
        result = node.execute("query", intent="GENERAL_POLICY", entities={})
        assert result["retrieved_chunks"] == []
        assert result["inventory_status"] is None

    def test_inventory_lookup_skipped_for_non_availability_intent(self):
        node = HybridRetrieveNode(inventory_tool=_FakeInventoryTool({"in_stock": True}))
        result = node.execute("query", intent="GENERAL_POLICY", entities={"registry_id": "REG-1"})
        assert result["inventory_status"] is None

    def test_inventory_lookup_requires_registry_id(self):
        node = HybridRetrieveNode(inventory_tool=_FakeInventoryTool({"in_stock": True}))
        result = node.execute("query", intent="AVAILABILITY", entities={"registry_id": None})
        assert result["inventory_status"] is None

    def test_inventory_lookup_runs_for_availability_with_registry_id(self):
        node = HybridRetrieveNode(inventory_tool=_FakeInventoryTool({"in_stock": True}))
        result = node.execute("query", intent="AVAILABILITY", entities={"registry_id": "REG-1"})
        assert result["inventory_status"] == {"in_stock": True}

    def test_inventory_response_is_field_allowlisted(self):
        # Risk #2: registrant metadata returned alongside item status must be stripped.
        node = HybridRetrieveNode(
            inventory_tool=_FakeInventoryTool({
                "in_stock": True,
                "registrant_name": "田中太郎",
                "registrant_address": "東京都千代田区1-1-1",
            })
        )
        result = node.execute("query", intent="AVAILABILITY", entities={"registry_id": "REG-1"})
        assert result["inventory_status"] == {"in_stock": True}
        assert "registrant_name" not in result["inventory_status"]
        assert "registrant_address" not in result["inventory_status"]

    def test_no_inventory_tool_configured_gracefully_returns_none(self):
        node = HybridRetrieveNode()
        result = node.execute("query", intent="AVAILABILITY", entities={"registry_id": "REG-1"})
        assert result["inventory_status"] is None
