"""Codec handler for media manager integration."""
import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from ..audio.codecs import AudioProcessor, AudioCodec, PCMUCodec, PCMACodec

logger = logging.getLogger(__name__)


class SupportedCodec(Enum):
    """Supported audio codecs."""
    PCMU = "PCMU"
    PCMA = "PCMA"
    G722 = "G722"
    G729 = "G729"
    OPUS = "opus"


class CodecHandler:
    """Handler for audio codec operations."""
    
    def __init__(self):
        self.audio_processor = AudioProcessor()
        self.transcoding_stats = {
            "total_conversions": 0,
            "failed_conversions": 0,
            "conversion_times": []
        }
        
        # Codec preferences (ordered by quality/preference)
        self.codec_preferences = [
            SupportedCodec.OPUS,
            SupportedCodec.G722,
            SupportedCodec.PCMA,
            SupportedCodec.PCMU,
            SupportedCodec.G729
        ]
    
    def get_preferred_codec(self, available_codecs: List[SupportedCodec]) -> SupportedCodec:
        """Get preferred codec from available list."""
        for preferred in self.codec_preferences:
            if preferred in available_codecs:
                return preferred
        
        # Default fallback
        return SupportedCodec.PCMU
    
    def get_codec_info(self, codec: SupportedCodec) -> Dict[str, Any]:
        """Get codec information."""
        codec_info = {
            SupportedCodec.PCMU: {
                "name": "G.711 μ-law",
                "payload_type": 0,
                "sample_rate": 8000,
                "channels": 1,
                "bitrate": 64000,
                "frame_size_ms": 20
            },
            SupportedCodec.PCMA: {
                "name": "G.711 A-law",
                "payload_type": 8,
                "sample_rate": 8000,
                "channels": 1,
                "bitrate": 64000,
                "frame_size_ms": 20
            },
            SupportedCodec.G722: {
                "name": "G.722",
                "payload_type": 9,
                "sample_rate": 16000,
                "channels": 1,
                "bitrate": 64000,
                "frame_size_ms": 20
            },
            SupportedCodec.G729: {
                "name": "G.729",
                "payload_type": 18,
                "sample_rate": 8000,
                "channels": 1,
                "bitrate": 8000,
                "frame_size_ms": 20
            },
            SupportedCodec.OPUS: {
                "name": "Opus",
                "payload_type": 111,
                "sample_rate": 48000,
                "channels": 1,
                "bitrate": 32000,
                "frame_size_ms": 20
            }
        }
        
        return codec_info.get(codec, {})
    
    def can_transcode(self, from_codec: SupportedCodec, to_codec: SupportedCodec) -> bool:
        """Check if transcoding is supported between codecs."""
        # Currently support G.711 variants
        supported_codecs = [SupportedCodec.PCMU, SupportedCodec.PCMA]
        return from_codec in supported_codecs and to_codec in supported_codecs
    
    def transcode_audio(self, data: bytes, from_codec: SupportedCodec, 
                       to_codec: SupportedCodec) -> Optional[bytes]:
        """Transcode audio between different codecs."""
        try:
            if from_codec == to_codec:
                return data
            
            if not self.can_transcode(from_codec, to_codec):
                logger.warning(f"Transcoding not supported: {from_codec.value} -> {to_codec.value}")
                return None
            
            # Convert using audio processor
            result = self.audio_processor.convert_format(
                data, from_codec.value, to_codec.value
            )
            
            self.transcoding_stats["total_conversions"] += 1
            return result
            
        except Exception as e:
            logger.error(f"Transcoding error: {e}")
            self.transcoding_stats["failed_conversions"] += 1
            return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get codec handler statistics."""
        total = self.transcoding_stats["total_conversions"]
        failed = self.transcoding_stats["failed_conversions"]
        
        return {
            "total_conversions": total,
            "failed_conversions": failed,
            "success_rate": (total - failed) / max(total, 1),
            "supported_codecs": [codec.value for codec in SupportedCodec],
            "preferred_order": [codec.value for codec in self.codec_preferences]
        }