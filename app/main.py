"""
Main FastAPI application.
Entry point for the backend server.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import Base, sync_engine
from app.core.config import settings

# Create tables (from all models that inherit from Base)
Base.metadata.create_all(bind=sync_engine)

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": settings.VERSION}


@app.get("/")
def read_root():
    """Root endpoint."""
    return {
        "message": "T1D Prediction API",
        "version": settings.VERSION,
        "docs": "/docs",
    }


# TODO: Import and include routers
# from app.api.routes import auth, glucose, predictions
# app.include_router(auth.router, prefix="/auth", tags=["auth"])
# app.include_router(glucose.router, prefix="/glucose", tags=["glucose"])
# app.include_router(predictions.router, prefix="/predictions", tags=["predictions"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
