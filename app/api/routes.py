from typing import List
from fastapi import APIRouter, HTTPException
from app.database import db
from app.engine.proxy_manager import proxy_pool
from app.models.schemas import (
    BatchCrawlRequest,
    ClusterMetricsOut,
    CrawlRequest,
    CrawlResultResponse,
    ExtractionMode,
    PriceMonitorCreate,
    PriceMonitorOut,
    ProxyNodeCreate,
    ProxyNodeOut,
)
from app.workers.queue_manager import queue_manager

router = APIRouter(prefix="/api/v1", tags=["CrawlMesh API"])


@router.get("/metrics", response_model=ClusterMetricsOut)
async def get_metrics():
    return queue_manager.get_metrics()


@router.post("/crawl", response_model=CrawlResultResponse)
async def trigger_crawl(payload: CrawlRequest):
    job = await queue_manager.execute_crawl(payload)
    return job


@router.post("/crawl/batch", response_model=List[CrawlResultResponse])
async def trigger_batch_crawl(payload: BatchCrawlRequest):
    requests = [
        CrawlRequest(
            url=u,
            mode=payload.mode,
            priority=payload.priority,
            selectors=payload.selectors,
        )
        for u in payload.urls
    ]
    return await queue_manager.execute_batch(requests)


@router.get("/jobs", response_model=List[CrawlResultResponse])
async def list_crawl_jobs(limit: int = 50):
    return db.list_jobs(limit=min(limit, 200))


@router.get("/jobs/{job_id}", response_model=CrawlResultResponse)
async def get_crawl_job(job_id: str):
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.get("/monitors", response_model=List[PriceMonitorOut])
async def list_price_monitors():
    return db.list_monitors()


@router.post("/monitors", response_model=PriceMonitorOut)
async def create_price_monitor(payload: PriceMonitorCreate):
    data = payload.model_dump()
    if data.get("current_price") is None:
        crawl_res = await queue_manager.execute_crawl(
            CrawlRequest(
                url=payload.url,
                mode=ExtractionMode.PRICE,
                selectors={"price": payload.css_selector}
                if payload.css_selector
                else None,
            )
        )
        price_intel = crawl_res.get("price_intel") or {}
        if price_intel.get("detected") and price_intel.get("amount"):
            data["current_price"] = price_intel["amount"]
            data["in_stock"] = price_intel.get("in_stock", True)
    return db.create_monitor(data)


@router.post("/monitors/{monitor_id}/check", response_model=PriceMonitorOut)
async def check_price_monitor(monitor_id: int):
    monitor = db.get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    crawl_res = await queue_manager.execute_crawl(
        CrawlRequest(
            url=monitor["url"],
            mode=ExtractionMode.PRICE,
        )
    )
    price_intel = crawl_res.get("price_intel") or {}
    new_price = price_intel.get("amount") or monitor.get("current_price") or monitor["target_price"]
    in_stock = price_intel.get("in_stock", True)
    updated = db.update_monitor_price(monitor_id, float(new_price), in_stock=in_stock)
    return updated


@router.delete("/monitors/{monitor_id}")
async def remove_price_monitor(monitor_id: int):
    removed = db.delete_monitor(monitor_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return {"deleted": True, "id": monitor_id}


@router.get("/proxies", response_model=List[ProxyNodeOut])
async def list_proxies():
    return proxy_pool.list_nodes()


@router.post("/proxies", response_model=ProxyNodeOut)
async def register_proxy(payload: ProxyNodeCreate):
    node = proxy_pool.add_node(
        endpoint=payload.endpoint,
        region=payload.region,
        protocol=payload.protocol,
    )
    return node.to_dict()


@router.delete("/proxies/{node_id}")
async def delete_proxy(node_id: str):
    removed = proxy_pool.remove_node(node_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Proxy node not found")
    return {"deleted": True, "id": node_id}


@router.get("/connectors/fx")
async def get_live_exchange_rates():
    from app.engine.public_connectors import public_connectors

    return await public_connectors.get_live_fx_rates()


@router.get("/connectors/ip/{ip_address}")
async def inspect_ip_telemetry(ip_address: str):
    from app.engine.public_connectors import public_connectors

    return await public_connectors.inspect_ip_network(ip_address)


@router.get("/connectors/catalog")
async def search_public_catalog(q: str = "laptop", limit: int = 5):
    from app.engine.public_connectors import public_connectors

    return await public_connectors.fetch_public_catalog_products(query=q, limit=limit)
