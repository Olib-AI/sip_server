"""WebSocket integration for connecting call manager to AI platform."""
import asyncio
import websockets
import websockets.exceptions
import json
import logging
import socket
import base64
from typing import Dict, Any, Optional, Set, Callable, Tuple
from datetime import datetime, timezone
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
        # Use port 10000 range for RTP to match Kamailio SDP
        self.rtp_manager = RTPManager((10000, 10010))
        self.audio_processor = AudioProcessor()
        self.authenticator = WebSocketAuthenticator()
        
        # Active WebSocket connections per call
        self.active_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.call_to_conversation: Dict[str, str] = {}  # call_id -> conversation_id
        self.conversation_to_call: Dict[str, str] = {}  # conversation_id -> call_id
        self.connection_auth: Dict[str, Dict] = {}  # connection_id -> user_info
        self.permanent_rtp_session = None  # Will be set later
        self.call_rtp_destinations: Dict[str, Tuple[str, int]] = {}  # call_id -> (remote_host, remote_port)
        
        # Message handlers
        self.message_handlers: Dict[str, Callable] = {
            "auth": self._handle_auth_message,
            "audio": self._handle_audio_message,
            "audio_data": self._handle_audio_data_message,
            "call_control": self._handle_call_control,
            "dtmf": self._handle_dtmf_message,
            "status": self._handle_status_message,
            "conversation_end": self._handle_conversation_end,
            "subtitle": self._handle_subtitle_message
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
            
            # Suppress websocket connection errors completely - they're just health checks
            websockets_logger = logging.getLogger('websockets.server')
            websockets_logger.setLevel(logging.CRITICAL)
            
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
            
            # Clean up RTP destination tracking
            self.call_rtp_destinations.pop(call_id, None)
            
            # Cleanup RTP session
            await self.rtp_manager.destroy_session(call_id)
            
            # End call if still active
            call_session = self.call_manager.get_call_session(call_id)
            if call_session and call_session.state in [CallState.CONNECTED, CallState.RINGING]:
                await self.call_manager.hangup_call(call_id, "websocket_disconnected")
            
            logger.info(f"Cleaned up WebSocket connection for call {call_id}")
    
    async def _setup_call_audio(self, call_id: str, websocket):
        """Set up audio processing for call using permanent RTP session."""
        try:
            # Check if we already have an active session for this call
            existing_session = self.rtp_manager.get_session(call_id)
            if existing_session:
                logger.info(f"♻️ Reusing existing RTP session for call {call_id}")
                return
            
            logger.info(f"🎧 Setting up audio for call {call_id} using permanent RTP session")
            
            # Verify we have a permanent RTP session
            if not self.permanent_rtp_session:
                logger.error(f"❌ No permanent RTP session available for call {call_id}")
                return
            
            # Register this call as using the permanent RTP session
            # We don't create a new session, just track the call
            self.rtp_manager.sessions[call_id] = self.permanent_rtp_session
            
            logger.info(f"✅ Audio setup complete for call {call_id} - using permanent RTP session on port 10000")
            
        except Exception as e:
            logger.error(f"❌ Failed to setup audio for call {call_id}: {e}")
            import traceback
            traceback.print_exc()
    
    async def _forward_audio_to_websocket(self, call_id: str, audio_data: bytes):
        """Forward audio from RTP to WebSocket."""
        try:
            websocket = self.active_connections.get(call_id)
            if not websocket:
                logger.debug(f"No WebSocket connection for call {call_id}")
                return
            
            logger.info(f"🎵 Processing {len(audio_data)} bytes of RTP audio for call {call_id}")
            
            # Validate input audio data
            if len(audio_data) == 0:
                logger.warning("⚠️ Received empty audio data")
                return
            
            # Log raw audio data characteristics
            logger.info(f"📊 Raw RTP data: {len(audio_data)} bytes, first 8 bytes: {audio_data[:8].hex()}")
            
            # Send raw μ-law (PCMU) directly to AI platform for high-power conversion
            try:
                logger.info(f"🎯 Preparing raw μ-law audio for AI platform (8kHz, 8-bit)")
                
                # Use raw RTP payload as-is (already μ-law encoded)
                ulaw_data = audio_data
                
                logger.info(f"✅ Raw μ-law ready: {len(ulaw_data)} bytes")
                
                # Comprehensive μ-law validation and analysis
                import numpy as np
                if len(ulaw_data) > 0:
                    # Interpret as 8-bit unsigned integers (μ-law format)
                    ulaw_samples = np.frombuffer(ulaw_data, dtype=np.uint8)
                    
                    # Calculate μ-law statistics
                    min_val = np.min(ulaw_samples)
                    max_val = np.max(ulaw_samples)
                    mean_val = np.mean(ulaw_samples)
                    unique_values = len(np.unique(ulaw_samples))
                    
                    logger.info(f"📊 μ-law Audio Stats:")
                    logger.info(f"   📏 Samples: {len(ulaw_samples)} (8-bit μ-law)")
                    logger.info(f"   📈 Value range: {min_val} - {max_val} (0-255)")
                    logger.info(f"   📊 Mean value: {mean_val:.1f}")
                    logger.info(f"   🎯 Unique values: {unique_values}/256")
                    logger.info(f"   📊 Sample rate: 8000 Hz")
                    logger.info(f"   📊 Duration: {len(ulaw_samples)/8000*1000:.1f}ms")
                    
                    # Check for audio quality indicators
                    if unique_values < 5:
                        logger.warning("⚠️ Very limited dynamic range (possible silence)")
                    elif unique_values < 20:
                        logger.warning(f"⚠️ Limited dynamic range ({unique_values} unique values)")
                    else:
                        logger.info(f"✅ Good dynamic range ({unique_values} unique values)")
                    
                    # Check for common μ-law patterns
                    if min_val == max_val:
                        logger.warning(f"⚠️ Audio is constant value: {min_val} (silence or error)")
                    elif np.all(ulaw_samples == 255) or np.all(ulaw_samples == 127):
                        logger.warning("⚠️ Audio appears to be silence (μ-law silence values)")
                    else:
                        logger.info("✅ Audio contains varying μ-law values (good signal)")
                    
                    # Sample some μ-law values for debugging
                    sample_values = ulaw_samples[:min(10, len(ulaw_samples))]
                    logger.info(f"🎵 First 10 μ-law samples: {sample_values}")
                    
                    # Log hex representation for debugging
                    if len(ulaw_data) >= 16:
                        hex_sample = ulaw_data[:16].hex()
                        logger.info(f"🔍 First 16 bytes (hex): {hex_sample}")
                    
                else:
                    logger.warning("⚠️ Empty μ-law data")
                        
            except Exception as e:
                logger.error(f"❌ μ-law analysis failed: {e}")
                ulaw_data = audio_data
                import traceback
                traceback.print_exc()
            
            # Send raw μ-law as binary WebSocket message
            logger.info(f"📡 Sending {len(ulaw_data)} bytes of raw μ-law (8kHz, 8-bit) to AI platform")
            await websocket.send(ulaw_data)
            
            logger.info(f"✅ Successfully sent {len(ulaw_data)} bytes of μ-law audio to AI platform for call {call_id}")
            
        except Exception as e:
            logger.error(f"❌ Error forwarding audio for call {call_id}: {e}")
            import traceback
            traceback.print_exc()
    
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
            
            # Send via permanent RTP session
            if self.permanent_rtp_session:
                logger.info(f"🎵 Sending {len(sip_audio)} bytes via permanent RTP session")
                await self.permanent_rtp_session.send_audio(sip_audio)
            else:
                logger.warning("No permanent RTP session available for outgoing audio")
            
        except Exception as e:
            logger.error(f"Error handling audio message: {e}")
    
    async def _handle_audio_data_message(self, websocket, data: Dict[str, Any]):
        """Handle audio_data message from AI platform (new format)."""
        try:
            # Find the call_id for this websocket
            call_id = None
            for cid, ws in self.active_connections.items():
                if ws == websocket:
                    call_id = cid
                    break
            
            if not call_id:
                logger.warning("No call_id found for websocket connection")
                return
            
            # Extract audio data from the nested structure
            audio_data_info = data.get("data", {})
            audio_b64 = audio_data_info.get("audio")
            codec = audio_data_info.get("codec", "PCM")
            sample_rate = audio_data_info.get("sample_rate", 16000)
            
            if not audio_b64:
                logger.warning("No audio data in audio_data message")
                return
            
            # Decode base64 audio
            try:
                pcm_data = base64.b64decode(audio_b64)
            except Exception as e:
                logger.error(f"Failed to decode base64 audio: {e}")
                return
            
            logger.info(f"🎵 Received {len(pcm_data)} bytes of {codec} audio at {sample_rate}Hz from AI platform for call {call_id}")
            
            # Convert sample rate if needed (AI platform sends 16kHz, SIP expects 8kHz)
            if sample_rate == 16000:
                # Simple downsampling: take every other sample
                import numpy as np
                pcm_16k = np.frombuffer(pcm_data, dtype=np.int16)
                pcm_8k = pcm_16k[::2]  # Downsample 16kHz to 8kHz
                pcm_data = pcm_8k.tobytes()
                logger.debug(f"Downsampled from 16kHz to 8kHz: {len(pcm_data)} bytes")
            
            # Convert from PCM to PCMU for SIP
            try:
                import audioop
                sip_audio = audioop.lin2ulaw(pcm_data, 2)  # Convert to μ-law
                logger.debug(f"Converted PCM to PCMU: {len(sip_audio)} bytes")
            except Exception as e:
                logger.error(f"Audio format conversion failed: {e}")
                sip_audio = pcm_data  # Fallback to raw data
            
            # Get the RTP destination for this call
            rtp_dest = self.call_rtp_destinations.get(call_id)
            if not rtp_dest:
                logger.warning(f"No RTP destination found for call {call_id}")
                return
            
            # Send via permanent RTP session to the correct destination
            if self.permanent_rtp_session:
                # Temporarily update the permanent session's destination
                old_host = self.permanent_rtp_session.remote_host
                old_port = self.permanent_rtp_session.remote_port
                
                self.permanent_rtp_session.remote_host = rtp_dest[0]
                self.permanent_rtp_session.remote_port = rtp_dest[1]
                
                logger.info(f"🎵 Sending {len(sip_audio)} bytes to {rtp_dest[0]}:{rtp_dest[1]} for call {call_id}")
                await self.permanent_rtp_session.send_audio(sip_audio)
                
                # Restore the old destination (though it might be overwritten by incoming packets)
                self.permanent_rtp_session.remote_host = old_host
                self.permanent_rtp_session.remote_port = old_port
            else:
                logger.warning("No permanent RTP session available for outgoing audio")
            
        except Exception as e:
            logger.error(f"Error handling audio_data message: {e}")
            import traceback
            traceback.print_exc()
    
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
    
    async def _handle_subtitle_message(self, websocket, data: Dict[str, Any]):
        """Handle subtitle messages from AI platform (STT results)."""
        try:
            # Find the call_id for this websocket
            call_id = None
            for cid, ws in self.active_connections.items():
                if ws == websocket:
                    call_id = cid
                    break
            
            if not call_id:
                logger.warning("No call_id found for websocket connection receiving subtitle")
                return
            
            text = data.get("text", "")
            is_user = data.get("is_user", False)
            conversation_id = data.get("conversation_id", "")
            metrics = data.get("metrics", {})
            
            logger.info(f"📝 Subtitle for call {call_id}: '{text}' (user: {is_user})")
            
            # Log metrics if available
            if metrics:
                stt_time = metrics.get("stt_time", 0)
                total_time = metrics.get("total_time", 0)
                logger.debug(f"📊 STT metrics - processing: {stt_time}ms, total: {total_time}ms")
            
            # Note: This confirms the AI platform is receiving and processing audio (STT working)
            # but it indicates that TTS (audio_data messages) is not configured or enabled
            
        except Exception as e:
            logger.error(f"Error handling subtitle message: {e}")
    
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
                    "timestamp": datetime.now(timezone.utc).isoformat()
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
            
            logger.info(f"Processing call completed event for call {call_id}")
            
            if websocket:
                await self._send_message(websocket, {
                    "type": "call_completed",
                    "call_id": call_id,
                    "duration": call_session.duration(),
                    "end_reason": call_session.custom_data.get("hangup_reason", "normal"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                # Close WebSocket connection
                await websocket.close()
                logger.info(f"Closed WebSocket connection for completed call {call_id}")
            
            # Force cleanup of this call
            await self._force_cleanup_call(call_id)
            
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
    
    async def _connect_to_ai_platform(self, call_id: str, call_data: Dict[str, Any]):
        """Connect as client to AI platform WebSocket."""
        try:
            logger.info(f"🔗 Establishing connection to AI platform for call {call_id}")
            
            # Extract call information
            from_user = call_data.get("from_number", call_data.get("from", "unknown"))
            to_user = call_data.get("to_number", call_data.get("to", "unknown"))
            
            # Create authentication data for WebSocket headers
            auth_message = self.authenticator.create_sip_auth_message(
                call_id=call_id,
                from_number=from_user,
                to_number=to_user,
                direction="incoming",
                codec="PCMU",
                sample_rate=8000
            )
            
            # Connect to AI platform WebSocket
            async with websockets.connect(self.ai_websocket_url) as websocket:
                logger.info(f"✅ Connected to AI platform for call {call_id}")
                
                # Store the connection
                self.active_connections[call_id] = websocket
                
                # Send the complete auth message as first message
                await self._send_message(websocket, auth_message)
                logger.info(f"🔐 Sent authentication message for call {call_id}")
                
                # Set up audio processing for this call
                await self._setup_call_audio(call_id, websocket)
                
                # Keep connection alive and handle messages
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        message_type = data.get("type")
                        
                        if message_type in self.message_handlers:
                            handler = self.message_handlers[message_type]
                            await handler(websocket, data)
                        elif message_type == "ready":
                            # AI platform is ready to receive audio
                            logger.info(f"✅ AI platform ready for call {call_id}")
                        elif message_type == "heartbeat":
                            # AI platform heartbeat - respond with heartbeat ack
                            await self._send_message(websocket, {
                                "type": "heartbeat_ack",
                                "timestamp": time.time()
                            })
                        else:
                            logger.warning(f"Unknown message type from AI platform: {message_type}")
                            logger.info(f"📋 Full message from AI platform: {data}")  # Log the complete message for debugging
                            
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON from AI platform: {e}")
                    except Exception as e:
                        logger.error(f"Error processing AI platform message: {e}")
                        
        except websockets.exceptions.ConnectionClosed as e:
            # Check if it's a service restart (code 1012)
            if hasattr(e, 'code') and e.code == 1012:
                logger.warning(f"AI platform restarted during call {call_id}: {e}")
                # Attempt reconnection for service restart
                await self._attempt_reconnection(call_id, call_data)
            else:
                logger.warning(f"AI platform connection closed for call {call_id}: {e}")
        except websockets.exceptions.InvalidStatusCode as e:
            logger.error(f"AI platform rejected connection for call {call_id}: HTTP {e.status_code}")
        except websockets.exceptions.InvalidURI as e:
            logger.error(f"Invalid WebSocket URI for call {call_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to connect to AI platform for call {call_id}: {type(e).__name__}: {e}")
        finally:
            # Clean up connection
            self.active_connections.pop(call_id, None)
            logger.info(f"🔌 Disconnected from AI platform for call {call_id}")
    
    async def _attempt_reconnection(self, call_id: str, call_data: Dict[str, Any], max_attempts: int = 3):
        """Attempt to reconnect to AI platform after service restart."""
        for attempt in range(max_attempts):
            try:
                logger.info(f"🔄 Attempting reconnection {attempt + 1}/{max_attempts} for call {call_id}")
                await asyncio.sleep(2)  # Wait 2 seconds before retry
                
                # Try to reconnect
                await self._connect_to_ai_platform(call_id, call_data)
                logger.info(f"✅ Successfully reconnected to AI platform for call {call_id}")
                return
                
            except Exception as e:
                logger.warning(f"Reconnection attempt {attempt + 1} failed for call {call_id}: {e}")
                
        logger.error(f"❌ All reconnection attempts failed for call {call_id}")
    
    # Public API for SIP server integration
    
    async def notify_incoming_call(self, call_data: Dict[str, Any]) -> Dict[str, Any]:
        """Notify about incoming call from SIP server."""
        try:
            # Process call through call manager
            result = await self.call_manager.handle_incoming_call(call_data)
            
            # Connect to AI platform for this call
            call_id = call_data.get("call_id")
            if call_id and self.ai_websocket_url:
                logger.info(f"🤖 Connecting to AI platform for call {call_id}: {self.ai_websocket_url}")
                # Start background task to connect to AI platform
                asyncio.create_task(self._connect_to_ai_platform(call_id, call_data))
            
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
    
    async def handle_call_hangup(self, call_id: str, reason: str = "normal") -> Dict[str, Any]:
        """Handle call hangup from SIP server (BYE message)."""
        try:
            logger.info(f"Handling call hangup for {call_id}: {reason}")
            
            # Force cleanup of the call and WebSocket
            await self._force_cleanup_call(call_id)
            
            # Also hangup via call manager to ensure proper state handling
            await self.call_manager.hangup_call(call_id, reason)
            
            return {"success": True, "message": "Call hung up successfully"}
            
        except Exception as e:
            logger.error(f"Error handling call hangup: {e}")
            return {"success": False, "error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            "active_connections": len(self.active_connections),
            "call_mappings": len(self.call_to_conversation),
            "rtp_sessions": len(self.rtp_manager.sessions),
            "call_manager_stats": self.call_manager.get_statistics()
        }
    
    async def _route_rtp_to_active_call(self, audio_data: bytes, remote_addr: Tuple[str, int] = None):
        """Route RTP audio from permanent listener to active call."""
        try:
            # Find the first active WebSocket connection
            # In a real system, you'd need better routing logic
            if not self.active_connections:
                logger.debug("No active WebSocket connections to route RTP audio")
                return
                
            # For now, route to the first active connection
            call_id = next(iter(self.active_connections.keys()))
            
            # Store the RTP destination for this call
            if remote_addr and call_id:
                self.call_rtp_destinations[call_id] = remote_addr
                logger.info(f"🎯 Updated RTP destination for call {call_id}: {remote_addr}")
            
            logger.info(f"🎵 Routing RTP audio to call {call_id}")
            
            # Forward to WebSocket using existing method
            await self._forward_audio_to_websocket(call_id, audio_data)
            
        except Exception as e:
            logger.error(f"Error routing RTP audio: {e}")
    
    def set_permanent_rtp_session(self, rtp_session):
        """Set the permanent RTP session for outgoing audio."""
        self.permanent_rtp_session = rtp_session
        logger.info("🎵 Connected permanent RTP session to WebSocket bridge")
    
    async def _force_cleanup_call(self, call_id: str):
        """Force cleanup of a specific call."""
        try:
            logger.info(f"Force cleaning up call {call_id}")
            
            # Remove from all tracking dictionaries
            conversation_id = self.call_to_conversation.pop(call_id, None)
            if conversation_id:
                self.conversation_to_call.pop(conversation_id, None)
            
            # Close and remove WebSocket connection
            websocket = self.active_connections.pop(call_id, None)
            if websocket:
                try:
                    await websocket.close()
                    logger.info(f"Forcefully closed WebSocket for call {call_id}")
                except Exception as e:
                    logger.warning(f"Error closing WebSocket for call {call_id}: {e}")
            
            # Clean up RTP destination tracking
            self.call_rtp_destinations.pop(call_id, None)
            
            # Cleanup RTP session
            await self.rtp_manager.destroy_session(call_id)
            
            logger.info(f"Completed force cleanup for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error in force cleanup for call {call_id}: {e}")