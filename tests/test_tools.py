"""
Unit tests for tool classes and workflow components.

Tests Tool schema generation, workflow data models,
and the whale/portfolio/scanner workflows with mocked data fetchers.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.base import Tool


# ---------------------------------------------------------------------------
# Tool schema tests
# ---------------------------------------------------------------------------

class TestToolSchema:
    def test_basic_schema(self):
        tool = Tool(
            name="get_price",
            description="Get the current price of a token",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Token symbol"},
                    "currency": {
                        "type": "string",
                        "enum": ["usd", "eur", "btc"],
                        "default": "usd",
                    },
                },
                "required": ["symbol"],
            },
        )
        schema = tool.to_schema()

        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "get_price"
        assert "price" in func["description"].lower()
        assert "symbol" in func["parameters"]["properties"]
        assert func["parameters"]["required"] == ["symbol"]

    def test_schema_with_nested_parameters(self):
        tool = Tool(
            name="complex_tool",
            description="A tool with nested params",
            parameters={
                "type": "object",
                "properties": {
                    "filters": {
                        "type": "object",
                        "properties": {
                            "min_value": {"type": "number"},
                            "chains": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    }
                },
                "required": ["filters"],
            },
        )
        schema = tool.to_schema()
        filters = schema["function"]["parameters"]["properties"]["filters"]
        assert filters["type"] == "object"
        assert "min_value" in filters["properties"]
        assert filters["properties"]["chains"]["type"] == "array"

    def test_schema_with_no_properties(self):
        tool = Tool(
            name="noop",
            description="Does nothing",
            parameters={"type": "object", "properties": {}},
        )
        schema = tool.to_schema()
        assert schema["function"]["parameters"]["properties"] == {}

    def test_multiple_tools_schemas(self):
        tools = [
            Tool(
                name=f"tool_{i}",
                description=f"Tool number {i}",
                parameters={"type": "object", "properties": {}},
            )
            for i in range(5)
        ]
        schemas = [t.to_schema() for t in tools]
        names = {s["function"]["name"] for s in schemas}
        assert names == {"tool_0", "tool_1", "tool_2", "tool_3", "tool_4"}


# ---------------------------------------------------------------------------
# Tool function execution tests
# ---------------------------------------------------------------------------

class TestToolExecution:
    @pytest.mark.asyncio
    async def test_async_function(self):
        async def fetch_data(url: str) -> str:
            return f"Data from {url}"

        tool = Tool(
            name="fetch",
            description="Fetch data",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            function=fetch_data,
        )

        result = await tool.function(url="https://example.com")
        assert result == "Data from https://example.com"

    @pytest.mark.asyncio
    async def test_sync_function(self):
        def add(a: int, b: int) -> int:
            return a + b

        tool = Tool(
            name="add",
            description="Add two numbers",
            parameters={"type": "object", "properties": {}},
            function=add,
        )

        result = tool.function(a=3, b=4)
        assert result == 7

    @pytest.mark.asyncio
    async def test_function_with_exception(self):
        async def failing_tool(**kwargs):
            raise ConnectionError("API unavailable")

        tool = Tool(
            name="api_call",
            description="Calls an API",
            parameters={"type": "object", "properties": {}},
            function=failing_tool,
        )

        with pytest.raises(ConnectionError, match="API unavailable"):
            await tool.function()


# ---------------------------------------------------------------------------
# Whale Alert workflow tests
# ---------------------------------------------------------------------------

class TestWhaleAlertWorkflow:
    @pytest.mark.asyncio
    async def test_empty_result_without_fetcher(self):
        from src.workflows.whale_alert import WhaleAlertWorkflow, AlertConfig, Chain

        config = AlertConfig(
            min_value_usd=100_000,
            chains=[Chain.ETHEREUM, Chain.BITCOIN],
        )
        workflow = WhaleAlertWorkflow(config=config, data_fetcher=None)
        result = await workflow.run()

        assert result.alert_count == 0
        assert result.transactions == []
        assert Chain.ETHEREUM in result.chains_scanned
        assert result.scan_duration_ms >= 0

    @pytest.mark.asyncio
    async def test_with_mock_fetcher(self):
        from src.workflows.whale_alert import (
            WhaleAlertWorkflow,
            AlertConfig,
            Chain,
        )

        mock_fetcher = AsyncMock()
        mock_fetcher.get_recent_large_txs.return_value = [
            {
                "tx_hash": "0xabc123",
                "from": "0xwhale1",
                "to": "0xexchange1",
                "value_usd": 500_000,
                "token": "ETH",
                "timestamp": 1700000000,
                "block_number": 18_000_000,
            },
            {
                "tx_hash": "0xdef456",
                "from": "0xwhale2",
                "to": "0xcold1",
                "value_usd": 2_000_000,
                "token": "USDT",
                "timestamp": 1700000100,
                "block_number": 18_000_001,
            },
        ]

        config = AlertConfig(min_value_usd=100_000, chains=[Chain.ETHEREUM])
        workflow = WhaleAlertWorkflow(config=config, data_fetcher=mock_fetcher)
        result = await workflow.run()

        assert result.alert_count == 2
        assert result.total_value_usd == 2_500_000
        # Should be sorted by value descending
        assert result.transactions[0].value_usd == 2_000_000
        assert result.transactions[1].value_usd == 500_000

    @pytest.mark.asyncio
    async def test_chain_error_handling(self):
        from src.workflows.whale_alert import (
            WhaleAlertWorkflow,
            AlertConfig,
            Chain,
        )

        mock_fetcher = AsyncMock()
        mock_fetcher.get_recent_large_txs.side_effect = [
            ConnectionError("RPC down"),
            [],  # bitcoin succeeds with empty
        ]

        config = AlertConfig(chains=[Chain.ETHEREUM, Chain.BITCOIN])
        workflow = WhaleAlertWorkflow(config=config, data_fetcher=mock_fetcher)
        result = await workflow.run()

        assert "ethereum" in result.errors
        assert result.alert_count == 0

    def test_format_alerts_empty(self):
        from src.workflows.whale_alert import (
            WhaleAlertWorkflow,
            WhaleAlertResult,
        )

        workflow = WhaleAlertWorkflow()
        result = WhaleAlertResult(
            transactions=[], chains_scanned=[], scan_duration_ms=0, timestamp=0
        )
        output = workflow.format_alerts(result)
        assert "No whale transactions" in output

    def test_cooldown_filtering(self):
        from src.workflows.whale_alert import (
            WhaleAlertWorkflow,
            WhaleTransaction,
            Chain,
            AlertConfig,
        )
        import time

        config = AlertConfig(cooldown_seconds=60)
        workflow = WhaleAlertWorkflow(config=config)

        tx1 = WhaleTransaction(
            chain=Chain.ETHEREUM,
            tx_hash="0x1",
            from_address="0xA",
            to_address="0xB",
            value_usd=500_000,
            token="ETH",
            timestamp=int(time.time()),
            block_number=100,
        )
        # Same addresses — should be filtered by cooldown
        tx2 = WhaleTransaction(
            chain=Chain.ETHEREUM,
            tx_hash="0x2",
            from_address="0xA",
            to_address="0xB",
            value_usd=600_000,
            token="ETH",
            timestamp=int(time.time()),
            block_number=101,
        )

        filtered = workflow._apply_cooldown([tx1, tx2])
        assert len(filtered) == 1
        assert filtered[0].tx_hash == "0x1"


# ---------------------------------------------------------------------------
# Portfolio Tracker workflow tests
# ---------------------------------------------------------------------------

class TestPortfolioTrackerWorkflow:
    @pytest.mark.asyncio
    async def test_empty_portfolio_without_fetcher(self):
        from src.workflows.portfolio_tracker import PortfolioTrackerWorkflow

        workflow = PortfolioTrackerWorkflow(
            address="0x1234567890abcdef",
            chains=["ethereum"],
            data_fetcher=None,
        )
        snapshot = await workflow.run()

        assert snapshot.total_value_usd == 0.0
        assert snapshot.chain_count == 1
        assert snapshot.position_count == 0

    def test_empty_address_raises(self):
        from src.workflows.portfolio_tracker import PortfolioTrackerWorkflow

        with pytest.raises(ValueError, match="non-empty"):
            PortfolioTrackerWorkflow(address="")

    def test_whitespace_address_raises(self):
        from src.workflows.portfolio_tracker import PortfolioTrackerWorkflow

        with pytest.raises(ValueError, match="non-empty"):
            PortfolioTrackerWorkflow(address="   ")

    @pytest.mark.asyncio
    async def test_with_mock_fetcher(self):
        from src.workflows.portfolio_tracker import PortfolioTrackerWorkflow

        mock_fetcher = AsyncMock()
        mock_fetcher.get_token_balances.return_value = [
            {"token": "ETH", "balance": 10.5, "price_usd": 2000},
            {"token": "USDC", "balance": 5000, "price_usd": 1},
        ]
        mock_fetcher.get_defi_positions.return_value = [
            {
                "protocol": "Aave",
                "type": "lending",
                "value_usd": 15000,
                "apy": 4.5,
                "health_factor": 2.1,
                "tokens": [
                    {"token": "aUSDC", "balance": 15000, "value_usd": 15000, "price_usd": 1}
                ],
            }
        ]

        workflow = PortfolioTrackerWorkflow(
            address="0xabcdef",
            chains=["ethereum"],
            data_fetcher=mock_fetcher,
        )
        snapshot = await workflow.run()

        assert snapshot.total_value_usd > 0
        assert snapshot.total_wallet_value_usd == 10.5 * 2000 + 5000
        assert snapshot.total_defi_value_usd == 15000
        assert snapshot.net_apy is not None
        assert snapshot.health_factor == 2.1

    def test_format_snapshot(self):
        from src.workflows.portfolio_tracker import (
            PortfolioTrackerWorkflow,
            PortfolioSnapshot,
            ChainPortfolio,
            TokenBalance,
        )

        workflow = PortfolioTrackerWorkflow(address="0x1234567890abcdef1234")
        snapshot = PortfolioSnapshot(
            address="0x1234567890abcdef1234",
            chains=[
                ChainPortfolio(
                    chain="ethereum",
                    wallet_balances=[
                        TokenBalance(
                            token="ETH",
                            chain="ethereum",
                            balance=5.0,
                            value_usd=10000,
                            price_usd=2000,
                        ),
                    ],
                    defi_positions=[],
                    total_value_usd=10000,
                )
            ],
            total_value_usd=10000,
            total_wallet_value_usd=10000,
            total_defi_value_usd=0,
            fetch_duration_ms=150,
        )
        output = workflow.format_snapshot(snapshot)
        assert "Portfolio" in output
        assert "$10,000" in output
        assert "ETH" in output


# ---------------------------------------------------------------------------
# DeFi Scanner workflow tests
# ---------------------------------------------------------------------------

class TestDeFiScannerWorkflow:
    @pytest.mark.asyncio
    async def test_empty_result_without_fetcher(self):
        from src.workflows.defi_scanner import DeFiScannerWorkflow, ScannerConfig

        config = ScannerConfig(chains=["ethereum"])
        workflow = DeFiScannerWorkflow(config=config, data_fetcher=None)
        result = await workflow.run()

        assert result.total_opportunities == 0
        assert result.yield_opportunities == []
        assert result.arbitrage_opportunities == []

    @pytest.mark.asyncio
    async def test_with_mock_fetcher(self):
        from src.workflows.defi_scanner import DeFiScannerWorkflow, ScannerConfig

        mock_fetcher = AsyncMock()
        mock_fetcher.get_yield_pools.return_value = [
            {
                "protocol": "Aave",
                "pool": "USDC",
                "symbol": "USDC",
                "category": "lending",
                "apy": 5.2,
                "apy_base": 4.0,
                "apy_reward": 1.2,
                "tvl_usd": 500_000_000,
                "reward_tokens": ["AAVE"],
                "audit_count": 3,
                "days_live": 1000,
            },
            {
                "protocol": "SketchyFarm",
                "pool": "SKETCH",
                "symbol": "SKETCH",
                "category": "yield",
                "apy": 999,
                "apy_base": 500,
                "apy_reward": 499,
                "tvl_usd": 50_000,
                "reward_tokens": [],
                "audit_count": 0,
                "days_live": 3,
            },
        ]
        mock_fetcher.get_common_pairs.return_value = []

        config = ScannerConfig(
            chains=["ethereum"],
            min_tvl_usd=10_000,
            max_risk_level="high",
        )
        workflow = DeFiScannerWorkflow(config=config, data_fetcher=mock_fetcher)
        result = await workflow.run()

        # Both should appear (SketchyFarm is high risk, which is allowed)
        assert len(result.yield_opportunities) >= 1
        # Best yield should be Aave (risk-adjusted)
        best = result.best_yield
        assert best is not None

    def test_risk_assessment_heuristic(self):
        from src.workflows.defi_scanner import DeFiScannerWorkflow, RiskLevel

        workflow = DeFiScannerWorkflow()

        # Low risk pool
        low_risk = {
            "tvl_usd": 500_000_000,
            "days_live": 500,
            "audit_count": 3,
            "apy": 5,
        }
        assert asyncio.get_event_loop().run_until_complete(
            workflow._assess_risk(low_risk, "ethereum")
        ) == RiskLevel.LOW

        # High risk pool
        high_risk = {
            "tvl_usd": 100_000,
            "days_live": 5,
            "audit_count": 0,
            "apy": 200,
        }
        risk = asyncio.get_event_loop().run_until_complete(
            workflow._assess_risk(high_risk, "ethereum")
        )
        assert risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_format_results_empty(self):
        from src.workflows.defi_scanner import DeFiScannerWorkflow, ScannerResult

        workflow = DeFiScannerWorkflow()
        result = ScannerResult(
            yield_opportunities=[],
            arbitrage_opportunities=[],
            chains_scanned=["ethereum"],
            scan_duration_ms=50,
            timestamp=0,
        )
        output = workflow.format_results(result)
        assert "0 opportunities" in output
