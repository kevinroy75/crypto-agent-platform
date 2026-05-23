"""Agent base classes and interfaces."""
from src.agents.base import BaseAgent, AgentResult
from src.agents.orchestrator import OrchestratorAgent
from src.agents.onchain import OnChainAgent
from src.agents.market import MarketAgent
from src.agents.research import ResearchAgent

__all__ = [
    "BaseAgent",
    "AgentResult",
    "OrchestratorAgent",
    "OnChainAgent",
    "MarketAgent",
    "ResearchAgent",
]
