"""
Main FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from app.config import settings
from app.database import init_db, close_db
from app.config import settings
from app.database import init_db, close_db
from app.api import (
    health,
    patients,
    glucose,
    insulin,
    therapy_limits,
    imports,
    carbs,
    meals,
    activities,
    hormonal,
    settings as settings_router,
    time_of_day,
)

# Configure logging
logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage app startup and shutdown.
    Initializes database on startup, closes connection on shutdown.
    """
    # Startup
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    yield
    # Shutdown
    logger.info("🛑 Shutting down...")
    await close_db()


# Create app
app = FastAPI(
    title=settings.APP_NAME,
    description="T1D Glucose Forecasting System - Backend API",
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(patients.router)
app.include_router(glucose.router)
app.include_router(insulin.router)
app.include_router(therapy_limits.router)
app.include_router(imports.router)
app.include_router(carbs.router)
app.include_router(meals.router)
app.include_router(activities.router)
app.include_router(hormonal.router)
app.include_router(settings_router.router)
app.include_router(time_of_day.router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )