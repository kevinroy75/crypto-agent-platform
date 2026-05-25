"""
DeFi Opportunity Scanner Workflow.

Scans DeFi protocols across multiple chains for yield opportunities,
arbitrage opportunities, and risk assessments.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class OpportunityType(str, Enum):
    """Categories of DeFi opportunities."""
    YIELD = "yield"
    ARBITRAGE = "arbitrage"
    LIQUIDATION = "liquidation"
    AIRDROP = "airdrop"
    NEW_POOL = "new_pool"
    LEVERAGED_YIELD = "leveraged_yield"


class RiskLevel(str, Enum):
    """Risk classification for DeFi opportunities."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DeFiProtocol:
    """Metadata about a DeFi protocol."""
    name: str
    chain: str
    category: str  # lending, dex, yield, derivatives, etc.
    tvl_usd: float
    url: str | None = None
    audit_count: int = 0
    days_live: int = 0


@dataclass
class YieldOpportunity:
    """A yield-bearing DeFi opportunity."""
    protocol: DeFiProtocol
    pool_name: str
    apy: float
    apy_base: float
    apy_reward: float
    tvl_usd: float
    token_pair: str
    risk_level: RiskLevel
    opportunity_type: OpportunityType = OpportunityType.YIELD
    impermanent_loss_risk: float | None = None
    chain: str = ""
    reward_tokens: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def risk_adjusted_apy(self) -> float:
        """APY adjusted for risk level."""
        risk_multipliers = {
            RiskLevel.LOW: 1.0,
            RiskLevel.MEDIUM: 0.85,
            RiskLevel.HIGH: 0.65,
            RiskLevel.CRITICAL: 0.4,
        }
        return round(self.apy * risk_multipliers.get(self.risk_level, 0.5), 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol.name,
            "chain": self.chain or self.protocol.chain,
            "pool": self.pool_name,
            "token_pair": self.token_pair,
            "apy": self.apy,
            "apy_base": self.apy_base,
            "apy_reward": self.apy_reward,
            "tvl_usd": self.tvl_usd,
            "risk_level": self.risk_level.value,
            "risk_adjusted_apy": self.risk_adjusted_apy,
            "opportunity_type": self.opportunity_type.value,
            "reward_tokens": self.reward_tokens,
            "warnings": self.warnings,
        }


@dataclass
class ArbitrageOpportunity:
    """A cross-DEX or cross-chain arbitrage opportunity."""
    token: str
    buy_chain: str
    buy_dex: str
    buy_price: float
    sell_chain: str
    sell_dex: str
    sell_price: float
    spread_pct: float
    estimated_profit_usd: float
    max_size_usd: float
    gas_cost_usd: float
    risk_level: RiskLevel = RiskLevel.MEDIUM
    warnings: list[str] = field(default_factory=list)

    @property
    def net_profit_usd(self) -> float:
        return self.estimated_profit_usd - self.gas_cost_usd

    @property
    def is_profitable(self) -> bool:
        return self.net_profit_usd > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "buy": f"{self.buy_dex} ({self.buy_chain}) @ ${self.buy_price:.6f}",
            "sell": f"{self.sell_dex} ({self.sell_chain}) @ ${self.sell_price:.6f}",
            "spread_pct": self.spread_pct,
            "gross_profit_usd": self.estimated_profit_usd,
            "gas_cost_usd": self.gas_cost_usd,
            "net_profit_usd": self.net_profit_usd,
            "is_profitable": self.is_profitable,
            "max_size_usd": self.max_size_usd,
            "risk_level": self.risk_level.value,
        }


@dataclass
class ScannerConfig:
    """Configuration for the DeFi scanner."""
    chains: list[str] = field(
        default_factory=lambda: ["ethereum", "arbitrum", "base", "solana"]
    )
    min_tvl_usd: float = 1_000_000.0
    min_apy: float = 1.0
    max_apy: float = 500.0  # Flag suspiciously high APY
    max_risk_level: RiskLevel = RiskLevel.HIGH
    opportunity_types: list[OpportunityType] = field(
        default_factory=lambda: list(OpportunityType)
    )
    exclude_protocols: set[str] = field(default_factory=set)
    min_audit_count: int = 0
    min_days_live: int = 7


@dataclass
class ScannerResult:
    """Results from a DeFi scan."""
    yield_opportunities: list[YieldOpportunity]
    arbitrage_opportunities: list[ArbitrageOpportunity]
    chains_scanned: list[str]
    scan_duration_ms: int
    timestamp: int
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total_opportunities(self) -> int:
        return len(self.yield_opportunities) + len(self.arbitrage_opportunities)

    @property
    def best_yield(self) -> YieldOpportunity | None:
        if not self.yield_opportunities:
            return None
        return max(self.yield_opportunities, key=lambda o: o.risk_adjusted_apy)

    @property
    def best_arbitrage(self) -> ArbitrageOpportunity | None:
        profitable = [a for a in self.arbitrage_opportunities if a.is_profitable]
        if not profitable:
            return None
        return max(profitable, key=lambda a: a.net_profit_usd)

    def to_dict(self) -> dict[str, Any]:
        return {
            "yield_opportunities": [o.to_dict() for o in self.yield_opportunities],
            "arbitrage_opportunities": [
                a.to_dict() for a in self.arbitrage_opportunities
            ],
            "chains_scanned": self.chains_scanned,
            "total_opportunities": self.total_opportunities,
            "scan_duration_ms": self.scan_duration_ms,
            "timestamp": self.timestamp,
            "errors": self.errors,
        }


class DeFiScannerWorkflow:
    """
    DeFi opportunity scanner workflow.

    Scans multiple chains and protocols for yield, arbitrage,
    and liquidation opportunities. Applies risk assessment and
    returns filtered, ranked results.
    """

    def __init__(
        self,
        config: ScannerConfig | None = None,
        data_fetcher: Any | None = None,
        risk_assessor: Any | None = None,
    ) -> None:
        self.config = config or ScannerConfig()
        self._fetcher = data_fetcher
        self._risk_assessor = risk_assessor

    async def run(self) -> ScannerResult:
        """Execute a full DeFi opportunity scan."""
        start = time.monotonic()
        now = int(time.time())

        logger.info(
            "Starting DeFi scan: chains=%s, min_apy=%.1f%%, min_tvl=$%s",
            self.config.chains,
            self.config.min_apy,
            f"{self.config.min_tvl_usd:,.0f}",
        )

        # Run yield and arbitrage scans concurrently
        yield_task = self._scan_yields()
        arb_task = self._scan_arbitrage()

        yield_results, arb_results = await asyncio.gather(
            yield_task, arb_task, return_exceptions=True
        )

        errors: dict[str, str] = {}

        # Process yield results
        yield_opportunities: list[YieldOpportunity] = []
        if isinstance(yield_results, Exception):
            logger.error("Yield scan failed: %s", yield_results)
            errors["yield_scan"] = str(yield_results)
        else:
            yield_opportunities = yield_results

        # Process arbitrage results
        arb_opportunities: list[ArbitrageOpportunity] = []
        if isinstance(arb_results, Exception):
            logger.error("Arbitrage scan failed: %s", arb_results)
            errors["arbitrage_scan"] = str(arb_results)
        else:
            arb_opportunities = arb_results

        # Apply filters
        yield_opportunities = self._filter_yields(yield_opportunities)
        arb_opportunities = self._filter_arbitrage(arb_opportunities)

        # Sort by risk-adjusted returns
        yield_opportunities.sort(key=lambda o: o.risk_adjusted_apy, reverse=True)
        arb_opportunities.sort(key=lambda a: a.net_profit_usd, reverse=True)

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "DeFi scan complete: %d yield + %d arb opportunities in %dms",
            len(yield_opportunities),
            len(arb_opportunities),
            duration_ms,
        )

        return ScannerResult(
            yield_opportunities=yield_opportunities,
            arbitrage_opportunities=arb_opportunities,
            chains_scanned=self.config.chains,
            scan_duration_ms=duration_ms,
            timestamp=now,
            errors=errors,
        )

    async def _scan_yields(self) -> list[YieldOpportunity]:
        """Scan for yield opportunities across all chains."""
        if self._fetcher is None:
            return []

        all_opportunities: list[YieldOpportunity] = []

        for chain in self.config.chains:
            try:
                pools = await self._fetcher.get_yield_pools(
                    chain=chain,
                    min_tvl=self.config.min_tvl_usd,
                )

                for pool in pools:
                    protocol_name = pool.get("protocol", "unknown")

                    # Skip excluded protocols
                    if protocol_name.lower() in {
                        p.lower() for p in self.config.exclude_protocols
                    }:
                        continue

                    apy = float(pool.get("apy", 0))
                    if apy < self.config.min_apy:
                        continue

                    # Assess risk
                    risk = await self._assess_risk(pool, chain)

                    protocol = DeFiProtocol(
                        name=protocol_name,
                        chain=chain,
                        category=pool.get("category", "unknown"),
                        tvl_usd=float(pool.get("tvl_usd", 0)),
                        url=pool.get("url"),
                        audit_count=int(pool.get("audit_count", 0)),
                        days_live=int(pool.get("days_live", 0)),
                    )

                    warnings: list[str] = []
                    if apy > self.config.max_apy:
                        warnings.append(
                            f"APY ({apy:.1f}%) exceeds configured maximum "
                            f"({self.config.max_apy:.1f}%) — possible unsustainability"
                        )

                    all_opportunities.append(
                        YieldOpportunity(
                            protocol=protocol,
                            pool_name=pool.get("pool", "unknown"),
                            apy=apy,
                            apy_base=float(pool.get("apy_base", 0)),
                            apy_reward=float(pool.get("apy_reward", 0)),
                            tvl_usd=float(pool.get("tvl_usd", 0)),
                            token_pair=pool.get("symbol", "UNKNOWN"),
                            risk_level=risk,
                            chain=chain,
                            reward_tokens=pool.get("reward_tokens", []),
                            warnings=warnings,
                        )
                    )

            except Exception as e:
                logger.warning("Yield scan failed for %s: %s", chain, e)

        return all_opportunities

    async def _scan_arbitrage(self) -> list[ArbitrageOpportunity]:
        """Scan for arbitrage opportunities across DEXs and chains."""
        if self._fetcher is None:
            return []

        opportunities: list[ArbitrageOpportunity] = []

        try:
            pairs = await self._fetcher.get_common_pairs(chains=self.config.chains)

            for pair_data in pairs:
                prices = pair_data.get("prices", [])
                if len(prices) < 2:
                    continue

                # Find best buy and sell
                prices.sort(key=lambda p: p.get("price", float("inf")))
                buy = prices[0]
                sell = prices[-1]

                buy_price = float(buy.get("price", 0))
                sell_price = float(sell.get("price", 0))

                if buy_price <= 0:
                    continue

                spread_pct = ((sell_price - buy_price) / buy_price) * 100

                if spread_pct < 0.1:  # Minimum 0.1% spread
                    continue

                max_size = float(pair_data.get("max_size_usd", 10_000))
                estimated_profit = max_size * (spread_pct / 100)
                gas_cost = float(pair_data.get("gas_cost_usd", 5.0))

                opportunities.append(
                    ArbitrageOpportunity(
                        token=pair_data.get("symbol", "UNKNOWN"),
                        buy_chain=buy.get("chain", "unknown"),
                        buy_dex=buy.get("dex", "unknown"),
                        buy_price=buy_price,
                        sell_chain=sell.get("chain", "unknown"),
                        sell_dex=sell.get("dex", "unknown"),
                        sell_price=sell_price,
                        spread_pct=round(spread_pct, 4),
                        estimated_profit_usd=round(estimated_profit, 2),
                        max_size_usd=max_size,
                        gas_cost_usd=gas_cost,
                        warnings=[],
                    )
                )

        except Exception as e:
            logger.warning("Arbitrage scan failed: %s", e)

        return opportunities

    async def _assess_risk(self, pool: dict, chain: str) -> RiskLevel:
        """Assess the risk level of a DeFi pool."""
        if self._risk_assessor:
            try:
                return await self._risk_assessor.assess(pool, chain)
            except Exception as e:
                logger.debug("Risk assessor failed, using heuristic: %s", e)

        # Fallback heuristic risk assessment
        risk_score = 0

        tvl = float(pool.get("tvl_usd", 0))
        if tvl < 1_000_000:
            risk_score += 2
        elif tvl < 10_000_000:
            risk_score += 1

        days = int(pool.get("days_live", 0))
        if days < 30:
            risk_score += 2
        elif days < 90:
            risk_score += 1

        audits = int(pool.get("audit_count", 0))
        if audits == 0:
            risk_score += 2
        elif audits == 1:
            risk_score += 1

        apy = float(pool.get("apy", 0))
        if apy > 100:
            risk_score += 2
        elif apy > 50:
            risk_score += 1

        if risk_score >= 5:
            return RiskLevel.CRITICAL
        elif risk_score >= 3:
            return RiskLevel.HIGH
        elif risk_score >= 2:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _filter_yields(
        self, opportunities: list[YieldOpportunity]
    ) -> list[YieldOpportunity]:
        """Apply configured filters to yield opportunities."""
        risk_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }
        max_risk = risk_order.get(self.config.max_risk_level, 2)

        return [
            o
            for o in opportunities
            if risk_order.get(o.risk_level, 3) <= max_risk
        ]

    def _filter_arbitrage(
        self, opportunities: list[ArbitrageOpportunity]
    ) -> list[ArbitrageOpportunity]:
        """Apply configured filters to arbitrage opportunities."""
        return [a for a in opportunities if a.is_profitable]

    def format_results(self, result: ScannerResult) -> str:
        """Format scanner results as a human-readable string."""
        lines = [
            "🔍 **DeFi Scanner Results**",
            f"Found {result.total_opportunities} opportunities "
            f"across {len(result.chains_scanned)} chains",
            "",
        ]

        # Top yield opportunities
        if result.yield_opportunities:
            lines.append("**Top Yield Opportunities:**")
            for opp in result.yield_opportunities[:10]:
                risk_emoji = {
                    RiskLevel.LOW: "🟢",
                    RiskLevel.MEDIUM: "🟡",
                    RiskLevel.HIGH: "🟠",
                    RiskLevel.CRITICAL: "🔴",
                }.get(opp.risk_level, "⚪")

                lines.append(
                    f"  {risk_emoji} **{opp.protocol.name}** ({opp.chain}) — "
                    f"{opp.token_pair}\n"
                    f"    APY: {opp.apy:.1f}% "
                    f"(base: {opp.apy_base:.1f}% + rewards: {opp.apy_reward:.1f}%) "
                    f"| TVL: ${opp.tvl_usd:,.0f}\n"
                    f"    Risk-adjusted APY: {opp.risk_adjusted_apy:.1f}%"
                )
                for warning in opp.warnings:
                    lines.append(f"    ⚠️ {warning}")

        # Arbitrage opportunities
        if result.arbitrage_opportunities:
            lines.append("\n**Arbitrage Opportunities:**")
            for arb in result.arbitrage_opportunities[:5]:
                lines.append(
                    f"  • **{arb.token}** — spread {arb.spread_pct:.2f}%\n"
                    f"    Buy: {arb.buy_dex} ({arb.buy_chain}) @ ${arb.buy_price:.6f}\n"
                    f"    Sell: {arb.sell_dex} ({arb.sell_chain}) @ ${arb.sell_price:.6f}\n"
                    f"    Net profit: ${arb.net_profit_usd:,.2f} "
                    f"(gas: ${arb.gas_cost_usd:.2f})"
                )

        if result.errors:
            lines.append(f"\n⚠️ Errors: {', '.join(result.errors.keys())}")

        lines.append(f"\n_Scan completed in {result.scan_duration_ms}ms_")
        return "\n".join(lines)
