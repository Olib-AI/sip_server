"""HTTP API for SIP server integration with Kamailio."""
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Any, Optional
import json
from datetime import datetime
import uvicorn

from ..call_handling.call_manager import CallManager
from ..call_handling.websocket_integration import WebSocketCallBridge

logger = logging.getLogger(__name__)

# Global instances (initialized in main)
app = FastAPI(title="SIP Server Integration API", version="1.0.0")
call_manager: Optional[CallManager] = None
websocket_bridge: Optional[WebSocketCallBridge] = None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests."""
    start_time = datetime.now()
    
    # Get request body for logging
    body = await request.body()
    if body:
        try:
            body_json = json.loads(body.decode())
            logger.info(f"API Request: {request.method} {request.url.path} - Body: {body_json}")
        except:
            logger.info(f"API Request: {request.method} {request.url.path} - Body: {body.decode()[:200]}")
    else:
        logger.info(f"API Request: {request.method} {request.url.path}")
    
    # Process request
    response = await call_next(request)
    
    # Log response time
    duration = (datetime.now() - start_time).total_seconds()
    logger.info(f"API Response: {response.status_code} - Duration: {duration:.3f}s")
    
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@app.post("/api/sip/calls/incoming")
async def handle_incoming_call(request: Request):
    """Handle incoming call notification from Kamailio."""
    try:
        if not call_manager or not websocket_bridge:
            raise HTTPException(status_code=503, detail="Services not initialized")
        
        # Parse request body
        body = await request.body()
        call_data = json.loads(body.decode())
        
        logger.info(f"Incoming call notification: {call_data}")
        
        # Validate required fields
        required_fields = ["call_id", "from", "to", "type"]
        for field in required_fields:
            if field not in call_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Convert to call manager format
        sip_data = {
            "call_id": call_data["call_id"],
            "from_number": call_data["from"],
            "to_number": call_data["to"],
            "sip_call_id": call_data["call_id"],
            "remote_ip": call_data.get("source_ip", "unknown"),
            "headers": call_data.get("headers", {})
        }
        
        # Process through WebSocket bridge
        result = await websocket_bridge.notify_incoming_call(sip_data)
        
        # Return result to Kamailio
        return JSONResponse(content={
            "success": True,
            "call_id": call_data["call_id"],
            "action": result.get("action", "accept"),
            "code": result.get("code", 200),
            "reason": result.get("reason", "OK")
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in incoming call request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error handling incoming call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sip/sms/incoming")
async def handle_incoming_sms(request: Request):
    """Handle incoming SMS notification from Kamailio."""
    try:
        if not websocket_bridge:
            raise HTTPException(status_code=503, detail="WebSocket bridge not initialized")
        
        # Parse request body
        body = await request.body()
        sms_data = json.loads(body.decode())
        
        logger.info(f"Incoming SMS notification: {sms_data}")
        
        # Validate required fields
        required_fields = ["from", "to", "body", "type"]
        for field in required_fields:
            if field not in sms_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        # Process through WebSocket bridge
        result = await websocket_bridge.handle_sip_message(sms_data)
        
        # Return result to Kamailio
        return JSONResponse(content={
            "success": result.get("success", True),
            "message": result.get("message", "SMS processed"),
            "error": result.get("error")
        })
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in incoming SMS request")
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        logger.error(f"Error handling incoming SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sip/calls/active")
async def get_active_calls():
    """Get list of active calls."""
    try:
        if not call_manager:
            raise HTTPException(status_code=503, detail="Call manager not initialized")
        
        active_calls = call_manager.get_active_calls()
        
        call_list = []
        for call in active_calls:
            call_list.append({
                "call_id": call.call_id,
                "session_id": call.session_id,
                "from_number": call.caller.number,
                "to_number": call.callee.number,
                "direction": call.direction.value,
                "state": call.state.value,
                "duration": call.duration(),
                "created_at": call.created_at.isoformat(),
                "is_recording": call.is_recording,
                "is_on_hold": call.is_on_hold
            })
        
        return JSONResponse(content={
            "success": True,
            "calls": call_list,
            "count": len(call_list)
        })
        
    except Exception as e:
        logger.error(f"Error getting active calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sip/calls/{call_id}")
async def get_call_details(call_id: str):
    """Get details for a specific call."""
    try:
        if not call_manager:
            raise HTTPException(status_code=503, detail="Call manager not initialized")
        
        call_session = call_manager.get_call_session(call_id)
        if not call_session:
            raise HTTPException(status_code=404, detail="Call not found")
        
        return JSONResponse(content={
            "success": True,
            "call": {
                "call_id": call_session.call_id,
                "session_id": call_session.session_id,
                "from_number": call_session.caller.number,
                "to_number": call_session.callee.number,
                "direction": call_session.direction.value,
                "state": call_session.state.value,
                "priority": call_session.priority.value,
                "duration": call_session.duration(),
                "ring_duration": call_session.ring_duration(),
                "created_at": call_session.created_at.isoformat(),
                "connect_time": call_session.connect_time.isoformat() if call_session.connect_time else None,
                "end_time": call_session.end_time.isoformat() if call_session.end_time else None,
                "codec": call_session.codec,
                "is_recording": call_session.is_recording,
                "is_on_hold": call_session.is_on_hold,
                "custom_data": call_session.custom_data
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting call details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sip/calls/{call_id}/hangup")
async def hangup_call(call_id: str):
    """Hang up a specific call."""
    try:
        if not call_manager:
            raise HTTPException(status_code=503, detail="Call manager not initialized")
        
        success = await call_manager.hangup_call(call_id, "api_request")
        
        if not success:
            raise HTTPException(status_code=404, detail="Call not found")
        
        return JSONResponse(content={
            "success": True,
            "call_id": call_id,
            "message": "Call ended"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error hanging up call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sip/calls/{call_id}/hold")
async def hold_call(call_id: str):
    """Put call on hold."""
    try:
        if not call_manager:
            raise HTTPException(status_code=503, detail="Call manager not initialized")
        
        success = await call_manager.hold_call(call_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Call not found or cannot be held")
        
        return JSONResponse(content={
            "success": True,
            "call_id": call_id,
            "message": "Call placed on hold"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error holding call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sip/calls/{call_id}/resume")
async def resume_call(call_id: str):
    """Resume call from hold."""
    try:
        if not call_manager:
            raise HTTPException(status_code=503, detail="Call manager not initialized")
        
        success = await call_manager.resume_call(call_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Call not found or not on hold")
        
        return JSONResponse(content={
            "success": True,
            "call_id": call_id,
            "message": "Call resumed"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming call {call_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sip/statistics")
async def get_statistics():
    """Get SIP server statistics."""
    try:
        stats = {}
        
        if call_manager:
            stats["call_manager"] = call_manager.get_statistics()
        
        if websocket_bridge:
            stats["websocket_bridge"] = websocket_bridge.get_statistics()
        
        return JSONResponse(content={
            "success": True,
            "statistics": stats,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def initialize_services(call_mgr: CallManager, ws_bridge: WebSocketCallBridge):
    """Initialize global service instances."""
    global call_manager, websocket_bridge
    call_manager = call_mgr
    websocket_bridge = ws_bridge
    logger.info("SIP integration API services initialized")


async def start_api_server(host: str = "0.0.0.0", port: int = 8080):
    """Start the API server."""
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    
    server = uvicorn.Server(config)
    logger.info(f"Starting SIP integration API server on {host}:{port}")
    await server.serve()


if __name__ == "__main__":
    # For development/testing
    uvicorn.run(app, host="0.0.0.0", port=8080)