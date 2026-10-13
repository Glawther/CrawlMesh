import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.config import settings


class DatabaseManager:
    """Thread-safe persistence engine supporting SQLite local mode and relational queries."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._lock = threading.RLock()
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS crawl_jobs (
                    job_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    status TEXT NOT NULL,
                    http_status INTEGER DEFAULT 0,
                    mode TEXT NOT NULL,
                    title TEXT,
                    description TEXT,
                    markdown TEXT,
                    extracted_data TEXT DEFAULT '{}',
                    price_intel TEXT DEFAULT '{}',
                    links TEXT DEFAULT '[]',
                    fingerprint_used TEXT,
                    proxy_used TEXT,
                    elapsed_ms REAL DEFAULT 0.0,
                    retries INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    error TEXT
                );

                CREATE TABLE IF NOT EXISTS price_monitors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    store_name TEXT NOT NULL,
                    currency TEXT DEFAULT 'BRL',
                    current_price REAL,
                    lowest_price REAL,
                    highest_price REAL,
                    target_price REAL NOT NULL,
                    css_selector TEXT,
                    in_stock INTEGER DEFAULT 1,
                    last_checked_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    monitor_id INTEGER NOT NULL,
                    price REAL NOT NULL,
                    recorded_at TEXT NOT NULL,
                    FOREIGN KEY(monitor_id) REFERENCES price_monitors(id) ON DELETE CASCADE
                );
                """
            )
            conn.commit()

    def save_job(self, job_data: Dict[str, Any]) -> None:
        with self._lock, self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO crawl_jobs (
                    job_id, url, domain, status, http_status, mode,
                    title, description, markdown, extracted_data, price_intel,
                    links, fingerprint_used, proxy_used, elapsed_ms, retries,
                    created_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_data["job_id"],
                    job_data["url"],
                    job_data["domain"],
                    job_data["status"],
                    job_data.get("http_status", 0),
                    job_data.get("mode", "auto"),
                    job_data.get("title"),
                    job_data.get("description"),
                    job_data.get("markdown"),
                    json.dumps(job_data.get("extracted_data", {}), ensure_ascii=False),
                    json.dumps(job_data.get("price_intel") or {}, ensure_ascii=False),
                    json.dumps(job_data.get("links", []), ensure_ascii=False),
                    job_data.get("fingerprint_used"),
                    job_data.get("proxy_used"),
                    job_data.get("elapsed_ms", 0.0),
                    job_data.get("retries", 0),
                    job_data.get("created_at")
                    or datetime.now(timezone.utc).isoformat(),
                    job_data.get("error"),
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM crawl_jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
            if not row:
                return None
            return self._deserialize_job(dict(row))

    def list_jobs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM crawl_jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._deserialize_job(dict(r)) for r in rows]

    def _deserialize_job(self, row: Dict[str, Any]) -> Dict[str, Any]:
        links = json.loads(row.get("links") or "[]")
        price_intel = json.loads(row.get("price_intel") or "{}")
        return {
            "job_id": row["job_id"],
            "url": row["url"],
            "domain": row["domain"],
            "status": row["status"],
            "http_status": row["http_status"],
            "mode": row["mode"],
            "title": row["title"],
            "description": row["description"],
            "markdown": row["markdown"],
            "extracted_data": json.loads(row.get("extracted_data") or "{}"),
            "price_intel": price_intel if price_intel else None,
            "links_count": len(links),
            "links": links,
            "fingerprint_used": row["fingerprint_used"],
            "proxy_used": row["proxy_used"],
            "elapsed_ms": round(float(row.get("elapsed_ms") or 0.0), 2),
            "retries": row.get("retries", 0),
            "created_at": row["created_at"],
            "error": row["error"],
        }

    def create_monitor(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        curr = data.get("current_price")
        with self._lock, self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO price_monitors (
                    name, url, store_name, currency, current_price,
                    lowest_price, highest_price, target_price, css_selector,
                    in_stock, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"],
                    data["url"],
                    data.get("store_name", "Generic Store"),
                    data.get("currency", "BRL"),
                    curr,
                    curr,
                    curr,
                    data["target_price"],
                    data.get("css_selector"),
                    1 if data.get("in_stock", True) else 0,
                    now,
                ),
            )
            monitor_id = cursor.lastrowid
            if curr is not None:
                conn.execute(
                    "INSERT INTO price_history (monitor_id, price, recorded_at) VALUES (?, ?, ?)",
                    (monitor_id, curr, now),
                )
            conn.commit()
        return self.get_monitor(monitor_id)

    def update_monitor_price(
        self, monitor_id: int, new_price: float, in_stock: bool = True
    ) -> Optional[Dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM price_monitors WHERE id = ?", (monitor_id,)
            ).fetchone()
            if not row:
                return None
            lowest = (
                min(row["lowest_price"], new_price)
                if row["lowest_price"] is not None
                else new_price
            )
            highest = (
                max(row["highest_price"], new_price)
                if row["highest_price"] is not None
                else new_price
            )
            conn.execute(
                """
                UPDATE price_monitors
                SET current_price = ?, lowest_price = ?, highest_price = ?,
                    in_stock = ?, last_checked_at = ?
                WHERE id = ?
                """,
                (new_price, lowest, highest, 1 if in_stock else 0, now, monitor_id),
            )
            conn.execute(
                "INSERT INTO price_history (monitor_id, price, recorded_at) VALUES (?, ?, ?)",
                (monitor_id, new_price, now),
            )
            conn.commit()
        return self.get_monitor(monitor_id)

    def get_monitor(self, monitor_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM price_monitors WHERE id = ?", (monitor_id,)
            ).fetchone()
            if not row:
                return None
            return self._format_monitor(conn, dict(row))

    def list_monitors(self) -> List[Dict[str, Any]]:
        with self._lock, self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM price_monitors ORDER BY id DESC"
            ).fetchall()
            return [self._format_monitor(conn, dict(r)) for r in rows]

    def delete_monitor(self, monitor_id: int) -> bool:
        with self._lock, self._get_conn() as conn:
            cur = conn.execute(
                "DELETE FROM price_monitors WHERE id = ?", (monitor_id,)
            )
            conn.execute(
                "DELETE FROM price_history WHERE monitor_id = ?", (monitor_id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def _format_monitor(
        self, conn: sqlite3.Connection, row: Dict[str, Any]
    ) -> Dict[str, Any]:
        hist = conn.execute(
            "SELECT price, recorded_at FROM price_history WHERE monitor_id = ? ORDER BY id ASC LIMIT 30",
            (row["id"],),
        ).fetchall()
        curr = row["current_price"]
        target = row["target_price"]
        return {
            "id": row["id"],
            "name": row["name"],
            "url": row["url"],
            "store_name": row["store_name"],
            "currency": row["currency"],
            "current_price": curr,
            "lowest_price": row["lowest_price"],
            "highest_price": row["highest_price"],
            "target_price": target,
            "in_stock": bool(row["in_stock"]),
            "alert_triggered": (curr is not None and curr <= target),
            "last_checked_at": row["last_checked_at"],
            "history": [dict(h) for h in hist],
        }

    def seed_demo_data_if_empty(self) -> None:
        with self._lock, self._get_conn() as conn:
            count = conn.execute("SELECT COUNT(*) FROM price_monitors").fetchone()[0]
            if count > 0:
                return

        now = datetime.now(timezone.utc)
        demo_monitors = [
            {
                "name": "Placa de Vídeo RTX 4070 Super 12GB GDDR6X",
                "url": "https://kabum.com.br/produto/rtx-4070-super-12gb",
                "store_name": "KaBuM!",
                "currency": "BRL",
                "prices": [4399.90, 4250.00, 4199.00, 3989.90, 3849.90],
                "target_price": 3900.00,
                "in_stock": True,
            },
            {
                "name": "MacBook Air M3 13\" 16GB RAM 512GB SSD",
                "url": "https://amazon.com.br/dp/B0CX23V2ZK",
                "store_name": "Amazon BR",
                "currency": "BRL",
                "prices": [10499.00, 9899.00, 9590.00, 9299.00],
                "target_price": 9000.00,
                "in_stock": True,
            },
            {
                "name": "Monitor Dell Alienware AW2724DM 27\" QHD 180Hz",
                "url": "https://dell.com/pt-br/shop/alienware-27-aw2724dm",
                "store_name": "Dell Store",
                "currency": "BRL",
                "prices": [3299.00, 3150.00, 2899.00, 2699.90],
                "target_price": 2750.00,
                "in_stock": True,
            },
            {
                "name": "SSD Kingston Fury Renegade 2TB NVMe PCIe 4.0",
                "url": "https://pichau.com.br/ssd-kingston-fury-renegade-2tb",
                "store_name": "Pichau",
                "currency": "BRL",
                "prices": [1199.90, 1089.90, 999.90, 949.90],
                "target_price": 950.00,
                "in_stock": True,
            },
        ]

        with self._lock, self._get_conn() as conn:
            for item in demo_monitors:
                prices = item["prices"]
                curr = prices[-1]
                lowest = min(prices)
                highest = max(prices)
                cur = conn.execute(
                    """
                    INSERT INTO price_monitors (
                        name, url, store_name, currency, current_price,
                        lowest_price, highest_price, target_price, in_stock, last_checked_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["name"],
                        item["url"],
                        item["store_name"],
                        item["currency"],
                        curr,
                        lowest,
                        highest,
                        item["target_price"],
                        1 if item["in_stock"] else 0,
                        now.isoformat(),
                    ),
                )
                mid = cur.lastrowid
                for idx, p in enumerate(prices):
                    ts = (now - timedelta(days=len(prices) - 1 - idx)).isoformat()
                    conn.execute(
                        "INSERT INTO price_history (monitor_id, price, recorded_at) VALUES (?, ?, ?)",
                        (mid, p, ts),
                    )
            conn.commit()

        demo_jobs = [
            {
                "job_id": "cm-9f82a104",
                "url": "https://kabum.com.br/produto/rtx-4070-super-12gb",
                "domain": "kabum.com.br",
                "status": "COMPLETED",
                "http_status": 200,
                "mode": "price",
                "title": "Placa de Vídeo RTX 4070 Super 12GB GDDR6X | KaBuM!",
                "description": "RTX 4070 Super 12GB GDDR6X com DLSS 3 e Ray Tracing.",
                "markdown": "# Placa de Vídeo RTX 4070 Super 12GB GDDR6X\n\n**Preço à vista:** R$ 3.849,90 no PIX (12% de desconto)\n\n## Especificações Técnicas\n- Memória: 12GB GDDR6X\n- Interface: 192-bit\n- Boost Clock: 2475 MHz\n- Conectores: 3x DisplayPort 1.4a, 1x HDMI 2.1a",
                "extracted_data": {
                    "sku": "KB-4070S-12G",
                    "seller": "KaBuM!",
                    "availability": "InStock",
                },
                "price_intel": {
                    "detected": True,
                    "currency": "BRL",
                    "amount": 3849.90,
                    "formatted": "R$ 3.849,90",
                    "original_amount": 4399.90,
                    "discount_pct": 12.5,
                    "in_stock": True,
                    "source_method": "json-ld",
                    "product_title": "Placa de Vídeo RTX 4070 Super 12GB GDDR6X",
                },
                "links": [
                    "https://kabum.com.br/hardware",
                    "https://kabum.com.br/placas-de-video",
                ],
                "fingerprint_used": "Chrome 131.0 / Windows 10 x64",
                "proxy_used": "br-sp-node01 (189.12.44.10:8080)",
                "elapsed_ms": 184.6,
                "retries": 0,
                "created_at": (now - timedelta(minutes=12)).isoformat(),
            },
            {
                "job_id": "cm-7d31b892",
                "url": "https://news.ycombinator.com",
                "domain": "news.ycombinator.com",
                "status": "COMPLETED",
                "http_status": 200,
                "mode": "auto",
                "title": "Hacker News",
                "description": "Links for the intellectually curious, ranked by developers.",
                "markdown": "# Hacker News\n\n1. **SQLite in Distributed Systems: Lessons Learned** (sqlite.org)\n2. **High-Throughput Async Crawlers in Python 3.12** (engineering.blog)\n3. **Why Token Bucket Rate Limiting Matters at Scale** (systems.io)",
                "extracted_data": {
                    "headings": ["Hacker News"],
                    "meta_tags": {"viewport": "width=device-width, initial-scale=1.0"},
                },
                "price_intel": {"detected": False},
                "links": [
                    "https://news.ycombinator.com/newest",
                    "https://news.ycombinator.com/show",
                ],
                "fingerprint_used": "Firefox 132.0 / Linux x86_64",
                "proxy_used": "us-east-node02 (45.33.18.91:3128)",
                "elapsed_ms": 142.3,
                "retries": 0,
                "created_at": (now - timedelta(minutes=5)).isoformat(),
            },
            {
                "job_id": "cm-3c90e411",
                "url": "https://dell.com/pt-br/shop/alienware-27-aw2724dm",
                "domain": "dell.com",
                "status": "COMPLETED",
                "http_status": 200,
                "mode": "price",
                "title": "Monitor Gamer Alienware 27 AW2724DM | Dell Brasil",
                "description": "Monitor QHD Fast IPS de 27 polegadas com taxa de atualização de 180Hz.",
                "markdown": "# Monitor Gamer Alienware 27 - AW2724DM\n\n**Valor promocional:** R$ 2.699,90\n\n- Resolução: QHD 2560 x 1440 a 180 Hz\n- Painel: Fast IPS Nano Color\n- Tempo de resposta: 1ms GTG",
                "extracted_data": {"brand": "Alienware", "model": "AW2724DM"},
                "price_intel": {
                    "detected": True,
                    "currency": "BRL",
                    "amount": 2699.90,
                    "formatted": "R$ 2.699,90",
                    "original_amount": 3299.00,
                    "discount_pct": 18.16,
                    "in_stock": True,
                    "source_method": "schema-microdata",
                    "product_title": "Monitor Gamer Alienware 27 AW2724DM",
                },
                "links": ["https://dell.com/pt-br/shop/monitors"],
                "fingerprint_used": "Chrome 131.0 / macOS Sonoma",
                "proxy_used": "br-sp-node01 (189.12.44.10:8080)",
                "elapsed_ms": 219.8,
                "retries": 0,
                "created_at": (now - timedelta(minutes=2)).isoformat(),
            },
        ]
        for j in demo_jobs:
            self.save_job(j)


db = DatabaseManager()
