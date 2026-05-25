"""
Market data tools: Jupiter, Uniswap, 1inch, and CoinGecko aggregators.
"""
import asyncio
import logging
import math
from typing import Any, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

COINGECKO_API = "https://api.coingecko.com/api/v3"
JUPITER_API = "https://quote-api.jup.ag/v6"
UNISWAP_SUBGRAPH = "https://api.thegraph.com/subgraphs/name/uniswap/uniswap-v3"
ONEINCH_API = "https://api.1inch.dev"


# ═══════════════════════════════════════════════════════════════════════
# CoinGecko Tool
# ═══════════════════════════════════════════════════════════════════════

class CoinGeckoTool(BaseTool):
    """Fetch token prices, market data, and trending coins from CoinGecko."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(timeout=15.0, **kwargs)
        self._api_key = api_key or self._env("COINGECKO_API_KEY")
        self._base_url = (
            "https://pro-api.coingecko.com/api/v3" if self._api_key else COINGECKO_API
        )

    @property
    def name(self) -> str:
        return "coingecko"

    @property
    def description(self) -> str:
        return (
            "Get token prices, market caps, 24h volume, trending coins, "
            "and historical market data from CoinGecko."
        )

    def _cg_headers(self) -> dict[str, str]:
        if self._api_key:
            return {"x-cg-pro-api-key": self._api_key}
        return {}

    async def get_token_price(
        self,
        ids: str | list[str],
        vs_currencies: str = "usd",
        include_market_cap: bool = True,
        include_24hr_change: bool = True,
    ) -> dict:
        """Get current price for one or more tokens."""
        try:
            id_str = ids if isinstance(ids, str) else ",".join(ids)
            result = await self._get(
                f"{self._base_url}/simple/price",
                params={
                    "ids": id_str,
                    "vs_currencies": vs_currencies,
                    "include_market_cap": str(include_market_cap).lower(),
                    "include_24hr_change": str(include_24hr_change).lower(),
                },
                headers=self._cg_headers(),
            )
            return self.success(result, meta={"source": "coingecko"})
        except Exception as exc:
            logger.error(f"CoinGecko price error: {exc}")
            return self.error(str(exc), code="CG_PRICE_ERROR")

    async def get_trending_tokens(self) -> dict:
        """Get the top 7 trending coins on CoinGecko."""
        try:
            result = await self._get(
                f"{self._base_url}/search/trending",
                headers=self._cg_headers(),
            )
            coins = result.get("coins", []) if isinstance(result, dict) else []
            trending = [
                {
                    "id": c.get("item", {}).get("id"),
                    "name": c.get("item", {}).get("name"),
                    "symbol": c.get("item", {}).get("symbol"),
                    "market_cap_rank": c.get("item", {}).get("market_cap_rank"),
                    "score": c.get("item", {}).get("score"),
                }
                for c in coins
            ]
            return self.success({"trending": trending, "count": len(trending)})
        except Exception as exc:
            return self.error(str(exc), code="CG_TRENDING_ERROR")

    async def get_market_data(
        self, ids: str | list[str], vs_currency: str = "usd", per_page: int = 50
    ) -> dict:
        """Get detailed market data for specific coins."""
        try:
            id_str = ids if isinstance(ids, str) else ",".join(ids)
            result = await self._get(
                f"{self._base_url}/coins/markets",
                params={
                    "vs_currency": vs_currency,
                    "ids": id_str,
                    "order": "market_cap_desc",
                    "per_page": per_page,
                    "sparkline": "false",
                },
                headers=self._cg_headers(),
            )
            return self.success({"coins": result, "count": len(result) if isinstance(result, list) else 0})
        except Exception as exc:
            return self.error(str(exc), code="CG_MARKET_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "price")
        dispatch = {
            "price": self.get_token_price,
            "trending": lambda **kw: self.get_trending_tokens(),
            "market": self.get_market_data,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Jupiter Tool  (Solana DEX Aggregator)
# ═══════════════════════════════════════════════════════════════════════

class JupiterTool(BaseTool):
    """Get swap quotes and routes from Jupiter Aggregator on Solana."""

    def __init__(self, **kwargs):
        super().__init__(timeout=15.0, **kwargs)

    @property
    def name(self) -> str:
        return "jupiter"

    @property
    def description(self) -> str:
        return (
            "Fetch best-swap quotes and routes from Jupiter on Solana. "
            "Supports SPL token pair pricing and slippage calculations."
        )

    async def get_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: int,
        slippage_bps: int = 50,
    ) -> dict:
        """Get a swap quote from Jupiter."""
        try:
            result = await self._get(
                f"{JUPITER_API}/quote",
                params={
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": str(amount),
                    "slippageBps": slippage_bps,
                },
            )
            if isinstance(result, dict) and "error" in result:
                return self.error(result["error"], code="JUPITER_QUOTE_ERROR")

            return self.success({
                "input_mint": input_mint,
                "output_mint": output_mint,
                "in_amount": result.get("inAmount"),
                "out_amount": result.get("outAmount"),
                "price_impact_pct": result.get("priceImpactPct"),
                "route_plan": result.get("routePlan", []),
                "slippage_bps": slippage_bps,
            }, meta={"source": "jupiter"})
        except Exception as exc:
            return self.error(str(exc), code="JUPITER_QUOTE_ERROR")

    async def get_price(self, ids: str) -> dict:
        """Get current prices for Solana tokens via Jupiter price API."""
        try:
            result = await self._get(
                "https://price.jup.ag/v6/price",
                params={"ids": ids},
            )
            data = result.get("data", {}) if isinstance(result, dict) else {}
            return self.success(data, meta={"source": "jupiter_price"})
        except Exception as exc:
            return self.error(str(exc), code="JUPITER_PRICE_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "quote")
        dispatch = {
            "quote": self.get_quote,
            "price": self.get_price,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Uniswap Tool  (Ethereum DEX via TheGraph)
# ═══════════════════════════════════════════════════════════════════════

class UniswapTool(BaseTool):
    """Query Uniswap V3 data via TheGraph subgraph."""

    def __init__(self, subgraph_url: Optional[str] = None, **kwargs):
        super().__init__(timeout=20.0, **kwargs)
        self._subgraph_url = subgraph_url or self._env(
            "UNISWAP_SUBGRAPH_URL", UNISWAP_SUBGRAPH
        )

    @property
    def name(self) -> str:
        return "uniswap"

    @property
    def description(self) -> str:
        return (
            "Query Uniswap V3 pools, top pairs by TVL, token volumes, "
            "and pool liquidity data via TheGraph."
        )

    async def _graphql_query(self, query: str, variables: Optional[dict] = None) -> dict:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        return await self._post(self._subgraph_url, json_body=payload)

    async def get_top_pairs(self, limit: int = 10) -> dict:
        """Get top Uniswap V3 pools by total value locked."""
        try:
            query = """
            query TopPairs($first: Int!) {
              pools(first: $first, orderBy: totalValueLockedUSD, orderDirection: desc) {
                id
                token0 { id symbol name }
                token1 { id symbol name }
                feeTier
                liquidity
                totalValueLockedUSD
                volumeUSD
                token0Price
                token1Price
              }
            }
            """
            result = await self._graphql_query(query, {"first": limit})
            pools = (
                result.get("data", {}).get("pools", [])
                if isinstance(result, dict)
                else []
            )
            return self.success({"pools": pools, "count": len(pools)}, meta={"source": "uniswap_v3"})
        except Exception as exc:
            return self.error(str(exc), code="UNISWAP_PAIRS_ERROR")

    async def get_pool_info(self, pool_address: str) -> dict:
        """Get detailed information about a specific Uniswap V3 pool."""
        try:
            query = """
            query PoolInfo($id: ID!) {
              pool(id: $id) {
                id
                token0 { id symbol name decimals }
                token1 { id symbol name decimals }
                feeTier
                liquidity
                sqrtPrice
                tick
                totalValueLockedUSD
                totalValueLockedToken0
                totalValueLockedToken1
                volumeUSD
                txCount
                token0Price
                token1Price
              }
            }
            """
            result = await self._graphql_query(query, {"id": pool_address.lower()})
            pool = result.get("data", {}).get("pool") if isinstance(result, dict) else None
            if pool is None:
                return self.error("Pool not found", code="POOL_NOT_FOUND")
            return self.success(pool, meta={"source": "uniswap_v3"})
        except Exception as exc:
            return self.error(str(exc), code="UNISWAP_POOL_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "top_pairs")
        dispatch = {
            "top_pairs": self.get_top_pairs,
            "pool_info": self.get_pool_info,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# 1inch Tool  (EVM DEX Aggregator)
# ═══════════════════════════════════════════════════════════════════════

class OneInchTool(BaseTool):
    """Get swap quotes from 1inch aggregator across EVM chains."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(timeout=15.0, **kwargs)
        self._api_key = api_key or self._env("1INCH_API_KEY")

    @property
    def name(self) -> str:
        return "oneinch"

    @property
    def description(self) -> str:
        return (
            "Get cross-chain swap quotes from 1inch DEX aggregator. "
            "Supports Ethereum, BSC, Polygon, Arbitrum, and Optimism."
        )

    @property
    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    _CHAIN_IDS = {
        "ethereum": 1,
        "bsc": 56,
        "polygon": 137,
        "arbitrum": 42161,
        "optimism": 10,
    }

    async def get_quote(
        self,
        src: str,
        dst: str,
        amount: str,
        chain: str = "ethereum",
    ) -> dict:
        """Get a swap quote from 1inch."""
        try:
            chain_id = self._CHAIN_IDS.get(chain.lower(), 1)
            result = await self._get(
                f"{ONEINCH_API}/swap/v6.0/{chain_id}/quote",
                params={"src": src, "dst": dst, "amount": amount},
                headers=self._headers,
            )
            return self.success({
                "src_token": src,
                "dst_token": dst,
                "src_amount": result.get("srcAmount") if isinstance(result, dict) else amount,
                "dst_amount": result.get("dstAmount") if isinstance(result, dict) else None,
                "protocols": result.get("protocols", []) if isinstance(result, dict) else [],
                "chain": chain,
                "gas_estimate": result.get("gas") if isinstance(result, dict) else None,
            }, meta={"source": "1inch"})
        except Exception as exc:
            return self.error(str(exc), code="1INCH_QUOTE_ERROR")

    async def get_supported_tokens(self, chain: str = "ethereum") -> dict:
        """List tokens supported by 1inch on the given chain."""
        try:
            chain_id = self._CHAIN_IDS.get(chain.lower(), 1)
            result = await self._get(
                f"{ONEINCH_API}/swap/v6.0/{chain_id}/tokens",
                headers=self._headers,
            )
            tokens = result.get("tokens", {}) if isinstance(result, dict) else {}
            return self.success({
                "chain": chain,
                "token_count": len(tokens),
                "tokens": {
                    addr: {
                        "symbol": t.get("symbol"),
                        "name": t.get("name"),
                        "decimals": t.get("decimals"),
                    }
                    for addr, t in list(tokens.items())[:50]
                },
            })
        except Exception as exc:
            return self.error(str(exc), code="1INCH_TOKENS_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "quote")
        dispatch = {
            "quote": self.get_quote,
            "tokens": self.get_supported_tokens,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# DeFi Calculator
# ═══════════════════════════════════════════════════════════════════════

class DeFiCalculatorTool(BaseTool):
    """Pure-calculation DeFi utilities (impermanent loss, IL estimates, etc.)."""

    def __init__(self, **kwargs):
        super().__init__(timeout=5.0, **kwargs)

    @property
    def name(self) -> str:
        return "defi_calculator"

    @property
    def description(self) -> str:
        return (
            "Calculate impermanent loss, yield projections, and other "
            "DeFi metrics for liquidity providers."
        )

    @staticmethod
    def _calc_impermanent_loss(price_ratio: float) -> float:
        """
        Calculate impermanent loss as a percentage.
        price_ratio = current_price / initial_price (of one asset relative to the other).
        """
        if price_ratio <= 0:
            return 0.0
        # IL formula: 2 * sqrt(r) / (1 + r) - 1
        il = (2 * math.sqrt(price_ratio)) / (1 + price_ratio) - 1
        return il * 100  # percentage

    async def calculate_impermanent_loss(
        self,
        initial_price_ratio: float,
        current_price_ratio: float,
        liquidity_usd: float = 10000.0,
    ) -> dict:
        """Calculate the impermanent loss for an LP position."""
        try:
            if initial_price_ratio <= 0 or current_price_ratio <= 0:
                return self.error("Price ratios must be positive", code="INVALID_INPUT")

            ratio = current_price_ratio / initial_price_ratio
            il_pct = self._calc_impermanent_loss(ratio)

            # What the LP position is worth now vs holding
            lp_value = liquidity_usd * ((2 * math.sqrt(ratio)) / (1 + ratio))
            hold_value = liquidity_usd * (1 + ratio) / 2  # equal-weight hold
            il_usd = hold_value - lp_value

            return self.success({
                "initial_price_ratio": initial_price_ratio,
                "current_price_ratio": current_price_ratio,
                "price_change_ratio": ratio,
                "impermanent_loss_pct": round(il_pct, 4),
                "impermanent_loss_usd": round(il_usd, 2),
                "lp_value_usd": round(lp_value, 2),
                "hold_value_usd": round(hold_value, 2),
                "liquidity_usd": liquidity_usd,
            })
        except Exception as exc:
            return self.error(str(exc), code="IL_CALC_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "impermanent_loss")
        if action == "impermanent_loss":
            return await self.calculate_impermanent_loss(**kwargs)
        return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
