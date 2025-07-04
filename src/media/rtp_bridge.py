"""Custom RTP Bridge that implements RTPproxy protocol for AI platform integration."""
import asyncio
import socket
import struct
import logging
import json
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import threading
import websockets
from ..audio.codecs import AudioProcessor
from ..audio.rtp import RTPHeader
from ..utils.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class MediaSession:
    """Represents an active media session between SIP and AI platform."""
    session_id: str
    caller_ip: str
    caller_port: int
    callee_ip: str
    callee_port: int
    local_ip: str
    local_port: int
    ai_websocket: Optional[websockets.WebSocketServerProtocol] = None
    audio_processor: Optional[AudioProcessor] = None
    created_at: float = 0.0
    last_activity: float = 0.0


class RTPproxy:
    """Custom RTPproxy implementation that bridges SIP RTP to AI platform WebSocket."""
    
    def __init__(self, control_socket_addr: Optional[str] = None, control_port: Optional[int] = None):
        config = get_config()
        self.control_addr = control_socket_addr or config.sip.rtp_proxy_host
        self.control_port = control_port or config.sip.rtp_proxy_port
        self.sessions: Dict[str, MediaSession] = {}
        self.socket_pairs: Dict[int, socket.socket] = {}
        self.audio_processor = AudioProcessor()
        self.running = False
        self.websocket_server = None
        
        # Port range for RTP sessions
        self.rtp_port_start = config.audio.rtp_port_start
        self.rtp_port_end = config.audio.rtp_port_end
        self.current_port = self.rtp_port_start
        self.websocket_port = config.websocket.port
        
    async def start(self):
        """Start the RTP bridge server."""
        logger.info("Starting custom RTP bridge...")
        self.running = True
        
        # Start WebSocket server for AI platform connection
        self.websocket_server = await websockets.serve(
            self.handle_ai_websocket, "0.0.0.0", self.websocket_port
        )
        logger.info(f"AI platform WebSocket server started on port {self.websocket_port}")
        
        # Start RTPproxy control protocol server
        control_task = asyncio.create_task(self.start_control_server())
        
        # Start RTP packet processing
        rtp_task = asyncio.create_task(self.process_rtp_packets())
        
        logger.info("RTP bridge started successfully")
        await asyncio.gather(control_task, rtp_task)
    
    async def start_control_server(self):
        """Start the RTPproxy control protocol server."""
        try:
            # Create UDP socket for control commands
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.control_addr, self.control_port))
            sock.setblocking(False)
            
            logger.info(f"RTPproxy control server listening on {self.control_addr}:{self.control_port}")
            
            while self.running:
                try:
                    data, addr = sock.recvfrom(1024)
                    command = data.decode().strip()
                    logger.info(f"Received RTPproxy command: '{command}' from {addr}")
                    response = self.handle_control_command_sync(command, addr)
                    if response:
                        logger.info(f"Sending response: '{response}' to {addr}")
                        sock.sendto(response.encode(), addr)
                except socket.error as e:
                    if e.errno not in (socket.EAGAIN, socket.EWOULDBLOCK):
                        logger.error(f"Socket error: {e}")
                    pass  # Remove sleep - socket is non-blocking
                except Exception as e:
                    logger.error(f"Error processing command: {e}")
                    pass  # Remove sleep
                    
        except Exception as e:
            logger.error(f"Control server error: {e}")
            raise
    
    def handle_control_command_sync(self, command: str, addr: Tuple[str, int]) -> str:
        """Handle RTPproxy control protocol commands synchronously."""
        try:
            if not command:
                return "E1"
            
            # RTPproxy protocol: [cookie] command [parameters]
            parts = command.split()
            if not parts:
                return "E1"
            
            # First part might be cookie or command
            if len(parts) == 1:
                cmd = parts[0]
                cookie = ""
            else:
                # Could be "cookie V" or just "V"
                if parts[0] in ["V", "I", "Q"]:
                    cmd = parts[0]
                    cookie = ""
                else:
                    cookie = parts[0]
                    cmd = parts[1] if len(parts) > 1 else ""
            
            logger.info(f"Processing command: '{cmd}' with cookie: '{cookie}'")
            
            if cmd == "V":
                # Version command - respond with version (must be immediate)
                logger.info("Responding to version command")
                return "20040107"
            
            elif cmd.startswith("U") or cmd == "U":
                # Update/Create session
                return self.handle_update_command_sync(parts, cookie)
            
            elif cmd.startswith("D") or cmd == "D":
                # Delete session
                return self.handle_delete_command_sync(parts, cookie)
            
            elif cmd == "I":
                # Info command
                active_sessions = len([s for s in self.sessions.values() if time.time() - s.last_activity < 300])
                return f"sessions created: {len(self.sessions)} active: {active_sessions}"
            
            elif cmd == "Q":
                # Quit command
                return "0"
            
            else:
                logger.warning(f"Unknown command: '{cmd}' in '{command}'")
                return "E1"
                
        except Exception as e:
            logger.error(f"Error handling control command '{command}': {e}")
            import traceback
            traceback.print_exc()
            return "E1"
    
    async def handle_control_command(self, command: str, addr: Tuple[str, int]) -> str:
        """Handle RTPproxy control protocol commands."""
        return self.handle_control_command_sync(command, addr)
    
    def handle_update_command_sync(self, parts: list, cookie: str = "") -> str:
        """Handle session update/create command synchronously."""
        try:
            # Parse U command: [cookie] U call_id ip port [from_tag] [to_tag]
            if len(parts) < 4:
                return "E1"
            
            # Extract parameters - adjust for cookie presence
            if not cookie and len(parts) > 1:
                cookie = parts[0] if not parts[0].startswith("U") else ""
            
            # Find U command position
            u_index = 0
            for i, part in enumerate(parts):
                if part.startswith("U"):
                    u_index = i
                    break
            
            if u_index + 3 >= len(parts):
                return "E1"
                
            call_id = parts[u_index + 1]
            remote_ip = parts[u_index + 2] 
            remote_port = int(parts[u_index + 3])
            
            # Allocate local port for RTP
            local_port = self.allocate_rtp_port()
            if not local_port:
                return "E7"  # Port allocation failed
            
            # Create media session
            session_id = f"{call_id}_{cookie}"
            session = MediaSession(
                session_id=session_id,
                caller_ip=remote_ip,
                caller_port=remote_port,
                callee_ip="127.0.0.1",
                callee_port=local_port,
                local_ip="127.0.0.1",
                local_port=local_port,
                audio_processor=AudioProcessor(),
                created_at=time.time(),
                last_activity=time.time()
            )
            
            self.sessions[session_id] = session
            
            # Create RTP socket for this session (sync version)
            self.create_rtp_socket_sync(session)
            
            logger.info(f"Created RTP session {session_id}: {remote_ip}:{remote_port} -> 127.0.0.1:{local_port}")
            
            # Return allocated port to Kamailio
            return f"{local_port}"
            
        except Exception as e:
            logger.error(f"Error in update command: {e}")
            return "E1"
    
    async def handle_update_command(self, parts: list, cookie: str = "") -> str:
        """Handle session update/create command."""
        return self.handle_update_command_sync(parts, cookie)
    
    def handle_delete_command_sync(self, parts: list, cookie: str = "") -> str:
        """Handle session delete command synchronously."""
        try:
            if len(parts) < 2 and not cookie:
                return "E1"
            
            if not cookie:
                cookie = parts[1] if len(parts) > 1 else parts[0]
            
            # Find and remove session by cookie
            sessions_to_remove = [sid for sid in self.sessions if cookie in sid]
            
            for session_id in sessions_to_remove:
                session = self.sessions.pop(session_id, None)
                if session:
                    # Close WebSocket connection (sync)
                    if session.ai_websocket:
                        session.ai_websocket = None
                    
                    # Close RTP socket
                    if session.local_port in self.socket_pairs:
                        self.socket_pairs[session.local_port].close()
                        del self.socket_pairs[session.local_port]
                    
                    logger.info(f"Deleted RTP session {session_id}")
            
            return "0"
            
        except Exception as e:
            logger.error(f"Error in delete command: {e}")
            return "E1"
    
    async def handle_delete_command(self, parts: list, cookie: str = "") -> str:
        """Handle session delete command."""
        return self.handle_delete_command_sync(parts, cookie)
    
    def allocate_rtp_port(self) -> Optional[int]:
        """Allocate an available RTP port."""
        for _ in range(100):  # Try 100 ports
            port = self.current_port
            self.current_port += 2  # RTP uses even ports, RTCP uses odd
            if self.current_port >= self.rtp_port_end:
                self.current_port = self.rtp_port_start
            
            try:
                # Test if port is available
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                test_sock.bind(("127.0.0.1", port))
                test_sock.close()
                return port
            except socket.error:
                continue
        
        return None
    
    def create_rtp_socket_sync(self, session: MediaSession):
        """Create RTP socket for a media session synchronously."""
        try:
            # Create UDP socket for RTP
            rtp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rtp_sock.bind(("127.0.0.1", session.local_port))
            rtp_sock.setblocking(False)
            
            self.socket_pairs[session.local_port] = rtp_sock
            
            logger.info(f"Created RTP socket for session {session.session_id} on port {session.local_port}")
            
        except Exception as e:
            logger.error(f"Error creating RTP socket: {e}")
    
    async def create_rtp_socket(self, session: MediaSession):
        """Create RTP socket for a media session."""
        self.create_rtp_socket_sync(session)
    
    async def process_rtp_packets(self):
        """Process incoming RTP packets and forward to AI platform."""
        while self.running:
            try:
                # Process packets for each active session
                for session in list(self.sessions.values()):
                    if session.local_port in self.socket_pairs:
                        await self.process_session_packets(session)
                
                await asyncio.sleep(0)  # Yield control to other tasks
                
            except Exception as e:
                logger.error(f"Error processing RTP packets: {e}")
                await asyncio.sleep(1)
    
    async def process_session_packets(self, session: MediaSession):
        """Process RTP packets for a specific session."""
        try:
            sock = self.socket_pairs.get(session.local_port)
            if not sock:
                return
            
            try:
                data, addr = sock.recvfrom(1500)
                session.last_activity = time.time()
                
                # Parse RTP header
                if len(data) < 12:
                    return
                
                header = RTPHeader.parse(data)
                payload = data[12:]  # Skip RTP header
                
                # Convert audio if needed
                if header.payload_type == 0:  # PCMU
                    pcm_data = session.audio_processor.convert_format(payload, "PCMU", "PCM")
                elif header.payload_type == 8:  # PCMA  
                    pcm_data = session.audio_processor.convert_format(payload, "PCMA", "PCM")
                else:
                    pcm_data = payload  # Assume PCM
                
                # Forward to AI platform via WebSocket
                if session.ai_websocket:
                    await self.send_audio_to_ai(session, pcm_data, header)
                
            except socket.error:
                # No data available
                pass
                
        except Exception as e:
            logger.error(f"Error processing session packets: {e}")
    
    async def send_audio_to_ai(self, session: MediaSession, audio_data: bytes, rtp_header: RTPHeader):
        """Send audio data to AI platform via WebSocket."""
        try:
            if not session.ai_websocket:
                return
            
            # Create message for AI platform
            message = {
                "type": "audio_data",
                "session_id": session.session_id,
                "timestamp": rtp_header.timestamp,
                "sequence": rtp_header.sequence_number,
                "audio_data": audio_data.hex(),  # Send as hex string
                "sample_rate": get_config().audio.sample_rate,
                "channels": 1,
                "format": "pcm"
            }
            
            await session.ai_websocket.send(json.dumps(message))
            
        except Exception as e:
            logger.error(f"Error sending audio to AI platform: {e}")
    
    async def handle_ai_websocket(self, websocket, path):
        """Handle WebSocket connection from AI platform."""
        logger.info(f"AI platform connected from {websocket.remote_address}")
        
        try:
            # Find available session to attach to
            available_session = None
            for session in self.sessions.values():
                if session.ai_websocket is None:
                    session.ai_websocket = websocket
                    available_session = session
                    break
            
            if not available_session:
                logger.warning("No available session for AI platform connection")
                await websocket.close()
                return
            
            logger.info(f"Attached AI platform to session {available_session.session_id}")
            
            # Handle messages from AI platform
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_ai_message(available_session, data)
                except json.JSONDecodeError:
                    logger.error("Invalid JSON from AI platform")
                
        except websockets.exceptions.ConnectionClosed:
            logger.info("AI platform disconnected")
        except Exception as e:
            logger.error(f"Error handling AI WebSocket: {e}")
        finally:
            # Clean up session
            if available_session:
                available_session.ai_websocket = None
    
    async def handle_ai_message(self, session: MediaSession, data: dict):
        """Handle message from AI platform."""
        try:
            msg_type = data.get("type")
            
            if msg_type == "audio_response":
                # Convert AI audio response back to RTP
                audio_hex = data.get("audio_data", "")
                audio_data = bytes.fromhex(audio_hex)
                
                # Convert PCM to telephony format (PCMU)
                telephony_data = session.audio_processor.convert_format(audio_data, "PCM", "PCMU")
                
                # Send back to SIP caller
                await self.send_rtp_to_caller(session, telephony_data)
                
        except Exception as e:
            logger.error(f"Error handling AI message: {e}")
    
    async def send_rtp_to_caller(self, session: MediaSession, audio_data: bytes):
        """Send RTP packet back to SIP caller."""
        try:
            if session.local_port not in self.socket_pairs:
                return
            
            sock = self.socket_pairs[session.local_port]
            
            # Create RTP header
            # This is a simplified RTP packet creation
            rtp_header = struct.pack('!BBHII',
                0x80,  # V=2, P=0, X=0, CC=0
                0,     # M=0, PT=0 (PCMU)
                0,     # Sequence number (should be tracked)
                int(time.time() * 8000) & 0xFFFFFFFF,  # Timestamp
                12345  # SSRC
            )
            
            rtp_packet = rtp_header + audio_data
            
            # Send to caller
            sock.sendto(rtp_packet, (session.caller_ip, session.caller_port))
            
        except Exception as e:
            logger.error(f"Error sending RTP to caller: {e}")


async def main():
    """Main entry point for RTP bridge."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    bridge = RTPproxy()
    try:
        await bridge.start()
    except KeyboardInterrupt:
        logger.info("RTP bridge stopped")
    except Exception as e:
        logger.error(f"RTP bridge error: {e}")


if __name__ == "__main__":
    asyncio.run(main())