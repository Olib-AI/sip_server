"""SIP Trunk Manager for handling external SIP provider connectivity."""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import aiohttp
import json
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, select, insert, update, delete
import os

from ..models.database import Dispatcher, TrunkConfiguration, get_db, DATABASE_URL
from ..utils.config import get_config

logger = logging.getLogger(__name__)


class TrunkStatus(Enum):
    """SIP trunk status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    REGISTERING = "registering"
    REGISTERED = "registered"


class AuthMethod(Enum):
    """Authentication methods."""
    NONE = "none"
    DIGEST = "digest"
    IP_AUTH = "ip_auth"
    CERTIFICATE = "certificate"


@dataclass
class TrunkCredentials:
    """SIP trunk authentication credentials."""
    username: Optional[str] = None
    password: Optional[str] = None
    realm: Optional[str] = None
    auth_method: AuthMethod = AuthMethod.DIGEST
    
    # IP-based authentication
    allowed_ips: List[str] = field(default_factory=list)
    
    # Certificate-based authentication
    certificate_path: Optional[str] = None
    private_key_path: Optional[str] = None


@dataclass 
class TrunkConfig:
    """SIP trunk configuration."""
    trunk_id: str
    name: str
    provider: str
    
    # Connection details
    proxy_address: str
    proxy_port: int = 5060
    registrar_address: Optional[str] = None
    registrar_port: int = 5060
    
    # Authentication
    credentials: TrunkCredentials = field(default_factory=TrunkCredentials)
    
    # Transport
    transport: str = "UDP"  # UDP, TCP, TLS
    
    # Features
    supports_registration: bool = True
    supports_outbound: bool = True
    supports_inbound: bool = True
    
    # Routing
    dial_prefix: str = ""
    strip_digits: int = 0
    prepend_digits: str = ""
    
    # Capacity limits
    max_concurrent_calls: int = 100
    calls_per_second_limit: int = 10
    
    # Failover
    backup_trunks: List[str] = field(default_factory=list)
    failover_timeout: int = 30
    
    # Codec preferences
    preferred_codecs: List[str] = field(default_factory=lambda: ["PCMU", "PCMA"])
    
    # Quality settings
    enable_dtmf_relay: bool = True
    rtp_timeout: int = 60
    
    # Monitoring
    heartbeat_interval: int = 30
    registration_expire: int = 3600
    
    # Status tracking
    status: TrunkStatus = TrunkStatus.INACTIVE
    last_registration: Optional[float] = None
    failure_count: int = 0
    
    # Statistics
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    current_calls: int = 0
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get trunk statistics."""
        uptime = time.time() - (self.last_registration or 0)
        success_rate = self.successful_calls / max(self.total_calls, 1)
        
        return {
            "trunk_id": self.trunk_id,
            "name": self.name,
            "provider": self.provider,
            "status": self.status.value,
            "uptime_seconds": uptime,
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "current_calls": self.current_calls,
            "success_rate": success_rate,
            "failure_count": self.failure_count,
            "last_registration": self.last_registration
        }


class SIPTrunkManager:
    """Manager for SIP trunk connections."""
    
    def __init__(self, kamailio_rpc_url: Optional[str] = None):
        config = get_config()
        self.kamailio_rpc_url = kamailio_rpc_url or f"http://{config.sip.host}:{config.sip.port}/RPC"
        self.trunks: Dict[str, TrunkConfig] = {}
        self.active_calls: Dict[str, str] = {}  # call_id -> trunk_id
        
        # Database engine for direct database operations
        self.db_engine = create_engine(DATABASE_URL)
        
        # Monitoring tasks
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.registration_tasks: Dict[str, asyncio.Task] = {}
        
        # Statistics
        self.total_trunk_calls = 0
        self.failed_trunk_calls = 0
        self.trunk_registrations = 0
        
    async def start(self):
        """Start trunk manager."""
        logger.info("SIP Trunk Manager started")
        
        # Load trunk configurations from database
        await self.load_trunks_from_database()
        
        # Start monitoring for existing trunks
        for trunk_id in self.trunks.keys():
            await self._start_trunk_monitoring(trunk_id)
    
    async def stop(self):
        """Stop trunk manager."""
        try:
            # Stop all monitoring tasks
            for task in self.monitoring_tasks.values():
                task.cancel()
            
            for task in self.registration_tasks.values():
                task.cancel()
            
            # Wait for tasks to complete
            if self.monitoring_tasks:
                await asyncio.gather(*self.monitoring_tasks.values(), return_exceptions=True)
            
            if self.registration_tasks:
                await asyncio.gather(*self.registration_tasks.values(), return_exceptions=True)
            
            logger.info("SIP Trunk Manager stopped")
            
        except Exception as e:
            logger.error(f"Error stopping trunk manager: {e}")
    
    async def add_trunk(self, config: TrunkConfig) -> bool:
        """Add SIP trunk configuration."""
        try:
            # Validate configuration
            if not self._validate_trunk_config(config):
                return False
            
            # Store configuration
            self.trunks[config.trunk_id] = config
            
            # Update Kamailio dispatcher table
            await self._update_kamailio_dispatcher(config)
            
            # Start monitoring
            await self._start_trunk_monitoring(config.trunk_id)
            
            # Start registration if required
            if config.supports_registration:
                await self._start_trunk_registration(config.trunk_id)
            
            logger.info(f"Added SIP trunk: {config.trunk_id} ({config.provider})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add trunk {config.trunk_id}: {e}")
            return False
    
    async def remove_trunk(self, trunk_id: str) -> bool:
        """Remove SIP trunk."""
        try:
            if trunk_id not in self.trunks:
                return False
            
            # Stop monitoring
            if trunk_id in self.monitoring_tasks:
                self.monitoring_tasks[trunk_id].cancel()
                del self.monitoring_tasks[trunk_id]
            
            # Stop registration
            if trunk_id in self.registration_tasks:
                self.registration_tasks[trunk_id].cancel()
                del self.registration_tasks[trunk_id]
            
            # Remove from Kamailio
            await self._remove_from_kamailio_dispatcher(trunk_id)
            
            # Remove configuration
            del self.trunks[trunk_id]
            
            logger.info(f"Removed SIP trunk: {trunk_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove trunk {trunk_id}: {e}")
            return False
    
    async def route_outbound_call(self, call_id: str, destination: str, 
                                 preferences: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Route outbound call through appropriate trunk."""
        try:
            # Find suitable trunk
            trunk = await self._select_trunk_for_destination(destination, preferences)
            
            if not trunk:
                logger.error(f"No suitable trunk found for destination: {destination}")
                return None
            
            # Check capacity
            if trunk.current_calls >= trunk.max_concurrent_calls:
                logger.warning(f"Trunk {trunk.trunk_id} at capacity")
                return None
            
            # Prepare routing information
            route_info = await self._prepare_outbound_route(trunk, destination)
            
            # Track call
            self.active_calls[call_id] = trunk.trunk_id
            trunk.current_calls += 1
            trunk.total_calls += 1
            self.total_trunk_calls += 1
            
            logger.info(f"Routing call {call_id} to {destination} via trunk {trunk.trunk_id}")
            return route_info
            
        except Exception as e:
            logger.error(f"Failed to route call {call_id}: {e}")
            self.failed_trunk_calls += 1
            return None
    
    async def handle_inbound_call(self, call_id: str, from_trunk: str, 
                                 caller_info: Dict[str, Any]) -> bool:
        """Handle inbound call from trunk."""
        try:
            trunk = self.trunks.get(from_trunk)
            if not trunk or not trunk.supports_inbound:
                logger.warning(f"Inbound call rejected from trunk: {from_trunk}")
                return False
            
            # Validate source
            if not await self._validate_inbound_source(trunk, caller_info):
                logger.warning(f"Invalid inbound source for trunk {from_trunk}")
                return False
            
            # Track call
            self.active_calls[call_id] = trunk.trunk_id
            trunk.current_calls += 1
            trunk.total_calls += 1
            
            logger.info(f"Accepted inbound call {call_id} from trunk {from_trunk}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle inbound call: {e}")
            return False
    
    async def end_call(self, call_id: str, success: bool = True):
        """End call and update statistics."""
        try:
            trunk_id = self.active_calls.get(call_id)
            if not trunk_id:
                return
            
            trunk = self.trunks.get(trunk_id)
            if trunk:
                trunk.current_calls = max(0, trunk.current_calls - 1)
                
                if success:
                    trunk.successful_calls += 1
                else:
                    trunk.failed_calls += 1
            
            # Remove from active calls
            del self.active_calls[call_id]
            
        except Exception as e:
            logger.error(f"Error ending call {call_id}: {e}")
    
    async def get_trunk_status(self, trunk_id: str) -> Optional[Dict[str, Any]]:
        """Get trunk status and statistics."""
        trunk = self.trunks.get(trunk_id)
        if not trunk:
            return None
        
        return trunk.get_statistics()
    
    async def get_all_trunks_status(self) -> Dict[str, Any]:
        """Get status of all trunks."""
        trunks_status = {}
        
        for trunk_id, trunk in self.trunks.items():
            trunks_status[trunk_id] = trunk.get_statistics()
        
        return {
            "trunks": trunks_status,
            "total_trunks": len(self.trunks),
            "active_trunks": len([t for t in self.trunks.values() if t.status == TrunkStatus.ACTIVE]),
            "total_calls": self.total_trunk_calls,
            "failed_calls": self.failed_trunk_calls,
            "active_calls": len(self.active_calls)
        }
    
    async def _start_trunk_monitoring(self, trunk_id: str):
        """Start monitoring task for trunk."""
        if trunk_id in self.monitoring_tasks:
            return
        
        task = asyncio.create_task(self._monitor_trunk(trunk_id))
        self.monitoring_tasks[trunk_id] = task
    
    async def _monitor_trunk(self, trunk_id: str):
        """Monitor trunk health and connectivity."""
        while True:
            try:
                trunk = self.trunks.get(trunk_id)
                if not trunk:
                    break
                
                # Check trunk connectivity
                is_reachable = await self._check_trunk_connectivity(trunk)
                
                if is_reachable:
                    if trunk.status == TrunkStatus.FAILED:
                        trunk.status = TrunkStatus.ACTIVE
                        trunk.failure_count = 0
                        logger.info(f"Trunk {trunk_id} recovered")
                else:
                    trunk.failure_count += 1
                    if trunk.failure_count >= 3:
                        trunk.status = TrunkStatus.FAILED
                        logger.warning(f"Trunk {trunk_id} marked as failed")
                
                # Wait for next check
                await asyncio.sleep(trunk.heartbeat_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring trunk {trunk_id}: {e}")
                await asyncio.sleep(30)
    
    async def _start_trunk_registration(self, trunk_id: str):
        """Start registration task for trunk."""
        if trunk_id in self.registration_tasks:
            return
        
        task = asyncio.create_task(self._register_trunk(trunk_id))
        self.registration_tasks[trunk_id] = task
    
    async def _register_trunk(self, trunk_id: str):
        """Handle trunk registration."""
        while True:
            try:
                trunk = self.trunks.get(trunk_id)
                if not trunk or not trunk.supports_registration:
                    break
                
                # Perform registration
                success = await self._send_register(trunk)
                
                if success:
                    trunk.status = TrunkStatus.REGISTERED
                    trunk.last_registration = time.time()
                    trunk.failure_count = 0
                    self.trunk_registrations += 1
                    
                    # Wait for next registration (before expiry)
                    await asyncio.sleep(trunk.registration_expire * 0.8)
                else:
                    trunk.failure_count += 1
                    if trunk.failure_count >= 3:
                        trunk.status = TrunkStatus.FAILED
                    
                    # Retry registration
                    await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error registering trunk {trunk_id}: {e}")
                await asyncio.sleep(60)
    
    async def _send_register(self, trunk: TrunkConfig) -> bool:
        """Send SIP REGISTER to trunk."""
        try:
            # This would typically use a SIP client library
            # For now, we'll use Kamailio's UAC module via RPC
            
            register_params = {
                "method": "uac.reg_register",
                "params": [
                    f"sip:{trunk.credentials.username}@{trunk.registrar_address or trunk.proxy_address}",
                    f"sip:{trunk.proxy_address}:{trunk.proxy_port}",
                    trunk.credentials.username,
                    trunk.credentials.password,
                    trunk.registration_expire
                ]
            }
            
            success = await self._send_kamailio_rpc(register_params)
            
            if success:
                logger.info(f"Successfully registered trunk {trunk.trunk_id}")
                return True
            else:
                logger.error(f"Failed to register trunk {trunk.trunk_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending REGISTER for trunk {trunk.trunk_id}: {e}")
            return False
    
    async def _check_trunk_connectivity(self, trunk: TrunkConfig) -> bool:
        """Check if trunk is reachable."""
        try:
            # Send OPTIONS ping
            options_params = {
                "method": "uac.req_send", 
                "params": [
                    "OPTIONS",
                    f"sip:{trunk.proxy_address}:{trunk.proxy_port}",
                    "",
                    "",
                    ""
                ]
            }
            
            return await self._send_kamailio_rpc(options_params)
            
        except Exception as e:
            logger.error(f"Error checking connectivity for trunk {trunk.trunk_id}: {e}")
            return False
    
    async def _send_kamailio_rpc(self, params: Dict[str, Any]) -> bool:
        """Send RPC command to Kamailio."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.kamailio_rpc_url,
                    json=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result.get("result") == "ok"
                    return False
                    
        except Exception as e:
            logger.error(f"Kamailio RPC error: {e}")
            return False
    
    def _validate_trunk_config(self, config: TrunkConfig) -> bool:
        """Validate trunk configuration."""
        if not config.trunk_id or not config.proxy_address:
            logger.error("Invalid trunk configuration: missing required fields")
            return False
        
        if config.supports_registration and not config.credentials.username:
            logger.error("Registration enabled but no credentials provided")
            return False
        
        return True
    
    async def _update_kamailio_dispatcher(self, config: TrunkConfig):
        """Update Kamailio dispatcher table with trunk."""
        try:
            with Session(self.db_engine) as session:
                # Prepare dispatcher destination URI
                destination = f"sip:{config.proxy_address}:{config.proxy_port}"
                
                # Set dispatcher group ID (setid) based on trunk capabilities
                setid = 1 if config.supports_outbound else 2
                
                # Check if entry already exists
                existing = session.execute(
                    select(Dispatcher).where(
                        Dispatcher.destination == destination,
                        Dispatcher.setid == setid
                    )
                ).first()
                
                if existing:
                    # Update existing entry
                    session.execute(
                        update(Dispatcher)
                        .where(Dispatcher.id == existing[0].id)
                        .values(
                            flags=0 if config.status == TrunkStatus.ACTIVE else 1,
                            priority=1,
                            attrs=f"trunk_id={config.trunk_id};provider={config.provider}",
                            description=f"{config.name} - {config.provider}"
                        )
                    )
                else:
                    # Insert new entry
                    session.execute(
                        insert(Dispatcher).values(
                            setid=setid,
                            destination=destination,
                            flags=0 if config.status == TrunkStatus.ACTIVE else 1,
                            priority=1,
                            attrs=f"trunk_id={config.trunk_id};provider={config.provider}",
                            description=f"{config.name} - {config.provider}"
                        )
                    )
                
                session.commit()
                
                # Save trunk configuration to database
                await self._save_trunk_config(config)
                
                # Reload Kamailio dispatcher
                await self._reload_kamailio_dispatcher()
                
                logger.info(f"Updated Kamailio dispatcher for trunk {config.trunk_id}")
                
        except Exception as e:
            logger.error(f"Failed to update Kamailio dispatcher for trunk {config.trunk_id}: {e}")
            raise
    
    async def _remove_from_kamailio_dispatcher(self, trunk_id: str):
        """Remove trunk from Kamailio dispatcher."""
        try:
            trunk = self.trunks.get(trunk_id)
            if not trunk:
                return
                
            with Session(self.db_engine) as session:
                # Remove from dispatcher table
                destination = f"sip:{trunk.proxy_address}:{trunk.proxy_port}"
                
                session.execute(
                    delete(Dispatcher).where(
                        Dispatcher.destination == destination
                    )
                )
                
                # Remove trunk configuration
                session.execute(
                    delete(TrunkConfiguration).where(
                        TrunkConfiguration.trunk_id == trunk_id
                    )
                )
                
                session.commit()
                
                # Reload Kamailio dispatcher
                await self._reload_kamailio_dispatcher()
                
                logger.info(f"Removed trunk {trunk_id} from Kamailio dispatcher")
                
        except Exception as e:
            logger.error(f"Failed to remove trunk {trunk_id} from Kamailio dispatcher: {e}")
            raise
    
    async def _select_trunk_for_destination(self, destination: str, 
                                          preferences: Optional[Dict[str, Any]] = None) -> Optional[TrunkConfig]:
        """Select best trunk for destination."""
        # Find active trunks that support outbound
        candidates = [
            trunk for trunk in self.trunks.values()
            if trunk.status in [TrunkStatus.ACTIVE, TrunkStatus.REGISTERED] 
            and trunk.supports_outbound
        ]
        
        if not candidates:
            return None
        
        # Apply preferences and routing logic
        # For now, return first available trunk
        return candidates[0]
    
    async def _prepare_outbound_route(self, trunk: TrunkConfig, destination: str) -> str:
        """Prepare routing information for outbound call."""
        # Apply dial plan transformations
        processed_dest = destination
        
        # Strip digits
        if trunk.strip_digits > 0:
            processed_dest = processed_dest[trunk.strip_digits:]
        
        # Prepend digits
        if trunk.prepend_digits:
            processed_dest = trunk.prepend_digits + processed_dest
        
        # Add prefix
        if trunk.dial_prefix:
            processed_dest = trunk.dial_prefix + processed_dest
        
        # Return SIP URI
        return f"sip:{processed_dest}@{trunk.proxy_address}:{trunk.proxy_port}"
    
    async def _validate_inbound_source(self, trunk: TrunkConfig, 
                                     caller_info: Dict[str, Any]) -> bool:
        """Validate inbound call source."""
        # Check IP authentication if configured
        if trunk.credentials.auth_method == AuthMethod.IP_AUTH:
            source_ip = caller_info.get("source_ip")
            return source_ip in trunk.credentials.allowed_ips
        
        # For other auth methods, assume valid for now
        return True
    
    async def _save_trunk_config(self, config: TrunkConfig):
        """Save trunk configuration to database."""
        try:
            with Session(self.db_engine) as session:
                # Check if configuration already exists
                existing = session.execute(
                    select(TrunkConfiguration).where(
                        TrunkConfiguration.trunk_id == config.trunk_id
                    )
                ).first()
                
                config_data = {
                    "trunk_id": config.trunk_id,
                    "name": config.name,
                    "provider": config.provider,
                    "proxy_address": config.proxy_address,
                    "proxy_port": config.proxy_port,
                    "registrar_address": config.registrar_address,
                    "registrar_port": config.registrar_port,
                    "username": config.credentials.username,
                    "password": config.credentials.password,  # Should be encrypted in production
                    "realm": config.credentials.realm,
                    "auth_method": config.credentials.auth_method.value,
                    "transport": config.transport,
                    "supports_registration": config.supports_registration,
                    "supports_outbound": config.supports_outbound,
                    "supports_inbound": config.supports_inbound,
                    "dial_prefix": config.dial_prefix,
                    "strip_digits": config.strip_digits,
                    "prepend_digits": config.prepend_digits,
                    "max_concurrent_calls": config.max_concurrent_calls,
                    "calls_per_second_limit": config.calls_per_second_limit,
                    "preferred_codecs": config.preferred_codecs,
                    "enable_dtmf_relay": config.enable_dtmf_relay,
                    "rtp_timeout": config.rtp_timeout,
                    "heartbeat_interval": config.heartbeat_interval,
                    "registration_expire": config.registration_expire,
                    "failover_timeout": config.failover_timeout,
                    "backup_trunks": config.backup_trunks,
                    "allowed_ips": config.credentials.allowed_ips,
                    "status": config.status.value,
                    "failure_count": config.failure_count,
                    "last_registration": config.last_registration,
                    "total_calls": config.total_calls,
                    "successful_calls": config.successful_calls,
                    "failed_calls": config.failed_calls,
                    "current_calls": config.current_calls
                }
                
                if existing:
                    # Update existing configuration
                    session.execute(
                        update(TrunkConfiguration)
                        .where(TrunkConfiguration.trunk_id == config.trunk_id)
                        .values(**config_data)
                    )
                else:
                    # Insert new configuration
                    session.execute(
                        insert(TrunkConfiguration).values(**config_data)
                    )
                
                session.commit()
                logger.info(f"Saved trunk configuration for {config.trunk_id}")
                
        except Exception as e:
            logger.error(f"Failed to save trunk configuration for {config.trunk_id}: {e}")
            raise
    
    async def _reload_kamailio_dispatcher(self):
        """Reload Kamailio dispatcher configuration."""
        try:
            # Send RPC command to reload dispatcher
            reload_params = {
                "method": "dispatcher.reload",
                "params": []
            }
            
            success = await self._send_kamailio_rpc(reload_params)
            
            if success:
                logger.info("Kamailio dispatcher configuration reloaded")
            else:
                logger.warning("Failed to reload Kamailio dispatcher configuration")
                
        except Exception as e:
            logger.error(f"Error reloading Kamailio dispatcher: {e}")
    
    async def load_trunks_from_database(self):
        """Load trunk configurations from database on startup."""
        try:
            with Session(self.db_engine) as session:
                trunk_configs = session.execute(select(TrunkConfiguration)).scalars().all()
                
                for db_config in trunk_configs:
                    # Convert database record to TrunkConfig
                    credentials = TrunkCredentials(
                        username=db_config.username,
                        password=db_config.password,
                        realm=db_config.realm,
                        auth_method=AuthMethod(db_config.auth_method),
                        allowed_ips=db_config.allowed_ips or []
                    )
                    
                    trunk_config = TrunkConfig(
                        trunk_id=db_config.trunk_id,
                        name=db_config.name,
                        provider=db_config.provider,
                        proxy_address=db_config.proxy_address,
                        proxy_port=db_config.proxy_port,
                        registrar_address=db_config.registrar_address,
                        registrar_port=db_config.registrar_port,
                        credentials=credentials,
                        transport=db_config.transport,
                        supports_registration=db_config.supports_registration,
                        supports_outbound=db_config.supports_outbound,
                        supports_inbound=db_config.supports_inbound,
                        dial_prefix=db_config.dial_prefix,
                        strip_digits=db_config.strip_digits,
                        prepend_digits=db_config.prepend_digits,
                        max_concurrent_calls=db_config.max_concurrent_calls,
                        calls_per_second_limit=db_config.calls_per_second_limit,
                        preferred_codecs=db_config.preferred_codecs or ["PCMU", "PCMA"],
                        enable_dtmf_relay=db_config.enable_dtmf_relay,
                        rtp_timeout=db_config.rtp_timeout,
                        heartbeat_interval=db_config.heartbeat_interval,
                        registration_expire=db_config.registration_expire,
                        failover_timeout=db_config.failover_timeout,
                        backup_trunks=db_config.backup_trunks or [],
                        status=TrunkStatus(db_config.status),
                        last_registration=db_config.last_registration.timestamp() if db_config.last_registration else None,
                        failure_count=db_config.failure_count,
                        total_calls=db_config.total_calls,
                        successful_calls=db_config.successful_calls,
                        failed_calls=db_config.failed_calls,
                        current_calls=db_config.current_calls
                    )
                    
                    # Load into memory
                    self.trunks[trunk_config.trunk_id] = trunk_config
                    
                    # Start monitoring if trunk is active
                    if trunk_config.status in [TrunkStatus.ACTIVE, TrunkStatus.REGISTERED]:
                        await self._start_trunk_monitoring(trunk_config.trunk_id)
                        
                        if trunk_config.supports_registration:
                            await self._start_trunk_registration(trunk_config.trunk_id)
                
                logger.info(f"Loaded {len(trunk_configs)} trunk configurations from database")
                
        except Exception as e:
            logger.error(f"Failed to load trunk configurations from database: {e}")
    
    async def get_trunk_by_id(self, trunk_id: str) -> Optional[TrunkConfig]:
        """Get trunk configuration by ID."""
        return self.trunks.get(trunk_id)
    
    async def update_trunk_statistics(self, trunk_id: str, call_success: bool):
        """Update trunk call statistics."""
        trunk = self.trunks.get(trunk_id)
        if not trunk:
            return
            
        # Update in-memory statistics
        if call_success:
            trunk.successful_calls += 1
        else:
            trunk.failed_calls += 1
            
        # Persist to database
        try:
            await self._save_trunk_config(trunk)
        except Exception as e:
            logger.error(f"Failed to update trunk statistics for {trunk_id}: {e}")