"""API routes for SIP trunk management."""
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging

from ...sip.trunk_manager import (
    SIPTrunkManager, TrunkConfig, TrunkCredentials, 
    TrunkStatus, AuthMethod
)
from ...utils.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trunks", tags=["trunks"])
security = HTTPBearer()

# Global trunk manager instance
trunk_manager: Optional[SIPTrunkManager] = None


def get_trunk_manager() -> SIPTrunkManager:
    """Get trunk manager instance."""
    global trunk_manager
    if trunk_manager is None:
        trunk_manager = SIPTrunkManager()
    return trunk_manager


# Pydantic models for API
class TrunkCredentialsModel(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    realm: Optional[str] = None
    auth_method: str = "digest"
    allowed_ips: List[str] = []
    certificate_path: Optional[str] = None
    private_key_path: Optional[str] = None


class TrunkConfigModel(BaseModel):
    trunk_id: str
    name: str
    provider: str
    proxy_address: str
    proxy_port: int = 5060
    registrar_address: Optional[str] = None
    registrar_port: int = 5060
    credentials: TrunkCredentialsModel
    transport: str = "UDP"
    supports_registration: bool = True
    supports_outbound: bool = True
    supports_inbound: bool = True
    dial_prefix: str = ""
    strip_digits: int = 0
    prepend_digits: str = ""
    max_concurrent_calls: int = 100
    calls_per_second_limit: int = 10
    backup_trunks: List[str] = []
    failover_timeout: int = 30
    preferred_codecs: List[str] = ["PCMU", "PCMA"]
    enable_dtmf_relay: bool = True
    rtp_timeout: int = 60
    heartbeat_interval: int = 30
    registration_expire: int = 3600


class TrunkStatusResponse(BaseModel):
    trunk_id: str
    name: str
    provider: str
    status: str
    uptime_seconds: float
    total_calls: int
    successful_calls: int
    failed_calls: int
    current_calls: int
    success_rate: float
    failure_count: int
    last_registration: Optional[float]


class AllTrunksStatusResponse(BaseModel):
    trunks: Dict[str, TrunkStatusResponse]
    total_trunks: int
    active_trunks: int
    total_calls: int
    failed_calls: int
    active_calls: int


def _convert_to_trunk_config(model: TrunkConfigModel) -> TrunkConfig:
    """Convert API model to internal TrunkConfig."""
    credentials = TrunkCredentials(
        username=model.credentials.username,
        password=model.credentials.password,
        realm=model.credentials.realm,
        auth_method=AuthMethod(model.credentials.auth_method),
        allowed_ips=model.credentials.allowed_ips,
        certificate_path=model.credentials.certificate_path,
        private_key_path=model.credentials.private_key_path
    )
    
    return TrunkConfig(
        trunk_id=model.trunk_id,
        name=model.name,
        provider=model.provider,
        proxy_address=model.proxy_address,
        proxy_port=model.proxy_port,
        registrar_address=model.registrar_address,
        registrar_port=model.registrar_port,
        credentials=credentials,
        transport=model.transport,
        supports_registration=model.supports_registration,
        supports_outbound=model.supports_outbound,
        supports_inbound=model.supports_inbound,
        dial_prefix=model.dial_prefix,
        strip_digits=model.strip_digits,
        prepend_digits=model.prepend_digits,
        max_concurrent_calls=model.max_concurrent_calls,
        calls_per_second_limit=model.calls_per_second_limit,
        backup_trunks=model.backup_trunks,
        failover_timeout=model.failover_timeout,
        preferred_codecs=model.preferred_codecs,
        enable_dtmf_relay=model.enable_dtmf_relay,
        rtp_timeout=model.rtp_timeout,
        heartbeat_interval=model.heartbeat_interval,
        registration_expire=model.registration_expire
    )


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_trunk(
    trunk_config: TrunkConfigModel,
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Create a new SIP trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Get trunk manager
        manager = get_trunk_manager()
        
        # Convert to internal format
        config = _convert_to_trunk_config(trunk_config)
        
        # Add trunk
        success = await manager.add_trunk(config)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to create trunk"
            )
        
        return {
            "message": "Trunk created successfully",
            "trunk_id": trunk_config.trunk_id
        }
        
    except Exception as e:
        logger.error(f"Error creating trunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/", response_model=AllTrunksStatusResponse)
async def list_trunks(token: str = Depends(security)) -> AllTrunksStatusResponse:
    """List all SIP trunks and their status."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Get trunk manager
        manager = get_trunk_manager()
        
        # Get all trunks status
        status_data = await manager.get_all_trunks_status()
        
        # Convert to response format
        trunks_response = {}
        for trunk_id, trunk_data in status_data["trunks"].items():
            trunks_response[trunk_id] = TrunkStatusResponse(**trunk_data)
        
        return AllTrunksStatusResponse(
            trunks=trunks_response,
            total_trunks=status_data["total_trunks"],
            active_trunks=status_data["active_trunks"],
            total_calls=status_data["total_calls"],
            failed_calls=status_data["failed_calls"],
            active_calls=status_data["active_calls"]
        )
        
    except Exception as e:
        logger.error(f"Error listing trunks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{trunk_id}", response_model=TrunkStatusResponse)
async def get_trunk_status(
    trunk_id: str,
    token: str = Depends(security)
) -> TrunkStatusResponse:
    """Get status of a specific SIP trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Get trunk manager
        manager = get_trunk_manager()
        
        # Get trunk status
        status_data = await manager.get_trunk_status(trunk_id)
        
        if not status_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk {trunk_id} not found"
            )
        
        return TrunkStatusResponse(**status_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting trunk status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.put("/{trunk_id}")
async def update_trunk(
    trunk_id: str,
    trunk_config: TrunkConfigModel,
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Update SIP trunk configuration."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Ensure trunk_id matches
        if trunk_config.trunk_id != trunk_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trunk ID mismatch"
            )
        
        # Get trunk manager
        manager = get_trunk_manager()
        
        # Remove existing trunk
        await manager.remove_trunk(trunk_id)
        
        # Add updated trunk
        config = _convert_to_trunk_config(trunk_config)
        success = await manager.add_trunk(config)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update trunk"
            )
        
        return {
            "message": "Trunk updated successfully",
            "trunk_id": trunk_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating trunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{trunk_id}")
async def delete_trunk(
    trunk_id: str,
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Delete SIP trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Get trunk manager
        manager = get_trunk_manager()
        
        # Remove trunk
        success = await manager.remove_trunk(trunk_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trunk {trunk_id} not found"
            )
        
        return {
            "message": "Trunk deleted successfully",
            "trunk_id": trunk_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting trunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{trunk_id}/route")
async def route_call_via_trunk(
    trunk_id: str,
    call_data: Dict[str, Any],
    token: str = Depends(security)
) -> Dict[str, Any]:
    """Route a call via specific trunk."""
    try:
        # Verify authentication
        verify_token(token.credentials)
        
        # Get trunk manager
        manager = get_trunk_manager()
        
        # Extract call information
        call_id = call_data.get("call_id")
        destination = call_data.get("destination")
        
        if not call_id or not destination:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="call_id and destination are required"
            )
        
        # Route call
        route_info = await manager.route_outbound_call(
            call_id, destination, {"preferred_trunk": trunk_id}
        )
        
        if not route_info:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to route call via trunk"
            )
        
        return {
            "message": "Call routed successfully",
            "call_id": call_id,
            "trunk_id": trunk_id,
            "route_info": route_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error routing call via trunk: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )