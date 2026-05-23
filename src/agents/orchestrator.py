"""
Orchestrator Agent: routes tasks to specialist agents and synthesizes results.
Uses a supervisor pattern with task decomposition.
"""
import json
import logging
from typing import Optional

from src.agents.base import BaseAgent, AgentResult, Tool
from src.agents.onchain import OnChainAgent
from src.agents.market import MarketAgent
from src.agents.research import ResearchAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Orchestrator of a multi-agent crypto research platform.

Your job:
1. Analyze the user's request and decompose it into sub-tasks
2. Route each sub-task to the most appropriate specialist agent
3. Synthesize the results into a coherent, actionable report

Available specialist agents:
- onchain: On-chain analysis (wallet tracking, whale movements, smart contract analysis, token flows)
- market: Market analysis (DEX prices, liquidity, arbitrage, impermanent loss, cross-exchange data)
- research: Research & intelligence (paper summaries, news aggregation, sentiment, protocol docs)

Strategy:
- For simple requests, use ONE agent directly
- For complex requests, decompose into 2-3 sub-tasks and run them sequentially
- Always synthesize agent outputs into a clear final answer with actionable insights
- Include specific numbers, addresses, and data points when available
- Flag risks and uncertainties explicitly

Output format: structured analysis with sections, bullet points, and a conclusion."""


class OrchestratorAgent(BaseAgent):
    """Top-level orchestrator that delegates to specialist agents."""

    def __init__(self, verbose: bool = False, **kwargs):
        super().__init__(
            name="Orchestrator",
            system_prompt=SYSTEM_PROMPT,
            verbose=verbose,
            **kwargs,
        )
        self.specialists = {
            "onchain": OnChainAgent(verbose=verbose),
            "market": MarketAgent(verbose=verbose),
            "research": ResearchAgent(verbose=verbose),
        }

    def _register_tools(self):
        self.add_tool(Tool(
            name="delegate_to_onchain",
            description="Delegate a task to the On-Chain Agent for blockchain analysis. Use for: wallet analysis, whale tracking, smart contract investigation, token flow analysis.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The specific analysis task to perform",
                    }
                },
                "required": ["task"],
            },
            function=self._delegate_onchain,
        ))

        self.add_tool(Tool(
            name="delegate_to_market",
            description="Delegate a task to the Market Agent for DEX/CEX analysis. Use for: price data, liquidity analysis, arbitrage detection, IL calculation.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The specific market analysis task",
                    }
                },
                "required": ["task"],
            },
            function=self._delegate_market,
        ))

        self.add_tool(Tool(
            name="delegate_to_research",
            description="Delegate a task to the Research Agent for papers/news/sentiment. Use for: paper search, news aggregation, sentiment analysis, protocol research.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "The specific research task",
                    }
                },
                "required": ["task"],
            },
            function=self._delegate_research,
        ))

    async def _delegate_onchain(self, task: str) -> str:
        result = await self.specialists["onchain"].think(task)
        return result.output

    async def _delegate_market(self, task: str) -> str:
        result = await self.specialists["market"].think(task)
        return result.output

    async def _delegate_research(self, task: str) -> str:
        result = await self.specialists["research"].think(task)
        return result.output

    async def execute(self, task: str) -> AgentResult:
        """Execute a top-level task through the multi-agent pipeline."""
        if self.verbose:
            logger.info(f"[Orchestrator] Starting task: {task}")

        # Reset all agents for fresh context
        self.reset()
        for agent in self.specialists.values():
            agent.reset()

        return await self.think(task)
