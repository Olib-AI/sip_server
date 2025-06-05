"""Configuration API routes."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import logging
from sqlalchemy.orm import Session

from ...models.database import get_db
from ...models.schemas import SIPConfig, ServerStatus
from ...utils.auth import get_current_user, require_admin
from ...utils.config_manager import ConfigManager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=SIPConfig)
async def get_configuration(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get current SIP server configuration."""
    try:
        config_manager = ConfigManager()
        config = await config_manager.get_config()
        return config
        
    except Exception as e:
        logger.error(f"Failed to get configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/")
async def update_configuration(
    config: SIPConfig,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Update SIP server configuration (admin only)."""
    try:
        config_manager = ConfigManager()
        
        # Validate configuration
        if not config_manager.validate_config(config):
            raise HTTPException(status_code=400, detail="Invalid configuration")
        
        # Update configuration
        success = await config_manager.update_config(config)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update configuration")
        
        # Reload Kamailio if needed
        if config.auto_reload:
            await config_manager.reload_kamailio()
        
        return {"message": "Configuration updated successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=ServerStatus)
async def get_server_status(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get SIP server status and statistics."""
    try:
        config_manager = ConfigManager()
        status = await config_manager.get_server_status()
        return status
        
    except Exception as e:
        logger.error(f"Failed to get server status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload")
async def reload_configuration(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Reload SIP server configuration (admin only)."""
    try:
        config_manager = ConfigManager()
        success = await config_manager.reload_kamailio()
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to reload configuration")
        
        return {"message": "Configuration reloaded successfully"}
        
    except Exception as e:
        logger.error(f"Failed to reload configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/domains")
async def get_sip_domains(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get list of configured SIP domains."""
    try:
        config_manager = ConfigManager()
        domains = await config_manager.get_sip_domains()
        return {"domains": domains}
        
    except Exception as e:
        logger.error(f"Failed to get SIP domains: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/domains/{domain}")
async def add_sip_domain(
    domain: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Add a new SIP domain (admin only)."""
    try:
        config_manager = ConfigManager()
        
        # Validate domain
        if not config_manager.validate_domain(domain):
            raise HTTPException(status_code=400, detail="Invalid domain")
        
        # Add domain
        success = await config_manager.add_sip_domain(domain)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add domain")
        
        return {"message": f"Domain {domain} added successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add domain: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/domains/{domain}")
async def remove_sip_domain(
    domain: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """Remove a SIP domain (admin only)."""
    try:
        config_manager = ConfigManager()
        
        # Check if domain exists
        domains = await config_manager.get_sip_domains()
        if domain not in domains:
            raise HTTPException(status_code=404, detail="Domain not found")
        
        # Remove domain
        success = await config_manager.remove_sip_domain(domain)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to remove domain")
        
        return {"message": f"Domain {domain} removed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove domain: {e}")
        raise HTTPException(status_code=500, detail=str(e))