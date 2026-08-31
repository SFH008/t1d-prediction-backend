"""
Health check endpoints.
GET /health - API status
GET /health/db - Database connectivity
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime
import time
import logging

from app.database import get_db
from app.config import settings
from app.schema.schemas import HealthCheckResponse, DatabaseHealthResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthCheckResponse)
async def health_check():
    """
    API health check endpoint.

    Returns:
        HealthCheckResponse with status, app name, version, and timestamp
    """
    return HealthCheckResponse(
        status="healthy",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        timestamp=datetime.utcnow()
    )


@router.get("/db", response_model=DatabaseHealthResponse)
async def database_health(db: AsyncSession = Depends(get_db)):
    """
    Database connectivity health check.

    Returns:
        DatabaseHealthResponse with connection status and timing
    """
    try:
        start_time = time.time()

        # Simple query to test connection
        result = await db.execute(text("SELECT 1"))
        await db.commit()

        connection_time_ms = (time.time() - start_time) * 1000

        return DatabaseHealthResponse(
            status="healthy",
            database_url=settings.DATABASE_URL.replace(
                settings.DATABASE_URL.split("@")[0].split("://")[1],
                "***:***"
            ),  # Hide password
            connection_time_ms=round(connection_time_ms, 2),
            timestamp=datetime.utcnow()
        )

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return DatabaseHealthResponse(
            status="unhealthy",
            database_url="<connection failed>",
            connection_time_ms=0,
            timestamp=datetime.utcnow()
        )