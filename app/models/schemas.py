from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExtractionMode(str, Enum):
    AUTO = "auto"
    PRICE = "price"
    SELECTORS = "selectors"


class JobPriority(str, Enum):
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CrawlRequest(BaseModel):
    url: str = Field(..., description="Target URL to extract")
    mode: ExtractionMode = Field(
        default=ExtractionMode.AUTO,
        description="Extraction mode: auto (Markdown + Metadata + Price), price, or selectors",
    )
    selectors: Optional[Dict[str, str]] = Field(
        default=None,
        description="Custom CSS selectors map (e.g. {'title': 'h1', 'price': '.price'})",
    )
    priority: JobPriority = Field(default=JobPriority.NORMAL)
    use_stealth_headers: bool = Field(default=True)
    raw_html_override: Optional[str] = Field(
        default=None,
        description="Optional raw HTML payload for offline/deterministic parsing",
    )


class BatchCrawlRequest(BaseModel):
    urls: List[str] = Field(..., min_length=1, max_length=50)
    mode: ExtractionMode = Field(default=ExtractionMode.AUTO)
    priority: JobPriority = Field(default=JobPriority.NORMAL)
    selectors: Optional[Dict[str, str]] = None


class PriceDetectionResult(BaseModel):
    detected: bool = False
    currency: Optional[str] = None
    amount: Optional[float] = None
    formatted: Optional[str] = None
    original_amount: Optional[float] = None
    discount_pct: Optional[float] = None
    in_stock: bool = True
    source_method: Optional[str] = None
    product_title: Optional[str] = None


class CrawlResultResponse(BaseModel):
    job_id: str
    url: str
    domain: str
    status: JobStatus
    http_status: int
    mode: ExtractionMode
    title: Optional[str] = None
    description: Optional[str] = None
    markdown: Optional[str] = None
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    price_intel: Optional[PriceDetectionResult] = None
    links_count: int = 0
    links: List[str] = Field(default_factory=list)
    fingerprint_used: Optional[str] = None
    proxy_used: Optional[str] = None
    elapsed_ms: float = 0.0
    retries: int = 0
    created_at: str
    error: Optional[str] = None


class PriceMonitorCreate(BaseModel):
    name: str = Field(..., description="Product display name")
    url: str = Field(..., description="Product page URL")
    store_name: str = Field(default="Generic Store")
    target_price: float = Field(..., gt=0, description="Alert threshold price")
    currency: str = Field(default="BRL")
    css_selector: Optional[str] = None
    current_price: Optional[float] = None


class PriceMonitorOut(BaseModel):
    id: int
    name: str
    url: str
    store_name: str
    currency: str
    current_price: Optional[float] = None
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    target_price: float
    in_stock: bool = True
    alert_triggered: bool = False
    last_checked_at: str
    history: List[Dict[str, Any]] = Field(default_factory=list)


class ProxyNodeCreate(BaseModel):
    endpoint: str = Field(..., description="Proxy URL (e.g. http://10.0.1.15:8080)")
    region: str = Field(default="br-saopaulo-1")
    protocol: str = Field(default="HTTP/S")


class ProxyNodeOut(BaseModel):
    id: str
    endpoint: str
    region: str
    protocol: str
    healthy: bool
    latency_ms: float
    success_count: int
    failure_count: int
    circuit_state: str


class ClusterMetricsOut(BaseModel):
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    active_workers: int
    success_rate_pct: float
    avg_latency_ms: float
    active_monitors: int
    alerts_triggered: int
    healthy_proxies: int
    tracked_domains: int
    execution_mode: str
