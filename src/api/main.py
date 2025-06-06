"""FastAPI application for SIP server management."""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import logging
from datetime import datetime, timezone
import asyncio
import httpx
import psutil
import time
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "sip-server"
    }


# Metrics endpoint for Prometheus
@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint."""
    try:
        # System metrics
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Process metrics
        process = psutil.Process()
        proc_cpu = process.cpu_percent()
        proc_memory = process.memory_info()
        
        # Custom application metrics
        uptime = time.time() - process.create_time()
        
        metrics_text = f"""# HELP sip_server_cpu_percent CPU usage percentage
# TYPE sip_server_cpu_percent gauge
sip_server_cpu_percent {cpu_percent}

# HELP sip_server_memory_percent Memory usage percentage
# TYPE sip_server_memory_percent gauge
sip_server_memory_percent {memory.percent}

# HELP sip_server_memory_bytes Memory usage in bytes
# TYPE sip_server_memory_bytes gauge
sip_server_memory_bytes_available {memory.available}
sip_server_memory_bytes_used {memory.used}
sip_server_memory_bytes_total {memory.total}

# HELP sip_server_disk_percent Disk usage percentage
# TYPE sip_server_disk_percent gauge
sip_server_disk_percent {(disk.used / disk.total) * 100}

# HELP sip_server_disk_bytes Disk usage in bytes
# TYPE sip_server_disk_bytes gauge
sip_server_disk_bytes_free {disk.free}
sip_server_disk_bytes_used {disk.used}
sip_server_disk_bytes_total {disk.total}

# HELP sip_server_process_cpu_percent Process CPU usage percentage
# TYPE sip_server_process_cpu_percent gauge
sip_server_process_cpu_percent {proc_cpu}

# HELP sip_server_process_memory_bytes Process memory usage in bytes
# TYPE sip_server_process_memory_bytes gauge
sip_server_process_memory_bytes_rss {proc_memory.rss}
sip_server_process_memory_bytes_vms {proc_memory.vms}

# HELP sip_server_uptime_seconds Process uptime in seconds
# TYPE sip_server_uptime_seconds gauge
sip_server_uptime_seconds {uptime}

# HELP sip_server_info Application information
# TYPE sip_server_info gauge
sip_server_info{{version="1.0.0",service="sip-server"}} 1
"""
        return metrics_text
        
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return f"# Error generating metrics: {str(e)}\n"


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