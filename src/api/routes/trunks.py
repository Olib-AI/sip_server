"""API routes for SIP trunk management using database."""
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import hashlib
import base64

from ...models.database import get_db, TrunkConfiguration
from ...models.schemas import TrunkCreate, TrunkUpdate, TrunkInfo, TrunkList, TrunkStatus, TrunkStats
from ...utils.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trunks", tags=["trunks"])
security = HTTPBearer()


def encrypt_password(password: str) -> str:
    """Simple password encryption (use proper encryption in production)."""
    if not password:
        return ""
    return base64.b64encode(password.encode()).decode()


def decrypt_password(encrypted_password: str) -> str:
    """Simple password decryption (use proper decryption in production)."""
    if not encrypted_password:
        return ""
    try:
        return base64.b64decode(encrypted_password.encode()).decode()
    except Exception:
        return ""


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def create_trunk(
    trunk_data: TrunkCreate,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Create a new SIP trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Check if trunk_id already exists
        existing_trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_data.trunk_id
        ).first()
        
        if existing_trunk:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Trunk with ID '{trunk_data.trunk_id}' already exists"
            )
        
        # Create new trunk
        trunk = TrunkConfiguration(
            trunk_id=trunk_data.trunk_id,
            name=trunk_data.name,
            provider=trunk_data.provider,
            proxy_address=trunk_data.proxy_address,
            proxy_port=trunk_data.proxy_port,
            registrar_address=trunk_data.registrar_address,
            registrar_port=trunk_data.registrar_port,
            username=trunk_data.username,
            password=encrypt_password(trunk_data.password) if trunk_data.password else None,
            realm=trunk_data.realm,
            auth_method=trunk_data.auth_method,
            transport=trunk_data.transport,
            supports_registration=trunk_data.supports_registration,
            supports_outbound=trunk_data.supports_outbound,
            supports_inbound=trunk_data.supports_inbound,
            dial_prefix=trunk_data.dial_prefix,
            strip_digits=trunk_data.strip_digits,
            prepend_digits=trunk_data.prepend_digits,
            max_concurrent_calls=trunk_data.max_concurrent_calls,
            calls_per_second_limit=trunk_data.calls_per_second_limit,
            preferred_codecs=trunk_data.preferred_codecs,
            enable_dtmf_relay=trunk_data.enable_dtmf_relay,
            rtp_timeout=trunk_data.rtp_timeout,
            heartbeat_interval=trunk_data.heartbeat_interval,
            registration_expire=trunk_data.registration_expire,
            failover_timeout=trunk_data.failover_timeout,
            backup_trunks=trunk_data.backup_trunks,
            allowed_ips=trunk_data.allowed_ips,
            status="inactive",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        db.add(trunk)
        db.commit()
        db.refresh(trunk)
        
        logger.info(f"Created trunk {trunk_data.trunk_id} for provider {trunk_data.provider}")
        
        return {
            "message": "Trunk created successfully",
            "trunk_id": trunk.trunk_id,
            "id": trunk.id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating trunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create trunk: {str(e)}"
        )


@router.get("/", response_model=TrunkList)
async def list_trunks(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
    provider: Optional[str] = Query(None, description="Filter by provider"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> TrunkList:
    """List all SIP trunks with pagination and filtering."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Build query with filters
        query = db.query(TrunkConfiguration)
        
        if provider:
            query = query.filter(TrunkConfiguration.provider == provider)
        
        if status:
            query = query.filter(TrunkConfiguration.status == status)
        
        # Get total count
        total = query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        trunks = query.offset(offset).limit(per_page).all()
        
        # Convert to response format
        trunk_list = []
        for trunk in trunks:
            trunk_info = TrunkInfo(
                id=trunk.id,
                trunk_id=trunk.trunk_id,
                name=trunk.name,
                provider=trunk.provider,
                proxy_address=trunk.proxy_address,
                proxy_port=trunk.proxy_port,
                registrar_address=trunk.registrar_address,
                registrar_port=trunk.registrar_port,
                username=trunk.username,
                realm=trunk.realm,
                auth_method=trunk.auth_method,
                transport=trunk.transport,
                supports_registration=trunk.supports_registration,
                supports_outbound=trunk.supports_outbound,
                supports_inbound=trunk.supports_inbound,
                dial_prefix=trunk.dial_prefix,
                strip_digits=trunk.strip_digits,
                prepend_digits=trunk.prepend_digits,
                max_concurrent_calls=trunk.max_concurrent_calls,
                calls_per_second_limit=trunk.calls_per_second_limit,
                preferred_codecs=trunk.preferred_codecs or ["PCMU", "PCMA"],
                enable_dtmf_relay=trunk.enable_dtmf_relay,
                rtp_timeout=trunk.rtp_timeout,
                heartbeat_interval=trunk.heartbeat_interval,
                registration_expire=trunk.registration_expire,
                failover_timeout=trunk.failover_timeout,
                backup_trunks=trunk.backup_trunks or [],
                allowed_ips=trunk.allowed_ips or [],
                status=trunk.status,
                failure_count=trunk.failure_count,
                last_registration=trunk.last_registration,
                total_calls=trunk.total_calls,
                successful_calls=trunk.successful_calls,
                failed_calls=trunk.failed_calls,
                current_calls=trunk.current_calls,
                created_at=trunk.created_at,
                updated_at=trunk.updated_at
            )
            trunk_list.append(trunk_info)
        
        return TrunkList(
            trunks=trunk_list,
            total=total,
            page=page,
            per_page=per_page
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing trunks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list trunks: {str(e)}"
        )


@router.get("/{trunk_id}", response_model=TrunkInfo)
async def get_trunk(
    trunk_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> TrunkInfo:
    """Get specific trunk by ID."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        return TrunkInfo(
            id=trunk.id,
            trunk_id=trunk.trunk_id,
            name=trunk.name,
            provider=trunk.provider,
            proxy_address=trunk.proxy_address,
            proxy_port=trunk.proxy_port,
            registrar_address=trunk.registrar_address,
            registrar_port=trunk.registrar_port,
            username=trunk.username,
            realm=trunk.realm,
            auth_method=trunk.auth_method,
            transport=trunk.transport,
            supports_registration=trunk.supports_registration,
            supports_outbound=trunk.supports_outbound,
            supports_inbound=trunk.supports_inbound,
            dial_prefix=trunk.dial_prefix,
            strip_digits=trunk.strip_digits,
            prepend_digits=trunk.prepend_digits,
            max_concurrent_calls=trunk.max_concurrent_calls,
            calls_per_second_limit=trunk.calls_per_second_limit,
            preferred_codecs=trunk.preferred_codecs or ["PCMU", "PCMA"],
            enable_dtmf_relay=trunk.enable_dtmf_relay,
            rtp_timeout=trunk.rtp_timeout,
            heartbeat_interval=trunk.heartbeat_interval,
            registration_expire=trunk.registration_expire,
            failover_timeout=trunk.failover_timeout,
            backup_trunks=trunk.backup_trunks or [],
            allowed_ips=trunk.allowed_ips or [],
            status=trunk.status,
            failure_count=trunk.failure_count,
            last_registration=trunk.last_registration,
            total_calls=trunk.total_calls,
            successful_calls=trunk.successful_calls,
            failed_calls=trunk.failed_calls,
            current_calls=trunk.current_calls,
            created_at=trunk.created_at,
            updated_at=trunk.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trunk {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trunk: {str(e)}"
        )


@router.put("/{trunk_id}", response_model=Dict[str, Any])
async def update_trunk(
    trunk_id: str,
    trunk_update: TrunkUpdate,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Update trunk configuration."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        # Update fields
        update_data = trunk_update.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            if field == "password" and value:
                # Encrypt password
                setattr(trunk, field, encrypt_password(value))
            else:
                setattr(trunk, field, value)
        
        trunk.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(trunk)
        
        logger.info(f"Updated trunk {trunk_id}")
        
        return {
            "message": "Trunk updated successfully",
            "trunk_id": trunk_id,
            "updated_fields": list(update_data.keys())
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating trunk {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update trunk: {str(e)}"
        )


@router.delete("/{trunk_id}", response_model=Dict[str, Any])
async def delete_trunk(
    trunk_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Delete trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        # Check if trunk has active calls
        if trunk.current_calls > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete trunk with {trunk.current_calls} active calls"
            )
        
        db.delete(trunk)
        db.commit()
        
        logger.info(f"Deleted trunk {trunk_id}")
        
        return {
            "message": "Trunk deleted successfully",
            "trunk_id": trunk_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting trunk {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete trunk: {str(e)}"
        )


@router.get("/{trunk_id}/status", response_model=TrunkStatus)
async def get_trunk_status(
    trunk_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> TrunkStatus:
    """Get trunk status information."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        # Calculate success rate
        success_rate = 0.0
        if trunk.total_calls > 0:
            success_rate = (trunk.successful_calls / trunk.total_calls) * 100
        
        # Calculate registration expiry
        registration_expires = None
        if trunk.last_registration and trunk.supports_registration:
            registration_expires = datetime.fromtimestamp(
                trunk.last_registration.timestamp() + trunk.registration_expire,
                tz=timezone.utc
            )
        
        return TrunkStatus(
            trunk_id=trunk.trunk_id,
            name=trunk.name,
            provider=trunk.provider,
            status=trunk.status,
            last_registration=trunk.last_registration,
            registration_expires=registration_expires,
            total_calls=trunk.total_calls,
            successful_calls=trunk.successful_calls,
            failed_calls=trunk.failed_calls,
            current_calls=trunk.current_calls,
            success_rate=success_rate,
            failure_count=trunk.failure_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trunk status {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trunk status: {str(e)}"
        )


@router.get("/stats/summary", response_model=TrunkStats)
async def get_trunk_stats(
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> TrunkStats:
    """Get overall trunk statistics."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Get aggregated stats
        from sqlalchemy import case
        stats = db.query(
            func.count(TrunkConfiguration.id).label('total_trunks'),
            func.sum(case((TrunkConfiguration.status == 'active', 1), else_=0)).label('active_trunks'),
            func.sum(case((TrunkConfiguration.status == 'inactive', 1), else_=0)).label('inactive_trunks'),
            func.sum(TrunkConfiguration.total_calls).label('total_calls'),
            func.sum(TrunkConfiguration.successful_calls).label('successful_calls'),
            func.sum(TrunkConfiguration.failed_calls).label('failed_calls'),
            func.sum(TrunkConfiguration.current_calls).label('current_calls')
        ).first()
        
        # Calculate overall success rate
        overall_success_rate = 0.0
        if stats.total_calls and stats.total_calls > 0:
            overall_success_rate = (stats.successful_calls / stats.total_calls) * 100
        
        return TrunkStats(
            total_trunks=stats.total_trunks or 0,
            active_trunks=stats.active_trunks or 0,
            inactive_trunks=stats.inactive_trunks or 0,
            total_calls=stats.total_calls or 0,
            successful_calls=stats.successful_calls or 0,
            failed_calls=stats.failed_calls or 0,
            current_calls=stats.current_calls or 0,
            overall_success_rate=overall_success_rate
        )
        
    except Exception as e:
        logger.error(f"Error getting trunk stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trunk stats: {str(e)}"
        )


@router.post("/{trunk_id}/activate", response_model=Dict[str, Any])
async def activate_trunk(
    trunk_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Activate a trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        trunk.status = "active"
        trunk.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(f"Activated trunk {trunk_id}")
        
        return {
            "message": "Trunk activated successfully",
            "trunk_id": trunk_id,
            "status": "active"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error activating trunk {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to activate trunk: {str(e)}"
        )


@router.post("/{trunk_id}/deactivate", response_model=Dict[str, Any])
async def deactivate_trunk(
    trunk_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Deactivate a trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        trunk.status = "inactive"
        trunk.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        
        logger.info(f"Deactivated trunk {trunk_id}")
        
        return {
            "message": "Trunk deactivated successfully",
            "trunk_id": trunk_id,
            "status": "inactive"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deactivating trunk {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deactivate trunk: {str(e)}"
        )


@router.get("/{trunk_id}/credentials", response_model=Dict[str, Any])
async def get_trunk_credentials(
    trunk_id: str,
    db: Session = Depends(get_db),
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Get trunk credentials for SIP client configuration."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Find trunk
        trunk = db.query(TrunkConfiguration).filter(
            TrunkConfiguration.trunk_id == trunk_id
        ).first()
        
        if not trunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk '{trunk_id}' not found"
            )
        
        return {
            "trunk_id": trunk.trunk_id,
            "name": trunk.name,
            "provider": trunk.provider,
            "proxy_address": trunk.proxy_address,
            "proxy_port": trunk.proxy_port,
            "registrar_address": trunk.registrar_address or trunk.proxy_address,
            "registrar_port": trunk.registrar_port,
            "username": trunk.username,
            "realm": trunk.realm,
            "transport": trunk.transport,
            "registration_expire": trunk.registration_expire,
            "preferred_codecs": trunk.preferred_codecs or ["PCMU", "PCMA"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trunk credentials {trunk_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trunk credentials: {str(e)}"
        )