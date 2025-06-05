"""Advanced WebSocket bridge for connecting SIP calls to AI platform."""
import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Optional, Callable, Set, Any
import websockets
from websockets.legacy.server import WebSocketServerProtocol
from websockets.legacy.client import WebSocketClientProtocol
from dataclasses import dataclass, asdict
from enum import Enum
import struct
import base64
import traceback
from collections import deque, defaultdict

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ..audio.codecs import AudioProcessor
from ..audio.rtp import RTPManager, RTPSession, RTPStatistics
from ..utils.config import get_config

logger = logging.getLogger(__name__)


class CallState(Enum):
    """Call states."""
    INITIALIZING = "initializing"
    CONNECTING = "connecting"
    RINGING = "ringing"
    CONNECTED = "connected"
    ON_HOLD = "on_hold"
    TRANSFERRING = "transferring"
    ENDING = "ending"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class MessageType(Enum):
    """WebSocket message types."""
    CALL_START = "call_start"
    CALL_ANSWER = "call_answer"
    CALL_END = "call_end"
    CALL_HOLD = "call_hold"
    CALL_RESUME = "call_resume"
    CALL_TRANSFER = "call_transfer"
    AUDIO_DATA = "audio_data"
    AUDIO_START = "audio_start"
    AUDIO_STOP = "audio_stop"
    DTMF = "dtmf"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    STATUS = "status"


@dataclass
class CallInfo:
    """Enhanced call information."""
    call_id: str
    from_number: str
    to_number: str
    sip_headers: Dict[str, str]
    state: CallState = CallState.INITIALIZING
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    rtp_local_port: Optional[int] = None
    rtp_remote_host: Optional[str] = None
    rtp_remote_port: Optional[int] = None
    codec: str = "PCMU"
    ai_session_id: Optional[str] = None


class AudioBuffer:
    """Advanced audio buffering with jitter control."""
    
    def __init__(self, max_frames: int = 10, target_delay_ms: int = 60):
        self.max_frames = max_frames
        self.target_delay_ms = target_delay_ms
        self.frames = deque(maxlen=max_frames)
        self.frame_times = deque(maxlen=max_frames)
        self.total_bytes = 0
        
    def add_frame(self, audio_data: bytes) -> None:
        """Add audio frame to buffer."""
        current_time = time.time()
        
        if len(self.frames) >= self.max_frames:
            # Remove oldest frame
            old_frame = self.frames.popleft()
            self.frame_times.popleft()
            self.total_bytes -= len(old_frame)
            
        self.frames.append(audio_data)
        self.frame_times.append(current_time)
        self.total_bytes += len(audio_data)
        
    def get_frame(self) -> Optional[bytes]:
        """Get next audio frame if ready."""
        if not self.frames:
            return None
            
        # Check if we should delay playback for jitter control
        current_time = time.time()
        frame_time = self.frame_times[0]
        age_ms = (current_time - frame_time) * 1000
        
        if age_ms >= self.target_delay_ms or len(self.frames) >= self.max_frames:
            self.frame_times.popleft()
            frame = self.frames.popleft()
            self.total_bytes -= len(frame)
            return frame
            
        return None
        
    def clear(self) -> None:
        """Clear all buffered frames."""
        self.frames.clear()
        self.frame_times.clear()
        self.total_bytes = 0
        
    def get_buffer_level(self) -> float:
        """Get buffer level (0.0 to 1.0)."""
        return len(self.frames) / self.max_frames if self.max_frames > 0 else 0.0


class ConnectionManager:
    """Manages AI platform connections with reconnection logic."""
    
    def __init__(self, ai_platform_url: str, max_retries: int = 5):
        self.ai_platform_url = ai_platform_url
        self.max_retries = max_retries
        self.connections: Dict[str, WebSocketClientProtocol] = {}
        self.connection_tasks: Dict[str, asyncio.Task] = {}
        self.retry_counts: Dict[str, int] = defaultdict(int)
        
    async def connect_for_call(self, call_id: str, call_info: CallInfo) -> Optional[WebSocketClientProtocol]:
        """Create AI platform connection for a call."""
        try:
            # Generate unique session ID
            session_id = str(uuid.uuid4())
            call_info.ai_session_id = session_id
            
            # Connect with custom headers
            extra_headers = {
                "X-Call-ID": call_id,
                "X-Session-ID": session_id,
                "X-From-Number": call_info.from_number,
                "X-To-Number": call_info.to_number,
                "X-Source": "sip-server"
            }
            
            connection = await websockets.connect(
                self.ai_platform_url,
                extra_headers=extra_headers,
                ping_interval=30,
                ping_timeout=10
            )
            
            self.connections[call_id] = connection
            self.retry_counts[call_id] = 0
            
            # Send initial call start message
            await self._send_call_start(connection, call_info)
            
            logger.info(f"Connected to AI platform for call {call_id}")
            return connection
            
        except Exception as e:
            logger.error(f"Failed to connect to AI platform for call {call_id}: {e}")
            self.retry_counts[call_id] += 1
            
            if self.retry_counts[call_id] < self.max_retries:
                # Schedule retry
                await asyncio.sleep(2 ** self.retry_counts[call_id])  # Exponential backoff
                return await self.connect_for_call(call_id, call_info)
            
            return None
            
    async def _send_call_start(self, connection: WebSocketClientProtocol, call_info: CallInfo) -> None:
        """Send call start message to AI platform with authentication."""
        # Create authentication message first
        auth_message = {
            "type": "auth",
            "auth": {
                "token": f"Bearer {call_info.ai_session_id}",
                "signature": "dummy_signature",  # Would be real HMAC in production
                "timestamp": str(int(time.time())),
                "call_id": call_info.call_id
            },
            "call": {
                "conversation_id": call_info.call_id,  # Use call_id as conversation_id for now
                "from_number": call_info.from_number,
                "to_number": call_info.to_number,
                "direction": "incoming",
                "sip_headers": call_info.sip_headers,
                "codec": call_info.codec,
                "sample_rate": get_config().audio.sample_rate
            }
        }
        await connection.send(json.dumps(auth_message))
        
    async def disconnect_call(self, call_id: str) -> None:
        """Disconnect AI platform connection for a call."""
        if call_id in self.connections:
            try:
                connection = self.connections[call_id]
                
                # Send call end message
                message = {
                    "type": MessageType.CALL_END.value,
                    "data": {
                        "call_id": call_id,
                        "timestamp": time.time()
                    }
                }
                await connection.send(json.dumps(message))
                await connection.close()
                
            except Exception as e:
                logger.error(f"Error disconnecting call {call_id}: {e}")
            finally:
                del self.connections[call_id]
                self.retry_counts.pop(call_id, None)
                
        if call_id in self.connection_tasks:
            self.connection_tasks[call_id].cancel()
            del self.connection_tasks[call_id]
            
    def get_connection(self, call_id: str) -> Optional[WebSocketClientProtocol]:
        """Get AI platform connection for a call."""
        return self.connections.get(call_id)
        
    async def send_audio(self, call_id: str, audio_data: bytes) -> bool:
        """Send audio data to AI platform."""
        connection = self.connections.get(call_id)
        if not connection:
            return False
            
        try:
            # Encode audio as base64 for JSON transport
            audio_b64 = base64.b64encode(audio_data).decode('utf-8')
            
            message = {
                "type": MessageType.AUDIO_DATA.value,
                "data": {
                    "call_id": call_id,
                    "audio": audio_b64,
                    "timestamp": time.time(),
                    "sequence": int(time.time() * 1000) % 65536  # Simple sequence number
                }
            }
            
            await connection.send(json.dumps(message))
            return True
            
        except Exception as e:
            logger.error(f"Error sending audio for call {call_id}: {e}")
            return False


class WebSocketBridge:
    """Advanced WebSocket bridge between SIP server and AI platform."""
    
    def __init__(self, ai_platform_url: Optional[str] = None, sip_ws_port: Optional[int] = None,
                 rtp_port_range: Optional[tuple] = None):
        config = get_config()
        self.ai_platform_url = ai_platform_url or config.websocket.ai_platform_url
        self.sip_ws_port = sip_ws_port or config.websocket.port
        self.rtp_port_range = rtp_port_range or (config.audio.rtp_port_start, config.audio.rtp_port_end)
        
        # Core components
        self.audio_processor = AudioProcessor()
        self.rtp_manager = RTPManager(self.rtp_port_range)
        self.connection_manager = ConnectionManager(self.ai_platform_url)
        
        # Call tracking
        self.active_calls: Dict[str, CallInfo] = {}
        self.sip_connections: Dict[str, WebSocketServerProtocol] = {}
        self.audio_buffers: Dict[str, AudioBuffer] = {}
        self.call_statistics: Dict[str, RTPStatistics] = {}
        
        # Performance monitoring
        self.total_calls_handled = 0
        self.concurrent_calls = 0
        self.bridge_start_time = time.time()
        
        # Control flags
        self.running = False
        self.cleanup_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Start the WebSocket bridge with all components."""
        logger.info("Starting advanced WebSocket bridge...")
        self.running = True
        
        # Start SIP WebSocket server
        sip_server = await websockets.serve(
            self.handle_sip_connection,
            "0.0.0.0",
            self.sip_ws_port,
            ping_interval=30,
            ping_timeout=10
        )
        logger.info(f"SIP WebSocket server listening on port {self.sip_ws_port}")
        
        # Start cleanup task
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        # Start heartbeat task
        asyncio.create_task(self._heartbeat_loop())
        
        logger.info("WebSocket bridge started successfully")
        
        # Keep the server running
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            await self.stop()
            
    async def stop(self):
        """Stop the WebSocket bridge and cleanup resources."""
        logger.info("Stopping WebSocket bridge...")
        self.running = False
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            
        # Cleanup all active calls
        for call_id in list(self.active_calls.keys()):
            await self.cleanup_call(call_id, reason="Bridge shutdown")
            
        # Cleanup RTP manager
        await self.rtp_manager.cleanup_all()
        
        logger.info("WebSocket bridge stopped")


# Import handlers mixin
from .bridge_handlers import BridgeHandlers

# Make WebSocketBridge inherit from BridgeHandlers
class AdvancedWebSocketBridge(WebSocketBridge, BridgeHandlers):
    """Complete WebSocket bridge with all handler methods."""
    pass


# Use the advanced bridge as the main class
WebSocketBridge = AdvancedWebSocketBridge


async def main():
    """Run the WebSocket bridge."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create and start bridge with default configuration
    bridge = WebSocketBridge()
    await bridge.start()


if __name__ == "__main__":
    asyncio.run(main())