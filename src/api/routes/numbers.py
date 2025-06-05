"""Number management API routes."""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from ...models.database import get_db
from ...models.schemas import BlockedNumber, NumberInfo
from ...utils.sip_client import SIPClient
from ...utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/block")
async def block_number(
    number_data: BlockedNumber,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Block a phone number."""
    try:
        sip_client = SIPClient()
        
        # Validate number format
        if not number_data.number:
            raise HTTPException(status_code=400, detail="Invalid phone number")
        
        # Check if already blocked
        if await sip_client.is_number_blocked(number_data.number):
            raise HTTPException(status_code=409, detail="Number already blocked")
        
        # Block number
        success = await sip_client.block_number(
            number=number_data.number,
            reason=number_data.reason,
            expires_at=number_data.expires_at
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to block number")
        
        # Store in database
        # TODO: Implement database storage
        
        return {"message": f"Number {number_data.number} blocked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to block number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/block/{number}")
async def unblock_number(
    number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Unblock a phone number."""
    try:
        sip_client = SIPClient()
        
        # Check if blocked
        if not await sip_client.is_number_blocked(number):
            raise HTTPException(status_code=404, detail="Number not blocked")
        
        # Unblock number
        success = await sip_client.unblock_number(number)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unblock number")
        
        # Update database
        # TODO: Implement database update
        
        return {"message": f"Number {number} unblocked successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unblock number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/blocked", response_model=List[BlockedNumber])
async def get_blocked_numbers(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get list of blocked numbers."""
    try:
        sip_client = SIPClient()
        blocked_numbers = await sip_client.get_blocked_numbers()
        
        # Apply pagination
        return blocked_numbers[offset:offset + limit]
        
    except Exception as e:
        logger.error(f"Failed to get blocked numbers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/registered", response_model=List[NumberInfo])
async def get_registered_numbers(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get list of registered numbers."""
    try:
        sip_client = SIPClient()
        registered_numbers = await sip_client.get_registered_numbers()
        
        # Apply pagination
        return registered_numbers[offset:offset + limit]
        
    except Exception as e:
        logger.error(f"Failed to get registered numbers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/register")
async def register_number(
    number_info: NumberInfo,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Register a new number with the SIP server."""
    try:
        sip_client = SIPClient()
        
        # Check if already registered
        if await sip_client.is_number_registered(number_info.number):
            raise HTTPException(status_code=409, detail="Number already registered")
        
        # Register number
        success = await sip_client.register_number(
            number=number_info.number,
            display_name=number_info.display_name,
            capabilities=number_info.capabilities,
            metadata=number_info.metadata
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to register number")
        
        # Store in database
        # TODO: Implement database storage
        
        return {"message": f"Number {number_info.number} registered successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to register number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/register/{number}")
async def unregister_number(
    number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Unregister a number from the SIP server."""
    try:
        sip_client = SIPClient()
        
        # Check if registered
        if not await sip_client.is_number_registered(number):
            raise HTTPException(status_code=404, detail="Number not registered")
        
        # Unregister number
        success = await sip_client.unregister_number(number)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to unregister number")
        
        # Update database
        # TODO: Implement database update
        
        return {"message": f"Number {number} unregistered successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unregister number: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{number}/status", response_model=NumberInfo)
async def get_number_status(
    number: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get detailed status of a specific number."""
    try:
        sip_client = SIPClient()
        
        # Get number info
        number_info = await sip_client.get_number_info(number)
        
        if not number_info:
            raise HTTPException(status_code=404, detail="Number not found")
        
        return number_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get number status: {e}")
        raise HTTPException(status_code=500, detail=str(e))