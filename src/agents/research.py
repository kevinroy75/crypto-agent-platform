"""
Research Agent: paper search, news aggregation, sentiment analysis.
"""
import json
import logging
import re

import httpx

from src.agents.base import BaseAgent, Tool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Research Agent specializing in crypto/AI research and intelligence.

Your capabilities:
- ArXiv paper search: find and summarize academic papers on blockchain, DeFi, AI agents
- News aggregation: collect and summarize recent crypto news from multiple sources
- Sentiment analysis: gauge market sentiment from social media and news
- Protocol documentation: parse and summarize whitepapers and docs

Output: structured summaries with sources, key findings, and relevance assessment.
Always include: paper titles, authors, dates, and direct links when available."""


class ResearchAgent(BaseAgent):
    """Agent for research, papers, and news analysis."""

    def __init__(self, verbose: bool = False, **kwargs):
        super().__init__(
            name="ResearchAgent",
            system_prompt=SYSTEM_PROMPT,
            verbose=verbose,
            **kwargs,
        )

    def _register_tools(self):
        self.add_tool(Tool(
            name="search_arxiv",
            description="Search ArXiv for academic papers. Returns titles, abstracts, authors, and links.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g., 'blockchain scalability', 'DeFi MEV')"},
                    "max_results": {"type": "integer", "description": "Maximum results (default 5)"},
                    "sort_by": {"type": "string", "enum": ["relevance", "lastUpdatedDate", "submittedDate"], "description": "Sort order"},
                },
                "required": ["query"],
            },
            function=self._search_arxiv,
        ))

        self.add_tool(Tool(
            name="get_crypto_news",
            description="Get latest crypto news from CoinGecko news feed.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of articles (default 10)"},
                },
            },
            function=self._get_news,
        ))

        self.add_tool(Tool(
            name="fetch_url_content",
            description="Fetch and extract text content from a URL. Use for reading documentation, blog posts, or whitepapers.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to fetch"},
                    "max_chars": {"type": "integer", "description": "Maximum characters to return (default 5000)"},
                },
                "required": ["url"],
            },
            function=self._fetch_url,
        ))

        self.add_tool(Tool(
            name="analyze_sentiment",
            description="Analyze market sentiment for a token or topic from recent news and social signals.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Token name or topic to analyze"},
                },
                "required": ["topic"],
            },
            function=self._analyze_sentiment,
        ))

        self.add_tool(Tool(
            name="search_web",
            description="Search the web for information on a topic. Returns top results with snippets.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results (default 5)"},
                },
                "required": ["query"],
            },
            function=self._search_web,
        ))

    async def _search_arxiv(self, query: str, max_results: int = 5, sort_by: str = "relevance") -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://export.arxiv.org/api/query",
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": sort_by,
                    "sortOrder": "descending",
                },
            )
            # Parse XML response
            entries = []
            xml_text = resp.text
            for match in re.finditer(r"<entry>(.*?)</entry>", xml_text, re.DOTALL):
                entry_xml = match.group(1)
                title = re.search(r"<title>(.*?)</title>", entry_xml, re.DOTALL)
                summary = re.search(r"<summary>(.*?)</summary>", entry_xml, re.DOTALL)
                link = re.search(r'<id>(.*?)</id>', entry_xml)
                published = re.search(r"<published>(.*?)</published>", entry_xml)
                authors = re.findall(r"<name>(.*?)</name>", entry_xml)

                entries.append({
                    "title": title.group(1).strip().replace("\n", " ") if title else "N/A",
                    "authors": authors[:3],
                    "abstract": summary.group(1).strip()[:300] + "..." if summary else "N/A",
                    "url": link.group(1) if link else "N/A",
                    "published": published.group(1) if published else "N/A",
                })

            return json.dumps({"query": query, "results": entries, "count": len(entries)}, indent=2)

    async def _get_news(self, limit: int = 10) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://api.coingecko.com/api/v3/news")
            data = resp.json()
            articles = []
            for item in data.get("data", [])[:limit]:
                articles.append({
                    "title": item.get("title", ""),
                    "description": item.get("description", "")[:200],
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "published_at": item.get("published_at", ""),
                })
            return json.dumps({"articles": articles, "count": len(articles)}, indent=2)

    async def _fetch_url(self, url: str, max_chars: int = 5000) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, follow_redirects=True, timeout=15)
            text = resp.text
            # Strip HTML tags (basic)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:max_chars]

    async def _analyze_sentiment(self, topic: str) -> str:
        # Combine news search with basic keyword sentiment
        news = await self._get_news(limit=20)
        news_data = json.loads(news)

        positive_words = {"surge", "rally", "bullish", "breakout", "adoption", "partnership", "launch", "growth", "upgrade"}
        negative_words = {"crash", "hack", "exploit", "bearish", "dump", "lawsuit", "ban", "vulnerability", "scam"}

        pos_count = 0
        neg_count = 0
        relevant = []

        for article in news_data.get("articles", []):
            text = (article.get("title", "") + " " + article.get("description", "")).lower()
            if topic.lower() in text:
                relevant.append(article["title"])
                for w in positive_words:
                    if w in text:
                        pos_count += 1
                for w in negative_words:
                    if w in text:
                        neg_count += 1

        total = pos_count + neg_count
        if total == 0:
            sentiment = "neutral"
            score = 0.5
        elif pos_count > neg_count:
            sentiment = "positive"
            score = 0.5 + (pos_count - neg_count) / (total * 2)
        else:
            sentiment = "negative"
            score = 0.5 - (neg_count - pos_count) / (total * 2)

        return json.dumps({
            "topic": topic,
            "sentiment": sentiment,
            "score": round(score, 2),
            "positive_signals": pos_count,
            "negative_signals": neg_count,
            "relevant_articles": relevant,
            "sample_size": len(news_data.get("articles", [])),
        }, indent=2)

    async def _search_web(self, query: str, num_results: int = 5) -> str:
        # Uses DuckDuckGo Lite for web search (no API key needed)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            text = resp.text
            # Parse results (basic extraction)
            results = []
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', text)
            for url, title in links[:num_results]:
                results.append({"title": re.sub(r"<[^>]+>", "", title).strip(), "url": url})

            if not results:
                # Fallback: extract any links
                links = re.findall(r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text)
                for url, title in links[:num_results]:
                    clean_title = re.sub(r"<[^>]+>", "", title).strip()
                    if clean_title and url.startswith("http"):
                        results.append({"title": clean_title, "url": url})

            return json.dumps({"query": query, "results": results, "count": len(results)}, indent=2)
