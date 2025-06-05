"""WebSocket integration for connecting call manager to AI platform."""
import asyncio
import websockets
import json
import logging
from typing import Dict, Any, Optional, Set, Callable
from datetime import datetime
import time
import uuid

from .call_manager import CallManager, CallSession, CallState, CallDirection
from ..audio.rtp import RTPManager
from ..audio.codecs import AudioProcessor
from ..utils.config import get_config
from ..utils.auth import WebSocketAuthenticator

logger = logging.getLogger(__name__)


class WebSocketCallBridge:
    """Bridge between SIP call manager and AI platform WebSocket."""
    
    def __init__(self, call_manager: CallManager, ai_websocket_url: Optional[str] = None, port: Optional[int] = None):
        config = get_config()
        self.call_manager = call_manager
        self.ai_websocket_url = ai_websocket_url or config.websocket.ai_platform_url
        self.port = port or config.websocket.port
        self.rtp_manager = RTPManager((config.audio.rtp_port_start, config.audio.rtp_port_end))
        self.audio_processor = AudioProcessor()
        self.authenticator = WebSocketAuthenticator()
        
        # Active WebSocket connections per call
        self.active_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.call_to_conversation: Dict[str, str] = {}  # call_id -> conversation_id
        self.conversation_to_call: Dict[str, str] = {}  # conversation_id -> call_id
        self.connection_auth: Dict[str, Dict] = {}  # connection_id -> user_info
        
        # Message handlers
        self.message_handlers: Dict[str, Callable] = {
            "auth": self._handle_auth_message,
            "audio": self._handle_audio_message,
            "call_control": self._handle_call_control,
            "dtmf": self._handle_dtmf_message,
            "status": self._handle_status_message,
            "conversation_end": self._handle_conversation_end
        }
        
        # Register call manager events
        self._register_call_events()
        
        # Connection state
        self.is_running = False
        self.reconnect_delay = 5
        self.max_reconnect_attempts = 10
        
    async def start(self):
        """Start the WebSocket bridge."""
        self.is_running = True
        logger.info("Starting WebSocket call bridge")
        
        # Start WebSocket server for AI platform
        await self._start_websocket_server()
        
    async def stop(self):
        """Stop the WebSocket bridge."""
        self.is_running = False
        logger.info("Stopping WebSocket call bridge")
        
        # Close all connections
        for connection in self.active_connections.values():
            await connection.close()
        
        # Cleanup RTP sessions
        await self.rtp_manager.cleanup_all()
        
    async def _start_websocket_server(self):
        """Start WebSocket server for AI platform connections."""
        try:
            # WebSocket server handler
            async def websocket_handler(websocket, path):
                try:
                    logger.info(f"New WebSocket connection from {websocket.remote_address}")
                    await self._handle_websocket_connection(websocket)
                except Exception as e:
                    logger.error(f"WebSocket connection error: {e}")
                finally:
                    # Cleanup connection
                    await self._cleanup_websocket_connection(websocket)
            
            # Start server on configured port
            server = await websockets.serve(
                websocket_handler,
                "0.0.0.0",
                self.port,
                subprotocols=["sip-bridge"],
                compression=None  # Disable compression for real-time audio
            )
            
            logger.info(f"WebSocket server started on port {self.port}")
            return server
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            raise
    
    async def _handle_websocket_connection(self, websocket):
        """Handle incoming WebSocket connection."""
        conversation_id = None
        call_id = None
        connection_id = str(uuid.uuid4())
        is_authenticated = False
        
        try:
            async for message in websocket:
                data = json.loads(message)
                message_type = data.get("type")
                
                # Require authentication first
                if not is_authenticated and message_type != "auth":
                    await self._send_message(websocket, {
                        "type": "error",
                        "error": "authentication_required",
                        "message": "Please authenticate first"
                    })
                    continue
                
                # Handle authentication
                if message_type == "auth":
                    try:
                        token = data.get("token")
                        user_info = self.authenticator.verify_websocket_token(token)
                        self.connection_auth[connection_id] = user_info
                        is_authenticated = True
                        
                        await self._send_message(websocket, {
                            "type": "auth_success",
                            "user_id": user_info.get("user_id"),
                            "username": user_info.get("username")
                        })
                        logger.info(f"WebSocket authenticated: {user_info.get('username')}")
                        continue
                        
                    except ValueError as e:
                        await self._send_message(websocket, {
                            "type": "auth_error",
                            "error": str(e)
                        })
                        await websocket.close()
                        return
                
                # Handle connection setup
                elif message_type == "connection_init":
                    conversation_id = data.get("conversation_id")
                    call_id = data.get("call_id")
                    
                    if conversation_id and call_id:
                        # Verify user has permission for this call
                        user_info = self.connection_auth.get(connection_id)
                        if not self.authenticator.verify_call_permissions(user_info, call_id):
                            await self._send_message(websocket, {
                                "type": "error",
                                "error": "permission_denied",
                                "message": "No permission for this call"
                            })
                            continue
                        
                        self.active_connections[call_id] = websocket
                        self.call_to_conversation[call_id] = conversation_id
                        self.conversation_to_call[conversation_id] = call_id
                        
                        logger.info(f"WebSocket connected for call {call_id}, conversation {conversation_id}")
                        
                        # Send connection acknowledgment
                        await self._send_message(websocket, {
                            "type": "connection_ack",
                            "call_id": call_id,
                            "conversation_id": conversation_id,
                            "status": "connected",
                            "user": user_info.get("username")
                        })
                        
                        # Start RTP session for this call
                        await self._setup_call_audio(call_id, websocket)
                
                # Handle other message types
                elif message_type in self.message_handlers:
                    handler = self.message_handlers[message_type]
                    await handler(websocket, data)
                else:
                    logger.warning(f"Unknown message type: {message_type}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"WebSocket connection closed for call {call_id}")
        except Exception as e:
            logger.error(f"Error in WebSocket handler: {e}")
        finally:
            # Clean up authentication info
            self.connection_auth.pop(connection_id, None)
    
    async def _cleanup_websocket_connection(self, websocket):
        """Clean up WebSocket connection."""
        # Find call_id for this connection
        call_id = None
        for cid, conn in self.active_connections.items():
            if conn == websocket:
                call_id = cid
                break
        
        if call_id:
            # Remove from tracking
            conversation_id = self.call_to_conversation.pop(call_id, None)
            if conversation_id:
                self.conversation_to_call.pop(conversation_id, None)
            self.active_connections.pop(call_id, None)
            
            # Cleanup RTP session
            await self.rtp_manager.destroy_session(call_id)
            
            # End call if still active
            call_session = self.call_manager.get_call_session(call_id)
            if call_session and call_session.state in [CallState.CONNECTED, CallState.RINGING]:
                await self.call_manager.hangup_call(call_id, "websocket_disconnected")
            
            logger.info(f"Cleaned up WebSocket connection for call {call_id}")
    
    async def _setup_call_audio(self, call_id: str, websocket):
        """Set up audio processing for call."""
        try:
            call_session = self.call_manager.get_call_session(call_id)
            if not call_session:
                return
            
            # Create RTP session
            rtp_session = await self.rtp_manager.create_session(
                call_id=call_id,
                remote_host="127.0.0.1",  # Will be updated with actual remote
                remote_port=0,  # Will be updated with actual port
                codec=call_session.codec
            )
            
            # Set up audio callback to forward to WebSocket
            async def audio_callback(audio_data: bytes):
                await self._forward_audio_to_websocket(call_id, audio_data)
            
            rtp_session.set_receive_callback(audio_callback)
            
            logger.info(f"Audio setup complete for call {call_id}")
            
        except Exception as e:
            logger.error(f"Failed to setup audio for call {call_id}: {e}")
    
    async def _forward_audio_to_websocket(self, call_id: str, audio_data: bytes):
        """Forward audio from RTP to WebSocket."""
        try:
            websocket = self.active_connections.get(call_id)
            if not websocket:
                return
            
            # Convert audio format if needed
            call_session = self.call_manager.get_call_session(call_id)
            if call_session:
                # Convert from SIP codec to PCM for AI platform
                pcm_data = self.audio_processor.convert_format(
                    audio_data, 
                    call_session.codec, 
                    "PCM"
                )
                
                # Send audio to AI platform
                await self._send_message(websocket, {
                    "type": "audio",
                    "call_id": call_id,
                    "audio_data": pcm_data.hex(),  # Hex encode for JSON
                    "format": "PCM",
                    "sample_rate": get_config().audio.sample_rate,
                    "channels": 1
                })
            
        except Exception as e:
            logger.error(f"Error forwarding audio for call {call_id}: {e}")
    
    async def _handle_auth_message(self, websocket, data: Dict[str, Any]):
        """Handle authentication messages - already handled in main loop."""
        # This is handled in the main connection loop
        pass
    
    async def _handle_audio_message(self, websocket, data: Dict[str, Any]):
        """Handle audio message from AI platform."""
        try:
            call_id = data.get("call_id")
            audio_hex = data.get("audio_data")
            
            if not call_id or not audio_hex:
                return
            
            # Decode audio data
            pcm_data = bytes.fromhex(audio_hex)
            
            # Get call session for codec info
            call_session = self.call_manager.get_call_session(call_id)
            if not call_session:
                return
            
            # Convert from PCM to SIP codec
            sip_audio = self.audio_processor.convert_format(
                pcm_data,
                "PCM",
                call_session.codec
            )
            
            # Send via RTP
            rtp_session = self.rtp_manager.get_session(call_id)
            if rtp_session:
                await rtp_session.send_audio(sip_audio)
            
        except Exception as e:
            logger.error(f"Error handling audio message: {e}")
    
    async def _handle_call_control(self, websocket, data: Dict[str, Any]):
        """Handle call control messages from AI platform."""
        try:
            call_id = data.get("call_id")
            action = data.get("action")
            
            if not call_id or not action:
                return
            
            if action == "hangup":
                await self.call_manager.hangup_call(call_id, "ai_platform_request")
            elif action == "hold":
                await self.call_manager.hold_call(call_id)
            elif action == "resume":
                await self.call_manager.resume_call(call_id)
            elif action == "transfer":
                target = data.get("target")
                if target:
                    await self.call_manager.transfer_call(call_id, target)
            elif action == "record_start":
                await self.call_manager.start_recording(call_id, data.get("params", {}))
            elif action == "record_stop":
                await self.call_manager.stop_recording(call_id)
            
            logger.info(f"Processed call control action {action} for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling call control: {e}")
    
    async def _handle_dtmf_message(self, websocket, data: Dict[str, Any]):
        """Handle DTMF messages from AI platform."""
        try:
            call_id = data.get("call_id")
            digit = data.get("digit")
            
            if call_id and digit:
                # Process DTMF through call manager
                dtmf_event = await self.call_manager.process_dtmf_sip_info(call_id, digit)
                logger.info(f"Processed DTMF {digit} for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error handling DTMF message: {e}")
    
    async def _handle_status_message(self, websocket, data: Dict[str, Any]):
        """Handle status request from AI platform."""
        try:
            call_id = data.get("call_id")
            
            if call_id:
                call_session = self.call_manager.get_call_session(call_id)
                if call_session:
                    await self._send_message(websocket, {
                        "type": "status_response",
                        "call_id": call_id,
                        "state": call_session.state.value,
                        "duration": call_session.duration(),
                        "is_recording": call_session.is_recording,
                        "is_on_hold": call_session.is_on_hold
                    })
            
        except Exception as e:
            logger.error(f"Error handling status message: {e}")
    
    async def _handle_conversation_end(self, websocket, data: Dict[str, Any]):
        """Handle conversation end from AI platform."""
        try:
            call_id = data.get("call_id")
            reason = data.get("reason", "conversation_ended")
            
            if call_id:
                await self.call_manager.hangup_call(call_id, reason)
                logger.info(f"Call {call_id} ended by AI platform: {reason}")
            
        except Exception as e:
            logger.error(f"Error handling conversation end: {e}")
    
    def _register_call_events(self):
        """Register event handlers with call manager."""
        # Register for call state changes
        self.call_manager.add_event_handler("call_state_changed", self._on_call_state_changed)
        self.call_manager.add_event_handler("call_accepted", self._on_call_accepted)
        self.call_manager.add_event_handler("call_completed", self._on_call_completed)
        self.call_manager.add_event_handler("dtmf_detected", self._on_dtmf_detected)
    
    async def _on_call_state_changed(self, call_session: CallSession, old_state, new_state):
        """Handle call state change events."""
        try:
            call_id = call_session.call_id
            websocket = self.active_connections.get(call_id)
            
            if websocket:
                await self._send_message(websocket, {
                    "type": "call_state_changed",
                    "call_id": call_id,
                    "old_state": old_state.value,
                    "new_state": new_state.value,
                    "timestamp": datetime.utcnow().isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error handling call state change event: {e}")
    
    async def _on_call_accepted(self, call_session: CallSession):
        """Handle call accepted events."""
        try:
            # Notify AI platform about new call
            # This would typically connect to AI platform's WebSocket
            logger.info(f"Call {call_session.call_id} accepted, waiting for AI platform connection")
            
        except Exception as e:
            logger.error(f"Error handling call accepted event: {e}")
    
    async def _on_call_completed(self, call_session: CallSession):
        """Handle call completed events."""
        try:
            call_id = call_session.call_id
            websocket = self.active_connections.get(call_id)
            
            if websocket:
                await self._send_message(websocket, {
                    "type": "call_completed",
                    "call_id": call_id,
                    "duration": call_session.duration(),
                    "end_reason": call_session.custom_data.get("hangup_reason", "normal"),
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Close WebSocket connection
                await websocket.close()
            
        except Exception as e:
            logger.error(f"Error handling call completed event: {e}")
    
    async def _on_dtmf_detected(self, dtmf_event, result):
        """Handle DTMF detected events."""
        try:
            call_id = dtmf_event.call_id
            websocket = self.active_connections.get(call_id)
            
            if websocket:
                await self._send_message(websocket, {
                    "type": "dtmf_detected",
                    "call_id": call_id,
                    "digit": dtmf_event.digit,
                    "detection_method": dtmf_event.detection_method,
                    "confidence": dtmf_event.confidence,
                    "timestamp": dtmf_event.timestamp.isoformat()
                })
            
        except Exception as e:
            logger.error(f"Error handling DTMF detected event: {e}")
    
    async def _send_message(self, websocket, message: Dict[str, Any]):
        """Send message to WebSocket connection."""
        try:
            message_json = json.dumps(message)
            await websocket.send(message_json)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
    
    # Public API for SIP server integration
    
    async def notify_incoming_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Notify about incoming call from SIP server."""
        try:
            # Process call through call manager
            result = await self.call_manager.handle_incoming_call(call_data)
            
            # Return result to SIP server
            return result
            
        except Exception as e:
            logger.error(f"Error processing incoming call notification: {e}")
            return {"action": "reject", "code": 500, "reason": "Internal Error"}
    
    async def handle_sip_message(self, sms_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle SMS message from SIP server."""
        try:
            # Forward SMS to AI platform if there's an active connection
            # For now, just log and return success
            logger.info(f"SMS received: {sms_data}")
            
            return {"success": True, "message": "SMS processed"}
            
        except Exception as e:
            logger.error(f"Error handling SIP message: {e}")
            return {"success": False, "error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            "active_connections": len(self.active_connections),
            "call_mappings": len(self.call_to_conversation),
            "rtp_sessions": len(self.rtp_manager.sessions),
            "call_manager_stats": self.call_manager.get_statistics()
        }