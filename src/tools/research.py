"""
Research and knowledge tools: ArXiv, news aggregation, web fetching, sentiment analysis.
"""
import asyncio
import json
import logging
import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

from .base import BaseTool

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────

ARXIV_API = "http://export.arxiv.org/api/query"
CRYPTOPANIC_API = "https://cryptopanic.com/api/v1"
NEWSAPI_API = "https://newsapi.org/v2"


# ═══════════════════════════════════════════════════════════════════════
# ArXiv Tool
# ═══════════════════════════════════════════════════════════════════════

class ArxivTool(BaseTool):
    """Search and retrieve academic papers from ArXiv."""

    def __init__(self, **kwargs):
        super().__init__(timeout=20.0, **kwargs)

    @property
    def name(self) -> str:
        return "arxiv"

    @property
    def description(self) -> str:
        return (
            "Search ArXiv for academic papers on cryptography, blockchain, "
            "zero-knowledge proofs, consensus mechanisms, and DeFi protocols."
        )

    @staticmethod
    def _parse_arxiv_response(xml_text: str) -> list[dict]:
        """Parse ArXiv Atom XML response into structured data."""
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        root = ET.fromstring(xml_text)
        papers = []
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).strip().replace("\n", " ")
            summary = entry.findtext("atom:summary", "", ns).strip().replace("\n", " ")
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            published = entry.findtext("atom:published", "", ns)
            link = ""
            for l in entry.findall("atom:link", ns):
                if l.get("type") == "text/html":
                    link = l.get("href", "")
                    break
            if not link:
                link = entry.findtext("atom:id", "", ns)

            categories = [c.get("term", "") for c in entry.findall("atom:category", ns)]
            papers.append({
                "title": title,
                "authors": authors,
                "abstract": summary[:500] + ("..." if len(summary) > 500 else ""),
                "published": published,
                "url": link,
                "categories": categories,
            })
        return papers

    async def search_arxiv(
        self,
        query: str,
        max_results: int = 5,
        sort_by: str = "relevance",
        category: Optional[str] = None,
    ) -> dict:
        """Search ArXiv for papers matching a query."""
        try:
            search_query = query
            if category:
                search_query = f"cat:{category} AND all:{query}"
            else:
                search_query = f"all:{query}"

            sort_map = {
                "relevance": "relevance",
                "date": "lastUpdatedDate",
                "submitted": "submittedDate",
            }

            result = await self._get(
                ARXIV_API,
                params={
                    "search_query": search_query,
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": sort_map.get(sort_by, "relevance"),
                    "sortOrder": "descending",
                },
            )

            if isinstance(result, str):
                papers = self._parse_arxiv_response(result)
                return self.success({
                    "query": query,
                    "papers": papers,
                    "count": len(papers),
                }, meta={"source": "arxiv"})

            return self.success({"query": query, "papers": [], "raw": str(result)[:500]})
        except Exception as exc:
            logger.error(f"ArXiv search failed: {exc}")
            return self.error(str(exc), code="ARXIV_SEARCH_ERROR")

    async def execute(self, **kwargs) -> dict:
        return await self.search_arxiv(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Crypto News Tool
# ═══════════════════════════════════════════════════════════════════════

class CryptoNewsTool(BaseTool):
    """Aggregate crypto news from multiple sources."""

    def __init__(self, cryptopanic_key: Optional[str] = None, newsapi_key: Optional[str] = None, **kwargs):
        super().__init__(timeout=15.0, **kwargs)
        self._cryptopanic_key = cryptopanic_key or self._env("CRYPTOPANIC_API_KEY")
        self._newsapi_key = newsapi_key or self._env("NEWSAPI_API_KEY")

    @property
    def name(self) -> str:
        return "crypto_news"

    @property
    def description(self) -> str:
        return (
            "Fetch the latest cryptocurrency news from CryptoPanic and NewsAPI. "
            "Filter by coin, sentiment (bullish/bearish), and source."
        )

    async def get_crypto_news(
        self,
        currencies: Optional[str] = None,
        filter_type: str = "hot",
        kind: str = "news",
        limit: int = 10,
    ) -> dict:
        """
        Fetch crypto news from CryptoPanic.
        filter_type: rising, hot, bullish, bearish, important, lol
        kind: news, media
        """
        try:
            if not self._cryptopanic_key:
                return self.error(
                    "CRYPTOPANIC_API_KEY not configured",
                    code="MISSING_API_KEY",
                )

            params: dict[str, Any] = {
                "auth_token": self._cryptopanic_key,
                "public": "true",
                "kind": kind,
            }
            if currencies:
                params["currencies"] = currencies

            result = await self._get(
                f"{CRYPTOPANIC_API}/posts/",
                params=params,
            )

            posts = result.get("results", []) if isinstance(result, dict) else []
            normalised = [
                {
                    "title": p.get("title"),
                    "url": p.get("url"),
                    "source": p.get("source", {}).get("title"),
                    "published": p.get("published_at"),
                    "currencies": [c.get("code") for c in p.get("currencies", [])],
                    "votes": p.get("votes", {}),
                }
                for p in posts[:limit]
            ]

            return self.success({
                "news": normalised,
                "count": len(normalised),
                "filter": filter_type,
            }, meta={"source": "cryptopanic"})
        except Exception as exc:
            return self.error(str(exc), code="NEWS_FETCH_ERROR")

    async def get_general_crypto_news(self, query: str = "cryptocurrency", limit: int = 10) -> dict:
        """Fallback: search for crypto news via NewsAPI."""
        try:
            if not self._newsapi_key:
                return self.error("NEWSAPI_API_KEY not configured", code="MISSING_API_KEY")

            result = await self._get(
                f"{NEWSAPI_API}/everything",
                params={
                    "q": query,
                    "language": "en",
                    "sortBy": "publishedAt",
                    "pageSize": limit,
                },
                headers={"X-Api-Key": self._newsapi_key},
            )

            articles = result.get("articles", []) if isinstance(result, dict) else []
            normalised = [
                {
                    "title": a.get("title"),
                    "description": a.get("description"),
                    "url": a.get("url"),
                    "source": a.get("source", {}).get("name"),
                    "published": a.get("publishedAt"),
                    "author": a.get("author"),
                }
                for a in articles[:limit]
            ]
            return self.success({"news": normalised, "count": len(normalised)}, meta={"source": "newsapi"})
        except Exception as exc:
            return self.error(str(exc), code="NEWSAPI_ERROR")

    async def execute(self, **kwargs) -> dict:
        action = kwargs.pop("action", "crypto")
        if action == "crypto":
            return await self.get_crypto_news(**kwargs)
        elif action == "general":
            return await self.get_general_crypto_news(**kwargs)
        return self.error(f"Unknown action: {action}", code="INVALID_ACTION")


# ═══════════════════════════════════════════════════════════════════════
# Web Fetch Tool
# ═══════════════════════════════════════════════════════════════════════

class WebFetchTool(BaseTool):
    """Fetch and extract content from arbitrary web URLs."""

    def __init__(self, **kwargs):
        super().__init__(timeout=20.0, **kwargs)

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch a URL and extract its text content. "
            "Useful for reading documentation, blog posts, and protocol pages."
        )

    @staticmethod
    def _extract_text(html: str, max_chars: int = 10_000) -> str:
        """Naive HTML-to-text extraction without BeautifulSoup dependency."""
        # Remove script and style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]

    async def fetch_url_content(self, url: str, extract_text: bool = True, max_chars: int = 10_000) -> dict:
        """Fetch a URL and return its content."""
        try:
            client = await self._get_client()
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            raw_text = response.text

            if extract_text and "html" in content_type:
                content = self._extract_text(raw_text, max_chars)
            else:
                content = raw_text[:max_chars]

            return self.success({
                "url": str(response.url),
                "status_code": response.status_code,
                "content_type": content_type,
                "content": content,
                "content_length": len(content),
            })
        except Exception as exc:
            return self.error(str(exc), code="FETCH_ERROR")

    async def execute(self, **kwargs) -> dict:
        return await self.fetch_url_content(**kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Sentiment Analysis Tool
# ═══════════════════════════════════════════════════════════════════════

class SentimentTool(BaseTool):
    """
    Rule-based + keyword sentiment analysis for crypto text.
    For production, this would wrap an LLM or fine-tuned model call.
    """

    def __init__(self, **kwargs):
        super().__init__(timeout=5.0, **kwargs)

    @property
    def name(self) -> str:
        return "sentiment"

    @property
    def description(self) -> str:
        return (
            "Analyze sentiment of crypto-related text. "
            "Returns a score from -1 (very bearish) to +1 (very bullish) with label."
        )

    _BULLISH_KEYWORDS = {
        "bullish", "moon", "pump", "surge", "rally", "breakout", "all-time high",
        "ath", "adoption", "partnership", "upgrade", "launch", "growth",
        "accumulation", "buy", "long", "outperform", "profit", "gain",
        "milestone", "record", "high", "increase", "rise", "soar",
    }
    _BEARISH_KEYWORDS = {
        "bearish", "dump", "crash", "plunge", "sell-off", "liquidation",
        "hack", "exploit", "rug", "scam", "fear", "loss", "decline",
        "drop", "low", "decrease", "fall", "correction", "capitulation",
        "short", "underperform", "risk", "warning", "ban", "regulate",
    }

    async def analyze_sentiment(self, text: str) -> dict:
        """Perform keyword-based sentiment analysis on crypto text."""
        try:
            lower = text.lower()
            words = set(re.findall(r"\b[\w'-]+\b", lower))

            bullish_hits = words & self._BULLISH_KEYWORDS
            bearish_hits = words & self._BEARISH_KEYWORDS

            total = len(bullish_hits) + len(bearish_hits)
            if total == 0:
                score = 0.0
                label = "neutral"
            else:
                score = (len(bullish_hits) - len(bearish_hits)) / total
                if score > 0.3:
                    label = "bullish"
                elif score < -0.3:
                    label = "bearish"
                else:
                    label = "neutral"

            return self.success({
                "text_preview": text[:200] + ("..." if len(text) > 200 else ""),
                "score": round(score, 3),
                "label": label,
                "bullish_signals": sorted(bullish_hits),
                "bearish_signals": sorted(bearish_hits),
                "confidence": min(total / 10, 1.0),
            })
        except Exception as exc:
            return self.error(str(exc), code="SENTIMENT_ERROR")

    async def execute(self, **kwargs) -> dict:
        text = kwargs.get("text", "")
        if not text:
            return self.error("No text provided for sentiment analysis", code="MISSING_INPUT")
        return await self.analyze_sentiment(text)


# ═══════════════════════════════════════════════════════════════════════
# Web Search Tool
# ═══════════════════════════════════════════════════════════════════════

class WebSearchTool(BaseTool):
    """Search the web using DuckDuckGo's lite HTML endpoint (no API key required)."""

    def __init__(self, **kwargs):
        super().__init__(timeout=15.0, **kwargs)

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for crypto-related information using DuckDuckGo. "
            "No API key required. Returns titles, URLs, and snippets."
        )

    async def search_web(self, query: str, max_results: int = 10) -> dict:
        """Search DuckDuckGo for a query."""
        try:
            client = await self._get_client()
            response = await client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; CryptoAgent/1.0)",
                },
            )
            response.raise_for_status()
            html = response.text

            # Parse result links from the lite HTML
            results = []
            # Find result blocks: look for <a> tags with class="result-link"
            link_pattern = re.compile(
                r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>([^<]+)</a>',
                re.IGNORECASE,
            )
            snippet_pattern = re.compile(
                r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
                re.DOTALL | re.IGNORECASE,
            )

            links = link_pattern.findall(html)
            snippets = snippet_pattern.findall(html)

            for i, (url, title) in enumerate(links[:max_results]):
                snippet = ""
                if i < len(snippets):
                    snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                results.append({
                    "title": title.strip(),
                    "url": url.strip(),
                    "snippet": snippet[:300],
                })

            return self.success({
                "query": query,
                "results": results,
                "count": len(results),
            }, meta={"source": "duckduckgo"})
        except Exception as exc:
            logger.error(f"Web search failed: {exc}")
            return self.error(str(exc), code="SEARCH_ERROR")

    async def execute(self, **kwargs) -> dict:
        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 10)
        if not query:
            return self.error("No query provided", code="MISSING_INPUT")
        return await self.search_web(query, max_results=max_results)
