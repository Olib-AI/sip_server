"""SIP authentication API routes for Kamailio integration."""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Dict, Any
from datetime import datetime, timezone
from ...models.database import get_db, SIPUser, SIPCallSession
from ...models.schemas import SIPAuthRequest, SIPAuthResponse
from ...utils.sip_auth import SIPAuthenticator
from ...utils.config import get_config
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sip-auth", tags=["sip-auth"])
sip_auth = SIPAuthenticator()
config = get_config()


@router.post("/authenticate", response_model=SIPAuthResponse)
async def authenticate_sip_request(
    auth_request: SIPAuthRequest,
    db: Session = Depends(get_db)
):
    """Authenticate SIP request from Kamailio.
    
    This endpoint is called by Kamailio to validate SIP user credentials
    during registration and call attempts.
    """
    try:
        logger.info(f"SIP authentication request for {auth_request.username}@{auth_request.realm}")
        
        # Authenticate using digest authentication
        auth_response = sip_auth.authenticate_sip_user(db, auth_request)
        
        # Log authentication result
        if auth_response.authenticated:
            logger.info(f"SIP authentication successful: {auth_request.username}@{auth_request.realm}")
        else:
            logger.warning(f"SIP authentication failed: {auth_request.username}@{auth_request.realm} - {auth_response.reason}")
        
        return auth_response
        
    except Exception as e:
        logger.error(f"Error in SIP authentication: {e}")
        return SIPAuthResponse(
            authenticated=False,
            reason="Authentication service error"
        )


@router.get("/user/{username}/info")
async def get_sip_user_info_for_kamailio(
    username: str,
    realm: str = None,
    db: Session = Depends(get_db)
):
    """Get SIP user information for Kamailio.
    
    This endpoint provides user information that Kamailio needs
    for call routing and authorization decisions.
    """
    try:
        if realm is None:
            realm = config.sip.domain
        
        # Find SIP user
        sip_user = db.query(SIPUser).filter(
            SIPUser.username == username,
            SIPUser.realm == realm
        ).first()
        
        if not sip_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SIP user not found"
            )
        
        # Check if user can make calls
        can_call, reason = sip_auth.can_make_call(db, sip_user.id)
        active_calls = sip_auth.get_active_call_count(db, sip_user.id)
        
        return {
            "username": sip_user.username,
            "realm": sip_user.realm,
            "display_name": sip_user.display_name,
            "is_active": sip_user.is_active,
            "is_blocked": sip_user.is_blocked,
            "max_concurrent_calls": sip_user.max_concurrent_calls,
            "active_calls": active_calls,
            "can_make_call": can_call,
            "reason": reason if not can_call else None,
            "call_recording_enabled": sip_user.call_recording_enabled,
            "sms_enabled": sip_user.sms_enabled,
            "account_locked": (
                sip_user.account_locked_until and 
                sip_user.account_locked_until > datetime.now(timezone.utc)
            ) if sip_user.account_locked_until else False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SIP user info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )


@router.post("/call-session/start")
async def start_call_session(
    call_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Start a new call session for tracking.
    
    Called by Kamailio when a call is established.
    """
    try:
        # Extract call information
        call_id = call_data.get("call_id")
        username = call_data.get("username")
        realm = call_data.get("realm", config.sip.domain)
        from_uri = call_data.get("from_uri")
        to_uri = call_data.get("to_uri")
        contact_uri = call_data.get("contact_uri")
        call_direction = call_data.get("direction", "inbound")
        sip_headers = call_data.get("headers", {})
        
        if not all([call_id, username, from_uri, to_uri]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required call session data"
            )
        
        # Find SIP user
        sip_user = db.query(SIPUser).filter(
            SIPUser.username == username,
            SIPUser.realm == realm
        ).first()
        
        if not sip_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SIP user not found"
            )
        
        # Create call session
        call_session = SIPCallSession(
            call_id=call_id,
            sip_user_id=sip_user.id,
            from_uri=from_uri,
            to_uri=to_uri,
            contact_uri=contact_uri,
            call_direction=call_direction,
            call_state="ringing",
            start_time=datetime.now(timezone.utc),
            sip_headers=sip_headers
        )
        
        db.add(call_session)
        db.commit()
        db.refresh(call_session)
        
        logger.info(f"Started call session: {call_id} for user {username}")
        
        return {
            "status": "success",
            "call_session_id": call_session.id,
            "message": "Call session started"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting call session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start call session"
        )


@router.put("/call-session/{call_id}/state")
async def update_call_session_state(
    call_id: str,
    state_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Update call session state.
    
    Called by Kamailio when call state changes (answered, held, ended, etc.).
    """
    try:
        new_state = state_data.get("state")
        if not new_state:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing call state"
            )
        
        # Find call session
        call_session = db.query(SIPCallSession).filter(
            SIPCallSession.call_id == call_id
        ).first()
        
        if not call_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Call session not found"
            )
        
        # Update state
        old_state = call_session.call_state
        call_session.call_state = new_state
        
        # Update timing based on state
        current_time = datetime.now(timezone.utc)
        
        if new_state == "connected" and not call_session.answer_time:
            call_session.answer_time = current_time
        elif new_state == "ended":
            call_session.end_time = current_time
            
            # Update user statistics
            sip_user = call_session.sip_user
            sip_user.total_calls += 1
            
            # Calculate duration if call was answered
            if call_session.answer_time:
                duration = (current_time - call_session.answer_time).total_seconds() / 60
                sip_user.total_minutes += int(duration)
        
        # Update additional metadata if provided
        if "codec" in state_data:
            call_session.codec_used = state_data["codec"]
        if "media_session_id" in state_data:
            call_session.media_session_id = state_data["media_session_id"]
        if "ai_conversation_id" in state_data:
            call_session.ai_conversation_id = state_data["ai_conversation_id"]
        
        db.commit()
        
        logger.info(f"Updated call session {call_id}: {old_state} -> {new_state}")
        
        return {
            "status": "success",
            "old_state": old_state,
            "new_state": new_state,
            "message": "Call session state updated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating call session state: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update call session state"
        )


@router.post("/registration")
async def update_sip_registration(
    registration_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Update SIP user registration information.
    
    Called by Kamailio when a user registers/unregisters.
    """
    try:
        username = registration_data.get("username")
        realm = registration_data.get("realm", config.sip.domain)
        contact = registration_data.get("contact")
        expires = registration_data.get("expires", 0)
        user_agent = registration_data.get("user_agent")
        
        if not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing username"
            )
        
        # Find SIP user
        sip_user = db.query(SIPUser).filter(
            SIPUser.username == username,
            SIPUser.realm == realm
        ).first()
        
        if not sip_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SIP user not found"
            )
        
        # Update registration information
        current_time = datetime.now(timezone.utc)
        sip_user.last_registration = current_time
        sip_user.last_seen = current_time
        
        if expires > 0:
            # User is registering
            from datetime import timedelta
            sip_user.registration_expires = current_time + timedelta(seconds=expires)
            
            # Update contact info and user agent
            contact_info = sip_user.contact_info or {}
            contact_info.update({
                "contact": contact,
                "expires": expires,
                "registered_at": current_time.isoformat()
            })
            sip_user.contact_info = contact_info
            
            if user_agent:
                sip_user.user_agent = user_agent
            
            logger.info(f"SIP user registered: {username}@{realm} (expires: {expires}s)")
        else:
            # User is unregistering
            sip_user.registration_expires = None
            logger.info(f"SIP user unregistered: {username}@{realm}")
        
        db.commit()
        
        return {
            "status": "success",
            "username": username,
            "registered": expires > 0,
            "expires": expires,
            "message": "Registration updated"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating SIP registration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update registration"
        )


@router.get("/nonce")
async def generate_auth_nonce():
    """Generate authentication nonce for SIP challenge.
    
    Called by Kamailio to get a fresh nonce for authentication challenges.
    """
    try:
        nonce = sip_auth.generate_nonce()
        return {
            "nonce": nonce,
            "realm": config.sip.domain,
            "algorithm": "MD5"
        }
    except Exception as e:
        logger.error(f"Error generating nonce: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate nonce"
        )