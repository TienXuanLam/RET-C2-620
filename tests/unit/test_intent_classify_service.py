# RET-C2-620 — Unit Tests: steps 1-2 (InputValidateNode, QueryClassifyNode)

import json

from src.services.intent_classify_service import InputValidateNode, QueryClassifyNode


class TestInputValidateNode:
    def test_valid_query_passes(self):
        result = InputValidateNode.execute({"user_input": "Is item X in stock?", "user_role": "customer"})
        assert "_step1_error" not in result
        assert result["_step1_validated_query"] == "Is item X in stock?"

    def test_empty_query_errors(self):
        result = InputValidateNode.execute({"user_input": "", "user_role": "customer"})
        assert "_step1_error" in result

    def test_query_over_token_limit_errors(self):
        long_query = " ".join(["word"] * 600)
        result = InputValidateNode.execute({"user_input": long_query, "user_role": "customer"})
        assert "_step1_error" in result

    def test_invalid_registry_id_format_errors(self):
        result = InputValidateNode.execute({
            "user_input": "question", "registry_id": "!!bad!!", "user_role": "customer",
        })
        assert "_step1_error" in result

    def test_valid_registry_id_passes(self):
        result = InputValidateNode.execute({
            "user_input": "question", "registry_id": "REG-1234", "user_role": "customer",
        })
        assert "_step1_error" not in result

    def test_disallowed_user_role_errors(self):
        result = InputValidateNode.execute({"user_input": "question", "user_role": "admin"})
        assert "_step1_error" in result

    def test_allowed_roles_pass(self):
        for role in ("customer", "staff", "ec_support"):
            result = InputValidateNode.execute({"user_input": "question", "user_role": role})
            assert "_step1_error" not in result, f"role {role} should pass"


class TestQueryClassifyNode:
    def test_classifies_availability_intent(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "Is this item in stock?")
        assert result["intent"] == "AVAILABILITY"

    def test_classifies_compliance_cca_intent(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "Can I cancel and get a refund? 消費者契約法")
        assert result["intent"] == "COMPLIANCE_CCA"

    def test_classifies_compliance_appi_intent(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "Does this fall under 個人情報保護法 第三者提供?")
        assert result["intent"] == "COMPLIANCE_APPI"

    def test_defaults_to_general_policy(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "What are your business hours?")
        assert result["intent"] == "GENERAL_POLICY"

    def test_staff_role_gets_elevated_trust(self):
        result = QueryClassifyNode.execute({"user_role": "staff"}, "question")
        assert result["trust_level"] == "elevated"

    def test_customer_role_gets_standard_trust(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "question")
        assert result["trust_level"] == "standard"

    def test_ec_support_role_gets_standard_trust(self):
        result = QueryClassifyNode.execute({"user_role": "ec_support"}, "question")
        assert result["trust_level"] == "standard"

    def test_pii_keyword_sets_pii_in_scope(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "Can you tell me the registrant's 住所?")
        assert result["pii_in_scope"] is True

    def test_no_pii_keyword_leaves_pii_in_scope_false(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "Is this item in stock?")
        assert result["pii_in_scope"] is False

    def test_entities_are_json_serializable(self):
        result = QueryClassifyNode.execute(
            {"user_role": "customer", "registry_id": "REG-1", "item_id": "ITEM-1"}, "question"
        )
        entities = result["entities"]
        json.dumps(entities)  # must not raise
        assert entities["registry_id"] == "REG-1"
        assert entities["item_id"] == "ITEM-1"


class TestIntentPriorityOrdering:
    """Compliance intents must win over generic intents on a mixed query
    (Risk #3 mitigation) — without this, a compliance-relevant question could
    be silently classified as a generic intent, suppressing the mandatory
    APPI/CCA annotation in MainNode. See src/services/intent_classify_service.py
    _COMPLIANCE_INTENTS_FIRST for the enforcement mechanism.
    """

    def test_cca_wins_over_availability_on_mixed_query(self):
        result = QueryClassifyNode.execute(
            {"user_role": "customer"}, "キャンセルの場合の在庫返却はどうなりますか？"
        )
        assert result["intent"] == "COMPLIANCE_CCA"

    def test_cca_wins_over_fulfillment_routing_on_mixed_query(self):
        result = QueryClassifyNode.execute({"user_role": "customer"}, "配送をキャンセルしたい")
        assert result["intent"] == "COMPLIANCE_CCA"

    def test_appi_wins_over_availability_on_mixed_query(self):
        result = QueryClassifyNode.execute(
            {"user_role": "customer"}, "在庫について個人情報保護法上問題ありますか？"
        )
        assert result["intent"] == "COMPLIANCE_APPI"

    def test_cca_wins_over_appi_when_both_present(self):
        # Order between the two compliance intents themselves: CCA (contract
        # enforceability, always escalates) takes priority over APPI (which
        # has its own dual-trigger safety net via pii_in_scope).
        result = QueryClassifyNode.execute(
            {"user_role": "customer"}, "個人情報保護法の観点からキャンセルしたい"
        )
        assert result["intent"] == "COMPLIANCE_CCA"
