"""SIP user management API routes."""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from ...models.database import get_db, SIPUser, SIPCallSession
from ...models.schemas import (
    SIPUserCreate, SIPUserUpdate, SIPUserInfo, SIPUserList, 
    SIPUserCredentials, SIPCallSessionInfo, SIPUserStats
)
from ...utils.sip_auth import SIPAuthenticator
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from ...utils.config import get_config
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sip-users", tags=["sip-users"])
sip_auth = SIPAuthenticator()
config = get_config()
security = HTTPBearer()


async def get_sip_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Get current user from SIP management JWT token."""
    token = credentials.credentials
    try:
        payload = sip_auth.verify_sip_management_token(token)
        return {
            "username": payload.get("sub"),
            "user_id": payload.get("user_id"),
            "is_admin": payload.get("is_admin", False)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SIP token authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate SIP management credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_sip_admin(current_user: dict = Depends(get_sip_current_user)) -> dict:
    """Require admin privileges for SIP user management."""
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="SIP user management requires admin privileges"
        )
    return current_user


@router.post("/", response_model=SIPUserInfo, status_code=status.HTTP_201_CREATED)
async def create_sip_user(
    user_data: SIPUserCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Create a new SIP user with authentication credentials."""
    try:
        # Create SIP user with HA1 hash generation
        sip_user = sip_auth.create_sip_user(
            db=db,
            username=user_data.username,
            password=user_data.password,
            realm=user_data.realm,
            display_name=user_data.display_name,
            max_concurrent_calls=user_data.max_concurrent_calls,
            call_recording_enabled=user_data.call_recording_enabled,
            sms_enabled=user_data.sms_enabled,
            api_user_id=user_data.api_user_id
        )
        
        logger.info(f"SIP user created by {current_user['username']}: {user_data.username}")
        return SIPUserInfo.model_validate(sip_user)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating SIP user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create SIP user"
        )


@router.get("/", response_model=SIPUserList)
async def list_sip_users(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Users per page"),
    active_only: bool = Query(False, description="Show only active users"),
    search: Optional[str] = Query(None, description="Search by username or display name"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """List SIP users with pagination and filtering."""
    try:
        # Build query
        query = db.query(SIPUser)
        
        if active_only:
            query = query.filter(SIPUser.is_active == True, SIPUser.is_blocked == False)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (SIPUser.username.ilike(search_term)) |
                (SIPUser.display_name.ilike(search_term))
            )
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        users = query.offset(offset).limit(per_page).all()
        
        return SIPUserList(
            users=[SIPUserInfo.model_validate(user) for user in users],
            total=total,
            page=page,
            per_page=per_page
        )
        
    except Exception as e:
        logger.error(f"Error listing SIP users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list SIP users"
        )


@router.get("/{user_id}", response_model=SIPUserInfo)
async def get_sip_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Get SIP user details by ID."""
    sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
    if not sip_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SIP user not found"
        )
    
    return SIPUserInfo.model_validate(sip_user)


@router.put("/{user_id}", response_model=SIPUserInfo)
async def update_sip_user(
    user_id: int,
    user_data: SIPUserUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Update SIP user information."""
    try:
        sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
        if not sip_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SIP user not found"
            )
        
        # Update password if provided
        if user_data.password:
            sip_user = sip_auth.update_sip_user_password(db, user_id, user_data.password)
        
        # Update other fields
        update_data = user_data.model_dump(exclude_unset=True, exclude={"password"})
        for field, value in update_data.items():
            setattr(sip_user, field, value)
        
        sip_user.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(sip_user)
        
        logger.info(f"SIP user updated by {current_user['username']}: {sip_user.username}")
        return SIPUserInfo.model_validate(sip_user)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating SIP user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update SIP user"
        )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sip_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Delete a SIP user and all associated data."""
    try:
        success = sip_auth.delete_sip_user(db, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SIP user not found"
            )
        
        logger.info(f"SIP user deleted by {current_user['username']}: user_id {user_id}")
        
    except Exception as e:
        logger.error(f"Error deleting SIP user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete SIP user"
        )


@router.post("/{user_id}/unlock", response_model=SIPUserInfo)
async def unlock_sip_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Unlock a SIP user account that was locked due to failed auth attempts."""
    try:
        success = sip_auth.unlock_sip_user(db, user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="SIP user not found"
            )
        
        sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
        logger.info(f"SIP user unlocked by {current_user['username']}: {sip_user.username}")
        
        return SIPUserInfo.model_validate(sip_user)
        
    except Exception as e:
        logger.error(f"Error unlocking SIP user: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlock SIP user"
        )


@router.get("/{user_id}/credentials", response_model=SIPUserCredentials)
async def get_sip_user_credentials(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Get SIP user credentials for client configuration."""
    sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
    if not sip_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SIP user not found"
        )
    
    return SIPUserCredentials(
        username=sip_user.username,
        realm=sip_user.realm,
        sip_domain=config.sip.domain,
        proxy_address=config.sip.proxy_address,
        proxy_port=config.sip.proxy_port,
        registration_expires=3600,  # 1 hour
        max_concurrent_calls=sip_user.max_concurrent_calls
    )


@router.get("/{user_id}/calls", response_model=List[SIPCallSessionInfo])
async def get_sip_user_calls(
    user_id: int,
    active_only: bool = Query(False, description="Show only active calls"),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of calls"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Get call sessions for a SIP user."""
    # Verify user exists
    sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
    if not sip_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SIP user not found"
        )
    
    # Build query
    query = db.query(SIPCallSession).filter(SIPCallSession.sip_user_id == user_id)
    
    if active_only:
        query = query.filter(SIPCallSession.call_state.in_(["ringing", "connected", "held"]))
    
    calls = query.order_by(SIPCallSession.start_time.desc()).limit(limit).all()
    
    # Convert to response format
    call_infos = []
    for call in calls:
        call_info = SIPCallSessionInfo.model_validate(call)
        call_info.sip_username = sip_user.username
        
        # Calculate duration if call has ended
        if call.end_time and call.start_time:
            call_info.duration_seconds = int((call.end_time - call.start_time).total_seconds())
        
        call_infos.append(call_info)
    
    return call_infos


@router.get("/{user_id}/stats", response_model=SIPUserStats)
async def get_sip_user_stats(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Get statistics for a SIP user."""
    sip_user = db.query(SIPUser).filter(SIPUser.id == user_id).first()
    if not sip_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="SIP user not found"
        )
    
    # Get active calls count
    active_calls = sip_auth.get_active_call_count(db, user_id)
    
    # Determine registration status
    registration_status = "never"
    if sip_user.last_registration:
        if (sip_user.registration_expires and 
            sip_user.registration_expires > datetime.now(timezone.utc)):
            registration_status = "registered"
        else:
            registration_status = "expired"
    
    return SIPUserStats(
        username=sip_user.username,
        total_calls=sip_user.total_calls,
        total_minutes=sip_user.total_minutes,
        total_sms=sip_user.total_sms,
        active_calls=active_calls,
        failed_auth_attempts=sip_user.failed_auth_attempts,
        last_seen=sip_user.last_seen,
        registration_status=registration_status
    )


@router.post("/bulk-create", response_model=List[SIPUserInfo])
async def bulk_create_sip_users(
    users_data: List[SIPUserCreate],
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_sip_admin)
):
    """Create multiple SIP users in bulk."""
    if len(users_data) > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 100 users can be created in one request"
        )
    
    created_users = []
    errors = []
    
    for i, user_data in enumerate(users_data):
        try:
            sip_user = sip_auth.create_sip_user(
                db=db,
                username=user_data.username,
                password=user_data.password,
                realm=user_data.realm,
                display_name=user_data.display_name,
                max_concurrent_calls=user_data.max_concurrent_calls,
                call_recording_enabled=user_data.call_recording_enabled,
                sms_enabled=user_data.sms_enabled,
                api_user_id=user_data.api_user_id
            )
            created_users.append(SIPUserInfo.model_validate(sip_user))
            
        except Exception as e:
            errors.append(f"User {i+1} ({user_data.username}): {str(e)}")
    
    if errors:
        logger.warning(f"Bulk create errors: {errors}")
        # Return partial success with created users
        # Errors are logged but not returned to avoid sensitive info exposure
    
    logger.info(f"Bulk created {len(created_users)} SIP users by {current_user['username']}")
    return created_users