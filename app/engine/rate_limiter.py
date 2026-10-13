import asyncio
import time
from dataclasses import dataclass
from typing import Dict
from urllib.parse import urlparse
from app.config import settings


@dataclass
class TokenBucket:
    rate: float
    capacity: float
    tokens: float
    last_refill: float

    def refill(self) -> None:
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    def consume(self, amount: float = 1.0) -> bool:
        self.refill()
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def wait_time(self, amount: float = 1.0) -> float:
        self.refill()
        if self.tokens >= amount:
            return 0.0
        needed = amount - self.tokens
        return needed / self.rate


class DomainRateLimiter:
    """Per-domain token bucket limiter preventing target server overload and IP bans."""

    def __init__(
        self, default_rps: float = settings.DEFAULT_RATE_LIMIT_RPS, burst: float = 2.0
    ) -> None:
        self.default_rps = default_rps
        self.default_burst = burst
        self._buckets: Dict[str, TokenBucket] = {}

    @staticmethod
    def extract_domain(url_or_domain: str) -> str:
        if "://" in url_or_domain:
            parsed = urlparse(url_or_domain)
            host = parsed.netloc.lower()
        else:
            host = url_or_domain.lower()
        if host.startswith("www."):
            host = host[4:]
        return host or "unknown"

    def _get_bucket(self, domain: str) -> TokenBucket:
        clean = self.extract_domain(domain)
        if clean not in self._buckets:
            self._buckets[clean] = TokenBucket(
                rate=self.default_rps,
                capacity=self.default_burst,
                tokens=self.default_burst,
                last_refill=time.monotonic(),
            )
        return self._buckets[clean]

    def try_acquire(self, url_or_domain: str) -> bool:
        bucket = self._get_bucket(url_or_domain)
        return bucket.consume(1.0)

    async def acquire(self, url_or_domain: str) -> float:
        bucket = self._get_bucket(url_or_domain)
        wait_s = bucket.wait_time(1.0)
        if wait_s > 0:
            await asyncio.sleep(min(wait_s, 2.0))
        bucket.consume(1.0)
        return wait_s

    def tracked_domains_count(self) -> int:
        return len(self._buckets)


rate_limiter = DomainRateLimiter()
