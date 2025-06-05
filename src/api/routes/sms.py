"""SMS management API routes."""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from ...models.database import get_db
from ...models.schemas import SMSSend, SMSInfo, SMSWebhook
from ...utils.sip_client import SIPClient
from ...utils.auth import get_current_user
from ...sms.sms_manager import SMSManager
from ...sms.sms_queue import SMSQueuePriority

logger = logging.getLogger(__name__)
router = APIRouter()

# Global SMS manager instance (would be properly initialized in main app)
sms_manager: Optional[SMSManager] = None

def get_sms_manager() -> SMSManager:
    """Get SMS manager instance."""
    global sms_manager
    if not sms_manager:
        raise HTTPException(status_code=503, detail="SMS service not available")
    return sms_manager


@router.post("/send", response_model=SMSInfo)
async def send_sms(
    sms_data: SMSSend,
    priority: Optional[str] = Query("normal", description="Message priority: low, normal, high, urgent"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Send an SMS message."""
    try:
        # Validate numbers
        if not sms_data.from_number or not sms_data.to_number:
            raise HTTPException(status_code=400, detail="Invalid phone numbers")
        
        # Check message length
        if len(sms_data.message) > 1600:
            raise HTTPException(status_code=400, detail="Message too long (max 1600 characters)")
        
        # Parse priority
        priority_map = {
            "low": SMSQueuePriority.LOW,
            "normal": SMSQueuePriority.NORMAL,
            "high": SMSQueuePriority.HIGH,
            "urgent": SMSQueuePriority.URGENT
        }
        sms_priority = priority_map.get(priority.lower(), SMSQueuePriority.NORMAL)
        
        # Send SMS via SMS manager
        sms_message = await sms_mgr.send_sms(
            from_number=sms_data.from_number,
            to_number=sms_data.to_number,
            message=sms_data.message,
            priority=sms_priority,
            webhook_url=sms_data.webhook_url
        )
        
        # Convert to API response format
        sms_info = SMSInfo(
            message_id=sms_message.message_id,
            from_number=sms_message.from_number,
            to_number=sms_message.to_number,
            message=sms_message.message,
            status=sms_message.status.value,
            direction=sms_message.direction.value,
            timestamp=sms_message.created_at,
            segments=sms_message.segments
        )
        
        return sms_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{message_id}", response_model=SMSInfo)
async def get_sms_status(
    message_id: str,
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Get SMS message status."""
    try:
        sms_message = await sms_mgr.get_message_status(message_id)
        
        if not sms_message:
            raise HTTPException(status_code=404, detail="SMS message not found")
        
        # Convert to API response format
        sms_info = SMSInfo(
            message_id=sms_message.message_id,
            from_number=sms_message.from_number,
            to_number=sms_message.to_number,
            message=sms_message.message,
            status=sms_message.status.value,
            direction=sms_message.direction.value,
            timestamp=sms_message.created_at,
            segments=sms_message.segments,
            error=sms_message.error_message
        )
        
        return sms_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get SMS status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[SMSInfo])
async def get_sms_history(
    number: Optional[str] = Query(None, description="Filter by phone number"),
    limit: int = Query(100, ge=1, le=1000, description="Number of messages to return"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Get SMS message history."""
    try:
        messages = await sms_mgr.get_message_history(number, limit, offset)
        
        # Convert to API response format
        sms_list = []
        for msg in messages:
            sms_info = SMSInfo(
                message_id=msg.message_id,
                from_number=msg.from_number,
                to_number=msg.to_number,
                message=msg.message,
                status=msg.status.value,
                direction=msg.direction.value,
                timestamp=msg.created_at,
                segments=msg.segments,
                error=msg.error_message
            )
            sms_list.append(sms_info)
        
        return sms_list
        
    except Exception as e:
        logger.error(f"Failed to get SMS history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry/{message_id}")
async def retry_sms(
    message_id: str,
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Retry failed SMS message."""
    try:
        success = await sms_mgr.retry_failed_message(message_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Cannot retry message")
        
        return {"message": "SMS retry initiated", "message_id": message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retry SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cancel/{message_id}")
async def cancel_sms(
    message_id: str,
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Cancel pending SMS message."""
    try:
        success = await sms_mgr.cancel_message(message_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Cannot cancel message")
        
        return {"message": "SMS cancelled", "message_id": message_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
async def get_sms_statistics(
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Get SMS service statistics."""
    try:
        stats = sms_mgr.get_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get SMS statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queue/status")
async def get_queue_status(
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Get SMS queue status."""
    try:
        queue_stats = sms_mgr.sms_queue.get_statistics()
        queue_contents = await sms_mgr.sms_queue.get_queue_contents()
        
        return {
            "statistics": queue_stats,
            "queue_contents": queue_contents[:50]  # Limit to first 50 items
        }
        
    except Exception as e:
        logger.error(f"Failed to get queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SMSWebhookData(BaseModel):
    """SMS webhook data model."""
    event_type: str = Field(..., description="Event type (message_received, delivery_status, etc.)")
    message_id: Optional[str] = Field(None, description="SMS message ID")
    from_number: str = Field(..., description="Sender phone number")
    to_number: str = Field(..., description="Recipient phone number")
    message: Optional[str] = Field(None, description="Message content")
    status: Optional[str] = Field(None, description="Message status")
    timestamp: datetime = Field(..., description="Event timestamp")
    sip_data: Optional[dict] = Field(None, description="Raw SIP data")


@router.post("/webhook/incoming")
async def handle_incoming_sms_webhook(
    webhook_data: SMSWebhookData,
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Handle incoming SMS webhook from Kamailio."""
    try:
        if webhook_data.event_type == "message_received":
            # Process incoming SMS
            sip_data = webhook_data.sip_data or {
                "from_uri": f"sip:{webhook_data.from_number}@sip.olib.local",
                "to_uri": f"sip:{webhook_data.to_number}@sip.olib.local",
                "body": webhook_data.message or "",
                "headers": {},
                "call_id": webhook_data.message_id or ""
            }
            
            sms_message = await sms_mgr.receive_sms(sip_data)
            
            return {
                "status": "processed",
                "message_id": sms_message.message_id
            }
        
        elif webhook_data.event_type == "delivery_status":
            # Handle delivery status update
            if webhook_data.message_id:
                message = await sms_mgr.get_message_status(webhook_data.message_id)
                if message:
                    # Update message status based on webhook data
                    # This would be implemented based on specific webhook format
                    pass
            
            return {"status": "processed"}
        
        else:
            logger.warning(f"Unknown SMS webhook event type: {webhook_data.event_type}")
            return {"status": "unknown_event_type"}
        
    except Exception as e:
        logger.error(f"Error handling SMS webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bulk", response_model=List[SMSInfo])
async def send_bulk_sms(
    sms_list: List[SMSSend],
    priority: Optional[str] = Query("normal", description="Message priority for all messages"),
    current_user: dict = Depends(get_current_user),
    sms_mgr: SMSManager = Depends(get_sms_manager)
):
    """Send multiple SMS messages in bulk."""
    try:
        if len(sms_list) > 100:
            raise HTTPException(status_code=400, detail="Too many messages (max 100)")
        
        # Parse priority
        priority_map = {
            "low": SMSQueuePriority.LOW,
            "normal": SMSQueuePriority.NORMAL,
            "high": SMSQueuePriority.HIGH,
            "urgent": SMSQueuePriority.URGENT
        }
        sms_priority = priority_map.get(priority.lower(), SMSQueuePriority.NORMAL)
        
        results = []
        
        for sms_data in sms_list:
            try:
                sms_message = await sms_mgr.send_sms(
                    from_number=sms_data.from_number,
                    to_number=sms_data.to_number,
                    message=sms_data.message,
                    priority=sms_priority,
                    webhook_url=sms_data.webhook_url
                )
                
                sms_info = SMSInfo(
                    message_id=sms_message.message_id,
                    from_number=sms_message.from_number,
                    to_number=sms_message.to_number,
                    message=sms_message.message,
                    status=sms_message.status.value,
                    direction=sms_message.direction.value,
                    timestamp=sms_message.created_at,
                    segments=sms_message.segments
                )
                results.append(sms_info)
                
            except Exception as e:
                logger.error(f"Failed to send SMS to {sms_data.to_number}: {e}")
                # Create failed SMS info
                results.append(SMSInfo(
                    message_id="",
                    from_number=sms_data.from_number,
                    to_number=sms_data.to_number,
                    message=sms_data.message,
                    status="failed",
                    direction="outbound",
                    timestamp=datetime.utcnow(),
                    error=str(e)
                ))
        
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send bulk SMS: {e}")
        raise HTTPException(status_code=500, detail=str(e))