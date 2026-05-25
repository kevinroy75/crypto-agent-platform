"""
Blockchain interaction tools: Etherscan, Solscan, and direct Web3 RPC calls.
"""
import asyncio
import logging
from typing import Any, Optional

from .base import BaseTool, RetryConfig

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

ETHERSCAN_API = "https://api.etherscan.io/api"
SOLSCAN_API = "https://public-api.solscan.io"
DEFAULT_ETH_RPC = "https://eth-mainnet.g.alchemy.com/v2"

WHALE_THRESHOLD_ETH = float(100)  # ETH
WHALE_THRESHOLD_SOL = float(5000)  # SOL

ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


# ═══════════════════════════════════════════════════════════════════════
# Etherscan Tool
# ═══════════════════════════════════════════════════════════════════════

class EtherscanTool(BaseTool):
    """Query Etherscan for wallet balances, transactions, and contract data."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(timeout=20.0, **kwargs)
        self._api_key = api_key or self._env("ETHERSCAN_API_KEY")

    @property
    def name(self) -> str:
        return "etherscan"

    @property
    def description(self) -> str:
        return (
            "Query Ethereum blockchain via Etherscan: wallet balances, "
            "transaction history, token transfers, and contract source code."
        )

    # ── Public helpers ────────────────────────────────────────────────

    async def _etherscan_get(self, **params) -> dict:
        params["apikey"] = self._api_key
        result = await self._get(ETHERSCAN_API, params=params)
        if isinstance(result, dict) and result.get("status") == "0":
            return self.error(
                result.get("result", "Etherscan API error"),
                code="ETHERSCAN_ERROR",
            )
        return result

    # ── Tool methods ──────────────────────────────────────────────────

    async def get_wallet_balance(self, address: str, chain: str = "eth") -> dict:
        """Get the native token balance for an address."""
        try:
            if chain == "eth":
                result = await self._etherscan_get(
                    module="account",
                    action="balance",
                    address=address,
                    tag="latest",
                )
                if isinstance(result, dict) and result.get("status") == "success":
                    return result
                balance_wei = int(result.get("result", 0) if isinstance(result, dict) else 0)
                return self.success({
                    "address": address,
                    "chain": "ethereum",
                    "balance_wei": str(balance_wei),
                    "balance_eth": balance_wei / 1e18,
                })
            return self.error(f"Unsupported chain: {chain}", code="UNSUPPORTED_CHAIN")
        except Exception as exc:
            logger.error(f"get_wallet_balance failed: {exc}")
            return self.error(str(exc), code="BALANCE_ERROR")

    async def get_recent_transactions(
        self, address: str, limit: int = 10, chain: str = "eth"
    ) -> dict:
        """Fetch recent transactions for a wallet address."""
        try:
            result = await self._etherscan_get(
                module="account",
                action="txlist",
                address=address,
                startblock=0,
                endblock=99999999,
                page=1,
                offset=limit,
                sort="desc",
            )
            txs = result.get("result", []) if isinstance(result, dict) else []
            if not isinstance(txs, list):
                txs = []

            normalised = [
                {
                    "hash": tx.get("hash"),
                    "block": tx.get("blockNumber"),
                    "timestamp": tx.get("timeStamp"),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "value_eth": int(tx.get("value", 0)) / 1e18,
                    "gas_used": tx.get("gasUsed"),
                    "status": "success" if tx.get("txreceipt_status") == "1" else "failed",
                }
                for tx in txs[:limit]
            ]
            return self.success(
                {"address": address, "transactions": normalised, "count": len(normalised)},
                meta={"source": "etherscan"},
            )
        except Exception as exc:
            logger.error(f"get_recent_transactions failed: {exc}")
            return self.error(str(exc), code="TX_LIST_ERROR")

    async def get_token_transfers(
        self, address: str, contract_address: Optional[str] = None, limit: int = 20
    ) -> dict:
        """Retrieve ERC-20 token transfer events for an address."""
        try:
            params: dict[str, Any] = dict(
                module="account",
                action="tokentx",
                address=address,
                page=1,
                offset=limit,
                sort="desc",
            )
            if contract_address:
                params["contractaddress"] = contract_address

            result = await self._etherscan_get(**params)
            transfers = result.get("result", []) if isinstance(result, dict) else []
            if not isinstance(transfers, list):
                transfers = []

            normalised = [
                {
                    "hash": t.get("hash"),
                    "token_name": t.get("tokenName"),
                    "token_symbol": t.get("tokenSymbol"),
                    "from": t.get("from"),
                    "to": t.get("to"),
                    "value": t.get("value"),
                    "contract": t.get("contractAddress"),
                }
                for t in transfers[:limit]
            ]
            return self.success({"address": address, "transfers": normalised})
        except Exception as exc:
            return self.error(str(exc), code="TOKEN_TRANSFER_ERROR")

    async def analyze_contract(self, address: str) -> dict:
        """Retrieve contract source code and ABI from Etherscan."""
        try:
            result = await self._etherscan_get(
                module="contract",
                action="getsourcecode",
                address=address,
            )
            source = result.get("result", []) if isinstance(result, dict) else []
            if not isinstance(source, list) or not source:
                return self.error("Contract not found or not verified", code="CONTRACT_NOT_FOUND")

            contract = source[0]
            return self.success({
                "address": address,
                "name": contract.get("ContractName"),
                "compiler": contract.get("CompilerVersion"),
                "optimization": contract.get("OptimizationUsed"),
                "is_proxy": bool(contract.get("Implementation")),
                "implementation": contract.get("Implementation") or None,
                "source_available": bool(contract.get("SourceCode")),
                "abi_available": contract.get("ABI") != "Contract source code not verified",
            })
        except Exception as exc:
            return self.error(str(exc), code="CONTRACT_ANALYSIS_ERROR")

    async def detect_whale_movements(
        self, address: str, threshold_eth: float = WHALE_THRESHOLD_ETH, limit: int = 50
    ) -> dict:
        """Scan recent transactions for whale-sized movements."""
        try:
            tx_result = await self.get_recent_transactions(address, limit=limit)
            if tx_result.get("status") != "success":
                return tx_result

            txs = tx_result["data"]["transactions"]
            whale_txs = [tx for tx in txs if tx["value_eth"] >= threshold_eth]

            return self.success({
                "address": address,
                "whale_threshold_eth": threshold_eth,
                "whale_transactions": whale_txs,
                "whale_count": len(whale_txs),
                "total_scanned": len(txs),
            })
        except Exception as exc:
            return self.error(str(exc), code="WHALE_DETECTION_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "balance")
        dispatch = {
            "balance": self.get_wallet_balance,
            "transactions": self.get_recent_transactions,
            "token_transfers": self.get_token_transfers,
            "contract": self.analyze_contract,
            "whale_movements": self.detect_whale_movements,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Solscan Tool
# ═══════════════════════════════════════════════════════════════════════

class SolscanTool(BaseTool):
    """Query Solscan for Solana wallet and token data."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(
            timeout=20.0,
            default_headers={"accept": "application/json"},
            **kwargs,
        )
        self._api_key = api_key or self._env("SOLSCAN_API_KEY")
        if self._api_key:
            self._default_headers["Authorization"] = f"Bearer {self._api_key}"

    @property
    def name(self) -> str:
        return "solscan"

    @property
    def description(self) -> str:
        return (
            "Query Solana blockchain via Solscan: SOL balance, "
            "SPL token holdings, recent transactions, and account info."
        )

    async def get_wallet_balance(self, address: str) -> dict:
        """Get the SOL balance for a Solana address."""
        try:
            result = await self._get(f"{SOLSCAN_API}/account/{address}")
            if isinstance(result, dict) and "data" in result:
                lamports = result["data"].get("lamports", 0)
                return self.success({
                    "address": address,
                    "chain": "solana",
                    "balance_lamports": lamports,
                    "balance_sol": lamports / 1e9,
                })
            return self.success({"address": address, "chain": "solana", "raw": result})
        except Exception as exc:
            return self.error(str(exc), code="SOL_BALANCE_ERROR")

    async def get_token_accounts(self, address: str) -> dict:
        """List SPL token accounts owned by a Solana address."""
        try:
            result = await self._get(
                f"{SOLSCAN_API}/account/tokens",
                params={"account": address},
            )
            tokens = result.get("data", []) if isinstance(result, dict) else []
            return self.success({"address": address, "tokens": tokens, "count": len(tokens)})
        except Exception as exc:
            return self.error(str(exc), code="SOL_TOKENS_ERROR")

    async def get_recent_transactions(self, address: str, limit: int = 10) -> dict:
        """Fetch recent transactions for a Solana address."""
        try:
            result = await self._get(
                f"{SOLSCAN_API}/account/transactions",
                params={"account": address, "limit": limit},
            )
            txs = result.get("data", []) if isinstance(result, dict) else []
            normalised = [
                {
                    "signature": tx.get("txHash"),
                    "slot": tx.get("slot"),
                    "timestamp": tx.get("blockTime"),
                    "status": tx.get("status"),
                    "fee_sol": tx.get("fee", 0) / 1e9,
                }
                for tx in (txs[:limit] if isinstance(txs, list) else [])
            ]
            return self.success({"address": address, "transactions": normalised})
        except Exception as exc:
            return self.error(str(exc), code="SOL_TX_ERROR")

    async def detect_whale_movements(
        self, address: str, threshold_sol: float = WHALE_THRESHOLD_SOL, limit: int = 50
    ) -> dict:
        """Scan for whale-sized SOL transfers."""
        try:
            result = await self.get_recent_transactions(address, limit=limit)
            if result.get("status") != "success":
                return result
            # Placeholder: detailed SOL value parsing requires inner instruction parsing
            return self.success({
                "address": address,
                "whale_threshold_sol": threshold_sol,
                "note": "Detailed SOL transfer amount parsing requires RPC inner-instruction analysis",
                "transactions": result["data"]["transactions"],
            })
        except Exception as exc:
            return self.error(str(exc), code="SOL_WHALE_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "balance")
        dispatch = {
            "balance": self.get_wallet_balance,
            "tokens": self.get_token_accounts,
            "transactions": self.get_recent_transactions,
            "whale_movements": self.detect_whale_movements,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Web3 RPC Tool
# ═══════════════════════════════════════════════════════════════════════

class Web3RPCTool(BaseTool):
    """Direct JSON-RPC calls to an Ethereum-compatible node."""

    def __init__(self, rpc_url: Optional[str] = None, **kwargs):
        super().__init__(timeout=15.0, **kwargs)
        self._rpc_url = rpc_url or self._env("ETH_RPC_URL", "https://eth.llamarpc.com")

    @property
    def name(self) -> str:
        return "web3_rpc"

    @property
    def description(self) -> str:
        return (
            "Send JSON-RPC requests directly to an Ethereum node. "
            "Supports eth_call, eth_getBalance, eth_getCode, eth_blockNumber, etc."
        )

    async def _rpc_call(self, method: str, params: list[Any] | None = None) -> Any:
        """Execute a single JSON-RPC call."""
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }
        result = await self._post(self._rpc_url, json_body=payload)
        if isinstance(result, dict):
            if "error" in result:
                return self.error(
                    result["error"].get("message", "RPC error"),
                    code="RPC_ERROR",
                    details=result["error"],
                )
            return result.get("result")
        return result

    async def get_balance(self, address: str, block: str = "latest") -> dict:
        """Get native token balance via eth_getBalance."""
        try:
            result = await self._rpc_call("eth_getBalance", [address, block])
            if isinstance(result, str) and result.startswith("0x"):
                balance_wei = int(result, 16)
                return self.success({
                    "address": address,
                    "balance_wei": str(balance_wei),
                    "balance_eth": balance_wei / 1e18,
                    "block": block,
                })
            return self.success({"address": address, "raw": result})
        except Exception as exc:
            return self.error(str(exc), code="RPC_BALANCE_ERROR")

    async def get_block_number(self) -> dict:
        """Get the latest block number."""
        try:
            result = await self._rpc_call("eth_blockNumber")
            block_num = int(result, 16) if isinstance(result, str) else result
            return self.success({"block_number": block_num})
        except Exception as exc:
            return self.error(str(exc), code="RPC_BLOCK_ERROR")

    async def get_code(self, address: str) -> dict:
        """Get deployed bytecode at an address (empty = EOA)."""
        try:
            result = await self._rpc_call("eth_getCode", [address, "latest"])
            is_contract = isinstance(result, str) and len(result) > 2
            return self.success({
                "address": address,
                "is_contract": is_contract,
                "bytecode_length": len(result) // 2 - 1 if is_contract else 0,
            })
        except Exception as exc:
            return self.error(str(exc), code="RPC_CODE_ERROR")

    async def eth_call(self, to: str, data: str, block: str = "latest") -> dict:
        """Execute a read-only eth_call (no gas consumed)."""
        try:
            result = await self._rpc_call(
                "eth_call",
                [{"to": to, "data": data}, block],
            )
            return self.success({"to": to, "result": result})
        except Exception as exc:
            return self.error(str(exc), code="RPC_CALL_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "balance")
        dispatch = {
            "balance": self.get_balance,
            "block_number": self.get_block_number,
            "code": self.get_code,
            "eth_call": self.eth_call,
        }
        fn = dispatch.get(action)
        if fn is None:
            return self.error(f"Unknown action: {action}", code="INVALID_ACTION")
        return await fn(**kwargs)
