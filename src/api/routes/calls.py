"""Call management API routes."""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from ...models.database import get_db
from ...models.schemas import CallInitiate, CallInfo, CallTransfer
from ...utils.sip_client import SIPClient
from ...utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/initiate", response_model=CallInfo)
async def initiate_call(
    call_data: CallInitiate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Initiate an outgoing call."""
    try:
        sip_client = SIPClient()
        
        # Validate numbers
        if not call_data.from_number or not call_data.to_number:
            raise HTTPException(status_code=400, detail="Invalid phone numbers")
        
        # Check if from_number is registered
        if not await sip_client.is_number_registered(call_data.from_number):
            raise HTTPException(status_code=400, detail="From number not registered")
        
        # Initiate call
        call_info = await sip_client.initiate_call(
            from_number=call_data.from_number,
            to_number=call_data.to_number,
            headers=call_data.headers,
            webhook_url=call_data.webhook_url
        )
        
        # Store call record in database
        # TODO: Implement database storage
        
        return call_info
        
    except Exception as e:
        logger.error(f"Failed to initiate call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/active", response_model=List[CallInfo])
async def get_active_calls(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get list of active calls."""
    try:
        sip_client = SIPClient()
        active_calls = await sip_client.get_active_calls()
        
        # Apply pagination
        return active_calls[offset:offset + limit]
        
    except Exception as e:
        logger.error(f"Failed to get active calls: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{call_id}", response_model=CallInfo)
async def get_call_info(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get information about a specific call."""
    try:
        sip_client = SIPClient()
        call_info = await sip_client.get_call_info(call_id)
        
        if not call_info:
            raise HTTPException(status_code=404, detail="Call not found")
        
        return call_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get call info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/hangup")
async def hangup_call(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Hang up an active call."""
    try:
        sip_client = SIPClient()
        
        # Check if call exists
        call_info = await sip_client.get_call_info(call_id)
        if not call_info:
            raise HTTPException(status_code=404, detail="Call not found")
        
        # Hang up call
        success = await sip_client.hangup_call(call_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to hang up call")
        
        return {"message": "Call terminated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to hang up call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/transfer")
async def transfer_call(
    call_id: str,
    transfer_data: CallTransfer,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Transfer an active call to another number."""
    try:
        sip_client = SIPClient()
        
        # Check if call exists
        call_info = await sip_client.get_call_info(call_id)
        if not call_info:
            raise HTTPException(status_code=404, detail="Call not found")
        
        # Transfer call
        success = await sip_client.transfer_call(
            call_id=call_id,
            target_number=transfer_data.target_number,
            blind_transfer=transfer_data.blind_transfer
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to transfer call")
        
        return {"message": "Call transferred successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to transfer call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/hold")
async def hold_call(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Put a call on hold."""
    try:
        sip_client = SIPClient()
        
        # Check if call exists
        call_info = await sip_client.get_call_info(call_id)
        if not call_info:
            raise HTTPException(status_code=404, detail="Call not found")
        
        # Hold call
        success = await sip_client.hold_call(call_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to hold call")
        
        return {"message": "Call placed on hold"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to hold call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/resume")
async def resume_call(
    call_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Resume a call on hold."""
    try:
        sip_client = SIPClient()
        
        # Check if call exists
        call_info = await sip_client.get_call_info(call_id)
        if not call_info:
            raise HTTPException(status_code=404, detail="Call not found")
        
        # Resume call
        success = await sip_client.resume_call(call_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to resume call")
        
        return {"message": "Call resumed"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume call: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{call_id}/dtmf")
async def send_dtmf(
    call_id: str,
    digits: str = Query(..., pattern="^[0-9*#]+$"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Send DTMF digits during a call."""
    try:
        sip_client = SIPClient()
        
        # Check if call exists
        call_info = await sip_client.get_call_info(call_id)
        if not call_info:
            raise HTTPException(status_code=404, detail="Call not found")
        
        # Send DTMF
        success = await sip_client.send_dtmf(call_id, digits)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send DTMF")
        
        return {"message": f"DTMF digits '{digits}' sent"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to send DTMF: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[CallInfo])
async def get_call_history(
    from_date: Optional[datetime] = Query(None),
    to_date: Optional[datetime] = Query(None),
    number: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get call history with filters."""
    try:
        # TODO: Implement database query for call history
        # For now, return empty list
        return []
        
    except Exception as e:
        logger.error(f"Failed to get call history: {e}")
        raise HTTPException(status_code=500, detail=str(e))