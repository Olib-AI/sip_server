"""FastAPI application for SIP server management."""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import logging
from datetime import datetime
import asyncio
import httpx
from contextlib import asynccontextmanager

from .routes import calls, sms, numbers, config, webhooks, trunks
from ..models.database import init_db, get_db
from ..utils.auth import get_current_user
from ..utils.sip_client import SIPClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting SIP API server...")
    await init_db()
    app.state.sip_client = SIPClient()
    yield
    # Shutdown
    logger.info("Shutting down SIP API server...")
    await app.state.sip_client.close()


app = FastAPI(
    title="Olib AI SIP Server API",
    description="API for managing SIP calls, SMS, and configurations",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "sip-server"
    }


# Include routers
app.include_router(calls.router, prefix="/api/calls", tags=["calls"])
app.include_router(sms.router, prefix="/api/sms", tags=["sms"])
app.include_router(numbers.router, prefix="/api/numbers", tags=["numbers"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(trunks.router, tags=["trunks"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)