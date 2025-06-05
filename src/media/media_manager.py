"""Media Manager for coordinating RTPEngine and media streams."""
import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

from .rtpengine_client import RTPEngineClient, RTPSession
from .codec_handler import CodecHandler, SupportedCodec

logger = logging.getLogger(__name__)


class MediaDirection(Enum):
    """Media stream direction."""
    SENDRECV = "sendrecv"
    SENDONLY = "sendonly"
    RECVONLY = "recvonly"
    INACTIVE = "inactive"


class MediaType(Enum):
    """Media stream types."""
    AUDIO = "audio"
    VIDEO = "video"
    APPLICATION = "application"


@dataclass
class MediaStream:
    """Media stream information."""
    call_id: str
    stream_id: str
    media_type: MediaType
    direction: MediaDirection
    codec: SupportedCodec
    
    # RTP information
    local_address: Optional[str] = None
    local_port: Optional[int] = None
    remote_address: Optional[str] = None
    remote_port: Optional[int] = None
    
    # Stream state
    is_active: bool = False
    is_on_hold: bool = False
    is_recording: bool = False
    
    # Statistics
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    packet_loss: float = 0.0
    jitter: float = 0.0
    rtt: float = 0.0
    
    # Timestamps
    created_at: float = field(default_factory=time.time)
    last_packet_time: Optional[float] = None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get stream statistics."""
        duration = time.time() - self.created_at
        
        return {
            "call_id": self.call_id,
            "stream_id": self.stream_id,
            "media_type": self.media_type.value,
            "direction": self.direction.value,
            "codec": self.codec.value,
            "is_active": self.is_active,
            "is_on_hold": self.is_on_hold,
            "is_recording": self.is_recording,
            "duration_seconds": duration,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "packet_loss_percentage": self.packet_loss * 100,
            "jitter_ms": self.jitter,
            "rtt_ms": self.rtt,
            "bitrate_kbps": (self.bytes_sent + self.bytes_received) * 8 / max(duration * 1000, 1)
        }


class MediaManager:
    """Main media manager coordinating RTPEngine and streams."""
    
    def __init__(self, rtpengine_host: str = "127.0.0.1", rtpengine_port: int = 2223):
        # RTPEngine client
        self.rtpengine = RTPEngineClient(rtpengine_host, rtpengine_port)
        
        # Codec handler
        self.codec_handler = CodecHandler()
        
        # Active media streams
        self.streams: Dict[str, MediaStream] = {}  # call_id -> stream
        self.rtp_sessions: Dict[str, RTPSession] = {}  # call_id -> RTP session
        
        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}
        
        # Configuration
        self.default_codec = SupportedCodec.PCMU
        self.enable_transcoding = True
        self.enable_recording = False
        self.recording_format = "wav"
        
        # Statistics
        self.total_streams = 0
        self.active_streams = 0
        self.failed_setups = 0
        
    async def start(self):
        """Start media manager."""
        try:
            await self.rtpengine.start()
            logger.info("Media manager started")
            
        except Exception as e:
            logger.error(f"Failed to start media manager: {e}")
            raise
    
    async def stop(self):
        """Stop media manager."""
        try:
            # End all streams
            for call_id in list(self.streams.keys()):
                await self.end_media_session(call_id)
            
            # Stop RTPEngine
            await self.rtpengine.stop()
            
            logger.info("Media manager stopped")
            
        except Exception as e:
            logger.error(f"Error stopping media manager: {e}")
    
    async def setup_media_session(self, call_id: str, from_tag: str, 
                                 caller_sdp: str, **kwargs) -> Dict[str, Any]:
        """Setup media session for incoming call (offer)."""
        try:
            logger.info(f"Setting up media session for call {call_id}")
            
            # Create media stream
            stream = MediaStream(
                call_id=call_id,
                stream_id=f"{call_id}_{from_tag}",
                media_type=MediaType.AUDIO,  # Default to audio
                direction=MediaDirection.SENDRECV,
                codec=self._determine_codec(caller_sdp)
            )
            
            # Setup RTPEngine offer
            offer_kwargs = {
                "direction": stream.direction.value,
                "transport": "UDP",
                "replace_origin": True,
                "replace_session_connection": True,
                "ice_remove": True,
                **kwargs
            }
            
            # Add transcoding if needed
            if self.enable_transcoding and kwargs.get("target_codec"):
                offer_kwargs["transcode"] = True
                offer_kwargs["transcode_codec"] = kwargs["target_codec"]
            
            # Send offer to RTPEngine
            modified_sdp, rtp_session = await self.rtpengine.offer(
                call_id, from_tag, caller_sdp, **offer_kwargs
            )
            
            # Store sessions
            self.streams[call_id] = stream
            self.rtp_sessions[call_id] = rtp_session
            
            # Update stream with RTP information
            if rtp_session.allocated_address:
                stream.local_address = rtp_session.allocated_address.address
                stream.local_port = rtp_session.allocated_address.port
            
            stream.is_active = True
            
            # Update statistics
            self.total_streams += 1
            self.active_streams += 1
            
            # Emit event
            await self._emit_event("media_session_setup", stream)
            
            logger.info(f"Media session setup complete for call {call_id}")
            
            return {
                "success": True,
                "modified_sdp": modified_sdp,
                "stream_info": stream.get_statistics()
            }
            
        except Exception as e:
            self.failed_setups += 1
            logger.error(f"Failed to setup media session for call {call_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def answer_media_session(self, call_id: str, from_tag: str, to_tag: str,
                                  callee_sdp: str, **kwargs) -> Dict[str, Any]:
        """Answer media session (200 OK response)."""
        try:
            logger.info(f"Answering media session for call {call_id}")
            
            stream = self.streams.get(call_id)
            rtp_session = self.rtp_sessions.get(call_id)
            
            if not stream or not rtp_session:
                raise Exception(f"No media session found for call {call_id}")
            
            # Send answer to RTPEngine
            modified_sdp, updated_session = await self.rtpengine.answer(
                call_id, from_tag, to_tag, callee_sdp, **kwargs
            )
            
            # Update stream with callee information
            if updated_session.callee_address:
                stream.remote_address = updated_session.callee_address.address
                stream.remote_port = updated_session.callee_address.port
            
            # Emit event
            await self._emit_event("media_session_answered", stream)
            
            logger.info(f"Media session answered for call {call_id}")
            
            return {
                "success": True,
                "modified_sdp": modified_sdp,
                "stream_info": stream.get_statistics()
            }
            
        except Exception as e:
            logger.error(f"Failed to answer media session for call {call_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def end_media_session(self, call_id: str) -> bool:
        """End media session."""
        try:
            logger.info(f"Ending media session for call {call_id}")
            
            stream = self.streams.get(call_id)
            rtp_session = self.rtp_sessions.get(call_id)
            
            if not stream and not rtp_session:
                logger.warning(f"No media session found for call {call_id}")
                return False
            
            # Stop recording if active
            if stream and stream.is_recording:
                await self.stop_recording(call_id)
            
            # Delete RTPEngine session
            if rtp_session:
                session_key = f"{call_id}_{rtp_session.from_tag}"
                await self.rtpengine.delete_session(session_key)
            
            # Remove sessions
            if call_id in self.streams:
                stream = self.streams.pop(call_id)
                stream.is_active = False
                self.active_streams -= 1
                
                # Emit event
                await self._emit_event("media_session_ended", stream)
            
            if call_id in self.rtp_sessions:
                del self.rtp_sessions[call_id]
            
            logger.info(f"Media session ended for call {call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to end media session for call {call_id}: {e}")
            return False
    
    async def hold_media_session(self, call_id: str) -> bool:
        """Put media session on hold."""
        try:
            stream = self.streams.get(call_id)
            if not stream:
                return False
            
            # Update stream direction to sendonly (caller) or recvonly (callee)
            stream.direction = MediaDirection.SENDONLY
            stream.is_on_hold = True
            
            # Emit event
            await self._emit_event("media_session_held", stream)
            
            logger.info(f"Media session held for call {call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to hold media session for call {call_id}: {e}")
            return False
    
    async def resume_media_session(self, call_id: str) -> bool:
        """Resume media session from hold."""
        try:
            stream = self.streams.get(call_id)
            if not stream:
                return False
            
            # Restore bidirectional media
            stream.direction = MediaDirection.SENDRECV
            stream.is_on_hold = False
            
            # Emit event
            await self._emit_event("media_session_resumed", stream)
            
            logger.info(f"Media session resumed for call {call_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to resume media session for call {call_id}: {e}")
            return False
    
    async def start_recording(self, call_id: str, recording_params: Dict[str, Any]) -> bool:
        """Start recording media session."""
        try:
            stream = self.streams.get(call_id)
            rtp_session = self.rtp_sessions.get(call_id)
            
            if not stream or not rtp_session:
                return False
            
            # Prepare recording parameters
            recording_file = recording_params.get("output_file", f"/tmp/recording_{call_id}.{self.recording_format}")
            
            params = {
                "output_file": recording_file,
                "format": self.recording_format,
                "metadata": {
                    "call_id": call_id,
                    "start_time": time.time(),
                    **recording_params.get("metadata", {})
                }
            }
            
            # Start recording in RTPEngine
            success = await self.rtpengine.start_recording(
                call_id, rtp_session.from_tag, params
            )
            
            if success:
                stream.is_recording = True
                
                # Emit event
                await self._emit_event("recording_started", stream, recording_file)
                
                logger.info(f"Started recording for call {call_id}: {recording_file}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to start recording for call {call_id}: {e}")
            return False
    
    async def stop_recording(self, call_id: str) -> bool:
        """Stop recording media session."""
        try:
            stream = self.streams.get(call_id)
            rtp_session = self.rtp_sessions.get(call_id)
            
            if not stream or not rtp_session:
                return False
            
            # Stop recording in RTPEngine
            success = await self.rtpengine.stop_recording(
                call_id, rtp_session.from_tag
            )
            
            if success:
                stream.is_recording = False
                
                # Emit event
                await self._emit_event("recording_stopped", stream)
                
                logger.info(f"Stopped recording for call {call_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to stop recording for call {call_id}: {e}")
            return False
    
    async def get_media_statistics(self, call_id: str) -> Optional[Dict[str, Any]]:
        """Get media statistics for call."""
        try:
            stream = self.streams.get(call_id)
            rtp_session = self.rtp_sessions.get(call_id)
            
            if not stream:
                return None
            
            # Get RTPEngine statistics
            rtpengine_stats = None
            if rtp_session:
                rtpengine_stats = await self.rtpengine.query_session(
                    call_id, rtp_session.from_tag
                )
            
            # Combine stream and RTPEngine statistics
            stats = stream.get_statistics()
            
            if rtpengine_stats:
                # Update with RTPEngine data
                stats.update({
                    "rtpengine_stats": rtpengine_stats,
                    "rtp_session_active": rtp_session.is_active()
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get media statistics for call {call_id}: {e}")
            return None
    
    def get_stream(self, call_id: str) -> Optional[MediaStream]:
        """Get media stream for call."""
        return self.streams.get(call_id)
    
    def get_all_streams(self) -> List[MediaStream]:
        """Get all active media streams."""
        return list(self.streams.values())
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """Get media manager statistics."""
        rtpengine_stats = self.rtpengine.get_statistics()
        
        return {
            "total_streams": self.total_streams,
            "active_streams": self.active_streams,
            "failed_setups": self.failed_setups,
            "success_rate": self.total_streams / max(self.total_streams + self.failed_setups, 1),
            "rtpengine_statistics": rtpengine_stats,
            "codec_handler_stats": self.codec_handler.get_statistics()
        }
    
    def add_event_handler(self, event_type: str, handler: Callable):
        """Add media event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def remove_event_handler(self, event_type: str, handler: Callable):
        """Remove media event handler."""
        if event_type in self.event_handlers and handler in self.event_handlers[event_type]:
            self.event_handlers[event_type].remove(handler)
    
    async def _emit_event(self, event_type: str, *args, **kwargs):
        """Emit media event to handlers."""
        handlers = self.event_handlers.get(event_type, [])
        
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in media event handler for {event_type}: {e}")
    
    def _determine_codec(self, sdp: str) -> SupportedCodec:
        """Determine codec from SDP."""
        try:
            # Parse SDP to find codecs
            if "PCMA" in sdp or "8" in sdp:
                return SupportedCodec.PCMA
            elif "PCMU" in sdp or "0" in sdp:
                return SupportedCodec.PCMU
            elif "G722" in sdp or "9" in sdp:
                return SupportedCodec.G722
            elif "G729" in sdp or "18" in sdp:
                return SupportedCodec.G729
            elif "opus" in sdp.lower():
                return SupportedCodec.OPUS
            else:
                return self.default_codec
                
        except Exception as e:
            logger.error(f"Error determining codec from SDP: {e}")
            return self.default_codec
    
    async def cleanup(self):
        """Cleanup media manager resources."""
        try:
            await self.stop()
            logger.info("Media manager cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up media manager: {e}")