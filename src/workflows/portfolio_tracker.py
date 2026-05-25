"""
Multi-Chain Portfolio Tracking Workflow.

Aggregates token balances, DeFi positions, and NFT holdings
across multiple blockchain networks into a unified portfolio view.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class PositionType(str, Enum):
    """Types of on-chain positions."""
    WALLET = "wallet"
    STAKING = "staking"
    LP = "liquidity_pool"
    LENDING = "lending"
    BORROWING = "borrowing"
    YIELD = "yield_farming"
    NFT = "nft"


@dataclass
class TokenBalance:
    """A single token holding."""
    token: str
    chain: str
    balance: float
    value_usd: float
    price_usd: float
    contract_address: str | None = None
    logo_url: str | None = None

    @property
    def display(self) -> str:
        return f"{self.balance:,.4f} {self.token} (${self.value_usd:,.2f})"


@dataclass
class DeFiPosition:
    """A DeFi protocol position."""
    protocol: str
    chain: str
    position_type: PositionType
    tokens: list[TokenBalance]
    value_usd: float
    apy: float | None = None
    health_factor: float | None = None

    @property
    def is_borrowing(self) -> bool:
        return self.position_type == PositionType.BORROWING

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "chain": self.chain,
            "position_type": self.position_type.value,
            "tokens": [
                {"token": t.token, "balance": t.balance, "value_usd": t.value_usd}
                for t in self.tokens
            ],
            "value_usd": self.value_usd,
            "apy": self.apy,
            "health_factor": self.health_factor,
        }


@dataclass
class ChainPortfolio:
    """Portfolio breakdown for a single chain."""
    chain: str
    wallet_balances: list[TokenBalance]
    defi_positions: list[DeFiPosition]
    total_value_usd: float

    @property
    def token_count(self) -> int:
        return len(self.wallet_balances)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain,
            "wallet_balances": [
                {"token": t.token, "balance": t.balance, "value_usd": t.value_usd}
                for t in self.wallet_balances
            ],
            "defi_positions": [p.to_dict() for p in self.defi_positions],
            "total_value_usd": self.total_value_usd,
        }


@dataclass
class PortfolioSnapshot:
    """Complete portfolio snapshot across all chains."""
    address: str
    chains: list[ChainPortfolio]
    total_value_usd: float
    total_wallet_value_usd: float
    total_defi_value_usd: float
    net_apy: float | None = None
    health_factor: float | None = None
    timestamp: int = 0
    fetch_duration_ms: int = 0

    @property
    def chain_count(self) -> int:
        return len(self.chains)

    @property
    def position_count(self) -> int:
        return sum(len(c.defi_positions) for c in self.chains)

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "total_value_usd": self.total_value_usd,
            "wallet_value_usd": self.total_wallet_value_usd,
            "defi_value_usd": self.total_defi_value_usd,
            "net_apy": self.net_apy,
            "health_factor": self.health_factor,
            "chain_count": self.chain_count,
            "position_count": self.position_count,
            "chains": [c.to_dict() for c in self.chains],
            "timestamp": self.timestamp,
            "fetch_duration_ms": self.fetch_duration_ms,
        }


class PortfolioTrackerWorkflow:
    """
    Multi-chain portfolio tracking workflow.

    Fetches wallet balances and DeFi positions across configured
    chains, calculates totals, and returns a unified snapshot.
    """

    DEFAULT_CHAINS = ["ethereum", "arbitrum", "base", "solana", "bsc"]

    def __init__(
        self,
        address: str,
        chains: list[str] | None = None,
        data_fetcher: Any | None = None,
        price_provider: Any | None = None,
        include_defi: bool = True,
        include_nfts: bool = False,
    ) -> None:
        if not address or not address.strip():
            raise ValueError("Address must be a non-empty string")

        self.address = address.strip()
        self.chains = chains or self.DEFAULT_CHAINS
        self._fetcher = data_fetcher
        self._prices = price_provider
        self.include_defi = include_defi
        self.include_nfts = include_nfts

    async def run(self) -> PortfolioSnapshot:
        """Fetch and aggregate portfolio data across all chains."""
        start = time.monotonic()
        now = int(time.time())

        logger.info(
            "Fetching portfolio for %s across chains: %s",
            self.address[:10] + "…",
            self.chains,
        )

        # Fetch all chains concurrently
        tasks = [
            self._fetch_chain_portfolio(chain) for chain in self.chains
        ]
        chain_results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_chains: list[ChainPortfolio] = []
        for chain, result in zip(self.chains, chain_results):
            if isinstance(result, Exception):
                logger.warning("Failed to fetch portfolio for %s: %s", chain, result)
                valid_chains.append(
                    ChainPortfolio(
                        chain=chain,
                        wallet_balances=[],
                        defi_positions=[],
                        total_value_usd=0.0,
                    )
                )
            else:
                valid_chains.append(result)

        # Calculate aggregate totals
        total_wallet = sum(
            sum(t.value_usd for t in c.wallet_balances) for c in valid_chains
        )
        total_defi = sum(
            sum(p.value_usd for p in c.defi_positions) for c in valid_chains
        )
        total_value = total_wallet + total_defi

        # Calculate weighted APY from DeFi positions
        net_apy = self._calculate_net_apy(valid_chains)

        # Calculate aggregate health factor
        health_factor = self._calculate_health_factor(valid_chains)

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "Portfolio fetch complete: $%s across %d chains in %dms",
            f"{total_value:,.2f}",
            len(valid_chains),
            duration_ms,
        )

        return PortfolioSnapshot(
            address=self.address,
            chains=valid_chains,
            total_value_usd=total_value,
            total_wallet_value_usd=total_wallet,
            total_defi_value_usd=total_defi,
            net_apy=net_apy,
            health_factor=health_factor,
            timestamp=now,
            fetch_duration_ms=duration_ms,
        )

    async def _fetch_chain_portfolio(self, chain: str) -> ChainPortfolio:
        """Fetch portfolio data for a single chain."""
        logger.debug("Fetching chain portfolio: %s", chain)

        if self._fetcher is None:
            logger.debug("No data fetcher configured, returning empty for %s", chain)
            return ChainPortfolio(
                chain=chain,
                wallet_balances=[],
                defi_positions=[],
                total_value_usd=0.0,
            )

        # Fetch wallet balances
        raw_balances = await self._fetcher.get_token_balances(
            address=self.address,
            chain=chain,
        )

        wallet_balances: list[TokenBalance] = []
        for bal in raw_balances:
            price = float(bal.get("price_usd", 0))
            balance = float(bal.get("balance", 0))
            wallet_balances.append(
                TokenBalance(
                    token=bal["token"],
                    chain=chain,
                    balance=balance,
                    value_usd=balance * price,
                    price_usd=price,
                    contract_address=bal.get("contract_address"),
                )
            )

        # Fetch DeFi positions if enabled
        defi_positions: list[DeFiPosition] = []
        if self.include_defi:
            raw_positions = await self._fetcher.get_defi_positions(
                address=self.address,
                chain=chain,
            )
            for pos in raw_positions:
                tokens = [
                    TokenBalance(
                        token=t["token"],
                        chain=chain,
                        balance=float(t.get("balance", 0)),
                        value_usd=float(t.get("value_usd", 0)),
                        price_usd=float(t.get("price_usd", 0)),
                    )
                    for t in pos.get("tokens", [])
                ]
                defi_positions.append(
                    DeFiPosition(
                        protocol=pos["protocol"],
                        chain=chain,
                        position_type=PositionType(pos.get("type", "wallet")),
                        tokens=tokens,
                        value_usd=float(pos.get("value_usd", 0)),
                        apy=float(pos["apy"]) if pos.get("apy") else None,
                        health_factor=(
                            float(pos["health_factor"])
                            if pos.get("health_factor")
                            else None
                        ),
                    )
                )

        total = sum(t.value_usd for t in wallet_balances) + sum(
            p.value_usd for p in defi_positions
        )

        return ChainPortfolio(
            chain=chain,
            wallet_balances=wallet_balances,
            defi_positions=defi_positions,
            total_value_usd=total,
        )

    def _calculate_net_apy(self, chains: list[ChainPortfolio]) -> float | None:
        """Calculate value-weighted average APY across DeFi positions."""
        total_weighted_apy = 0.0
        total_value = 0.0

        for chain in chains:
            for pos in chain.defi_positions:
                if pos.apy is not None and pos.value_usd > 0:
                    total_weighted_apy += pos.apy * pos.value_usd
                    total_value += pos.value_usd

        if total_value <= 0:
            return None

        return round(total_weighted_apy / total_value, 4)

    def _calculate_health_factor(
        self, chains: list[ChainPortfolio]
    ) -> float | None:
        """Calculate aggregate health factor from borrowing positions."""
        health_factors: list[float] = []

        for chain in chains:
            for pos in chain.defi_positions:
                if pos.health_factor is not None:
                    health_factors.append(pos.health_factor)

        if not health_factors:
            return None

        # Return the minimum health factor (most at risk)
        return round(min(health_factors), 4)

    def format_snapshot(self, snapshot: PortfolioSnapshot) -> str:
        """Format portfolio snapshot as a human-readable string."""
        lines = [
            f"📊 **Portfolio: `{self.address[:8]}…{self.address[-6:]}`**",
            f"Total Value: **${snapshot.total_value_usd:,.2f}**",
            f"• Wallet: ${snapshot.total_wallet_value_usd:,.2f}",
            f"• DeFi: ${snapshot.total_defi_value_usd:,.2f}",
        ]

        if snapshot.net_apy is not None:
            lines.append(f"• Net APY: {snapshot.net_apy:.2f}%")

        if snapshot.health_factor is not None:
            emoji = "🟢" if snapshot.health_factor > 1.5 else "🟡" if snapshot.health_factor > 1.1 else "🔴"
            lines.append(f"• Health Factor: {emoji} {snapshot.health_factor:.2f}")

        lines.append("")

        for chain in snapshot.chains:
            if chain.total_value_usd <= 0:
                continue

            lines.append(f"**{chain.chain.upper()}** — ${chain.total_value_usd:,.2f}")

            for token in sorted(
                chain.wallet_balances, key=lambda t: t.value_usd, reverse=True
            )[:5]:
                lines.append(f"  • {token.display}")

            for pos in chain.defi_positions:
                apy_str = f" @ {pos.apy:.1f}% APY" if pos.apy else ""
                lines.append(
                    f"  • [{pos.protocol}] {pos.position_type.value}: "
                    f"${pos.value_usd:,.2f}{apy_str}"
                )

        lines.append(f"\n_Fetched in {snapshot.fetch_duration_ms}ms_")
        return "\n".join(lines)
