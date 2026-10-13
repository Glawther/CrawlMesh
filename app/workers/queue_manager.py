import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from app.config import settings
from app.database import db
from app.engine.fetcher import fetch_and_extract
from app.engine.proxy_manager import proxy_pool
from app.engine.rate_limiter import rate_limiter
from app.models.schemas import CrawlRequest, JobStatus


class CrawlQueueManager:
    """Async worker pool managing job execution, exponential backoff retries and telemetry."""

    def __init__(self, max_workers: int = settings.MAX_CONCURRENT_WORKERS) -> None:
        self.max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._active_tasks = 0

    async def execute_crawl(self, req: CrawlRequest) -> Dict[str, Any]:
        job_id = f"cm-{uuid.uuid4().hex[:8]}"
        domain = rate_limiter.extract_domain(req.url)
        created_at = datetime.now(timezone.utc).isoformat()

        job_record: Dict[str, Any] = {
            "job_id": job_id,
            "url": req.url,
            "domain": domain,
            "status": JobStatus.RUNNING.value,
            "http_status": 0,
            "mode": req.mode.value,
            "title": None,
            "description": None,
            "markdown": None,
            "extracted_data": {},
            "price_intel": {},
            "links": [],
            "fingerprint_used": None,
            "proxy_used": None,
            "elapsed_ms": 0.0,
            "retries": 0,
            "created_at": created_at,
            "error": None,
        }
        db.save_job(job_record)

        retries = 0
        last_error = None
        async with self._semaphore:
            self._active_tasks += 1
            try:
                while retries <= settings.MAX_RETRIES:
                    try:
                        result = await fetch_and_extract(
                            url=req.url,
                            selectors=req.selectors,
                            use_stealth_headers=req.use_stealth_headers,
                            raw_html_override=req.raw_html_override,
                        )
                        job_record.update(
                            {
                                "status": JobStatus.COMPLETED.value,
                                "http_status": result["http_status"],
                                "title": result["title"],
                                "description": result["description"],
                                "markdown": result["markdown"],
                                "extracted_data": result["extracted_data"],
                                "price_intel": result["price_intel"],
                                "links": result["links"],
                                "fingerprint_used": result["fingerprint_used"],
                                "proxy_used": result["proxy_used"],
                                "elapsed_ms": result["elapsed_ms"],
                                "retries": retries,
                                "error": None,
                            }
                        )
                        db.save_job(job_record)
                        return db.get_job(job_id)
                    except Exception as exc:
                        last_error = str(exc)
                        retries += 1
                        if retries <= settings.MAX_RETRIES:
                            job_record["status"] = JobStatus.RETRYING.value
                            job_record["retries"] = retries
                            db.save_job(job_record)
                            await asyncio.sleep(0.05 * (2 ** (retries - 1)))
                        else:
                            break

                job_record.update(
                    {
                        "status": JobStatus.FAILED.value,
                        "retries": retries - 1,
                        "error": last_error or "Unknown extraction failure",
                    }
                )
                db.save_job(job_record)
                return db.get_job(job_id)
            finally:
                self._active_tasks = max(0, self._active_tasks - 1)

    async def execute_batch(self, requests: List[CrawlRequest]) -> List[Dict[str, Any]]:
        tasks = [self.execute_crawl(r) for r in requests]
        return await asyncio.gather(*tasks)

    def get_metrics(self) -> Dict[str, Any]:
        jobs = db.list_jobs(limit=200)
        monitors = db.list_monitors()

        total = len(jobs)
        completed = [j for j in jobs if j["status"] == JobStatus.COMPLETED.value]
        failed = [j for j in jobs if j["status"] == JobStatus.FAILED.value]

        success_rate = (
            round((len(completed) / total) * 100.0, 1) if total > 0 else 100.0
        )
        avg_latency = (
            round(
                sum(j["elapsed_ms"] for j in completed) / len(completed),
                1,
            )
            if completed
            else 0.0
        )
        alerts_count = sum(1 for m in monitors if m.get("alert_triggered"))

        return {
            "total_jobs": total,
            "completed_jobs": len(completed),
            "failed_jobs": len(failed),
            "active_workers": self.max_workers,
            "success_rate_pct": success_rate,
            "avg_latency_ms": avg_latency,
            "active_monitors": len(monitors),
            "alerts_triggered": alerts_count,
            "healthy_proxies": proxy_pool.healthy_count(),
            "tracked_domains": max(
                rate_limiter.tracked_domains_count(),
                len({j["domain"] for j in jobs}),
            ),
            "execution_mode": settings.EXECUTION_MODE,
        }


queue_manager = CrawlQueueManager()
