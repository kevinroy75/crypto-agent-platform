"""
Example: DeFi Opportunity Scanner

Multi-agent pipeline to find undervalued DeFi tokens:
- Research Agent: scans trending tokens and recent news
- Market Agent: checks prices, volume, and liquidity
- On-Chain Agent: verifies on-chain activity (holders, transactions)
- Orchestrator: synthesizes into ranked opportunity list
"""
import asyncio
from src.agents.orchestrator import OrchestratorAgent


async def main():
    agent = OrchestratorAgent(verbose=True)

    task = """
    Find 5 potentially undervalued DeFi tokens:
    1. Get the current trending tokens on CoinGecko
    2. For each trending token, check price, 24h volume, and market cap
    3. Research any recent partnerships, upgrades, or news
    4. Calculate impermanent loss risk for LP positions at current price levels
    5. Rank by potential (considering: low market cap, high volume, positive news, low IL risk)
    
    Provide a final ranked list with reasoning for each pick.
    """

    result = await agent.execute(task)

    print("=" * 60)
    print("DEFI OPPORTUNITY SCAN")
    print("=" * 60)
    print(result.output)


if __name__ == "__main__":
    asyncio.run(main())
