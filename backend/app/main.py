"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db, seed_default_settings
from app.routes import settings, groups, feeds, articles, tags, summary, briefing, export, stats, scheduled_tasks
from app.services.feed_fetcher import start_periodic_fetch
from app.services.task_scheduler import scheduler as briefing_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown."""
    logger.info("Initializing database...")
    await init_db()
    await seed_default_settings()
    logger.info("Database initialized successfully")
    await start_periodic_fetch(interval_minutes=30)
    await briefing_scheduler.start()
    yield
    logger.info("Shutting down...")
    await briefing_scheduler.stop()


app = FastAPI(
    title="RSS Reader API",
    description="A feature-rich RSS reader with AI summaries, daily briefings, and audio support",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(settings.router)
app.include_router(groups.router)
app.include_router(feeds.router)
app.include_router(export.router)  # Must be before articles to avoid {article_id} catching "export"
app.include_router(articles.router)
app.include_router(tags.router)
app.include_router(summary.router)
app.include_router(briefing.router)
app.include_router(stats.router)
app.include_router(scheduled_tasks.router)


@app.get("/")
async def root():
    return {"message": "RSS Reader API", "version": "0.1.0", "docs": "/docs"}
