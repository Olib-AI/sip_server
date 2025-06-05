"""Webhook endpoints for SIP events."""
from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import httpx
from datetime import datetime

from ...models.schemas import CallWebhook, SMSWebhook, RegistrationWebhook
from ...utils.webhook_manager import WebhookManager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/call/incoming")
async def handle_incoming_call(
    webhook_data: CallWebhook,
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle incoming call webhook from Kamailio."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        # Process incoming call
        logger.info(f"Incoming call: {webhook_data.call_id} from {webhook_data.from_number} to {webhook_data.to_number}")
        
        # Forward to AI platform
        background_tasks.add_task(
            webhook_manager.forward_to_ai_platform,
            "call.incoming",
            webhook_data.dict()
        )
        
        return {"status": "accepted", "call_id": webhook_data.call_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle incoming call webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/call/outbound")
async def handle_outbound_call(
    webhook_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle outbound call routing webhook from Kamailio."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        call_id = webhook_data.get("call_id")
        destination = webhook_data.get("to")
        
        logger.info(f"Outbound call routing: {call_id} to {destination}")
        
        # Get trunk manager and route call
        from ..routes.trunks import get_trunk_manager
        trunk_manager = get_trunk_manager()
        
        route_info = await trunk_manager.route_outbound_call(call_id, destination)
        
        if route_info:
            # Update call records
            background_tasks.add_task(
                webhook_manager.update_call_record,
                call_id,
                "routed",
                {"route_info": route_info, **webhook_data}
            )
        
        return {"status": "routed" if route_info else "failed", "route_info": route_info}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle outbound call webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/call/ended")
async def handle_call_ended(
    webhook_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle call ended webhook from Kamailio."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        call_id = webhook_data.get("call_id")
        logger.info(f"Call ended: {call_id}")
        
        # Update trunk manager
        from ..routes.trunks import get_trunk_manager
        trunk_manager = get_trunk_manager()
        await trunk_manager.end_call(call_id, success=True)  # Assume success for now
        
        # Update call records
        background_tasks.add_task(
            webhook_manager.update_call_record,
            call_id,
            "ended",
            webhook_data
        )
        
        # Forward to AI platform
        background_tasks.add_task(
            webhook_manager.forward_to_ai_platform,
            "call.ended",
            webhook_data
        )
        
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle call ended webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sms/incoming")
async def handle_incoming_sms(
    webhook_data: SMSWebhook,
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle incoming SMS webhook from Kamailio."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        logger.info(f"Incoming SMS from {webhook_data.from_number} to {webhook_data.to_number}")
        
        # Store SMS
        background_tasks.add_task(
            webhook_manager.store_sms,
            webhook_data
        )
        
        # Forward to AI platform
        background_tasks.add_task(
            webhook_manager.forward_to_ai_platform,
            "sms.incoming",
            webhook_data.dict()
        )
        
        return {"status": "received", "message_id": webhook_data.message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle incoming SMS webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/registration")
async def handle_registration(
    webhook_data: RegistrationWebhook,
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle SIP registration webhook from Kamailio."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        logger.info(f"SIP registration: {webhook_data.user}@{webhook_data.domain}")
        
        # Update registration status
        background_tasks.add_task(
            webhook_manager.update_registration,
            webhook_data
        )
        
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle registration webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dtmf")
async def handle_dtmf(
    webhook_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle DTMF input webhook."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        call_id = webhook_data.get("call_id")
        digit = webhook_data.get("digit")
        
        logger.info(f"DTMF received: {digit} for call {call_id}")
        
        # Forward to AI platform
        background_tasks.add_task(
            webhook_manager.forward_to_ai_platform,
            "call.dtmf",
            webhook_data
        )
        
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle DTMF webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/error")
async def handle_error(
    error_data: Dict[str, Any],
    background_tasks: BackgroundTasks,
    request: Request
):
    """Handle error notifications from Kamailio."""
    try:
        # Verify webhook authenticity
        webhook_manager = WebhookManager()
        if not webhook_manager.verify_webhook(request):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        
        error_type = error_data.get("type")
        error_message = error_data.get("message")
        
        logger.error(f"SIP error: {error_type} - {error_message}")
        
        # Store error for analysis
        background_tasks.add_task(
            webhook_manager.log_error,
            error_data
        )
        
        # Notify monitoring system
        background_tasks.add_task(
            webhook_manager.notify_monitoring,
            "sip.error",
            error_data
        )
        
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle error webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))