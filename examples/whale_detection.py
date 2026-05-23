"""
Example: Whale Movement Detection Pipeline

Demonstrates the multi-agent system analyzing whale activity
across Ethereum and Solana simultaneously.
"""
import asyncio
from src.agents.orchestrator import OrchestratorAgent


async def main():
    agent = OrchestratorAgent(verbose=True)

    # Complex multi-chain analysis task
    task = """
    Analyze recent whale activity on Ethereum and Solana:
    1. Find the top 5 whale wallets on Ethereum by recent large transfers (>500 ETH)
    2. Check current ETH/SOL prices and 24h trends
    3. Research any recent news about whale accumulation patterns
    4. Summarize findings with actionable insights
    """

    result = await agent.execute(task)

    print("=" * 60)
    print("WHALE ANALYSIS REPORT")
    print("=" * 60)
    print(result.output)
    print(f"\nTokens used: {result.tokens_used}")
    print(f"Duration: {result.duration_ms}ms")
    print(f"Iterations: {result.metadata.get('iterations', 'N/A')}")


if __name__ == "__main__":
    asyncio.run(main())
