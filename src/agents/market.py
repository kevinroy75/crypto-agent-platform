"""
Market Agent: DEX/CEX price feeds, liquidity analysis, arbitrage detection.
"""
import json
import logging

import httpx

from src.agents.base import BaseAgent, Tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Market Agent specializing in DEX and CEX market analysis.

Your capabilities:
- Price aggregation: real-time prices from Jupiter (Solana), Uniswap V3 (EVM), 1inch
- Liquidity analysis: pool depth, TVL, volume, fee tiers
- Arbitrage detection: cross-DEX and cross-chain price discrepancies
- Impermanent loss calculator: IL estimation for LP positions
- Token discovery: new pool creation, trending tokens, volume spikes

Output: structured data with specific numbers, percentages, and actionable insights.
Always include: token pair, price, 24h change, liquidity depth, and volume when reporting."""


class MarketAgent(BaseAgent):
    """Agent for market and DEX analysis."""

    def __init__(self, verbose: bool = False, **kwargs):
        super().__init__(
            name="MarketAgent",
            system_prompt=SYSTEM_PROMPT,
            verbose=verbose,
            **kwargs,
        )

    def _register_tools(self):
        self.add_tool(Tool(
            name="get_token_price",
            description="Get current price and 24h stats for a token from CoinGecko.",
            parameters={
                "type": "object",
                "properties": {
                    "token_id": {"type": "string", "description": "CoinGecko token ID (e.g., 'ethereum', 'solana', 'bitcoin')"},
                    "vs_currency": {"type": "string", "description": "Quote currency (default: usd)"},
                },
                "required": ["token_id"],
            },
            function=self._get_price,
        ))

        self.add_tool(Tool(
            name="get_jupiter_quote",
            description="Get a swap quote from Jupiter DEX on Solana. Returns price impact, routes, and output amount.",
            parameters={
                "type": "object",
                "properties": {
                    "input_mint": {"type": "string", "description": "Input token mint address"},
                    "output_mint": {"type": "string", "description": "Output token mint address"},
                    "amount": {"type": "string", "description": "Input amount in smallest unit (lamports)"},
                },
                "required": ["input_mint", "output_mint", "amount"],
            },
            function=self._jupiter_quote,
        ))

        self.add_tool(Tool(
            name="get_trending_tokens",
            description="Get trending tokens on CoinGecko with 24h price change and volume.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of tokens to return (default 10)"},
                },
            },
            function=self._trending,
        ))

        self.add_tool(Tool(
            name="calculate_impermanent_loss",
            description="Calculate impermanent loss for an LP position given price change ratio.",
            parameters={
                "type": "object",
                "properties": {
                    "price_ratio": {"type": "number", "description": "Price change ratio (e.g., 2.0 means price doubled, 0.5 means halved)"},
                },
                "required": ["price_ratio"],
            },
            function=self._calc_il,
        ))

        self.add_tool(Tool(
            name="get_top_pairs",
            description="Get top trading pairs by volume on a DEX.",
            parameters={
                "type": "object",
                "properties": {
                    "dex": {"type": "string", "enum": ["jupiter", "uniswap_v3"], "description": "DEX to query"},
                    "limit": {"type": "integer", "description": "Number of pairs (default 10)"},
                },
                "required": ["dex"],
            },
            function=self._top_pairs,
        ))

    async def _get_price(self, token_id: str, vs_currency: str = "usd") -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": token_id,
                    "vs_currencies": vs_currency,
                    "include_24hr_change": "true",
                    "include_24hr_vol": "true",
                    "include_market_cap": "true",
                },
            )
            data = resp.json()
            if token_id in data:
                info = data[token_id]
                return json.dumps({
                    "token": token_id,
                    "price": info.get(f"{vs_currency}", 0),
                    "change_24h_pct": round(info.get(f"{vs_currency}_24h_change", 0), 2),
                    "volume_24h": info.get(f"{vs_currency}_24h_vol", 0),
                    "market_cap": info.get(f"{vs_currency}_market_cap", 0),
                }, indent=2)
            return json.dumps({"error": "Token not found", "raw": data})

    async def _jupiter_quote(self, input_mint: str, output_mint: str, amount: str) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://quote-api.jup.ag/v6/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": amount,
                    "slippageBps": 50,
                },
            )
            data = resp.json()
            if "outAmount" in data:
                return json.dumps({
                    "input_mint": input_mint,
                    "output_mint": output_mint,
                    "in_amount": amount,
                    "out_amount": data["outAmount"],
                    "price_impact_pct": data.get("priceImpactPct", "N/A"),
                    "route_plan": len(data.get("routePlan", [])),
                    "slippage_bps": 50,
                }, indent=2)
            return json.dumps({"error": "No route found", "raw": data})

    async def _trending(self, limit: int = 10) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.coingecko.com/api/v3/search/trending")
            data = resp.json()
            coins = data.get("coins", [])[:limit]
            result = []
            for coin in coins:
                item = coin.get("item", {})
                result.append({
                    "name": item.get("name"),
                    "symbol": item.get("symbol"),
                    "market_cap_rank": item.get("market_cap_rank"),
                    "price_btc": item.get("price_btc"),
                    "score": item.get("score"),
                })
            return json.dumps({"trending_tokens": result, "count": len(result)}, indent=2)

    async def _calc_il(self, price_ratio: float) -> str:
        """Calculate impermanent loss for a 50/50 LP position."""
        import math
        il = 2 * math.sqrt(price_ratio) / (1 + price_ratio) - 1
        il_pct = il * 100

        return json.dumps({
            "price_ratio": price_ratio,
            "impermanent_loss_pct": round(il_pct, 4),
            "explanation": f"If price changes by {price_ratio}x, LP position loses {abs(il_pct):.2f}% vs holding",
            "hold_value_ratio": (1 + price_ratio) / 2,
            "lp_value_ratio": math.sqrt(price_ratio),
        }, indent=2)

    async def _top_pairs(self, dex: str, limit: int = 10) -> str:
        if dex == "jupiter":
            async with httpx.AsyncClient() as client:
                resp = await client.get("https://stats.jup.ag/info/day")
                data = resp.json()
                return json.dumps({
                    "dex": "jupiter",
                    "top_pairs": data.get("topPairs", [])[:limit],
                }, indent=2)
        return json.dumps({"dex": dex, "status": "not_implemented"})
