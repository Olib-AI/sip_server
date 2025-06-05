"""DTMF Processing and Pattern Matching with AI Integration."""
import asyncio
import json
import logging
import re
import time
from typing import Dict, List, Optional, Callable, Any, Pattern
from dataclasses import dataclass, field
from enum import Enum
from collections import deque, defaultdict

from .dtmf_detector import DTMFEvent, DTMFMethod

logger = logging.getLogger(__name__)


class DTMFAction(Enum):
    """DTMF action types."""
    FORWARD_TO_AI = "forward_to_ai"
    TRANSFER_CALL = "transfer_call"
    PLAY_AUDIO = "play_audio"
    HANGUP_CALL = "hangup_call"
    TOGGLE_RECORDING = "toggle_recording"
    ENTER_IVR = "enter_ivr"
    CUSTOM_HANDLER = "custom_handler"


@dataclass
class DTMFPattern:
    """DTMF pattern configuration."""
    pattern: str  # Regex pattern for DTMF sequence
    action: DTMFAction
    timeout_seconds: float = 5.0
    description: str = ""
    
    # Action parameters
    transfer_target: Optional[str] = None
    audio_file: Optional[str] = None
    ivr_menu_id: Optional[str] = None
    custom_handler: Optional[str] = None
    ai_context: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Compile regex pattern."""
        try:
            self.compiled_pattern: Pattern = re.compile(self.pattern)
        except re.error as e:
            logger.error(f"Invalid DTMF pattern '{self.pattern}': {e}")
            raise


@dataclass
class DTMFSequence:
    """Active DTMF sequence for a call."""
    call_id: str
    digits: str = ""
    last_digit_time: float = 0.0
    start_time: float = 0.0
    events: List[DTMFEvent] = field(default_factory=list)
    
    def add_digit(self, event: DTMFEvent):
        """Add digit to sequence."""
        if not self.digits:
            self.start_time = event.timestamp
        
        self.digits += event.digit
        self.last_digit_time = event.timestamp
        self.events.append(event)
    
    def is_expired(self, timeout: float) -> bool:
        """Check if sequence has expired."""
        return (time.time() - self.last_digit_time) > timeout
    
    def duration(self) -> float:
        """Get sequence duration in seconds."""
        if self.start_time > 0:
            return self.last_digit_time - self.start_time
        return 0.0


class DTMFProcessor:
    """Main DTMF processor with pattern matching and AI integration."""
    
    def __init__(self, ai_websocket_manager=None, call_manager=None):
        self.ai_websocket_manager = ai_websocket_manager
        self.call_manager = call_manager
        
        # Pattern management
        self.patterns: List[DTMFPattern] = []
        self.active_sequences: Dict[str, DTMFSequence] = {}
        
        # Configuration
        self.default_timeout = 5.0
        self.max_sequence_length = 20
        self.cleanup_interval = 30.0
        
        # Statistics
        self.total_sequences = 0
        self.matched_patterns = 0
        self.forwarded_to_ai = 0
        
        # Custom handlers
        self.custom_handlers: Dict[str, Callable] = {}
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_sequences())
        
    def add_pattern(self, pattern: DTMFPattern):
        """Add DTMF pattern."""
        self.patterns.append(pattern)
        # Sort by pattern length (longer patterns first for better matching)
        self.patterns.sort(key=lambda p: len(p.pattern), reverse=True)
        
        logger.info(f"Added DTMF pattern: {pattern.pattern} -> {pattern.action.value}")
    
    def remove_pattern(self, pattern_str: str) -> bool:
        """Remove DTMF pattern."""
        for i, pattern in enumerate(self.patterns):
            if pattern.pattern == pattern_str:
                del self.patterns[i]
                logger.info(f"Removed DTMF pattern: {pattern_str}")
                return True
        return False
    
    def add_custom_handler(self, name: str, handler: Callable):
        """Add custom DTMF handler."""
        self.custom_handlers[name] = handler
        logger.info(f"Added custom DTMF handler: {name}")
    
    async def process_dtmf_event(self, event: DTMFEvent) -> Optional[Dict[str, Any]]:
        """Process incoming DTMF event."""
        try:
            call_id = event.call_id
            
            # Get or create sequence for call
            if call_id not in self.active_sequences:
                self.active_sequences[call_id] = DTMFSequence(call_id=call_id)
                self.total_sequences += 1
            
            sequence = self.active_sequences[call_id]
            sequence.add_digit(event)
            
            logger.debug(f"DTMF sequence for {call_id}: '{sequence.digits}'")
            
            # Check for pattern matches
            matched_pattern = self._find_matching_pattern(sequence.digits)
            
            if matched_pattern:
                logger.info(f"DTMF pattern matched: {matched_pattern.pattern} for call {call_id}")
                result = await self._execute_pattern_action(call_id, sequence, matched_pattern)
                
                # Clear sequence after match
                self._clear_sequence(call_id)
                self.matched_patterns += 1
                
                return result
            
            # Check sequence length limit
            if len(sequence.digits) >= self.max_sequence_length:
                logger.warning(f"DTMF sequence too long for {call_id}, clearing")
                self._clear_sequence(call_id)
            
            # Forward individual digit to AI if no pattern matched
            await self._forward_digit_to_ai(event)
            
            return None
            
        except Exception as e:
            logger.error(f"Error processing DTMF event: {e}")
            return {"error": str(e)}
    
    def _find_matching_pattern(self, digits: str) -> Optional[DTMFPattern]:
        """Find matching pattern for digit sequence."""
        for pattern in self.patterns:
            try:
                if pattern.compiled_pattern.match(digits):
                    return pattern
            except Exception as e:
                logger.error(f"Error matching pattern {pattern.pattern}: {e}")
        
        return None
    
    async def _execute_pattern_action(self, call_id: str, sequence: DTMFSequence, 
                                    pattern: DTMFPattern) -> Dict[str, Any]:
        """Execute action for matched pattern."""
        try:
            action = pattern.action
            
            if action == DTMFAction.FORWARD_TO_AI:
                return await self._forward_sequence_to_ai(call_id, sequence, pattern)
            
            elif action == DTMFAction.TRANSFER_CALL:
                return await self._transfer_call(call_id, pattern.transfer_target)
            
            elif action == DTMFAction.PLAY_AUDIO:
                return await self._play_audio(call_id, pattern.audio_file)
            
            elif action == DTMFAction.HANGUP_CALL:
                return await self._hangup_call(call_id)
            
            elif action == DTMFAction.TOGGLE_RECORDING:
                return await self._toggle_recording(call_id)
            
            elif action == DTMFAction.ENTER_IVR:
                return await self._enter_ivr(call_id, pattern.ivr_menu_id)
            
            elif action == DTMFAction.CUSTOM_HANDLER:
                return await self._execute_custom_handler(call_id, sequence, pattern)
            
            else:
                logger.warning(f"Unknown DTMF action: {action}")
                return {"error": f"Unknown action: {action}"}
                
        except Exception as e:
            logger.error(f"Error executing DTMF action {action}: {e}")
            return {"error": str(e)}
    
    async def _forward_sequence_to_ai(self, call_id: str, sequence: DTMFSequence, 
                                    pattern: DTMFPattern) -> Dict[str, Any]:
        """Forward DTMF sequence to AI platform."""
        try:
            if not self.ai_websocket_manager:
                return {"error": "AI WebSocket manager not available"}
            
            # Prepare message for AI
            ai_message = {
                "type": "dtmf_sequence",
                "call_id": call_id,
                "sequence": sequence.digits,
                "pattern_matched": pattern.pattern,
                "duration_seconds": sequence.duration(),
                "event_count": len(sequence.events),
                "context": pattern.ai_context,
                "timestamp": time.time()
            }
            
            # Send to AI platform
            success = await self.ai_websocket_manager.send_message(call_id, ai_message)
            
            if success:
                self.forwarded_to_ai += 1
                logger.info(f"Forwarded DTMF sequence '{sequence.digits}' to AI for call {call_id}")
                return {"success": True, "action": "forwarded_to_ai", "sequence": sequence.digits}
            else:
                return {"error": "Failed to forward to AI"}
                
        except Exception as e:
            logger.error(f"Error forwarding DTMF to AI: {e}")
            return {"error": str(e)}
    
    async def _forward_digit_to_ai(self, event: DTMFEvent):
        """Forward individual DTMF digit to AI."""
        try:
            if not self.ai_websocket_manager:
                return
            
            # Prepare message for AI
            ai_message = {
                "type": "dtmf_digit",
                "call_id": event.call_id,
                "digit": event.digit,
                "method": event.method.value,
                "timestamp": event.timestamp,
                "duration_ms": event.duration_ms,
                "confidence": event.confidence
            }
            
            # Send to AI platform
            await self.ai_websocket_manager.send_message(event.call_id, ai_message)
            
            logger.debug(f"Forwarded DTMF digit '{event.digit}' to AI for call {event.call_id}")
            
        except Exception as e:
            logger.error(f"Error forwarding DTMF digit to AI: {e}")
    
    async def _transfer_call(self, call_id: str, target: str) -> Dict[str, Any]:
        """Transfer call to target number."""
        try:
            if not self.call_manager:
                return {"error": "Call manager not available"}
            
            success = await self.call_manager.transfer_call(call_id, target, "blind")
            
            if success:
                logger.info(f"Transferred call {call_id} to {target}")
                return {"success": True, "action": "call_transferred", "target": target}
            else:
                return {"error": "Transfer failed"}
                
        except Exception as e:
            logger.error(f"Error transferring call: {e}")
            return {"error": str(e)}
    
    async def _play_audio(self, call_id: str, audio_file: str) -> Dict[str, Any]:
        """Play audio file to call."""
        try:
            # This would integrate with audio playback system
            logger.info(f"Playing audio file '{audio_file}' to call {call_id}")
            return {"success": True, "action": "audio_played", "file": audio_file}
            
        except Exception as e:
            logger.error(f"Error playing audio: {e}")
            return {"error": str(e)}
    
    async def _hangup_call(self, call_id: str) -> Dict[str, Any]:
        """Hang up call."""
        try:
            if not self.call_manager:
                return {"error": "Call manager not available"}
            
            success = await self.call_manager.hangup_call(call_id, "dtmf_hangup")
            
            if success:
                logger.info(f"Hung up call {call_id} due to DTMF")
                return {"success": True, "action": "call_hung_up"}
            else:
                return {"error": "Hangup failed"}
                
        except Exception as e:
            logger.error(f"Error hanging up call: {e}")
            return {"error": str(e)}
    
    async def _toggle_recording(self, call_id: str) -> Dict[str, Any]:
        """Toggle call recording."""
        try:
            if not self.call_manager:
                return {"error": "Call manager not available"}
            
            call_session = self.call_manager.get_call_session(call_id)
            if not call_session:
                return {"error": "Call not found"}
            
            if call_session.is_recording:
                success = await self.call_manager.stop_recording(call_id)
                action = "recording_stopped"
            else:
                success = await self.call_manager.start_recording(call_id, {})
                action = "recording_started"
            
            if success:
                logger.info(f"Toggled recording for call {call_id}: {action}")
                return {"success": True, "action": action}
            else:
                return {"error": "Recording toggle failed"}
                
        except Exception as e:
            logger.error(f"Error toggling recording: {e}")
            return {"error": str(e)}
    
    async def _enter_ivr(self, call_id: str, ivr_menu_id: str) -> Dict[str, Any]:
        """Enter IVR menu."""
        try:
            # This would integrate with IVR system
            logger.info(f"Entering IVR menu '{ivr_menu_id}' for call {call_id}")
            return {"success": True, "action": "entered_ivr", "menu_id": ivr_menu_id}
            
        except Exception as e:
            logger.error(f"Error entering IVR: {e}")
            return {"error": str(e)}
    
    async def _execute_custom_handler(self, call_id: str, sequence: DTMFSequence, 
                                    pattern: DTMFPattern) -> Dict[str, Any]:
        """Execute custom handler."""
        try:
            handler_name = pattern.custom_handler
            if not handler_name or handler_name not in self.custom_handlers:
                return {"error": f"Custom handler '{handler_name}' not found"}
            
            handler = self.custom_handlers[handler_name]
            
            # Execute handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(call_id, sequence, pattern)
            else:
                result = handler(call_id, sequence, pattern)
            
            logger.info(f"Executed custom DTMF handler '{handler_name}' for call {call_id}")
            return {"success": True, "action": "custom_handler_executed", "result": result}
            
        except Exception as e:
            logger.error(f"Error executing custom handler: {e}")
            return {"error": str(e)}
    
    def _clear_sequence(self, call_id: str):
        """Clear DTMF sequence for call."""
        self.active_sequences.pop(call_id, None)
    
    async def _cleanup_expired_sequences(self):
        """Cleanup expired DTMF sequences."""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                current_time = time.time()
                expired_calls = []
                
                for call_id, sequence in self.active_sequences.items():
                    if sequence.is_expired(self.default_timeout):
                        expired_calls.append(call_id)
                
                for call_id in expired_calls:
                    logger.debug(f"Cleaning up expired DTMF sequence for call {call_id}")
                    self._clear_sequence(call_id)
                    
            except Exception as e:
                logger.error(f"Error in DTMF cleanup task: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get DTMF processor statistics."""
        return {
            "total_sequences": self.total_sequences,
            "active_sequences": len(self.active_sequences),
            "matched_patterns": self.matched_patterns,
            "forwarded_to_ai": self.forwarded_to_ai,
            "configured_patterns": len(self.patterns),
            "custom_handlers": len(self.custom_handlers)
        }
    
    def get_active_sequences(self) -> Dict[str, Dict[str, Any]]:
        """Get active DTMF sequences."""
        return {
            call_id: {
                "digits": seq.digits,
                "start_time": seq.start_time,
                "last_digit_time": seq.last_digit_time,
                "event_count": len(seq.events),
                "duration": seq.duration()
            }
            for call_id, seq in self.active_sequences.items()
        }
    
    def load_patterns_from_config(self, config: List[Dict[str, Any]]):
        """Load DTMF patterns from configuration."""
        try:
            for pattern_config in config:
                pattern = DTMFPattern(
                    pattern=pattern_config["pattern"],
                    action=DTMFAction(pattern_config["action"]),
                    timeout_seconds=pattern_config.get("timeout_seconds", 5.0),
                    description=pattern_config.get("description", ""),
                    transfer_target=pattern_config.get("transfer_target"),
                    audio_file=pattern_config.get("audio_file"),
                    ivr_menu_id=pattern_config.get("ivr_menu_id"),
                    custom_handler=pattern_config.get("custom_handler"),
                    ai_context=pattern_config.get("ai_context", {})
                )
                self.add_pattern(pattern)
                
            logger.info(f"Loaded {len(config)} DTMF patterns from configuration")
            
        except Exception as e:
            logger.error(f"Error loading DTMF patterns: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup processor resources."""
        try:
            if hasattr(self, '_cleanup_task'):
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            self.active_sequences.clear()
            logger.info("DTMF processor cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up DTMF processor: {e}")