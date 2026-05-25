<div align="center">

# 🪙 Multi-Agent Crypto Research Platform

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
[![Stars](https://img.shields.io/github/stars/kevinroy75/crypto-agent-platform?style=for-the-badge&logo=github)](https://github.com/kevinroy75/crypto-agent-platform)
[![GitHub issues](https://img.shields.io/github/issues/kevinroy75/crypto-agent-platform?style=for-the-badge&logo=github)](https://github.com/kevinroy75/crypto-agent-platform/issues)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen?style=for-the-badge)](https://github.com/kevinroy75/crypto-agent-platform/pulls)

**An autonomous multi-agent system for blockchain research, on-chain analysis, and DeFi opportunity discovery.**

Powered by **Xiaomi MiMo v2.5 Pro** with advanced tool-use and long-chain reasoning capabilities.

[Quick Start](#-quick-start) · [Agents](#-agents) · [CLI & API Usage](#-usage) · [Configuration](#%EF%B8%8F-configuration) · [Deployment](#-deployment)

</div>

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER REQUEST                               │
│          CLI  ·  Python API  ·  Batch Mode  ·  Docker               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     🎯 ORCHESTRATOR AGENT                           │
│                     Model: MiMo v2.5 Pro                            │
│          ┌─────────────────┬─────────────────┬─────────────┐        │
│          │ Task Decompose  │  Agent Routing  │  Synthesis  │        │
│          └─────────────────┴─────────────────┴─────────────┘        │
└──────────┬──────────────────┬──────────────────┬────────────────────┘
           │                  │                  │
     ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │  🔗 ON-   │    │  📊 MARKET  │    │  🔬 RESEARCH│
     │  CHAIN    │    │   AGENT     │    │    AGENT    │
     │  AGENT    │    │             │    │             │
     ├───────────┤    ├─────────────┤    ├─────────────┤
     │• Wallet   │    │• Price Feed │    │• ArXiv Scan │
     │  Balance  │    │• DEX Quotes │    │• News Aggr. │
     │• Whale    │    │• IL Calc    │    │• Sentiment  │
     │  Tracking │    │• Top Pairs  │    │• Web Search │
     │• Contract │    │• Trending   │    │• RSS Feeds  │
     │  Analysis │    │  Tokens     │    │• Doc Parser │
     └─────┬─────┘    └──────┬──────┘    └──────┬──────┘
           │                  │                  │
     ┌─────▼─────┐    ┌──────▼──────┐    ┌──────▼──────┐
     │ Etherscan │    │  Jupiter    │    │  ArXiv API  │
     │ Solscan   │    │  Uniswap V3 │    │  Web Scraper│
     │ Web3 RPC  │    │  1inch      │    │  RSS Feeds  │
     │ Base      │    │  CoinGecko  │    │  Web Search │
     │ Arbitrum  │    │             │    │             │
     └───────────┘    └─────────────┘    └─────────────┘
```

### Design Principles

- **ReAct Pattern** — Each agent reasons, acts (via tools), and observes in a loop until the task is complete
- **Supervisor Delegation** — The orchestrator decomposes complex queries and routes sub-tasks to specialists
- **Tool-Use** — Agents select and invoke tools autonomously based on the task at hand
- **Multi-Chain** — Native support for Ethereum, Solana, Base, and Arbitrum from a single platform

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 🤖 | **Multi-Agent Orchestration** | Supervisor agent delegates tasks to specialized sub-agents with context management |
| 🔗 | **On-Chain Intelligence** | Real-time wallet tracking, whale movement detection, smart money flow analysis |
| 📊 | **DEX/CEX Monitoring** | Cross-exchange price feeds, liquidity depth analysis, arbitrage opportunity detection |
| 🔬 | **Research Pipeline** | Automated paper summarization (ArXiv), news aggregation, social sentiment scoring |
| 🧠 | **Long-Chain Reasoning** | Multi-step analysis with up to 10 iterations and intermediate tool verification |
| 🛠️ | **15+ Integrated Tools** | Blockchain APIs, web scraping, data processing — all via OpenAI-compatible tool-use |
| ⚡ | **Async Execution** | Fully async (asyncio + httpx) for concurrent multi-chain queries |
| 📦 | **Multiple Output Formats** | Text, JSON, and Markdown output with artifact tracking |
| 🐳 | **Docker Ready** | Production Dockerfile and docker-compose for one-command deployment |

---

## 🚀 Quick Start

### Install from PyPI

```bash
pip install crypto-agent-platform
```

### Install from Source

```bash
git clone https://github.com/kevinroy75/crypto-agent-platform.git
cd crypto-agent-platform
pip install -e .
```

### Configure

```bash
cp configs/example.env configs/.env
# Edit configs/.env with your API keys (see Configuration section below)
```

### Run

```bash
python -m src.main --task "Analyze top 10 DEX tokens by TVL and find undervalued gems"
```

---

## 🕹️ Usage

### CLI

```bash
# Basic query
python -m src.main --task "What are the top whale wallets on Ethereum today?"

# Verbose output with debugging
python -m src.main --task "Scan for arbitrage opportunities on Solana DEXes" -v

# Export results to JSON
python -m src.main --task "Analyze Uniswap V3 liquidity for ETH/USDC" \
  --output report.json --format json

# Export as Markdown report
python -m src.main --task "Research recent L2 developments" \
  --output report.md --format markdown

# Use custom config
python -m src.main --task "Find trending meme coins" --config configs/custom.yaml
```

**CLI Options:**
- `--task` — Research task description (required)
- `-v, --verbose` — Enable verbose logging
- `--config` — Path to config YAML (default: `configs/agents.yaml`)
- `--output` — Save results to file
- `--format` — Output format: `text`, `json`, `markdown`

### Python API

```python
import asyncio
from src.agents.orchestrator import OrchestratorAgent

async def main():
    agent = OrchestratorAgent(verbose=True)
    result = await agent.execute(
        "Analyze whale activity on Ethereum and Solana over the last 24 hours"
    )

    print(result.output)            # Final text output
    print(result.tokens_used)       # Total LLM tokens consumed
    print(result.duration_ms)       # Execution time in milliseconds
    print(result.artifacts)         # List of tools invoked
    print(result.metadata)          # Extra info (iterations, status)

    # Export
    print(result.to_dict())         # As dictionary
    print(result.to_markdown())     # As Markdown string

asyncio.run(main())
```

### Batch Mode (Multiple Tasks)

```python
import asyncio
from src.agents.orchestrator import OrchestratorAgent

tasks = [
    "What are the current gas prices on Ethereum?",
    "Find the top 5 trending tokens on CoinGecko",
    "Search ArXiv for recent MEV research papers",
]

async def batch():
    agent = OrchestratorAgent()
    results = await asyncio.gather(*[agent.execute(t) for t in tasks])
    for task, result in zip(tasks, results):
        print(f"\n--- {task[:50]}... ---")
        print(result.output[:200])

asyncio.run(batch())
```

### Example Scripts

```bash
# Whale movement detection (multi-chain)
python examples/whale_detection.py

# DeFi opportunity scanner
python examples/defi_scanner.py
```

---

## 🤖 Agents

### 🎯 Orchestrator Agent
The central supervisor that receives user tasks, decomposes them into sub-tasks, routes each to the appropriate specialist agent, and synthesizes the final output.

**Capabilities:**
- Task decomposition and planning
- Multi-agent delegation with context passing
- Result synthesis and conflict resolution
- Conversation context management

### 🔗 On-Chain Agent
Deep blockchain intelligence across multiple chains.

**Capabilities:**
- Wallet profiling and portfolio analysis
- Whale wallet tracking (>100 ETH / large SOL transfers)
- Smart contract interaction analysis
- Gas optimization recommendations
- Token holder distribution analysis

**Chains:** Ethereum · Solana · Base · Arbitrum

### 📊 Market Agent
Real-time DEX/CEX market data and analytics.

**Capabilities:**
- Real-time price aggregation (Jupiter, Uniswap V3, 1inch)
- Liquidity depth analysis across pools
- Impermanent loss calculator for LP positions
- Trending token discovery and ranking
- Top trading pairs by volume

### 🔬 Research Agent
Automated research and intelligence gathering.

**Capabilities:**
- ArXiv paper search and AI-powered summarization
- Crypto news RSS aggregation from multiple sources
- Sentiment analysis from social feeds
- Protocol documentation parsing
- General web search and content extraction

---

## 🛠️ Tool Matrix

| Tool | On-Chain | Market | Research | Description |
|------|:--------:|:------:|:--------:|-------------|
| `get_wallet_balance` | ✅ | | | Fetch native and token balances for any address |
| `get_recent_transactions` | ✅ | | | Retrieve recent transaction history |
| `detect_whale_movements` | ✅ | | | Identify large transfers and whale wallets |
| `analyze_contract` | ✅ | | | Inspect smart contract source and interactions |
| `get_token_price` | | ✅ | | Real-time token price from aggregated feeds |
| `get_jupiter_quote` | | ✅ | | Get swap quotes from Jupiter (Solana) |
| `get_trending_tokens` | | ✅ | | Discover trending tokens on CoinGecko |
| `calculate_impermanent_loss` | | ✅ | | IL calculator for LP position analysis |
| `get_top_pairs` | | ✅ | | Top trading pairs by volume/TVL |
| `search_arxiv` | | | ✅ | Search and retrieve academic papers |
| `get_crypto_news` | | | ✅ | Aggregate crypto news from RSS feeds |
| `fetch_url_content` | | | ✅ | Scrape and extract web page content |
| `analyze_sentiment` | | | ✅ | Sentiment scoring on text content |
| `search_web` | | | ✅ | General web search for research |

---

## ⚙️ Configuration

### Environment Variables (`.env`)

```bash
# LLM API (OpenAI-compatible endpoint)
API_BASE=http://localhost:8080/v1
API_KEY=your_api_key
MODEL=mimo-v2.5-pro

# Blockchain APIs
ETHERSCAN_API_KEY=your_etherscan_key
SOLSCAN_API_KEY=your_solscan_key

# Optional
COINGECKO_API_KEY=
```

### Agent Config (`configs/agents.yaml`)

```yaml
orchestrator:
  model: mimo-v2.5-pro
  temperature: 0.3
  max_tokens: 4096
  max_iterations: 10

agents:
  onchain:
    model: mimo-v2.5-pro
    temperature: 0.2
    max_tokens: 4096
    tools:
      - get_wallet_balance
      - get_recent_transactions
      - detect_whale_movements
      - analyze_contract
    chains:
      - ethereum
      - solana
      - base
      - arbitrum

  market:
    model: mimo-v2.5-pro
    temperature: 0.2
    max_tokens: 4096
    tools:
      - get_token_price
      - get_jupiter_quote
      - get_trending_tokens
      - calculate_impermanent_loss
      - get_top_pairs

  research:
    model: mimo-v2.5-pro
    temperature: 0.4
    max_tokens: 4096
    tools:
      - search_arxiv
      - get_crypto_news
      - fetch_url_content
      - analyze_sentiment
      - search_web
```

**Key Config Knobs:**
- `temperature` — Lower = more deterministic (0.2 for data agents, 0.4 for research)
- `max_tokens` — Maximum tokens per LLM response
- `max_iterations` — Max ReAct reasoning loops before forced stop
- `tools` — Which tools each agent can access
- `chains` — Supported blockchains for the on-chain agent

---

## 🐳 Deployment

### Docker (Recommended)

```bash
# Build and run
docker build -t crypto-agent-platform .
docker run --env-file configs/.env crypto-agent-platform --task "Analyze ETH market"

# Or use docker-compose
docker-compose up -d
```

### Docker Compose

```yaml
version: "3.9"
services:
  agent:
    build: .
    env_file: ./configs/.env
    volumes:
      - ./configs:/app/configs
      - ./output:/app/output
    command: >
      python -m src.main
      --task "Daily DeFi scan: find top 5 opportunities"
      --output /app/output/report.md
      --format markdown
```

### Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python -m src.main --task "Hello" -v
```

### Production Tips

- Set `temperature: 0.2` for deterministic market/on-chain data queries
- Increase `max_iterations` to 15-20 for complex multi-step research
- Use `--format json` for pipeline integration
- Monitor `tokens_used` and `duration_ms` in results for cost tracking
- Run behind a reverse proxy if exposing as an API service

---

## 📁 Project Structure

```
crypto-agent-platform/
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py             # BaseAgent + Tool + AgentResult
│   │   ├── orchestrator.py     # Supervisor agent
│   │   ├── onchain.py          # Blockchain intelligence
│   │   ├── market.py           # DEX/CEX market data
│   │   └── research.py         # Papers, news, sentiment
│   ├── tools/
│   │   └── __init__.py
│   └── workflows/
│       └── __init__.py
├── configs/
│   ├── agents.yaml             # Agent configuration
│   └── example.env             # Environment template
├── examples/
│   ├── whale_detection.py      # Whale tracking pipeline
│   └── defi_scanner.py         # DeFi opportunity scanner
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Commit** your changes: `git commit -m 'Add amazing feature'`
4. **Push** to the branch: `git push origin feature/amazing-feature`
5. **Open** a Pull Request

### Development Setup

```bash
git clone https://github.com/kevinroy75/crypto-agent-platform.git
cd crypto-agent-platform
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Ideas for Contributions

- 🔗 Add new blockchain integrations (Polygon, Avalanche, BSC)
- 🛠️ Build new tools (NFT analytics, DAO governance tracking)
- 📊 Add visualization outputs (charts, dashboards)
- 🧪 Write tests and improve coverage
- 📖 Improve documentation and examples
- 🐛 Fix bugs and improve error handling

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
MIT License

Copyright (c) 2025 Kevin Roy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software...
```

---

## ⭐ Star History

<a href="https://github.com/kevinroy75/crypto-agent-platform/stargazers">
  <img src="https://api.star-history.com/svg?repos=kevinroy75/crypto-agent-platform&type=Date" alt="Star History Chart" width="100%">
</a>

---

<div align="center">

**Built with 🧠 MiMo v2.5 Pro** · **[Report Bug](https://github.com/kevinroy75/crypto-agent-platform/issues)** · **[Request Feature](https://github.com/kevinroy75/crypto-agent-platform/issues)**

</div>
