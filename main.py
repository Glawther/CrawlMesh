from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
from app.config import settings
from app.database import db

STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"


@asynccontextmanager
async def lifespan(application: FastAPI):
    db.seed_demo_data_if_empty()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Distributed Web Scraping, Clean Markdown Extraction & Price Intelligence Engine",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
async def serve_dashboard():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": settings.EXECUTION_MODE,
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
