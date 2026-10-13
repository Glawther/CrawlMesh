import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    APP_NAME: str = os.getenv("CRAWLMESH_APP_NAME", "CrawlMesh")
    APP_VERSION: str = "1.0.0"
    HOST: str = os.getenv("CRAWLMESH_HOST", "127.0.0.1")
    PORT: int = int(os.getenv("CRAWLMESH_PORT", "8090"))
    DATABASE_PATH: str = os.getenv(
        "CRAWLMESH_DB_PATH", str(STORAGE_DIR / "crawlmesh.db")
    )
    REDIS_URL: str = os.getenv("CRAWLMESH_REDIS_URL", "redis://localhost:6379/0")
    POSTGRES_DSN: str = os.getenv(
        "CRAWLMESH_POSTGRES_DSN",
        "postgresql://crawlmesh:crawlmesh@localhost:5432/crawlmesh",
    )
    EXECUTION_MODE: str = os.getenv("CRAWLMESH_MODE", "standalone")
    MAX_CONCURRENT_WORKERS: int = int(os.getenv("CRAWLMESH_WORKERS", "4"))
    DEFAULT_RATE_LIMIT_RPS: float = float(os.getenv("CRAWLMESH_RATE_LIMIT_RPS", "2.0"))
    REQUEST_TIMEOUT_SEC: float = float(os.getenv("CRAWLMESH_TIMEOUT", "15.0"))
    MAX_RETRIES: int = int(os.getenv("CRAWLMESH_MAX_RETRIES", "3"))


settings = Settings()
