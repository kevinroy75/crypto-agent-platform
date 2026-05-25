"""
Tools module for the crypto-agent-platform.

Provides blockchain query tools, market data aggregators, and research utilities.
All tools inherit from BaseTool and expose an async ``execute()`` interface.
"""
from .base import BaseTool, RateLimitConfig, RetryConfig, TokenBucketRateLimiter
from .blockchain import EtherscanTool, SolscanTool, Web3RPCTool
from .market import (
    CoinGeckoTool,
    DeFiCalculatorTool,
    JupiterTool,
    OneInchTool,
    UniswapTool,
)
from .research import (
    ArxivTool,
    CryptoNewsTool,
    SentimentTool,
    WebFetchTool,
    WebSearchTool,
)

__all__ = [
    # Base
    "BaseTool",
    "RateLimitConfig",
    "RetryConfig",
    "TokenBucketRateLimiter",
    # Blockchain
    "EtherscanTool",
    "SolscanTool",
    "Web3RPCTool",
    # Market
    "CoinGeckoTool",
    "DeFiCalculatorTool",
    "JupiterTool",
    "OneInchTool",
    "UniswapTool",
    # Research
    "ArxivTool",
    "CryptoNewsTool",
    "SentimentTool",
    "WebFetchTool",
    "WebSearchTool",
]

# ── Convenience registry ──────────────────────────────────────────────

TOOL_REGISTRY: dict[str, type[BaseTool]] = {
    cls.name if hasattr(cls, "name") and isinstance(cls.name, str) else cls.__name__.lower(): cls
    for cls in [
        EtherscanTool,
        SolscanTool,
        Web3RPCTool,
        CoinGeckoTool,
        JupiterTool,
        UniswapTool,
        OneInchTool,
        DeFiCalculatorTool,
        ArxivTool,
        CryptoNewsTool,
        WebFetchTool,
        SentimentTool,
        WebSearchTool,
    ]
}


def get_tool(name: str, **kwargs) -> BaseTool:
    """
    Instantiate a tool by its registered name.

    >>> tool = get_tool("etherscan", api_key="...")
    >>> result = await tool.execute(action="balance", address="0x...")
    """
    cls = TOOL_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown tool: {name!r}. Available: {list(TOOL_REGISTRY)}")
    return cls(**kwargs)
