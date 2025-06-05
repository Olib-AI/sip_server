"""Configuration management utilities."""
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path
import aiofiles
import re

from ..models.schemas import SIPConfig, ServerStatus

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages SIP server configuration."""
    
    def __init__(self, config_path: str = "/etc/kamailio/kamailio.cfg"):
        self.config_path = Path(config_path)
        self.backup_path = self.config_path.with_suffix('.cfg.bak')
        
    async def get_config(self) -> SIPConfig:
        """Get current configuration."""
        try:
            # Read from database or config file
            # For now, return default config
            return SIPConfig(
                sip_domains=["sip.olib.ai"],
                rtp_port_start=10000,
                rtp_port_end=20000,
                max_concurrent_calls=1000,
                call_timeout=3600,
                enable_recording=False,
                enable_transcription=False,
                nat_traversal=True,
                tls_enabled=True,
                rate_limit={
                    "calls_per_minute": 60,
                    "sms_per_minute": 100
                }
            )
        except Exception as e:
            logger.error(f"Failed to get config: {e}")
            raise
            
    async def update_config(self, config: SIPConfig) -> bool:
        """Update configuration."""
        try:
            # Backup current config
            if self.config_path.exists():
                async with aiofiles.open(self.config_path, 'r') as src:
                    content = await src.read()
                async with aiofiles.open(self.backup_path, 'w') as dst:
                    await dst.write(content)
                    
            # Generate new config
            new_config = await self._generate_kamailio_config(config)
            
            # Write new config
            async with aiofiles.open(self.config_path, 'w') as f:
                await f.write(new_config)
                
            # Validate config
            if not await self._validate_kamailio_config():
                # Restore backup
                async with aiofiles.open(self.backup_path, 'r') as src:
                    content = await src.read()
                async with aiofiles.open(self.config_path, 'w') as dst:
                    await dst.write(content)
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return False
            
    def validate_config(self, config: SIPConfig) -> bool:
        """Validate configuration values."""
        try:
            # Validate port ranges
            if config.rtp_port_start >= config.rtp_port_end:
                return False
                
            # Validate domains
            for domain in config.sip_domains:
                if not self.validate_domain(domain):
                    return False
                    
            # Validate rate limits
            if any(v <= 0 for v in config.rate_limit.values()):
                return False
                
            return True
            
        except Exception:
            return False
            
    def validate_domain(self, domain: str) -> bool:
        """Validate domain format."""
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9-_.]*[a-zA-Z0-9]$'
        return bool(re.match(pattern, domain))
        
    async def reload_kamailio(self) -> bool:
        """Reload Kamailio configuration."""
        try:
            # Send reload command
            proc = await asyncio.create_subprocess_exec(
                'kamctl', 'reload',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"Failed to reload Kamailio: {stderr.decode()}")
                return False
                
            logger.info("Kamailio configuration reloaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to reload Kamailio: {e}")
            return False
            
    async def get_server_status(self) -> ServerStatus:
        """Get server status and statistics."""
        try:
            # Get Kamailio statistics
            stats = await self._get_kamailio_stats()
            
            # Get system metrics
            import psutil
            
            # Calculate uptime
            with open('/proc/uptime', 'r') as f:
                uptime = int(float(f.readline().split()[0]))
                
            status = ServerStatus(
                status="healthy" if stats.get("active", False) else "unhealthy",
                uptime=uptime,
                active_calls=stats.get("active_calls", 0),
                total_calls_today=stats.get("total_calls_today", 0),
                registered_numbers=stats.get("registered_numbers", 0),
                memory_usage=psutil.virtual_memory().percent,
                cpu_usage=psutil.cpu_percent(interval=1),
                version=stats.get("version", "Unknown")
            )
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get server status: {e}")
            # Return degraded status
            return ServerStatus(
                status="degraded",
                uptime=0,
                memory_usage=0.0,
                cpu_usage=0.0,
                version="Unknown",
                last_error=str(e)
            )
            
    async def get_sip_domains(self) -> List[str]:
        """Get list of configured SIP domains."""
        try:
            # Read from config or database
            config = await self.get_config()
            return config.sip_domains
        except Exception as e:
            logger.error(f"Failed to get SIP domains: {e}")
            return []
            
    async def add_sip_domain(self, domain: str) -> bool:
        """Add a new SIP domain."""
        try:
            config = await self.get_config()
            if domain not in config.sip_domains:
                config.sip_domains.append(domain)
                return await self.update_config(config)
            return True
        except Exception as e:
            logger.error(f"Failed to add domain: {e}")
            return False
            
    async def remove_sip_domain(self, domain: str) -> bool:
        """Remove a SIP domain."""
        try:
            config = await self.get_config()
            if domain in config.sip_domains:
                config.sip_domains.remove(domain)
                return await self.update_config(config)
            return True
        except Exception as e:
            logger.error(f"Failed to remove domain: {e}")
            return False
            
    async def _generate_kamailio_config(self, config: SIPConfig) -> str:
        """Generate Kamailio configuration file."""
        # This would generate the actual Kamailio config
        # For now, return a template
        template = """#!KAMAILIO
# Auto-generated configuration
        
# Global parameters
debug=2
log_stderror=yes
        
# Aliases
"""
        for domain in config.sip_domains:
            template += f'alias="{domain}"\n'
            
        # Add more configuration based on SIPConfig
        return template
        
    async def _validate_kamailio_config(self) -> bool:
        """Validate Kamailio configuration file."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'kamailio', '-c', '-f', str(self.config_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            return proc.returncode == 0
            
        except Exception as e:
            logger.error(f"Failed to validate config: {e}")
            return False
            
    async def _get_kamailio_stats(self) -> Dict[str, Any]:
        """Get Kamailio statistics via RPC."""
        try:
            # This would make RPC calls to get stats
            # For now, return mock data
            return {
                "active": True,
                "version": "5.7.0",
                "active_calls": 42,
                "total_calls_today": 1337,
                "registered_numbers": 100
            }
        except Exception as e:
            logger.error(f"Failed to get Kamailio stats: {e}")
            return {}