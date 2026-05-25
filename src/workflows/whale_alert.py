"""
Whale Alert Monitoring Workflow.

Scans multiple blockchain networks for large (whale) transactions,
filters by configurable thresholds, and generates consolidated alerts.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Chain(str, Enum):
    """Supported blockchain networks."""
    ETHEREUM = "ethereum"
    BITCOIN = "bitcoin"
    SOLANA = "solana"
    ARBITRUM = "arbitrum"
    BASE = "base"
    BSC = "bsc"


@dataclass
class WhaleTransaction:
    """A detected whale transaction."""
    chain: Chain
    tx_hash: str
    from_address: str
    to_address: str
    value_usd: float
    token: str
    timestamp: int
    block_number: int
    label_from: str | None = None
    label_to: str | None = None

    @property
    def direction_summary(self) -> str:
        source = self.label_from or self.from_address[:10] + "…"
        dest = self.label_to or self.to_address[:10] + "…"
        return f"{source} → {dest}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain": self.chain.value,
            "tx_hash": self.tx_hash,
            "from": self.from_address,
            "to": self.to_address,
            "value_usd": self.value_usd,
            "token": self.token,
            "timestamp": self.timestamp,
            "block_number": self.block_number,
            "label_from": self.label_from,
            "label_to": self.label_to,
        }


@dataclass
class AlertConfig:
    """Configuration for whale alert thresholds."""
    min_value_usd: float = 100_000.0
    chains: list[Chain] = field(default_factory=lambda: list(Chain))
    tokens: list[str] = field(default_factory=list)  # empty = all tokens
    exclude_addresses: set[str] = field(default_factory=set)
    cooldown_seconds: int = 60


@dataclass
class WhaleAlertResult:
    """Result of a whale monitoring sweep."""
    transactions: list[WhaleTransaction]
    chains_scanned: list[Chain]
    scan_duration_ms: int
    timestamp: int
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total_value_usd(self) -> float:
        return sum(tx.value_usd for tx in self.transactions)

    @property
    def alert_count(self) -> int:
        return len(self.transactions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transactions": [tx.to_dict() for tx in self.transactions],
            "chains_scanned": [c.value for c in self.chains_scanned],
            "scan_duration_ms": self.scan_duration_ms,
            "timestamp": self.timestamp,
            "total_value_usd": self.total_value_usd,
            "alert_count": self.alert_count,
            "errors": self.errors,
        }


class WhaleAlertWorkflow:
    """
    Multi-chain whale transaction monitoring workflow.

    Scans configured blockchain networks in parallel, filters
    transactions by USD threshold, de-duplicates, and returns
    consolidated alert results.
    """

    def __init__(
        self,
        config: AlertConfig | None = None,
        data_fetcher: Any | None = None,
        address_labeler: Any | None = None,
    ) -> None:
        self.config = config or AlertConfig()
        self._fetcher = data_fetcher
        self._labeler = address_labeler
        self._last_alert_time: dict[str, float] = {}

    async def run(self) -> WhaleAlertResult:
        """Execute a full whale monitoring sweep across all configured chains."""
        start = time.monotonic()
        now = int(time.time())

        logger.info(
            "Starting whale alert sweep: chains=%s, threshold=$%s",
            [c.value for c in self.config.chains],
            f"{self.config.min_value_usd:,.0f}",
        )

        # Scan all chains concurrently
        tasks = {
            chain: self._scan_chain(chain) for chain in self.config.chains
        }
        chain_results = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )

        all_transactions: list[WhaleTransaction] = []
        errors: dict[str, str] = {}

        for chain, result in zip(tasks.keys(), chain_results):
            if isinstance(result, Exception):
                logger.error("Chain scan failed for %s: %s", chain.value, result)
                errors[chain.value] = str(result)
            else:
                all_transactions.extend(result)

        # Apply cooldown filtering
        filtered = self._apply_cooldown(all_transactions)

        # Sort by value descending
        filtered.sort(key=lambda tx: tx.value_usd, reverse=True)

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "Whale alert sweep complete: %d alerts found in %dms",
            len(filtered),
            duration_ms,
        )

        return WhaleAlertResult(
            transactions=filtered,
            chains_scanned=list(self.config.chains),
            scan_duration_ms=duration_ms,
            timestamp=now,
            errors=errors,
        )

    async def _scan_chain(self, chain: Chain) -> list[WhaleTransaction]:
        """Scan a single chain for whale transactions."""
        logger.debug("Scanning chain: %s", chain.value)

        if self._fetcher is None:
            logger.debug("No data fetcher configured, returning empty results for %s", chain.value)
            return []

        raw_txs = await self._fetcher.get_recent_large_txs(
            chain=chain.value,
            min_value_usd=self.config.min_value_usd,
        )

        transactions: list[WhaleTransaction] = []
        for raw in raw_txs:
            # Skip excluded addresses
            if raw.get("from") in self.config.exclude_addresses:
                continue
            if raw.get("to") in self.config.exclude_addresses:
                continue

            # Token filter
            if self.config.tokens and raw.get("token", "").upper() not in {
                t.upper() for t in self.config.tokens
            }:
                continue

            # Label addresses if labeler is available
            label_from = None
            label_to = None
            if self._labeler:
                label_from = await self._labeler.lookup(raw.get("from", ""))
                label_to = await self._labeler.lookup(raw.get("to", ""))

            transactions.append(
                WhaleTransaction(
                    chain=chain,
                    tx_hash=raw["tx_hash"],
                    from_address=raw["from"],
                    to_address=raw["to"],
                    value_usd=float(raw.get("value_usd", 0)),
                    token=raw.get("token", "UNKNOWN"),
                    timestamp=int(raw.get("timestamp", 0)),
                    block_number=int(raw.get("block_number", 0)),
                    label_from=label_from,
                    label_to=label_to,
                )
            )

        return transactions

    def _apply_cooldown(
        self, transactions: list[WhaleTransaction]
    ) -> list[WhaleTransaction]:
        """Filter out transactions that are within the cooldown window."""
        now = time.time()
        result: list[WhaleTransaction] = []

        for tx in transactions:
            key = f"{tx.chain.value}:{tx.from_address}:{tx.to_address}"
            last_time = self._last_alert_time.get(key, 0.0)

            if now - last_time >= self.config.cooldown_seconds:
                self._last_alert_time[key] = now
                result.append(tx)
            else:
                logger.debug(
                    "Cooldown active for %s, skipping tx %s", key, tx.tx_hash
                )

        return result

    def format_alerts(self, result: WhaleAlertResult) -> str:
        """Format alert result as a human-readable string."""
        if not result.transactions:
            return "🐋 No whale transactions detected above threshold."

        lines = [
            f"🐋 **Whale Alert** — {result.alert_count} transaction(s) detected",
            f"Total value: ${result.total_value_usd:,.0f}",
            "",
        ]

        for tx in result.transactions:
            lines.append(
                f"• **{tx.chain.value.upper()}** — "
                f"${tx.value_usd:,.0f} {tx.token}\n"
                f"  {tx.direction_summary}\n"
                f"  `{tx.tx_hash[:16]}…`"
            )

        if result.errors:
            lines.append(f"\n⚠️ Errors on: {', '.join(result.errors.keys())}")

        return "\n".join(lines)
