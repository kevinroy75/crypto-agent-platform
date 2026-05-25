"""
Base tool class with async HTTP client, retry logic, and rate limiting.
Provides a foundation for all platform tools.
"""
import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_second: float = 5.0
    burst_limit: int = 10
    cooldown_seconds: float = 1.0


@dataclass
class RetryConfig:
    """Retry configuration for HTTP requests."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)


class TokenBucketRateLimiter:
    """Token bucket rate limiter for API calls."""

    def __init__(self, rate: float, burst: int = 1):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_refill = now

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self.rate
                logger.debug(f"Rate limiter: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1


class BaseTool(ABC):
    """
    Abstract base class for all platform tools.
    Provides:
      - Managed httpx.AsyncClient with connection pooling
      - Configurable retry with exponential backoff
      - Token-bucket rate limiting
      - Structured error handling
      - Consistent result formatting
    """

    def __init__(
        self,
        rate_limit: Optional[RateLimitConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        timeout: float = 30.0,
        default_headers: Optional[dict[str, str]] = None,
    ):
        self._rate_limit = rate_limit or RateLimitConfig()
        self._retry = retry_config or RetryConfig()
        self._timeout = timeout
        self._default_headers = default_headers or {}
        self._limiter = TokenBucketRateLimiter(
            rate=self._rate_limit.requests_per_second,
            burst=self._rate_limit.burst_limit,
        )
        self._client: Optional[httpx.AsyncClient] = None

    # ── Properties to override ────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name used for registration."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers=self._default_headers,
                follow_redirects=True,
                http2=True,
            )
        return self._client

    async def close(self) -> None:
        """Gracefully close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    # ── HTTP helpers ──────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[Any] = None,
        data: Optional[dict] = None,
        headers: Optional[dict[str, str]] = None,
        retries: Optional[RetryConfig] = None,
    ) -> dict | list | str:
        """
        Execute an HTTP request with rate limiting and automatic retries.
        Returns parsed JSON when possible, raw text otherwise.
        """
        cfg = retries or self._retry
        client = await self._get_client()

        last_exc: Exception | None = None
        for attempt in range(1, cfg.max_retries + 1):
            await self._limiter.acquire()
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    headers=headers,
                )

                if response.status_code in cfg.retryable_status_codes:
                    delay = min(
                        cfg.base_delay * (cfg.exponential_base ** (attempt - 1)),
                        cfg.max_delay,
                    )
                    # Respect Retry-After header
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                    logger.warning(
                        f"[{self.name}] Retryable status {response.status_code} "
                        f"on {url} (attempt {attempt}/{cfg.max_retries}), "
                        f"sleeping {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue

                response.raise_for_status()

                # Try to return parsed JSON
                content_type = response.headers.get("content-type", "")
                if "json" in content_type or "javascript" in content_type:
                    return response.json()
                return response.text

            except httpx.TimeoutException as exc:
                last_exc = exc
                delay = min(
                    cfg.base_delay * (cfg.exponential_base ** (attempt - 1)),
                    cfg.max_delay,
                )
                logger.warning(
                    f"[{self.name}] Timeout on {url} (attempt {attempt}/{cfg.max_retries})"
                )
                if attempt < cfg.max_retries:
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in cfg.retryable_status_codes:
                    raise
                delay = min(
                    cfg.base_delay * (cfg.exponential_base ** (attempt - 1)),
                    cfg.max_delay,
                )
                if attempt < cfg.max_retries:
                    await asyncio.sleep(delay)

            except Exception as exc:
                last_exc = exc
                logger.error(f"[{self.name}] Unexpected error on {url}: {exc}")
                raise

        raise last_exc or RuntimeError(
            f"[{self.name}] Request failed after {cfg.max_retries} retries"
        )

    async def _get(self, url: str, **kwargs) -> Any:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> Any:
        return await self._request("POST", url, **kwargs)

    # ── Result helpers ────────────────────────────────────────────────

    @staticmethod
    def success(data: Any, *, meta: Optional[dict] = None) -> dict:
        """Build a structured success result."""
        return {
            "status": "success",
            "data": data,
            "meta": meta or {},
        }

    @staticmethod
    def error(message: str, *, code: str = "UNKNOWN", details: Any = None) -> dict:
        """Build a structured error result."""
        result: dict[str, Any] = {
            "status": "error",
            "error": message,
            "code": code,
        }
        if details is not None:
            result["details"] = details
        return result

    # ── Env helpers ───────────────────────────────────────────────────

    @staticmethod
    def _env(key: str, default: str = "") -> str:
        """Read an environment variable with a fallback."""
        return os.getenv(key, default)

    # ── Abstract interface ────────────────────────────────────────────

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """
        Run the tool with the given keyword arguments.
        Must return a dict with at minimum 'status' and 'data' or 'error'.
        """
        ...
