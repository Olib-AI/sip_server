"""Handler methods for WebSocket bridge operations."""
import asyncio
import json
import logging
import time
import base64
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)


class BridgeHandlers:
    """Mixin class containing handler methods for WebSocket bridge."""
    
    async def handle_sip_connection(self, websocket, path: str):
        """Handle incoming SIP WebSocket connections."""
        call_id = None
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        
        try:
            logger.info(f"New SIP connection from {client_ip} on path {path}")
            
            # Wait for initial call setup message
            initial_message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
            data = json.loads(initial_message)
            
            if data.get("type") != "call_setup":
                await self._send_error(websocket, "Expected call_setup message")
                return
                
            # Extract call information
            call_id = data.get("call_id")
            if not call_id:
                await self._send_error(websocket, "Missing call_id")
                return
                
            # Create call info
            call_info = await self._create_call_info(data)
            self.active_calls[call_id] = call_info
            self.sip_connections[call_id] = websocket
            self.total_calls_handled += 1
            self.concurrent_calls += 1
            
            logger.info(f"Call {call_id} setup: {call_info.from_number} -> {call_info.to_number}")
            
            # Setup RTP session
            await self._setup_rtp_session(call_id, call_info, data)
            
            # Connect to AI platform
            ai_connection = await self.connection_manager.connect_for_call(call_id, call_info)
            if not ai_connection:
                await self._send_error(websocket, "Failed to connect to AI platform")
                return
                
            # Start handling AI messages
            asyncio.create_task(self._handle_ai_messages(call_id))
            
            # Send success response
            await websocket.send(json.dumps({
                "type": "call_ready",
                "call_id": call_id,
                "rtp_port": call_info.rtp_local_port,
                "session_id": call_info.ai_session_id
            }))
            
            # Handle SIP messages
            await self._handle_sip_messages(websocket, call_id)
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for call setup from {client_ip}")
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"SIP connection closed for call {call_id}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from SIP connection {client_ip}")
        except Exception as e:
            logger.error(f"Error handling SIP connection: {e}")
            if websocket.open:
                await self._send_error(websocket, str(e))
        finally:
            if call_id:
                await self.cleanup_call(call_id, reason="SIP connection ended")
                
    async def _create_call_info(self, data: Dict) -> Any:
        """Create CallInfo object from SIP setup data."""
        from .bridge import CallInfo, CallState
        
        return CallInfo(
            call_id=data["call_id"],
            from_number=data.get("from_number", "unknown"),
            to_number=data.get("to_number", "unknown"),
            sip_headers=data.get("sip_headers", {}),
            state=CallState.CONNECTING,
            start_time=time.time(),
            codec=data.get("codec", "PCMU")
        )
        
    async def _setup_rtp_session(self, call_id: str, call_info: Any, data: Dict):
        """Setup RTP session for the call."""
        try:
            remote_host = data.get("remote_rtp_host", "127.0.0.1")
            remote_port = data.get("remote_rtp_port", 5004)
            
            # Create RTP session
            rtp_session = await self.rtp_manager.create_session(
                call_id, remote_host, remote_port, call_info.codec
            )
            
            # Update call info
            call_info.rtp_local_port = rtp_session.local_port
            call_info.rtp_remote_host = remote_host
            call_info.rtp_remote_port = remote_port
            
            # Setup audio callback
            rtp_session.set_receive_callback(
                lambda audio_data: asyncio.create_task(
                    self._handle_rtp_audio(call_id, audio_data)
                )
            )
            
            # Create audio buffer
            from .bridge import AudioBuffer
            self.audio_buffers[call_id] = AudioBuffer()
            from ..audio.rtp import RTPStatistics
            self.call_statistics[call_id] = RTPStatistics()
            
            logger.info(f"RTP session setup for call {call_id} on port {rtp_session.local_port}")
            
        except Exception as e:
            logger.error(f"Failed to setup RTP session for call {call_id}: {e}")
            raise
            
    async def _handle_sip_messages(self, websocket, call_id: str):
        """Handle ongoing SIP WebSocket messages."""
        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    # Binary audio data
                    await self._handle_sip_audio(call_id, message)
                else:
                    # Text control message
                    try:
                        data = json.loads(message)
                        await self._process_sip_control_message(call_id, data)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON from SIP call {call_id}")
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"SIP WebSocket closed for call {call_id}")
        except Exception as e:
            logger.error(f"Error handling SIP messages for call {call_id}: {e}")
            
    async def _handle_ai_messages(self, call_id: str):
        """Handle messages from AI platform."""
        connection = self.connection_manager.get_connection(call_id)
        if not connection:
            return
            
        try:
            async for message in connection:
                if isinstance(message, bytes):
                    # Binary audio from AI
                    await self._handle_ai_audio(call_id, message)
                else:
                    # Control message from AI
                    try:
                        data = json.loads(message)
                        await self._process_ai_control_message(call_id, data)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON from AI for call {call_id}")
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"AI connection closed for call {call_id}")
        except Exception as e:
            logger.error(f"Error handling AI messages for call {call_id}: {e}")
            
    async def _handle_rtp_audio(self, call_id: str, audio_data: bytes):
        """Handle audio received via RTP."""
        if call_id not in self.active_calls:
            return
            
        try:
            call_info = self.active_calls[call_id]
            
            # Convert codec format to PCM for AI platform
            pcm_data = self.audio_processor.convert_format(
                audio_data, call_info.codec, "PCM"
            )
            
            # Apply audio processing
            pcm_data = self.audio_processor.apply_agc(pcm_data)
            
            # Add to buffer for jitter control
            buffer = self.audio_buffers.get(call_id)
            if buffer:
                buffer.add_frame(pcm_data)
                
                # Send buffered frames to AI
                while True:
                    frame = buffer.get_frame()
                    if not frame:
                        break
                    await self.connection_manager.send_audio(call_id, frame)
                    
            # Update statistics
            stats = self.call_statistics.get(call_id)
            if stats:
                stats.record_received_packet(type('Packet', (), {'payload': audio_data})())
                
        except Exception as e:
            logger.error(f"Error handling RTP audio for call {call_id}: {e}")
            
    async def _handle_sip_audio(self, call_id: str, audio_data: bytes):
        """Handle audio received via SIP WebSocket."""
        # This is alternative to RTP - direct WebSocket audio
        await self._handle_rtp_audio(call_id, audio_data)
        
    async def _handle_ai_audio(self, call_id: str, audio_data: bytes):
        """Handle audio received from AI platform."""
        if call_id not in self.active_calls:
            return
            
        try:
            call_info = self.active_calls[call_id]
            
            # Convert PCM to SIP codec format
            codec_data = self.audio_processor.convert_format(
                audio_data, "PCM", call_info.codec
            )
            
            # Send via RTP
            rtp_session = self.rtp_manager.get_session(call_id)
            if rtp_session:
                await rtp_session.send_audio(codec_data)
                
            # Also send via SIP WebSocket if available
            sip_ws = self.sip_connections.get(call_id)
            if sip_ws and sip_ws.open:
                await sip_ws.send(codec_data)
                
            # Update statistics
            stats = self.call_statistics.get(call_id)
            if stats:
                stats.record_sent_packet(len(codec_data))
                
        except Exception as e:
            logger.error(f"Error handling AI audio for call {call_id}: {e}")
            
    async def _process_sip_control_message(self, call_id: str, data: Dict):
        """Process control messages from SIP."""
        message_type = data.get("type")
        
        if message_type == "dtmf":
            await self._forward_dtmf_to_ai(call_id, data.get("digit"))
        elif message_type == "call_hold":
            await self._handle_call_hold(call_id)
        elif message_type == "call_resume":
            await self._handle_call_resume(call_id)
        elif message_type == "call_end":
            await self.cleanup_call(call_id, reason="SIP initiated")
        else:
            logger.warning(f"Unknown SIP control message: {message_type}")
            
    async def _process_ai_control_message(self, call_id: str, data: Dict):
        """Process control messages from AI platform."""
        message_type = data.get("type")
        
        if message_type == "hangup":
            await self._hangup_call(call_id)
        elif message_type == "transfer":
            await self._transfer_call(call_id, data.get("target"))
        elif message_type == "hold":
            await self._handle_call_hold(call_id)
        elif message_type == "resume":
            await self._handle_call_resume(call_id)
        elif message_type == "dtmf_send":
            await self._send_dtmf_to_sip(call_id, data.get("digit"))
        else:
            logger.debug(f"Unhandled AI control message: {message_type}")
            
    async def _forward_dtmf_to_ai(self, call_id: str, digit: str):
        """Forward DTMF digit to AI platform."""
        connection = self.connection_manager.get_connection(call_id)
        if connection:
            message = {
                "type": "dtmf",
                "data": {
                    "call_id": call_id,
                    "digit": digit,
                    "timestamp": time.time()
                }
            }
            await connection.send(json.dumps(message))
            
    async def _send_dtmf_to_sip(self, call_id: str, digit: str):
        """Send DTMF digit to SIP side."""
        sip_ws = self.sip_connections.get(call_id)
        if sip_ws and sip_ws.open:
            message = {
                "type": "dtmf_send",
                "digit": digit
            }
            await sip_ws.send(json.dumps(message))
            
    async def _handle_call_hold(self, call_id: str):
        """Handle call hold request."""
        if call_id in self.active_calls:
            from .bridge import CallState
            self.active_calls[call_id].state = CallState.ON_HOLD
            logger.info(f"Call {call_id} placed on hold")
            
    async def _handle_call_resume(self, call_id: str):
        """Handle call resume request."""
        if call_id in self.active_calls:
            from .bridge import CallState
            self.active_calls[call_id].state = CallState.CONNECTED
            logger.info(f"Call {call_id} resumed")
            
    async def _hangup_call(self, call_id: str):
        """Hang up a call."""
        sip_ws = self.sip_connections.get(call_id)
        if sip_ws and sip_ws.open:
            message = {"type": "hangup"}
            await sip_ws.send(json.dumps(message))
        await self.cleanup_call(call_id, reason="AI initiated hangup")
        
    async def _transfer_call(self, call_id: str, target: str):
        """Transfer a call to another number."""
        sip_ws = self.sip_connections.get(call_id)
        if sip_ws and sip_ws.open:
            message = {
                "type": "transfer",
                "target": target
            }
            await sip_ws.send(json.dumps(message))
            
    async def _send_error(self, websocket, error_message: str):
        """Send error message to WebSocket."""
        try:
            if websocket.open:
                await websocket.send(json.dumps({
                    "type": "error",
                    "error": error_message
                }))
        except Exception:
            pass  # Connection might be closed
            
    async def cleanup_call(self, call_id: str, reason: str = "Normal cleanup"):
        """Clean up all resources for a call."""
        logger.info(f"Cleaning up call {call_id}: {reason}")
        
        try:
            # Update call state
            if call_id in self.active_calls:
                from .bridge import CallState
                call_info = self.active_calls[call_id]
                call_info.state = CallState.DISCONNECTED
                call_info.end_time = time.time()
                
            # Close AI connection
            await self.connection_manager.disconnect_call(call_id)
            
            # Close SIP connection
            sip_ws = self.sip_connections.get(call_id)
            if sip_ws and sip_ws.open:
                try:
                    await sip_ws.close()
                except Exception:
                    pass
                    
            # Cleanup RTP session
            await self.rtp_manager.destroy_session(call_id)
            
            # Clear buffers and statistics
            self.audio_buffers.pop(call_id, None)
            self.call_statistics.pop(call_id, None)
            
            # Remove from tracking
            self.active_calls.pop(call_id, None)
            self.sip_connections.pop(call_id, None)
            
            if self.concurrent_calls > 0:
                self.concurrent_calls -= 1
                
        except Exception as e:
            logger.error(f"Error during call cleanup for {call_id}: {e}")
            
    async def _cleanup_loop(self):
        """Periodic cleanup of stale calls."""
        while self.running:
            try:
                current_time = time.time()
                stale_calls = []
                
                for call_id, call_info in self.active_calls.items():
                    # Mark calls as stale if they're older than 4 hours
                    if call_info.start_time and (current_time - call_info.start_time) > 14400:
                        stale_calls.append(call_id)
                        
                for call_id in stale_calls:
                    await self.cleanup_call(call_id, reason="Stale call cleanup")
                    
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)
                
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to AI platform."""
        while self.running:
            try:
                for call_id in list(self.active_calls.keys()):
                    connection = self.connection_manager.get_connection(call_id)
                    if connection:
                        try:
                            await connection.ping()
                        except Exception:
                            # Connection is dead, cleanup
                            await self.cleanup_call(call_id, reason="Heartbeat failed")
                            
                await asyncio.sleep(30)  # Heartbeat every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(30)
                
    def get_statistics(self) -> Dict:
        """Get bridge statistics."""
        uptime = time.time() - self.bridge_start_time
        
        return {
            "uptime_seconds": int(uptime),
            "total_calls_handled": self.total_calls_handled,
            "concurrent_calls": self.concurrent_calls,
            "active_calls": len(self.active_calls),
            "ai_connections": len(self.connection_manager.connections),
            "rtp_sessions": len(self.rtp_manager.sessions),
            "audio_buffers": len(self.audio_buffers),
            "call_stats": {
                call_id: stats.get_stats_dict() 
                for call_id, stats in self.call_statistics.items()
            }
        }