# Multi-Agent Crypto Research Platform

> An autonomous multi-agent system for blockchain research, on-chain analysis, and DeFi opportunity discovery. Powered by LLM-driven agents with tool-use capabilities.

## Architecture

```
                    ┌─────────────────────┐
                    │   Orchestrator Agent │
                    │   (Task Router)      │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
   ┌────────▼────────┐ ┌──────▼──────┐ ┌─────────▼────────┐
   │  On-Chain Agent  │ │ Market Agent│ │  Research Agent   │
   │  (EVM/Solana)    │ │ (DEX/CEX)   │ │  (Papers/News)   │
   └────────┬────────┘ └──────┬──────┘ └─────────┬────────┘
            │                  │                  │
   ┌────────▼────────┐ ┌──────▼──────┐ ┌─────────▼────────┐
   │  Etherscan API   │ │  Jupiter    │ │  ArXiv Search    │
   │  Solscan API     │ │  Uniswap    │ │  Web Scraper     │
   │  Web3 RPC        │ │  1inch      │ │  RSS Feeds       │
   └─────────────────┘ └─────────────┘ └──────────────────┘
```

## Features

- **Multi-Agent Orchestration**: Supervisor agent delegates tasks to specialized sub-agents
- **On-Chain Intelligence**: Real-time wallet tracking, whale movement detection, smart money flow analysis
- **DEX/CEX Monitoring**: Cross-exchange price feeds, liquidity analysis, arbitrage opportunity detection
- **Research Pipeline**: Automated paper summarization, news aggregation, sentiment scoring
- **Long-Chain Reasoning**: Multi-step analysis with intermediate verification
- **Tool Use**: 15+ integrated tools (blockchain APIs, web scraping, data processing)

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/crypto-agent-platform.git
cd crypto-agent-platform

# Install
pip install -r requirements.txt

# Configure
cp configs/example.env configs/.env
# Edit .env with your API keys

# Run
python -m src.main --task "Analyze top 10 DEX tokens by TVL and find undervalued gems"
```

## Agents

### Orchestrator Agent
Routes tasks to appropriate specialist agents, manages conversation context, and synthesizes final outputs.

### On-Chain Agent
- Wallet profiling and portfolio analysis
- Whale wallet tracking (>100 ETH transfers)
- Smart contract interaction analysis
- Gas optimization recommendations

### Market Agent
- Real-time DEX price aggregation (Jupiter, Uniswap V3, 1inch)
- Liquidity depth analysis
- Impermanent loss calculator
- Cross-chain bridge monitoring

### Research Agent
- ArXiv paper search and summarization
- Crypto news RSS aggregation
- Sentiment analysis from social feeds
- Protocol documentation parsing

## Configuration

```yaml
# configs/agents.yaml
orchestrator:
  model: mimo-v2.5-pro
  temperature: 0.3
  max_tokens: 4096

onchain_agent:
  model: mimo-v2.5-pro
  tools: [etherscan, solscan, web3_rpc]
  chains: [ethereum, solana, base, arbitrum]

market_agent:
  model: mimo-v2.5-pro
  tools: [jupiter, uniswap, oneinch, coingecko]

research_agent:
  model: mimo-v2.5-pro
  tools: [arxiv, web_search, rss_reader]
```

## Tech Stack

- **Runtime**: Python 3.10+
- **LLM**: Xiaomi MiMo v2.5 Pro (via OpenAI-compatible API)
- **Blockchain**: web3.py, solana-py
- **APIs**: Etherscan, Solscan, Jupiter, 1inch, CoinGecko
- **Agent Framework**: Custom supervisor pattern with tool-use
- **Data**: SQLite for caching, pandas for analysis

## License

MIT
