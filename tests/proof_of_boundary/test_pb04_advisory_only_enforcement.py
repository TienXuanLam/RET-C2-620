# PB-04: advisory_only enforcement, end-to-end across both compliance gates.
# This agent must never issue a binding legal ruling on any code path —
# every compliance-adjacent output is advisory-worded, and config/agent.yaml
# declares advisory_only: true as the documented runtime contract.
# See docs/02_design.md "advisory_only guarantee".

import re
from pathlib import Path

from src.services.compliance_gate_service import APPIDisclosureGateNode, ConsumerContractActCheckNode
from src.services.response_generate_service import ResponseGenerateNode

_ADVISORY_MARKERS = ["guidance for human review", "not a final compliance ruling", "escalated for review"]
_RULING_LANGUAGE = ["unenforceable", "you are entitled to", "you are not entitled to", "this clause is void"]

_AGENT_YAML = Path(__file__).parent.parent.parent / "config" / "agent.yaml"


class TestPB04AdvisoryOnlyEnforcement:
    def test_agent_yaml_declares_advisory_only_true(self):
        # Avoid adding a pyyaml dependency for a single boolean-flag check —
        # match the declaration line directly (agent.yaml is a small, stable manifest).
        text = _AGENT_YAML.read_text()
        assert re.search(r"^\s*advisory_only:\s*true\s*$", text, re.MULTILINE), (
            "config/agent.yaml must declare 'advisory_only: true'"
        )

    def test_appi_notes_are_always_advisory_worded(self):
        for trust_level in ("standard", "elevated"):
            gate = APPIDisclosureGateNode.execute(
                intent="COMPLIANCE_APPI", pii_in_scope=True, trust_level=trust_level, retrieved_chunks=[],
            )
            assert any(marker in gate["appi_note"] for marker in _ADVISORY_MARKERS), (
                f"appi_note for trust_level={trust_level} is not advisory-worded: {gate['appi_note']!r}"
            )

    def test_cca_notes_are_always_escalation_worded_never_a_ruling(self):
        cca = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        lowered = cca["cca_note"].lower()
        assert "does not provide legal rulings" in lowered
        for phrase in _RULING_LANGUAGE:
            assert phrase not in lowered

    def test_no_code_path_in_response_generation_produces_ruling_language(self):
        cca = ConsumerContractActCheckNode.execute(intent="COMPLIANCE_CCA")
        appi = APPIDisclosureGateNode.execute(
            intent="COMPLIANCE_APPI", pii_in_scope=True, trust_level="standard", retrieved_chunks=[],
        )
        for escalation_flag, cca_note, appi_blocked in (
            (cca["escalation_flag"], cca["cca_note"], False),
            (False, None, appi["appi_blocked"]),
        ):
            result = ResponseGenerateNode(llm=None).execute(
                query="Is this legally enforceable?",
                safe_chunks=[{"chunk": "policy text"}],
                inventory_status=None,
                trust_level="standard",
                appi_blocked=appi_blocked,
                escalation_flag=escalation_flag,
                cca_note=cca_note,
            )
            lowered = result["answer"].lower()
            for phrase in _RULING_LANGUAGE:
                assert phrase not in lowered, f"ruling language leaked: {phrase!r} in {result['answer']!r}"

    def test_no_ruling_language_hardcoded_anywhere_in_compliance_modules(self):
        # Static guarantee: the source itself must not contain ruling-style
        # assertions that a future edit could accidentally start emitting.
        src_dir = Path(__file__).parent.parent.parent / "src" / "services"
        violations = []
        for path in src_dir.glob("*.py"):
            text = path.read_text().lower()
            for phrase in _RULING_LANGUAGE:
                if re.search(re.escape(phrase), text):
                    violations.append(f"{path.name}: {phrase!r}")
        assert violations == [], f"Ruling language found in source: {violations}"
