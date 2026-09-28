# RET-C2-620 — Unit Tests: step 6 (ResponseGenerateNode)

from src.services.response_generate_service import ResponseGenerateNode


class TestResponseGenerateNode:
    def test_cca_escalation_short_circuits_to_notice(self):
        node = ResponseGenerateNode(llm=None)
        result = node.execute(
            query="Can I cancel?",
            safe_chunks=[{"chunk": "irrelevant"}],
            inventory_status=None,
            trust_level="standard",
            appi_blocked=False,
            escalation_flag=True,
            cca_note="Escalation notice text",
        )
        assert result["answer"] == "Escalation notice text"

    def test_no_llm_uses_deterministic_fallback_grounded_in_chunks(self):
        node = ResponseGenerateNode(llm=None)
        result = node.execute(
            query="question",
            safe_chunks=[{"chunk": "Pickup window is 7 days."}],
            inventory_status=None,
            trust_level="standard",
            appi_blocked=False,
            escalation_flag=False,
            cca_note=None,
        )
        assert "Pickup window is 7 days." in result["answer"]
        assert "Live inventory status unavailable." in result["answer"]

    def test_appi_blocked_appends_consent_notice_in_fallback(self):
        node = ResponseGenerateNode(llm=None)
        result = node.execute(
            query="question",
            safe_chunks=[{"chunk": "policy text"}],
            inventory_status=None,
            trust_level="standard",
            appi_blocked=True,
            escalation_flag=False,
            cca_note=None,
        )
        assert "consent verification" in result["answer"].lower()

    def test_inventory_status_in_stock_formats_correctly(self):
        node = ResponseGenerateNode(llm=None)
        result = node.execute(
            query="question",
            safe_chunks=[],
            inventory_status={"in_stock": True},
            trust_level="standard",
            appi_blocked=False,
            escalation_flag=False,
            cca_note=None,
        )
        assert "in stock" in result["answer"].lower()

    def test_llm_used_when_configured(self):
        class _FakeLLM:
            def complete(self, messages, **kwargs):
                return {"content": "LLM generated answer"}

        node = ResponseGenerateNode(llm=_FakeLLM())
        result = node.execute(
            query="question", safe_chunks=[], inventory_status=None,
            trust_level="standard", appi_blocked=False, escalation_flag=False, cca_note=None,
        )
        assert result["answer"] == "LLM generated answer"

    def test_llm_failure_falls_back_to_deterministic_answer(self):
        class _BrokenLLM:
            def complete(self, messages, **kwargs):
                raise RuntimeError("LLM unavailable")

        node = ResponseGenerateNode(llm=_BrokenLLM())
        result = node.execute(
            query="question", safe_chunks=[{"chunk": "fallback context"}], inventory_status=None,
            trust_level="standard", appi_blocked=False, escalation_flag=False, cca_note=None,
        )
        assert "fallback context" in result["answer"]
