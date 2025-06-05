"""Advanced call management system for SIP server."""
import asyncio
import logging
import time
import uuid
from typing import Dict, List, Optional, Callable, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque

# DTMF and Interactive Features
from ..dtmf.dtmf_detector import DTMFDetector, DTMFEvent
from ..dtmf.dtmf_processor import DTMFProcessor
from ..dtmf.music_on_hold import MusicOnHoldManager
from ..dtmf.ivr_manager import IVRManager
from ..utils.config import get_config
from ..sms.sms_manager import SMSManager
import aiohttp

logger = logging.getLogger(__name__)


class CallDirection(Enum):
    """Call direction types."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class CallState(Enum):
    """Extended call states."""
    INITIALIZING = "initializing"
    RINGING = "ringing"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ON_HOLD = "on_hold"
    TRANSFERRING = "transferring"
    FORWARDING = "forwarding"
    RECORDING = "recording"
    ENDING = "ending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUSY = "busy"
    NO_ANSWER = "no_answer"


class CallPriority(Enum):
    """Call priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    EMERGENCY = 4


@dataclass
class CallParticipant:
    """Call participant information."""
    number: str
    display_name: Optional[str] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    is_registered: bool = False
    capabilities: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CallSession:
    """Complete call session information."""
    call_id: str
    session_id: str
    direction: CallDirection
    state: CallState
    priority: CallPriority
    
    # Participants
    caller: CallParticipant
    callee: CallParticipant
    
    # Timing
    created_at: datetime
    ring_start: Optional[datetime] = None
    connect_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    # SIP details
    sip_call_id: Optional[str] = None
    sip_dialog_id: Optional[str] = None
    from_tag: Optional[str] = None
    to_tag: Optional[str] = None
    
    # Media
    codec: str = "PCMU"
    rtp_local_port: Optional[int] = None
    rtp_remote_port: Optional[int] = None
    recording_url: Optional[str] = None
    
    # Features
    is_recording: bool = False
    is_on_hold: bool = False
    transfer_target: Optional[str] = None
    forward_target: Optional[str] = None
    
    # AI integration
    ai_session_id: Optional[str] = None
    ai_context: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    sip_headers: Dict[str, str] = field(default_factory=dict)
    custom_data: Dict[str, Any] = field(default_factory=dict)
    
    def duration(self) -> Optional[float]:
        """Calculate call duration in seconds."""
        if self.connect_time and self.end_time:
            return (self.end_time - self.connect_time).total_seconds()
        elif self.connect_time:
            return (datetime.utcnow() - self.connect_time).total_seconds()
        return None
    
    def ring_duration(self) -> Optional[float]:
        """Calculate ring duration in seconds."""
        if self.ring_start:
            end_time = self.connect_time or self.end_time or datetime.utcnow()
            return (end_time - self.ring_start).total_seconds()
        return None


class CallQueue:
    """Advanced call queue management."""
    
    def __init__(self, max_size: int = 100, timeout_seconds: int = 300):
        self.max_size = max_size
        self.timeout_seconds = timeout_seconds
        self.queued_calls: deque = deque()
        self.call_positions: Dict[str, int] = {}
        
    def add_call(self, call_session: CallSession) -> bool:
        """Add call to queue."""
        if len(self.queued_calls) >= self.max_size:
            logger.warning(f"Call queue full, rejecting call {call_session.call_id}")
            return False
            
        self.queued_calls.append(call_session)
        self._update_positions()
        
        logger.info(f"Call {call_session.call_id} added to queue, position {len(self.queued_calls)}")
        return True
    
    def remove_call(self, call_id: str) -> Optional[CallSession]:
        """Remove call from queue."""
        for i, call in enumerate(self.queued_calls):
            if call.call_id == call_id:
                call = self.queued_calls[i]
                del self.queued_calls[i]
                self._update_positions()
                return call
        return None
    
    def get_next_call(self) -> Optional[CallSession]:
        """Get next call from queue (priority-based)."""
        if not self.queued_calls:
            return None
            
        # Sort by priority, then by arrival time
        sorted_calls = sorted(
            self.queued_calls,
            key=lambda c: (c.priority.value, c.created_at),
            reverse=True
        )
        
        next_call = sorted_calls[0]
        self.remove_call(next_call.call_id)
        return next_call
    
    def get_position(self, call_id: str) -> Optional[int]:
        """Get call position in queue."""
        return self.call_positions.get(call_id)
    
    def cleanup_expired(self) -> List[CallSession]:
        """Remove expired calls from queue."""
        current_time = datetime.utcnow()
        expired_calls = []
        
        for call in list(self.queued_calls):
            age = (current_time - call.created_at).total_seconds()
            if age > self.timeout_seconds:
                expired_calls.append(self.remove_call(call.call_id))
                
        return [c for c in expired_calls if c]
    
    def _update_positions(self):
        """Update call positions in queue."""
        self.call_positions.clear()
        for i, call in enumerate(self.queued_calls):
            self.call_positions[call.call_id] = i + 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "total_queued": len(self.queued_calls),
            "max_size": self.max_size,
            "average_wait_time": self._calculate_average_wait_time(),
            "priority_breakdown": self._get_priority_breakdown()
        }
    
    def _calculate_average_wait_time(self) -> float:
        """Calculate average wait time in queue."""
        if not self.queued_calls:
            return 0.0
            
        current_time = datetime.utcnow()
        total_wait = sum(
            (current_time - call.created_at).total_seconds()
            for call in self.queued_calls
        )
        return total_wait / len(self.queued_calls)
    
    def _get_priority_breakdown(self) -> Dict[str, int]:
        """Get breakdown of calls by priority."""
        breakdown = defaultdict(int)
        for call in self.queued_calls:
            breakdown[call.priority.name] += 1
        return dict(breakdown)


class CallRouter:
    """Advanced call routing logic."""
    
    def __init__(self):
        self.routing_rules: List[Dict[str, Any]] = []
        self.blacklisted_numbers: Set[str] = set()
        self.whitelisted_numbers: Set[str] = set()
        self.number_patterns: Dict[str, str] = {}  # Pattern -> Route
        
    def add_routing_rule(self, rule: Dict[str, Any]):
        """Add routing rule."""
        self.routing_rules.append(rule)
        self.routing_rules.sort(key=lambda r: r.get('priority', 0), reverse=True)
    
    def route_call(self, call_session: CallSession) -> Dict[str, Any]:
        """Determine routing for call."""
        caller_number = call_session.caller.number
        callee_number = call_session.callee.number
        
        # Check blacklist
        if caller_number in self.blacklisted_numbers:
            return {"action": "reject", "reason": "caller_blacklisted"}
        
        # Check whitelist (if enabled)
        if self.whitelisted_numbers and caller_number not in self.whitelisted_numbers:
            return {"action": "reject", "reason": "caller_not_whitelisted"}
        
        # Apply routing rules
        for rule in self.routing_rules:
            if self._matches_rule(call_session, rule):
                return self._apply_rule(call_session, rule)
        
        # Default routing
        return {"action": "accept", "target": callee_number}
    
    def _matches_rule(self, call_session: CallSession, rule: Dict[str, Any]) -> bool:
        """Check if call matches routing rule."""
        conditions = rule.get("conditions", {})
        
        # Check caller number pattern
        if "caller_pattern" in conditions:
            import re
            pattern = conditions["caller_pattern"]
            if not re.match(pattern, call_session.caller.number):
                return False
        
        # Check callee number pattern
        if "callee_pattern" in conditions:
            import re
            pattern = conditions["callee_pattern"]
            if not re.match(pattern, call_session.callee.number):
                return False
        
        # Check time of day
        if "time_range" in conditions:
            current_time = datetime.now().time()
            start_time = datetime.strptime(conditions["time_range"]["start"], "%H:%M").time()
            end_time = datetime.strptime(conditions["time_range"]["end"], "%H:%M").time()
            
            if not (start_time <= current_time <= end_time):
                return False
        
        return True
    
    def _apply_rule(self, call_session: CallSession, rule: Dict[str, Any]) -> Dict[str, Any]:
        """Apply routing rule to call."""
        action = rule.get("action", {})
        
        if action.get("type") == "forward":
            return {
                "action": "forward",
                "target": action.get("target"),
                "timeout": action.get("timeout", 30)
            }
        elif action.get("type") == "queue":
            return {
                "action": "queue",
                "queue_name": action.get("queue_name", "default"),
                "priority": action.get("priority", "normal")
            }
        elif action.get("type") == "reject":
            return {
                "action": "reject",
                "reason": action.get("reason", "routing_rule")
            }
        
        return {"action": "accept"}


class KamailioStateSynchronizer:
    """Synchronizes call states with Kamailio SIP server."""
    
    def __init__(self, kamailio_rpc_url: Optional[str] = None):
        config = get_config()
        self.kamailio_rpc_url = kamailio_rpc_url or f"http://{config.sip.host}:{config.sip.port}/jsonrpc"
        self.pending_updates: Dict[str, Dict] = {}
        self.sync_interval = 5  # seconds
        self.running = False
        
    async def start(self):
        """Start synchronization loop."""
        self.running = True
        asyncio.create_task(self._sync_loop())
        logger.info("Kamailio state synchronizer started")
    
    async def stop(self):
        """Stop synchronization."""
        self.running = False
        logger.info("Kamailio state synchronizer stopped")
    
    async def notify_state_change(self, call_session, old_state: CallState, new_state: CallState):
        """Notify Kamailio of call state change."""
        try:
            # Map our call states to Kamailio dialog states
            kamailio_state = self._map_to_kamailio_state(new_state)
            
            if kamailio_state:
                # Queue update for batch processing
                self.pending_updates[call_session.call_id] = {
                    "call_id": call_session.call_id,
                    "sip_call_id": call_session.sip_call_id,
                    "state": kamailio_state,
                    "timestamp": datetime.utcnow().isoformat(),
                    "from_number": call_session.caller.number,
                    "to_number": call_session.callee.number
                }
                
                # For critical state changes, sync immediately
                if new_state in [CallState.CONNECTED, CallState.COMPLETED, CallState.FAILED]:
                    await self._sync_immediate(call_session.call_id)
                    
        except Exception as e:
            logger.error(f"Error notifying Kamailio state change: {e}")
    
    async def notify_call_creation(self, call_session):
        """Notify Kamailio of new call creation."""
        try:
            await self._send_kamailio_request("dlg.profile_set", [
                call_session.sip_call_id,
                "call_manager_id",
                call_session.call_id
            ])
            
            await self._send_kamailio_request("dlg.profile_set", [
                call_session.sip_call_id,
                "ai_session_id", 
                call_session.ai_session_id or ""
            ])
            
        except Exception as e:
            logger.error(f"Error notifying Kamailio call creation: {e}")
    
    async def notify_call_completion(self, call_session):
        """Notify Kamailio of call completion."""
        try:
            # Update call statistics
            await self._send_kamailio_request("stats.set_stat", [
                "call_manager.completed_calls",
                1
            ])
            
            # Clean up dialog profiles
            if call_session.sip_call_id:
                await self._send_kamailio_request("dlg.profile_unset", [
                    call_session.sip_call_id,
                    "call_manager_id"
                ])
                
        except Exception as e:
            logger.error(f"Error notifying Kamailio call completion: {e}")
    
    async def get_kamailio_dialog_info(self, sip_call_id: str) -> Optional[Dict]:
        """Get dialog information from Kamailio."""
        try:
            result = await self._send_kamailio_request("dlg.list", [])
            
            if result and "result" in result:
                dialogs = result["result"]
                for dialog in dialogs:
                    if dialog.get("callid") == sip_call_id:
                        return dialog
                        
        except Exception as e:
            logger.error(f"Error getting Kamailio dialog info: {e}")
        
        return None
    
    async def _sync_loop(self):
        """Main synchronization loop."""
        while self.running:
            try:
                if self.pending_updates:
                    # Process pending updates in batch
                    updates = list(self.pending_updates.values())
                    self.pending_updates.clear()
                    
                    for update in updates:
                        await self._sync_call_state(update)
                
                await asyncio.sleep(self.sync_interval)
                
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                await asyncio.sleep(self.sync_interval)
    
    async def _sync_immediate(self, call_id: str):
        """Sync specific call state immediately."""
        update = self.pending_updates.pop(call_id, None)
        if update:
            await self._sync_call_state(update)
    
    async def _sync_call_state(self, update: Dict):
        """Sync call state to Kamailio."""
        try:
            # Update dialog state in Kamailio
            if update.get("sip_call_id"):
                await self._send_kamailio_request("dlg.profile_set", [
                    update["sip_call_id"],
                    "call_state",
                    update["state"]
                ])
                
                await self._send_kamailio_request("dlg.profile_set", [
                    update["sip_call_id"],
                    "last_update",
                    update["timestamp"]
                ])
                
        except Exception as e:
            logger.error(f"Error syncing call state: {e}")
    
    async def _send_kamailio_request(self, method: str, params: List = None) -> Optional[Dict]:
        """Send RPC request to Kamailio."""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": method,
                "params": params or []
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.kamailio_rpc_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.warning(f"Kamailio RPC failed: HTTP {response.status}")
                        
        except Exception as e:
            logger.error(f"Kamailio RPC error: {e}")
        
        return None
    
    def _map_to_kamailio_state(self, call_state: CallState) -> Optional[str]:
        """Map CallState to Kamailio dialog state."""
        mapping = {
            CallState.INITIALIZING: "early",
            CallState.RINGING: "early", 
            CallState.CONNECTING: "early",
            CallState.CONNECTED: "confirmed",
            CallState.ON_HOLD: "confirmed",
            CallState.TRANSFERRING: "confirmed",
            CallState.RECORDING: "confirmed",
            CallState.COMPLETED: "terminated",
            CallState.FAILED: "terminated",
            CallState.CANCELLED: "terminated",
            CallState.BUSY: "terminated",
            CallState.NO_ANSWER: "terminated"
        }
        return mapping.get(call_state)


class CallManager:
    """Main call management system."""
    
    def __init__(self, max_concurrent_calls: int = 1000, ai_websocket_manager=None):
        self.max_concurrent_calls = max_concurrent_calls
        self.ai_websocket_manager = ai_websocket_manager
        
        # Core components
        self.active_calls: Dict[str, CallSession] = {}
        self.call_queues: Dict[str, CallQueue] = defaultdict(lambda: CallQueue())
        self.call_router = CallRouter()
        
        # State synchronization
        self.kamailio_sync = KamailioStateSynchronizer()
        
        # DTMF and Interactive Features
        self.dtmf_detector = DTMFDetector(enable_rfc2833=True, enable_inband=True)
        self.dtmf_processor = DTMFProcessor(ai_websocket_manager, self)
        self.music_on_hold = MusicOnHoldManager(self)
        self.ivr_manager = IVRManager(self, dtmf_processor=self.dtmf_processor)
        
        # SMS Management
        self.sms_manager = SMSManager(ai_websocket_manager=ai_websocket_manager)
        
        # Connect DTMF detector to processor
        self.dtmf_detector.add_event_handler(self._handle_dtmf_event)
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        
        # Statistics
        self.total_calls = 0
        self.completed_calls = 0
        self.failed_calls = 0
        self.start_time = time.time()
        
        # Call limits per number
        self.concurrent_limits: Dict[str, int] = {}
        self.number_call_counts: Dict[str, int] = defaultdict(int)
        
        # Running state
        self.is_running = False
    
    async def start(self):
        """Start the call manager and all sub-components."""
        if self.is_running:
            return
            
        self.is_running = True
        
        # Start synchronizer
        await self.kamailio_sync.start()
        
        # Start DTMF components
        await self.dtmf_processor.start()
        await self.music_on_hold.start()
        await self.ivr_manager.start()
        
        logger.info("Call manager started successfully")
    
    async def stop(self):
        """Stop the call manager and cleanup."""
        if not self.is_running:
            return
            
        self.is_running = False
        
        # Stop synchronizer
        await self.kamailio_sync.stop()
        
        # Stop DTMF components
        await self.dtmf_processor.stop()
        await self.music_on_hold.stop()
        await self.ivr_manager.stop()
        
        # Stop SMS manager
        await self.sms_manager.stop_processing()
        
        # Complete any active calls
        for call_session in list(self.active_calls.values()):
            await self.update_call_state(call_session.call_id, CallState.CANCELLED, 
                                        {"hangup_reason": "system_shutdown"})
        
        logger.info("Call manager stopped")
        
    async def handle_incoming_call(self, sip_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming SIP call."""
        try:
            # Extract call information
            call_id = sip_data.get("call_id", str(uuid.uuid4()))
            from_number = sip_data.get("from_number", "unknown")
            to_number = sip_data.get("to_number", "unknown")
            
            logger.info(f"Incoming call {call_id}: {from_number} -> {to_number}")
            
            # Create call session
            call_session = CallSession(
                call_id=call_id,
                session_id=str(uuid.uuid4()),
                direction=CallDirection.INBOUND,
                state=CallState.INITIALIZING,
                priority=self._determine_priority(sip_data),
                caller=CallParticipant(
                    number=from_number,
                    display_name=sip_data.get("caller_name"),
                    user_agent=sip_data.get("user_agent"),
                    ip_address=sip_data.get("remote_ip")
                ),
                callee=CallParticipant(
                    number=to_number,
                    is_registered=await self._is_number_registered(to_number)
                ),
                created_at=datetime.utcnow(),
                sip_call_id=sip_data.get("sip_call_id"),
                sip_headers=sip_data.get("headers", {})
            )
            
            # Check concurrent call limits
            if not self._check_concurrent_limits(call_session):
                await self._emit_event("call_rejected", call_session, "concurrent_limit_exceeded")
                return {"action": "reject", "code": 486, "reason": "Busy Here"}
            
            # Route the call
            routing_decision = self.call_router.route_call(call_session)
            
            if routing_decision["action"] == "reject":
                await self._emit_event("call_rejected", call_session, routing_decision["reason"])
                return {"action": "reject", "code": 403, "reason": "Forbidden"}
            
            elif routing_decision["action"] == "queue":
                return await self._queue_call(call_session, routing_decision)
            
            elif routing_decision["action"] == "forward":
                return await self._forward_call(call_session, routing_decision)
            
            else:
                return await self._accept_call(call_session)
                
        except Exception as e:
            logger.error(f"Error handling incoming call: {e}")
            return {"action": "reject", "code": 500, "reason": "Internal Server Error"}
    
    async def initiate_outbound_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Initiate outbound call."""
        try:
            call_id = str(uuid.uuid4())
            from_number = call_data["from_number"]
            to_number = call_data["to_number"]
            
            logger.info(f"Initiating outbound call {call_id}: {from_number} -> {to_number}")
            
            # Create call session
            call_session = CallSession(
                call_id=call_id,
                session_id=str(uuid.uuid4()),
                direction=CallDirection.OUTBOUND,
                state=CallState.INITIALIZING,
                priority=CallPriority.NORMAL,
                caller=CallParticipant(
                    number=from_number,
                    display_name=call_data.get("caller_name"),
                    is_registered=await self._is_number_registered(from_number)
                ),
                callee=CallParticipant(
                    number=to_number,
                    display_name=call_data.get("callee_name")
                ),
                created_at=datetime.utcnow(),
                custom_data=call_data.get("custom_data", {})
            )
            
            # Check if we can make the call
            if not self._check_concurrent_limits(call_session):
                return {"success": False, "error": "Concurrent call limit exceeded"}
            
            # Register call
            self.active_calls[call_id] = call_session
            self.total_calls += 1
            self.number_call_counts[from_number] += 1
            
            # Emit event
            await self._emit_event("call_initiated", call_session)
            
            # Return call information for SIP layer
            return {
                "success": True,
                "call_id": call_id,
                "session_id": call_session.session_id,
                "from_number": from_number,
                "to_number": to_number,
                "sip_headers": self._generate_sip_headers(call_session)
            }
            
        except Exception as e:
            logger.error(f"Error initiating outbound call: {e}")
            return {"success": False, "error": str(e)}
    
    async def update_call_state(self, call_id: str, new_state: CallState, 
                               metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Update call state."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            logger.warning(f"Attempted to update unknown call {call_id}")
            return False
        
        old_state = call_session.state
        call_session.state = new_state
        
        # Update timing based on state
        now = datetime.utcnow()
        if new_state == CallState.RINGING and not call_session.ring_start:
            call_session.ring_start = now
        elif new_state == CallState.CONNECTED and not call_session.connect_time:
            call_session.connect_time = now
        elif new_state in [CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED]:
            call_session.end_time = now
        
        # Update metadata
        if metadata:
            call_session.custom_data.update(metadata)
        
        logger.info(f"Call {call_id} state: {old_state.value} -> {new_state.value}")
        
        # Synchronize with Kamailio
        await self.kamailio_sync.notify_state_change(call_session, old_state, new_state)
        
        # Emit state change event
        await self._emit_event("call_state_changed", call_session, old_state, new_state)
        
        # Handle terminal states
        if new_state in [CallState.COMPLETED, CallState.FAILED, CallState.CANCELLED]:
            await self._complete_call(call_session)
        
        return True
    
    async def transfer_call(self, call_id: str, target_number: str, 
                           transfer_type: str = "blind") -> bool:
        """Transfer call to another number."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            return False
        
        if call_session.state != CallState.CONNECTED:
            logger.warning(f"Cannot transfer call {call_id} in state {call_session.state}")
            return False
        
        logger.info(f"Transferring call {call_id} to {target_number} ({transfer_type})")
        
        call_session.state = CallState.TRANSFERRING
        call_session.transfer_target = target_number
        
        await self._emit_event("call_transfer_initiated", call_session, target_number, transfer_type)
        
        return True
    
    async def hold_call(self, call_id: str, enable_music: bool = True, 
                       music_source: Optional[str] = None) -> bool:
        """Put call on hold with optional music."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            return False
        
        if call_session.state != CallState.CONNECTED:
            return False
        
        call_session.state = CallState.ON_HOLD
        call_session.is_on_hold = True
        
        # Start music on hold if enabled
        if enable_music:
            await self.music_on_hold.start_hold_music(call_id, music_source)
        
        logger.info(f"Call {call_id} placed on hold (music: {enable_music})")
        await self._emit_event("call_held", call_session)
        
        return True
    
    async def resume_call(self, call_id: str) -> bool:
        """Resume call from hold."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            return False
        
        if call_session.state != CallState.ON_HOLD:
            return False
        
        call_session.state = CallState.CONNECTED
        call_session.is_on_hold = False
        
        # Stop music on hold
        await self.music_on_hold.stop_hold_music(call_id)
        
        logger.info(f"Call {call_id} resumed from hold")
        await self._emit_event("call_resumed", call_session)
        
        return True
    
    async def start_recording(self, call_id: str, recording_params: Dict[str, Any]) -> bool:
        """Start call recording."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            return False
        
        if call_session.state not in [CallState.CONNECTED, CallState.ON_HOLD]:
            return False
        
        recording_url = recording_params.get("url", f"/recordings/{call_id}.wav")
        call_session.recording_url = recording_url
        call_session.is_recording = True
        
        logger.info(f"Started recording call {call_id} to {recording_url}")
        await self._emit_event("recording_started", call_session, recording_params)
        
        return True
    
    async def stop_recording(self, call_id: str) -> bool:
        """Stop call recording."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            return False
        
        if not call_session.is_recording:
            return False
        
        call_session.is_recording = False
        
        logger.info(f"Stopped recording call {call_id}")
        await self._emit_event("recording_stopped", call_session)
        
        return True
    
    async def hangup_call(self, call_id: str, reason: str = "normal") -> bool:
        """Hang up call."""
        call_session = self.active_calls.get(call_id)
        if not call_session:
            return False
        
        logger.info(f"Hanging up call {call_id}: {reason}")
        
        # Cleanup DTMF and interactive features
        await self._cleanup_call_features(call_id)
        
        if reason == "normal":
            await self.update_call_state(call_id, CallState.COMPLETED)
        else:
            await self.update_call_state(call_id, CallState.FAILED, {"hangup_reason": reason})
        
        return True
    
    # DTMF and Interactive Features Methods
    
    async def process_dtmf_rtp(self, call_id: str, rtp_payload: bytes) -> Optional[DTMFEvent]:
        """Process RTP packet for DTMF detection."""
        return await self.dtmf_detector.process_rtp_packet(call_id, rtp_payload)
    
    async def process_dtmf_audio(self, call_id: str, audio_data: bytes) -> Optional[DTMFEvent]:
        """Process audio data for in-band DTMF detection."""
        return await self.dtmf_detector.process_audio_data(call_id, audio_data)
    
    async def process_dtmf_sip_info(self, call_id: str, dtmf_digit: str) -> DTMFEvent:
        """Process DTMF from SIP INFO method."""
        return await self.dtmf_detector.process_sip_info(call_id, dtmf_digit)
    
    async def start_ivr_session(self, call_id: str, menu_id: Optional[str] = None) -> bool:
        """Start IVR session for call."""
        return await self.ivr_manager.start_ivr_session(call_id, menu_id)
    
    async def end_ivr_session(self, call_id: str, reason: str = "normal") -> bool:
        """End IVR session for call."""
        return await self.ivr_manager.end_ivr_session(call_id, reason)
    
    async def start_music_on_hold(self, call_id: str, source_name: Optional[str] = None) -> bool:
        """Start music on hold for call."""
        return await self.music_on_hold.start_hold_music(call_id, source_name)
    
    async def stop_music_on_hold(self, call_id: str) -> bool:
        """Stop music on hold for call."""
        return await self.music_on_hold.stop_hold_music(call_id)
    
    async def _handle_dtmf_event(self, event: DTMFEvent):
        """Handle DTMF event from detector."""
        try:
            # Process through DTMF processor
            result = await self.dtmf_processor.process_dtmf_event(event)
            
            # Emit DTMF event for other handlers
            await self._emit_event("dtmf_detected", event, result)
            
        except Exception as e:
            logger.error(f"Error handling DTMF event: {e}")
    
    async def _cleanup_call_features(self, call_id: str):
        """Cleanup DTMF and interactive features for call."""
        try:
            # Cleanup DTMF detection
            self.dtmf_detector.cleanup_call(call_id)
            
            # End IVR session if active
            await self.ivr_manager.end_ivr_session(call_id, "call_ended")
            
            # Stop music on hold if active
            await self.music_on_hold.stop_hold_music(call_id)
            
        except Exception as e:
            logger.error(f"Error cleaning up call features for {call_id}: {e}")
    
    def get_call_session(self, call_id: str) -> Optional[CallSession]:
        """Get call session by ID."""
        return self.active_calls.get(call_id)
    
    def get_active_calls(self, number: Optional[str] = None) -> List[CallSession]:
        """Get active calls, optionally filtered by number."""
        calls = list(self.active_calls.values())
        
        if number:
            calls = [
                call for call in calls
                if call.caller.number == number or call.callee.number == number
            ]
        
        return calls
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get call statistics."""
        uptime = time.time() - self.start_time
        active_count = len(self.active_calls)
        
        return {
            "uptime_seconds": int(uptime),
            "total_calls": self.total_calls,
            "active_calls": active_count,
            "completed_calls": self.completed_calls,
            "failed_calls": self.failed_calls,
            "success_rate": self.completed_calls / max(self.total_calls, 1),
            "concurrent_utilization": active_count / self.max_concurrent_calls,
            "calls_per_hour": self.total_calls / max(uptime / 3600, 1),
            "average_call_duration": self._calculate_average_duration(),
            "queue_stats": {
                name: queue.get_stats() 
                for name, queue in self.call_queues.items()
            },
            "dtmf_stats": self.dtmf_detector.get_statistics(),
            "dtmf_processor_stats": self.dtmf_processor.get_statistics(),
            "music_on_hold_stats": self.music_on_hold.get_statistics(),
            "ivr_stats": self.ivr_manager.get_statistics()
        }
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """Add event handler."""
        self.event_handlers[event_type].append(handler)
    
    def remove_event_handler(self, event_type: str, handler: Callable):
        """Remove event handler."""
        if handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
    
    async def _accept_call(self, call_session: CallSession) -> Dict[str, Any]:
        """Accept incoming call."""
        # Register call
        self.active_calls[call_session.call_id] = call_session
        self.total_calls += 1
        self.number_call_counts[call_session.caller.number] += 1
        
        # Update state
        call_session.state = CallState.RINGING
        call_session.ring_start = datetime.utcnow()
        
        # Notify Kamailio about call creation
        await self.kamailio_sync.notify_call_creation(call_session)
        
        await self._emit_event("call_accepted", call_session)
        
        return {
            "action": "accept",
            "call_id": call_session.call_id,
            "session_id": call_session.session_id,
            "ringing_timeout": 30
        }
    
    async def _queue_call(self, call_session: CallSession, routing: Dict[str, Any]) -> Dict[str, Any]:
        """Queue incoming call."""
        queue_name = routing.get("queue_name", "default")
        priority_str = routing.get("priority", "normal")
        
        # Set priority
        priority_map = {
            "low": CallPriority.LOW,
            "normal": CallPriority.NORMAL,
            "high": CallPriority.HIGH,
            "emergency": CallPriority.EMERGENCY
        }
        call_session.priority = priority_map.get(priority_str, CallPriority.NORMAL)
        
        # Add to queue
        queue = self.call_queues[queue_name]
        if queue.add_call(call_session):
            await self._emit_event("call_queued", call_session, queue_name)
            return {
                "action": "queue",
                "queue_name": queue_name,
                "position": queue.get_position(call_session.call_id),
                "estimated_wait": queue._calculate_average_wait_time()
            }
        else:
            return {"action": "reject", "code": 486, "reason": "Queue Full"}
    
    async def _forward_call(self, call_session: CallSession, routing: Dict[str, Any]) -> Dict[str, Any]:
        """Forward call to another number."""
        target = routing["target"]
        timeout = routing.get("timeout", 30)
        
        call_session.state = CallState.FORWARDING
        call_session.forward_target = target
        
        await self._emit_event("call_forwarded", call_session, target)
        
        return {
            "action": "forward",
            "target": target,
            "timeout": timeout,
            "call_id": call_session.call_id
        }
    
    async def _complete_call(self, call_session: CallSession):
        """Complete call and cleanup."""
        # Update statistics
        if call_session.state == CallState.COMPLETED:
            self.completed_calls += 1
        else:
            self.failed_calls += 1
        
        # Decrement concurrent counts
        caller_number = call_session.caller.number
        if self.number_call_counts[caller_number] > 0:
            self.number_call_counts[caller_number] -= 1
        
        # Notify Kamailio about call completion  
        await self.kamailio_sync.notify_call_completion(call_session)
        
        # Emit completion event
        await self._emit_event("call_completed", call_session)
        
        # Remove from active calls after delay (for cleanup)
        asyncio.create_task(self._delayed_cleanup(call_session.call_id))
    
    async def _delayed_cleanup(self, call_id: str, delay: int = 60):
        """Remove call from active calls after delay."""
        await asyncio.sleep(delay)
        self.active_calls.pop(call_id, None)
    
    def _check_concurrent_limits(self, call_session: CallSession) -> bool:
        """Check if call is within concurrent limits."""
        # Global limit
        if len(self.active_calls) >= self.max_concurrent_calls:
            return False
        
        # Per-number limit
        caller_number = call_session.caller.number
        limit = self.concurrent_limits.get(caller_number, 10)  # Default limit
        current_count = self.number_call_counts[caller_number]
        
        return current_count < limit
    
    def _determine_priority(self, sip_data: Dict[str, Any]) -> CallPriority:
        """Determine call priority from SIP data."""
        # Check headers for priority indicators
        headers = sip_data.get("headers", {})
        
        if "X-Priority" in headers:
            priority_map = {"1": CallPriority.LOW, "2": CallPriority.NORMAL, 
                           "3": CallPriority.HIGH, "4": CallPriority.EMERGENCY}
            return priority_map.get(headers["X-Priority"], CallPriority.NORMAL)
        
        # Check for emergency numbers
        from_number = sip_data.get("from_number", "")
        if from_number.startswith("911") or from_number.startswith("112"):
            return CallPriority.EMERGENCY
        
        return CallPriority.NORMAL
    
    async def _is_number_registered(self, number: str) -> bool:
        """Check if number is registered."""
        # This would integrate with your registration system
        # For now, return True as placeholder
        return True
    
    def _generate_sip_headers(self, call_session: CallSession) -> Dict[str, str]:
        """Generate SIP headers for call."""
        headers = {
            "X-Call-ID": call_session.call_id,
            "X-Session-ID": call_session.session_id,
            "X-Direction": call_session.direction.value,
            "X-Priority": str(call_session.priority.value)
        }
        
        # Add custom headers
        headers.update(call_session.custom_data.get("sip_headers", {}))
        
        return headers
    
    def _calculate_average_duration(self) -> float:
        """Calculate average call duration."""
        completed_calls = [
            call for call in self.active_calls.values()
            if call.state == CallState.COMPLETED and call.duration()
        ]
        
        if not completed_calls:
            return 0.0
        
        total_duration = sum(call.duration() for call in completed_calls)
        return total_duration / len(completed_calls)
    
    async def _emit_event(self, event_type: str, *args, **kwargs):
        """Emit event to registered handlers."""
        handlers = self.event_handlers.get(event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")
    
    async def cleanup(self):
        """Cleanup call manager and all subsystems."""
        try:
            logger.info("Cleaning up call manager...")
            
            # End all active calls
            for call_id in list(self.active_calls.keys()):
                await self.hangup_call(call_id, "system_shutdown")
            
            # Cleanup subsystems
            await self.dtmf_processor.cleanup()
            await self.music_on_hold.cleanup()
            await self.ivr_manager.cleanup()
            
            logger.info("Call manager cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during call manager cleanup: {e}")
    
    def load_configuration(self, config: Dict[str, Any]):
        """Load configuration for DTMF and interactive features."""
        try:
            # Load DTMF patterns
            if "dtmf_patterns" in config:
                self.dtmf_processor.load_patterns_from_config(config["dtmf_patterns"])
            
            # Load music sources
            if "music_sources" in config:
                self.music_on_hold.load_sources_from_config(config["music_sources"])
            
            # Load IVR menus
            if "ivr_menus" in config:
                self.ivr_manager.load_menus_from_config(config["ivr_menus"])
            
            logger.info("Loaded call manager configuration")
            
        except Exception as e:
            logger.error(f"Error loading call manager configuration: {e}")
            raise