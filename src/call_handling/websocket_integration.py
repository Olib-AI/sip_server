"""WebSocket integration for connecting call manager to AI platform."""
import asyncio
import websockets
import websockets.exceptions
import json
import logging
import base64
from typing import Dict, Any, Optional, Callable, Tuple
from datetime import datetime, timezone
import time
import uuid

from .call_manager import CallManager, CallSession, CallState
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
        # Use dynamic port range for RTP sessions per call
        self.rtp_manager = RTPManager((10000, 10100))
        self.audio_processor = AudioProcessor()
        self.authenticator = WebSocketAuthenticator()
        
        # Active WebSocket connections per call
        self.active_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.call_to_conversation: Dict[str, str] = {}  # call_id -> conversation_id
        self.conversation_to_call: Dict[str, str] = {}  # conversation_id -> call_id
        self.connection_auth: Dict[str, Dict] = {}  # connection_id -> user_info
        
        # Individual RTP sessions per call (no more permanent session)
        self.call_rtp_sessions: Dict[str, Any] = {}  # call_id -> RTPSession
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
        
        # Audio buffering for smooth RTP transmission
        self.audio_buffers: Dict[str, bytearray] = {}  # call_id -> audio buffer
        self.buffer_tasks: Dict[str, asyncio.Task] = {}  # call_id -> buffer task
        self.buffer_ready: Dict[str, bool] = {}  # call_id -> buffer ready for transmission
        self.rtp_frame_size = 160  # 20ms at 8kHz = 160 bytes µ-law
        self.rtp_interval = 0.02  # 20ms
        self.min_buffer_size = 160  # 20ms of buffer (1 frame) before starting transmission - reduced for lower latency
        self.silence_frame = b'\x7F' * 160  # µ-law silence frame
        
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
            logger.info(f"🧹 Cleaning up WebSocket connection for call {call_id}")
            
            # Remove from tracking
            conversation_id = self.call_to_conversation.pop(call_id, None)
            if conversation_id:
                self.conversation_to_call.pop(conversation_id, None)
            self.active_connections.pop(call_id, None)
            
            # Clean up RTP destination tracking
            self.call_rtp_destinations.pop(call_id, None)
            
            # Clean up individual RTP session for this call
            rtp_session = self.call_rtp_sessions.pop(call_id, None)
            if rtp_session:
                try:
                    await rtp_session.stop()
                    logger.info(f"🎵 Stopped individual RTP session for call {call_id}")
                except Exception as e:
                    logger.error(f"Error stopping RTP session for call {call_id}: {e}")
            
            # Clean up audio buffering
            await self._cleanup_audio_buffer(call_id)
            
            # Cleanup RTP session from manager
            await self.rtp_manager.destroy_session(call_id)
            
            # End call if still active
            call_session = self.call_manager.get_call_session(call_id)
            if call_session and call_session.state in [CallState.CONNECTED, CallState.RINGING]:
                await self.call_manager.hangup_call(call_id, "websocket_disconnected")
            
            logger.info(f"✅ Completed cleanup for WebSocket connection for call {call_id}")
    
    async def _setup_call_audio(self, call_id: str, websocket):
        """Set up individual RTP session for this specific call."""
        try:
            # Check if we already have an active session for this call
            if call_id in self.call_rtp_sessions:
                logger.info(f"♻️ RTP session already exists for call {call_id}")
                return
            
            logger.info(f"🎧 Setting up individual RTP session for SIP Call-ID: {call_id}")
            
            # Create a new individual RTP session for this call
            from ..audio.rtp import RTPSession
            
            # Allocate a unique port for this call
            local_port = self.rtp_manager.allocate_port()
            
            # Create RTP session for this specific call
            # Set remote host to the SIP client's IP immediately so AI platform audio can flow
            remote_host = "127.0.0.1"  # Default for local testing
            remote_port = 5004  # Default RTP port for SIP clients
            
            # Try to get the actual client IP from call context if available
            if hasattr(self, 'calls') and call_id in self.calls:
                call_info = self.calls[call_id]
                if call_info.get("remote_ip") and call_info["remote_ip"] != "unknown":
                    remote_host = call_info["remote_ip"]
            
            rtp_session = RTPSession(
                local_port=local_port,
                remote_host=remote_host,
                remote_port=remote_port,
                payload_type=0,  # PCMU
                codec="PCMU"
            )
            
            # Set the RTP destination immediately for outgoing audio
            self.call_rtp_destinations[call_id] = (remote_host, remote_port)
            logger.info(f"🎯 Call {call_id}: Pre-configured RTP destination to {remote_host}:{remote_port}")
            
            # Set up callback to route audio to this specific call's WebSocket
            def call_audio_callback(audio_data: bytes, remote_addr=None):
                logger.info(f"🎵 Call {call_id} RTP session received {len(audio_data)} bytes")
                # Update remote address for outgoing packets if we got a new one
                if remote_addr and (not rtp_session.remote_host or 
                                   remote_addr[0] != rtp_session.remote_host or 
                                   remote_addr[1] != rtp_session.remote_port):
                    logger.info(f"🎯 Call {call_id}: Updating RTP remote address to {remote_addr}")
                    rtp_session.remote_host = remote_addr[0]
                    rtp_session.remote_port = remote_addr[1]
                    # Store for outgoing audio
                    self.call_rtp_destinations[call_id] = remote_addr
                
                # Route audio to this call's WebSocket
                asyncio.create_task(
                    self._forward_audio_to_websocket(call_id, audio_data)
                )
            
            rtp_session.set_receive_callback(call_audio_callback)
            
            # Start the RTP session
            await rtp_session.start()
            
            # Store the session
            self.call_rtp_sessions[call_id] = rtp_session
            
            # Also register with RTP manager for tracking
            self.rtp_manager.sessions[call_id] = rtp_session
            
            logger.info(f"✅ Individual RTP session created for SIP Call-ID: {call_id} on port {local_port}")
            
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
            
            # Send via this call's individual RTP session
            rtp_session = self.call_rtp_sessions.get(call_id)
            if rtp_session:
                logger.info(f"🎵 Call {call_id}: Sending {len(sip_audio)} bytes via individual RTP session")
                await rtp_session.send_audio(sip_audio)
            else:
                logger.warning(f"No RTP session available for call {call_id}")
            
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
            
            # Handle different audio formats
            if codec == "PCMU":
                # Already µ-law encoded at 8kHz - use directly
                sip_audio = pcm_data
                logger.debug(f"Using µ-law audio directly: {len(sip_audio)} bytes")
            else:
                # PCM format - needs conversion
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
            
            # Add to audio buffer for smooth RTP transmission
            await self._buffer_audio_for_rtp(call_id, sip_audio)
            
        except Exception as e:
            logger.error(f"Error handling audio_data message: {e}")
            import traceback
            traceback.print_exc()
    
    async def _buffer_audio_for_rtp(self, call_id: str, audio_data: bytes):
        """Buffer audio data and ensure smooth RTP transmission."""
        try:
            # Initialize buffer for this call if needed
            if call_id not in self.audio_buffers:
                self.audio_buffers[call_id] = bytearray()
                self.buffer_ready[call_id] = False
                # Start buffering task for this call
                self.buffer_tasks[call_id] = asyncio.create_task(self._rtp_transmission_task(call_id))
                logger.info(f"🎵 Started audio buffering for call {call_id}")
            
            # Add audio data to buffer
            buffer = self.audio_buffers[call_id]
            buffer.extend(audio_data)
            
            # Check if we have enough data to start transmission
            if not self.buffer_ready[call_id] and len(buffer) >= self.min_buffer_size:
                self.buffer_ready[call_id] = True
                logger.info(f"🎵 Buffer ready for call {call_id}: {len(buffer)} bytes pre-buffered")
            
            logger.debug(f"🎵 Buffered {len(audio_data)} bytes for call {call_id}, total: {len(buffer)} bytes, ready: {self.buffer_ready[call_id]}")
            
        except Exception as e:
            logger.error(f"Error buffering audio for call {call_id}: {e}")
    
    async def _rtp_transmission_task(self, call_id: str):
        """Continuously send RTP packets at regular intervals from buffer."""
        try:
            logger.info(f"🎵 Starting RTP transmission task for call {call_id}")
            
            while call_id in self.audio_buffers:
                try:
                    # Wait until buffer is ready (pre-buffered) before starting transmission
                    if not self.buffer_ready.get(call_id, False):
                        await asyncio.sleep(0.005)  # Check every 5ms
                        continue
                    
                    # Check if we have enough data for an RTP frame
                    buffer = self.audio_buffers[call_id]
                    if len(buffer) >= self.rtp_frame_size:
                        # Extract one RTP frame worth of data
                        frame_data = bytes(buffer[:self.rtp_frame_size])
                        del buffer[:self.rtp_frame_size]
                        
                        # Send RTP frame
                        await self._send_rtp_frame(call_id, frame_data)
                        
                        # Check if buffer is getting low - log warning
                        if len(buffer) < self.rtp_frame_size * 2:  # Less than 40ms buffered
                            logger.debug(f"🎵 Buffer running low for call {call_id}: {len(buffer)} bytes remaining")
                    else:
                        # Buffer underrun - send silence to maintain timing
                        logger.debug(f"🎵 Buffer underrun for call {call_id}, sending silence")
                        await self._send_rtp_frame(call_id, self.silence_frame)
                    
                    # Wait for next RTP interval (20ms)
                    await asyncio.sleep(self.rtp_interval)
                    
                except Exception as e:
                    logger.error(f"Error in RTP transmission for call {call_id}: {e}")
                    await asyncio.sleep(self.rtp_interval)  # Continue despite errors
                    
        except asyncio.CancelledError:
            logger.info(f"🎵 RTP transmission task cancelled for call {call_id}")
        except Exception as e:
            logger.error(f"RTP transmission task error for call {call_id}: {e}")
        finally:
            # Clean up
            self.audio_buffers.pop(call_id, None)
            self.buffer_tasks.pop(call_id, None)
            logger.info(f"🎵 RTP transmission task ended for call {call_id}")
    
    async def _send_rtp_frame(self, call_id: str, frame_data: bytes):
        """Send a single RTP frame using the call's individual RTP session."""
        try:
            # Get the individual RTP session for this call
            rtp_session = self.call_rtp_sessions.get(call_id)
            if not rtp_session:
                logger.debug(f"No RTP session found for call {call_id}")
                return
            
            # Get the RTP destination for this call
            rtp_dest = self.call_rtp_destinations.get(call_id)
            if not rtp_dest:
                logger.debug(f"No RTP destination found for call {call_id}")
                return
            
            # Update the session's destination if needed
            if (rtp_session.remote_host != rtp_dest[0] or 
                rtp_session.remote_port != rtp_dest[1]):
                rtp_session.remote_host = rtp_dest[0]
                rtp_session.remote_port = rtp_dest[1]
            
            # Send via this call's individual RTP session
            await rtp_session.send_audio(frame_data)
            logger.debug(f"🎵 Call {call_id}: Sent RTP frame {len(frame_data)} bytes to {rtp_dest[0]}:{rtp_dest[1]}")
                
        except Exception as e:
            logger.error(f"Error sending RTP frame for call {call_id}: {e}")
    
    async def _cleanup_audio_buffer(self, call_id: str):
        """Clean up audio buffer and stop transmission task for a call."""
        try:
            # Cancel the buffer task
            task = self.buffer_tasks.pop(call_id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                logger.info(f"🎵 Cancelled audio buffer task for call {call_id}")
            
            # Clear the buffer and ready state
            self.audio_buffers.pop(call_id, None)
            self.buffer_ready.pop(call_id, None)
            logger.info(f"🎵 Cleaned up audio buffer for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error cleaning up audio buffer for call {call_id}: {e}")
    
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
        self.call_manager.add_event_handler("call_cleanup", self._on_call_cleanup)
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
            
            logger.info(f"🔚 Processing call completed event for call {call_id}")
            
            if websocket:
                # Send final message to AI platform
                await self._send_message(websocket, {
                    "type": "call_completed",
                    "call_id": call_id,
                    "duration": call_session.duration(),
                    "end_reason": call_session.custom_data.get("hangup_reason", "normal"),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                
                # Very brief wait for the message to be sent
                await asyncio.sleep(0.01)
                
                # Close WebSocket connection gracefully
                try:
                    await websocket.close(code=1000, reason="Call completed")
                    logger.info(f"✅ Gracefully closed WebSocket for completed call {call_id}")
                except Exception as e:
                    logger.warning(f"Error closing WebSocket for call {call_id}: {e}")
            
            # Schedule cleanup to happen after WebSocket close
            asyncio.create_task(self._delayed_force_cleanup(call_id))
            
        except Exception as e:
            logger.error(f"Error handling call completed event: {e}")
    
    async def _on_call_cleanup(self, call_session: CallSession):
        """Handle call cleanup events."""
        try:
            call_id = call_session.call_id
            logger.info(f"🧹 Processing call cleanup event for call {call_id}")
            
            # This event is fired after the call is removed from active_calls
            # Use it for final cleanup of WebSocket resources
            await self._force_cleanup_call(call_id)
            
        except Exception as e:
            logger.error(f"Error handling call cleanup event: {e}")
    
    async def _delayed_force_cleanup(self, call_id: str, delay: float = 0.1):
        """Force cleanup after a small delay to allow WebSocket close to complete."""
        await asyncio.sleep(delay)
        await self._force_cleanup_call(call_id)
    
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
            direction = call_data.get("direction", "incoming")
            
            # For outgoing calls, use the webhook URL if provided
            ai_websocket_url = self.ai_websocket_url
            if direction == "outgoing" and call_data.get("custom_data", {}).get("webhook_url"):
                ai_websocket_url = call_data["custom_data"]["webhook_url"]
                logger.info(f"🔗 Using webhook URL for outgoing call: {ai_websocket_url}")
            
            logger.info(f"🔗 Connecting to AI platform: {ai_websocket_url} (direction: {direction})")
            
            # Create authentication data for WebSocket headers
            auth_message = self.authenticator.create_sip_auth_message(
                call_id=call_id,
                from_number=from_user,
                to_number=to_user,
                direction=direction,
                codec="PCMU",
                sample_rate=8000
            )
            
            # For outgoing calls, add the AI headers and mark as outgoing
            if direction == "outgoing":
                ai_headers = call_data.get("headers", {})
                if ai_headers:
                    auth_message["headers"] = ai_headers
                else:
                    auth_message["headers"] = {}
                auth_message["headers"]["X-Outgoing-Call"] = "true"
            
            # Connect to AI platform WebSocket
            async with websockets.connect(ai_websocket_url) as websocket:
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
            call_id = call_data.get("call_id")
            sip_call_id = call_data.get("sip_call_id")
            
            logger.info(f"📞 WebSocket bridge processing call - ID: {call_id}, SIP Call-ID: {sip_call_id}")
            
            # Process call through call manager
            result = await self.call_manager.handle_incoming_call(call_data)
            
            # Connect to AI platform for this call
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
            logger.info(f"📞 WebSocket bridge handling call hangup for SIP Call-ID: {call_id}, reason: {reason}")
            
            # Check if this call exists in our tracking
            found_call = False
            if call_id in self.active_connections or call_id in self.call_rtp_sessions:
                found_call = True
                logger.info(f"✅ Found call {call_id} in WebSocket bridge tracking")
            else:
                logger.warning(f"⚠️ Call {call_id} not found in WebSocket bridge - checking for orphaned connections")
                
                # Look for orphaned connections (WebSocket connections without matching call IDs)
                orphaned_calls = []
                for tracked_call_id in list(self.active_connections.keys()):
                    if tracked_call_id != call_id:
                        # Check if this might be the same call (different ID format)
                        logger.info(f"🔍 Found active connection for different call ID: {tracked_call_id}")
                        orphaned_calls.append(tracked_call_id)
                
                # If we found orphaned connections, clean them up too
                if orphaned_calls:
                    logger.warning(f"🧹 Cleaning up {len(orphaned_calls)} orphaned connections: {orphaned_calls}")
                    for orphaned_call_id in orphaned_calls:
                        await self._force_cleanup_call(orphaned_call_id)
                        found_call = True
            
            # First hangup via call manager to ensure proper state handling
            hangup_success = await self.call_manager.hangup_call(call_id, reason)
            
            if not hangup_success:
                logger.warning(f"⚠️ Call manager could not find call {call_id} for hangup")
                
                # Even if call manager doesn't find it, try to clean up WebSocket resources
                if not found_call:
                    # Check if there are any active connections that need cleanup
                    if self.active_connections:
                        logger.warning(f"🧹 Cleaning up all {len(self.active_connections)} active connections due to unmatched hangup")
                        for orphaned_call_id in list(self.active_connections.keys()):
                            await self._force_cleanup_call(orphaned_call_id)
            
            # Force cleanup of the call and WebSocket connections
            await self._force_cleanup_call(call_id)
            
            logger.info(f"✅ Successfully handled hangup for call {call_id}")
            
            return {"success": True, "message": "Call hung up successfully"}
            
        except Exception as e:
            logger.error(f"Error handling call hangup for {call_id}: {e}")
            return {"success": False, "error": str(e)}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            "active_connections": len(self.active_connections),
            "active_connection_ids": list(self.active_connections.keys()),
            "call_mappings": len(self.call_to_conversation),
            "individual_rtp_sessions": len(self.call_rtp_sessions),
            "rtp_session_ids": list(self.call_rtp_sessions.keys()),
            "rtp_manager_sessions": len(self.rtp_manager.sessions),
            "call_manager_stats": self.call_manager.get_statistics(),
            "call_rtp_destinations": len(self.call_rtp_destinations)
        }
    
    async def handle_rtp_audio_for_call(self, call_id: str, audio_data: bytes, remote_addr: Tuple[str, int] = None):
        """Handle RTP audio for a specific call (called by individual RTP sessions)."""
        try:
            # This method is called by individual RTP session callbacks
            # The audio routing is already handled by the callback setup in _setup_call_audio
            logger.debug(f"🎵 Handling RTP audio for call {call_id}: {len(audio_data)} bytes")
            
            # Store the RTP destination for this call if provided
            if remote_addr and call_id:
                self.call_rtp_destinations[call_id] = remote_addr
                logger.debug(f"🎯 Updated RTP destination for call {call_id}: {remote_addr}")
            
            # Forward to WebSocket (this is already done by the callback)
            await self._forward_audio_to_websocket(call_id, audio_data)
            
        except Exception as e:
            logger.error(f"Error handling RTP audio for call {call_id}: {e}")
    
    def get_call_rtp_info(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get RTP session info for a specific call."""
        rtp_session = self.call_rtp_sessions.get(call_id)
        if rtp_session:
            return {
                "call_id": call_id,
                "local_port": rtp_session.local_port,
                "remote_host": rtp_session.remote_host,
                "remote_port": rtp_session.remote_port,
                "codec": rtp_session.codec,
                "running": rtp_session.running
            }
        return None
    
    async def _force_cleanup_call(self, call_id: str):
        """Force cleanup of a specific call."""
        try:
            logger.info(f"🧹 Force cleaning up call {call_id}")
            
            # Remove from all tracking dictionaries
            conversation_id = self.call_to_conversation.pop(call_id, None)
            if conversation_id:
                self.conversation_to_call.pop(conversation_id, None)
            
            # Close and remove WebSocket connection
            websocket = self.active_connections.pop(call_id, None)
            if websocket:
                try:
                    if not websocket.closed:
                        await websocket.close(code=1000, reason="Call cleanup")
                    logger.info(f"✅ Closed WebSocket for call {call_id}")
                except Exception as e:
                    logger.warning(f"Error closing WebSocket for call {call_id}: {e}")
            
            # Clean up individual RTP session for this call
            rtp_session = self.call_rtp_sessions.pop(call_id, None)
            if rtp_session:
                try:
                    await rtp_session.stop()
                    logger.info(f"🎵 Stopped individual RTP session for call {call_id}")
                except Exception as e:
                    logger.error(f"Error stopping RTP session for call {call_id}: {e}")
            
            # Clean up RTP destination tracking
            self.call_rtp_destinations.pop(call_id, None)
            
            # Clean up audio buffering
            await self._cleanup_audio_buffer(call_id)
            
            # Cleanup RTP session from manager
            await self.rtp_manager.destroy_session(call_id)
            
            logger.info(f"✅ Completed force cleanup for call {call_id}")
            
        except Exception as e:
            logger.error(f"Error in force cleanup for call {call_id}: {e}")