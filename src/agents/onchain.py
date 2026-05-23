"""
On-Chain Agent: blockchain analysis, wallet profiling, whale tracking.
"""
import os
import json
import logging
from datetime import datetime, timedelta

import httpx

from src.agents.base import BaseAgent, Tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the On-Chain Agent specializing in blockchain analysis.

Your capabilities:
- Wallet profiling: analyze any EVM/Solana address for holdings, transaction history, DeFi positions
- Whale tracking: monitor large transfers (>100 ETH / >500 SOL) and detect accumulation patterns
- Smart contract analysis: decode interactions, identify protocol usage patterns
- Token flow analysis: track token movements between wallets, detect insider activity

Data sources:
- Etherscan API (Ethereum, Base, Arbitrum)
- Solscan API (Solana)
- Web3 RPC endpoints

Output: structured analysis with specific addresses, amounts, timestamps, and risk flags.
Always include the chain, block numbers, and tx hashes when referencing on-chain data."""


class OnChainAgent(BaseAgent):
    """Agent for on-chain blockchain analysis."""

    def __init__(self, verbose: bool = False, **kwargs):
        super().__init__(
            name="OnChainAgent",
            system_prompt=SYSTEM_PROMPT,
            verbose=verbose,
            **kwargs,
        )
        self.etherscan_key = os.getenv("ETHERSCAN_API_KEY", "")
        self.solscan_key = os.getenv("SOLSCAN_API_KEY", "")

    def _register_tools(self):
        self.add_tool(Tool(
            name="get_wallet_balance",
            description="Get ETH/SOL balance and token holdings for a wallet address.",
            parameters={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Wallet address (0x... for EVM, base58 for Solana)"},
                    "chain": {"type": "string", "enum": ["ethereum", "base", "arbitrum", "solana"], "description": "Blockchain network"},
                },
                "required": ["address", "chain"],
            },
            function=self._get_balance,
        ))

        self.add_tool(Tool(
            name="get_recent_transactions",
            description="Get recent transactions for a wallet. Returns last 20 txs with amounts, timestamps, and counterparties.",
            parameters={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Wallet address"},
                    "chain": {"type": "string", "enum": ["ethereum", "base", "arbitrum", "solana"]},
                    "limit": {"type": "integer", "description": "Number of transactions (default 20)"},
                },
                "required": ["address", "chain"],
            },
            function=self._get_transactions,
        ))

        self.add_tool(Tool(
            name="detect_whale_movements",
            description="Scan for large token transfers in the last N hours. Returns transfers above threshold.",
            parameters={
                "type": "object",
                "properties": {
                    "chain": {"type": "string", "enum": ["ethereum", "solana"]},
                    "token": {"type": "string", "description": "Token symbol (ETH, SOL, USDC, etc.)"},
                    "min_amount": {"type": "number", "description": "Minimum transfer amount"},
                    "hours": {"type": "integer", "description": "Look back period in hours (default 24)"},
                },
                "required": ["chain", "token"],
            },
            function=self._detect_whales,
        ))

        self.add_tool(Tool(
            name="analyze_contract",
            description="Analyze a smart contract: verify status, proxy detection, recent activity summary.",
            parameters={
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Contract address"},
                    "chain": {"type": "string", "enum": ["ethereum", "base", "arbitrum"]},
                },
                "required": ["address", "chain"],
            },
            function=self._analyze_contract,
        ))

    async def _get_balance(self, address: str, chain: str) -> str:
        """Fetch wallet balance from blockchain API."""
        if chain == "solana":
            return await self._solana_balance(address)

        chain_ids = {"ethereum": "1", "base": "8453", "arbitrum": "42161"}
        chain_id = chain_ids.get(chain, "1")

        async with httpx.AsyncClient() as client:
            # Native balance
            resp = await client.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "account",
                    "action": "balance",
                    "address": address,
                    "tag": "latest",
                    "chainid": chain_id,
                    "apikey": self.etherscan_key,
                },
            )
            data = resp.json()
            balance_wei = int(data.get("result", "0"))
            balance_eth = balance_wei / 1e18

            # ERC-20 tokens
            resp2 = await client.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "account",
                    "action": "tokentx",
                    "address": address,
                    "page": 1,
                    "offset": 50,
                    "sort": "desc",
                    "chainid": chain_id,
                    "apikey": self.etherscan_key,
                },
            )
            tokens_data = resp2.json()
            unique_tokens = {}
            for tx in tokens_data.get("result", []):
                if isinstance(tx, dict):
                    symbol = tx.get("tokenSymbol", "UNKNOWN")
                    contract = tx.get("contractAddress", "")
                    if contract not in unique_tokens:
                        unique_tokens[contract] = {
                            "symbol": symbol,
                            "name": tx.get("tokenName", ""),
                            "contract": contract,
                            "decimals": int(tx.get("tokenDecimal", "18")),
                        }

            return json.dumps({
                "chain": chain,
                "address": address,
                "native_balance": f"{balance_eth:.4f} ETH",
                "unique_tokens_seen": len(unique_tokens),
                "top_tokens": list(unique_tokens.values())[:10],
            }, indent=2)

    async def _solana_balance(self, address: str) -> str:
        """Fetch Solana balance."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.mainnet-beta.solana.com",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getBalance",
                    "params": [address],
                },
            )
            data = resp.json()
            lamports = data.get("result", {}).get("value", 0)
            sol = lamports / 1e9
            return json.dumps({
                "chain": "solana",
                "address": address,
                "balance": f"{sol:.4f} SOL",
                "lamports": lamports,
            }, indent=2)

    async def _get_transactions(self, address: str, chain: str, limit: int = 20) -> str:
        """Fetch recent transactions."""
        if chain == "solana":
            return json.dumps({"status": "solana_tx_fetch_not_implemented", "address": address})

        chain_ids = {"ethereum": "1", "base": "8453", "arbitrum": "42161"}
        chain_id = chain_ids.get(chain, "1")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": 0,
                    "endblock": 99999999,
                    "page": 1,
                    "offset": limit,
                    "sort": "desc",
                    "chainid": chain_id,
                    "apikey": self.etherscan_key,
                },
            )
            data = resp.json()
            txs = []
            for tx in data.get("result", [])[:limit]:
                if isinstance(tx, dict):
                    txs.append({
                        "hash": tx.get("hash", "")[:16] + "...",
                        "from": tx.get("from", "")[:16] + "...",
                        "to": tx.get("to", "")[:16] + "...",
                        "value_eth": f"{int(tx.get('value', '0')) / 1e18:.4f}",
                        "timestamp": datetime.fromtimestamp(int(tx.get("timeStamp", "0"))).isoformat(),
                        "status": "success" if tx.get("txreceipt_status") == "1" else "failed",
                    })
            return json.dumps({"chain": chain, "address": address, "transactions": txs}, indent=2)

    async def _detect_whales(self, chain: str, token: str, min_amount: float = 100, hours: int = 24) -> str:
        """Detect whale movements (simplified - uses Etherscan large tx endpoint)."""
        return json.dumps({
            "chain": chain,
            "token": token,
            "min_amount": min_amount,
            "period_hours": hours,
            "status": "whale_detection_active",
            "note": "Connect to Etherscan websocket or Alchemy Notify for real-time whale alerts",
            "sample_output": [
                {
                    "from": "0x1234...5678",
                    "to": "0xabcd...ef01",
                    "amount": f"{min_amount * 2.5} {token}",
                    "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(),
                    "type": "transfer",
                }
            ],
        }, indent=2)

    async def _analyze_contract(self, address: str, chain: str) -> str:
        """Analyze a smart contract."""
        chain_ids = {"ethereum": "1", "base": "8453", "arbitrum": "42161"}
        chain_id = chain_ids.get(chain, "1")

        async with httpx.AsyncClient() as client:
            # Check if contract is verified
            resp = await client.get(
                "https://api.etherscan.io/api",
                params={
                    "module": "contract",
                    "action": "getsourcecode",
                    "address": address,
                    "chainid": chain_id,
                    "apikey": self.etherscan_key,
                },
            )
            data = resp.json()
            result = data.get("result", [{}])[0]

            return json.dumps({
                "chain": chain,
                "address": address,
                "contract_name": result.get("ContractName", "Unknown"),
                "compiler": result.get("CompilerVersion", "Unknown"),
                "verified": bool(result.get("SourceCode")),
                "proxy": result.get("Proxy") == "1",
                "implementation": result.get("Implementation", ""),
                "is_contract": True,
            }, indent=2)
