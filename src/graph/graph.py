"""AgentCore Platform v1.0"""

# Cat 2 — flat backbone (AgentBaseGraph, no inner subgraph).
# The architect's 8-step spec (source proposal Technical Spec) is realized as
# 8 pure-Python step helpers dispatched from these 3 real FunctionNode slots
# — see docs/02_design.md "Architecture Overview" for the full rationale.

from framework.graph.agent_base_graph import AgentBaseGraph

from src.nodes.main_node import MainNode
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State


class RetailGiftRegistryFulfillmentComplianceQAAgent(AgentBaseGraph):
    """Cat 2 ChatAgent + VectorRAG: gift registry Q&A with APPI 2026 Article 23
    and Consumer Contract Act Article 8 compliance annotation (advisory_only).
    """

    @property
    def name(self) -> str:
        return "RetailGiftRegistryFulfillmentComplianceQAAgent"

    @property
    def state_schema(self) -> type:
        return State

    def register_nodes(self) -> None:
        super().register_nodes()  # injects InitializeNode + FinalizeNode

        registry_kb = self.config.get("registry_kb")
        appi_kb = self.config.get("appi_kb")
        cca_kb = self.config.get("cca_kb")
        inventory_tool = self.config.get("inventory_tool")
        llm = self.config.get("llm")

        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = MainNode(
            llm=llm,
            registry_kb=registry_kb,
            appi_kb=appi_kb,
            cca_kb=cca_kb,
            inventory_tool=inventory_tool,
        )
        self._nodes["post_process"] = PostProcessNode()
