"""RTPEngine client for media handling and NAT traversal."""
import asyncio
import json
import logging
import socket
import struct
import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import bencodepy

logger = logging.getLogger(__name__)


class RTPDirection(Enum):
    """RTP media direction."""
    SENDRECV = "sendrecv"
    SENDONLY = "sendonly" 
    RECVONLY = "recvonly"
    INACTIVE = "inactive"


class TransportProtocol(Enum):
    """Transport protocols."""
    UDP = "UDP"
    TCP = "TCP"
    TLS = "TLS"
    DTLS = "DTLS"


@dataclass
class MediaAddress:
    """Media endpoint address."""
    address: str
    port: int
    family: str = "IP4"  # IP4 or IP6
    
    def __str__(self):
        return f"{self.address}:{self.port}"


@dataclass 
class CodecInfo:
    """Codec information."""
    payload_type: int
    codec_name: str
    clock_rate: int
    channels: int = 1
    fmtp: Optional[str] = None
    
    def __str__(self):
        return f"{self.payload_type} {self.codec_name}/{self.clock_rate}/{self.channels}"


@dataclass
class RTPSession:
    """RTP session information."""
    call_id: str
    from_tag: str
    to_tag: Optional[str] = None
    
    # Media information
    caller_address: Optional[MediaAddress] = None
    callee_address: Optional[MediaAddress] = None
    allocated_address: Optional[MediaAddress] = None
    
    # Session parameters
    direction: RTPDirection = RTPDirection.SENDRECV
    transport: TransportProtocol = TransportProtocol.UDP
    codecs: List[CodecInfo] = field(default_factory=list)
    
    # RTPEngine specific
    rtpengine_session_id: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    
    # Statistics
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    
    def is_active(self) -> bool:
        """Check if session is active."""
        return self.rtpengine_session_id is not None


class RTPEngineClient:
    """Client for communicating with RTPEngine."""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 2223, 
                 control_port: int = 9900, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.control_port = control_port
        self.timeout = timeout
        
        # Socket for communication
        self.sock: Optional[socket.socket] = None
        
        # Active sessions
        self.sessions: Dict[str, RTPSession] = {}
        
        # Statistics
        self.total_offers = 0
        self.total_answers = 0
        self.total_deletes = 0
        self.failed_operations = 0
        
    async def start(self):
        """Start RTPEngine client."""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.settimeout(self.timeout)
            
            # Test connectivity
            await self._ping()
            
            logger.info(f"RTPEngine client started, connected to {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start RTPEngine client: {e}")
            raise
    
    async def stop(self):
        """Stop RTPEngine client."""
        try:
            # Delete all active sessions
            for session_key in list(self.sessions.keys()):
                await self.delete_session(session_key)
            
            # Close socket
            if self.sock:
                self.sock.close()
                self.sock = None
                
            logger.info("RTPEngine client stopped")
            
        except Exception as e:
            logger.error(f"Error stopping RTPEngine client: {e}")
    
    async def offer(self, call_id: str, from_tag: str, 
                   caller_sdp: str, **kwargs) -> Tuple[str, RTPSession]:
        """Handle SIP INVITE offer."""
        try:
            session_key = f"{call_id}_{from_tag}"
            
            # Parse caller SDP
            caller_media = self._parse_sdp_media(caller_sdp)
            
            # Create session
            session = RTPSession(
                call_id=call_id,
                from_tag=from_tag,
                caller_address=caller_media.get("address"),
                direction=RTPDirection(kwargs.get("direction", "sendrecv")),
                transport=TransportProtocol(kwargs.get("transport", "UDP")),
                codecs=caller_media.get("codecs", [])
            )
            
            # Prepare RTPEngine request
            request = {
                "command": "offer",
                "call-id": call_id,
                "from-tag": from_tag,
                "sdp": caller_sdp,
                "replace": ["origin", "session-connection"],
                "flags": self._build_flags(**kwargs),
                "received-from": kwargs.get("received_from", ["IP4", self.host]),
                "ICE": kwargs.get("ice", "remove"),
                "transport-protocol": session.transport.value,
                "media-address": kwargs.get("media_address")
            }
            
            # Remove None values
            request = {k: v for k, v in request.items() if v is not None}
            
            # Send request
            response = await self._send_request(request)
            
            if response.get("result") == "ok":
                # Update session with allocated address
                session.rtpengine_session_id = session_key
                session.allocated_address = self._parse_allocated_address(response)
                
                # Store session
                self.sessions[session_key] = session
                self.total_offers += 1
                
                # Return modified SDP
                return response["sdp"], session
            else:
                self.failed_operations += 1
                error = response.get("error-reason", "Unknown error")
                raise Exception(f"RTPEngine offer failed: {error}")
                
        except Exception as e:
            logger.error(f"Error in RTPEngine offer: {e}")
            raise
    
    async def answer(self, call_id: str, from_tag: str, to_tag: str,
                    callee_sdp: str, **kwargs) -> Tuple[str, RTPSession]:
        """Handle SIP 200 OK answer."""
        try:
            session_key = f"{call_id}_{from_tag}"
            session = self.sessions.get(session_key)
            
            if not session:
                raise Exception(f"No session found for {session_key}")
            
            # Update session
            session.to_tag = to_tag
            
            # Parse callee SDP
            callee_media = self._parse_sdp_media(callee_sdp)
            session.callee_address = callee_media.get("address")
            
            # Prepare RTPEngine request
            request = {
                "command": "answer",
                "call-id": call_id,
                "from-tag": from_tag,
                "to-tag": to_tag,
                "sdp": callee_sdp,
                "replace": ["origin", "session-connection"],
                "flags": self._build_flags(**kwargs),
                "transport-protocol": session.transport.value
            }
            
            # Remove None values
            request = {k: v for k, v in request.items() if v is not None}
            
            # Send request
            response = await self._send_request(request)
            
            if response.get("result") == "ok":
                self.total_answers += 1
                
                # Return modified SDP
                return response["sdp"], session
            else:
                self.failed_operations += 1
                error = response.get("error-reason", "Unknown error")
                raise Exception(f"RTPEngine answer failed: {error}")
                
        except Exception as e:
            logger.error(f"Error in RTPEngine answer: {e}")
            raise
    
    async def delete_session(self, session_key: str, **kwargs) -> bool:
        """Delete RTP session."""
        try:
            session = self.sessions.get(session_key)
            if not session:
                logger.warning(f"Session {session_key} not found for deletion")
                return False
            
            # Prepare RTPEngine request
            request = {
                "command": "delete",
                "call-id": session.call_id,
                "from-tag": session.from_tag
            }
            
            if session.to_tag:
                request["to-tag"] = session.to_tag
            
            # Send request
            response = await self._send_request(request)
            
            if response.get("result") == "ok":
                # Remove session
                del self.sessions[session_key]
                self.total_deletes += 1
                
                logger.info(f"Deleted RTPEngine session: {session_key}")
                return True
            else:
                self.failed_operations += 1
                error = response.get("error-reason", "Unknown error")
                logger.error(f"RTPEngine delete failed: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting RTPEngine session: {e}")
            return False
    
    async def query_session(self, call_id: str, from_tag: str) -> Optional[Dict[str, Any]]:
        """Query session statistics."""
        try:
            request = {
                "command": "query",
                "call-id": call_id,
                "from-tag": from_tag
            }
            
            response = await self._send_request(request)
            
            if response.get("result") == "ok":
                return response
            else:
                error = response.get("error-reason", "Unknown error")
                logger.error(f"RTPEngine query failed: {error}")
                return None
                
        except Exception as e:
            logger.error(f"Error querying RTPEngine session: {e}")
            return None
    
    async def start_recording(self, call_id: str, from_tag: str, 
                             recording_params: Dict[str, Any]) -> bool:
        """Start call recording."""
        try:
            request = {
                "command": "start recording",
                "call-id": call_id,
                "from-tag": from_tag,
                "flags": ["PCM"],  # Record in PCM format
                "metadata": recording_params.get("metadata", {}),
                "output-destination": recording_params.get("output_file")
            }
            
            # Remove None values
            request = {k: v for k, v in request.items() if v is not None}
            
            response = await self._send_request(request)
            
            if response.get("result") == "ok":
                logger.info(f"Started recording for session {call_id}_{from_tag}")
                return True
            else:
                error = response.get("error-reason", "Unknown error")
                logger.error(f"RTPEngine start recording failed: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Error starting recording: {e}")
            return False
    
    async def stop_recording(self, call_id: str, from_tag: str) -> bool:
        """Stop call recording."""
        try:
            request = {
                "command": "stop recording",
                "call-id": call_id,
                "from-tag": from_tag
            }
            
            response = await self._send_request(request)
            
            if response.get("result") == "ok":
                logger.info(f"Stopped recording for session {call_id}_{from_tag}")
                return True
            else:
                error = response.get("error-reason", "Unknown error")
                logger.error(f"RTPEngine stop recording failed: {error}")
                return False
                
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            return False
    
    async def _ping(self) -> bool:
        """Ping RTPEngine to test connectivity."""
        try:
            request = {"command": "ping"}
            response = await self._send_request(request)
            
            return response.get("result") == "pong"
            
        except Exception as e:
            logger.error(f"RTPEngine ping failed: {e}")
            return False
    
    async def _send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send request to RTPEngine."""
        try:
            if not self.sock:
                raise Exception("RTPEngine client not started")
            
            # Encode request using bencode
            encoded_request = bencodepy.encode(request)
            
            # Send request
            self.sock.sendto(encoded_request, (self.host, self.port))
            
            # Receive response
            data, addr = self.sock.recvfrom(65536)
            
            # Decode response
            response = bencodepy.decode(data)
            
            # Convert bytes to strings in response
            response = self._convert_bytes_to_str(response)
            
            return response
            
        except socket.timeout:
            raise Exception("RTPEngine request timeout")
        except Exception as e:
            logger.error(f"RTPEngine communication error: {e}")
            raise
    
    def _build_flags(self, **kwargs) -> List[str]:
        """Build flags list for RTPEngine request."""
        flags = []
        
        # Common flags
        if kwargs.get("ice_remove"):
            flags.append("ICE=remove")
        
        if kwargs.get("generate_mid"):
            flags.append("generate-mid")
        
        if kwargs.get("loop_protect"):
            flags.append("loop-protect")
        
        if kwargs.get("replace_origin"):
            flags.append("replace-origin")
        
        if kwargs.get("replace_session_connection"):
            flags.append("replace-session-connection")
        
        # DTLS/SRTP flags
        if kwargs.get("dtls"):
            flags.append("DTLS=passive")
        
        if kwargs.get("sdes"):
            flags.append("SDES")
        
        # Codec flags
        if kwargs.get("transcode"):
            codec = kwargs.get("transcode_codec", "PCMU")
            flags.append(f"transcode-{codec}")
        
        # Recording flags
        if kwargs.get("record_call"):
            flags.append("record-call")
        
        return flags
    
    def _parse_sdp_media(self, sdp: str) -> Dict[str, Any]:
        """Parse SDP for media information."""
        try:
            lines = sdp.strip().split('\n')
            media_info = {
                "address": None,
                "port": None,
                "codecs": []
            }
            
            # Parse connection line
            for line in lines:
                line = line.strip()
                
                if line.startswith("c="):
                    # Connection line: c=IN IP4 192.168.1.100
                    parts = line.split()
                    if len(parts) >= 3:
                        media_info["address"] = MediaAddress(
                            address=parts[2],
                            port=0,  # Will be set from m= line
                            family=parts[1]
                        )
                
                elif line.startswith("m="):
                    # Media line: m=audio 5004 RTP/AVP 0 8
                    parts = line.split()
                    if len(parts) >= 3:
                        if media_info["address"]:
                            media_info["address"].port = int(parts[1])
                        else:
                            media_info["address"] = MediaAddress(
                                address="0.0.0.0",
                                port=int(parts[1])
                            )
                        
                        # Parse codec payload types
                        for pt in parts[3:]:
                            try:
                                media_info["codecs"].append(CodecInfo(
                                    payload_type=int(pt),
                                    codec_name="unknown",
                                    clock_rate=8000
                                ))
                            except ValueError:
                                continue
                
                elif line.startswith("a=rtpmap:"):
                    # RTP map: a=rtpmap:0 PCMU/8000
                    parts = line.split()
                    if len(parts) >= 2:
                        pt_codec = parts[1].split()
                        if len(pt_codec) >= 2:
                            try:
                                pt = int(pt_codec[0])
                                codec_info = pt_codec[1].split('/')
                                
                                # Find and update codec info
                                for codec in media_info["codecs"]:
                                    if codec.payload_type == pt:
                                        codec.codec_name = codec_info[0]
                                        if len(codec_info) > 1:
                                            codec.clock_rate = int(codec_info[1])
                                        if len(codec_info) > 2:
                                            codec.channels = int(codec_info[2])
                                        break
                            except (ValueError, IndexError):
                                continue
            
            return media_info
            
        except Exception as e:
            logger.error(f"Error parsing SDP: {e}")
            return {"address": None, "port": None, "codecs": []}
    
    def _parse_allocated_address(self, response: Dict[str, Any]) -> Optional[MediaAddress]:
        """Parse allocated address from RTPEngine response."""
        try:
            # RTPEngine returns allocated address in various formats
            if "sdp" in response:
                return self._parse_sdp_media(response["sdp"]).get("address")
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing allocated address: {e}")
            return None
    
    def _convert_bytes_to_str(self, obj: Any) -> Any:
        """Recursively convert bytes to strings in bencode response."""
        if isinstance(obj, bytes):
            try:
                return obj.decode('utf-8')
            except UnicodeDecodeError:
                return obj
        elif isinstance(obj, dict):
            return {self._convert_bytes_to_str(k): self._convert_bytes_to_str(v) 
                   for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_bytes_to_str(item) for item in obj]
        else:
            return obj
    
    def get_session(self, call_id: str, from_tag: str) -> Optional[RTPSession]:
        """Get RTP session."""
        session_key = f"{call_id}_{from_tag}"
        return self.sessions.get(session_key)
    
    def get_all_sessions(self) -> List[RTPSession]:
        """Get all active sessions."""
        return list(self.sessions.values())
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get RTPEngine client statistics."""
        return {
            "total_offers": self.total_offers,
            "total_answers": self.total_answers,
            "total_deletes": self.total_deletes,
            "failed_operations": self.failed_operations,
            "active_sessions": len(self.sessions),
            "success_rate": (self.total_offers + self.total_answers + self.total_deletes) / 
                          max(self.total_offers + self.total_answers + self.total_deletes + self.failed_operations, 1)
        }
    
    async def cleanup(self):
        """Cleanup client resources."""
        try:
            await self.stop()
            logger.info("RTPEngine client cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up RTPEngine client: {e}")