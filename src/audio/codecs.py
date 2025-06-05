"""Audio codec conversion utilities for SIP telephony."""
import audioop
import struct
import numpy as np
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class AudioCodec:
    """Base class for audio codec implementations."""
    
    def __init__(self, sample_rate: int = 8000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_size_ms = 20  # Standard 20ms frames
        self.frame_size_samples = int(sample_rate * frame_size_ms / 1000)
        self.frame_size_bytes = self.frame_size_samples * 2  # 16-bit PCM
        
    def encode(self, pcm_data: bytes) -> bytes:
        """Encode PCM data to codec format."""
        raise NotImplementedError
        
    def decode(self, encoded_data: bytes) -> bytes:
        """Decode codec data to PCM format."""
        raise NotImplementedError


class PCMUCodec(AudioCodec):
    """μ-law (PCMU) codec implementation."""
    
    def encode(self, pcm_data: bytes) -> bytes:
        """Convert 16-bit PCM to μ-law."""
        try:
            return audioop.lin2ulaw(pcm_data, 2)
        except Exception as e:
            logger.error(f"PCMU encode error: {e}")
            return b''
    
    def decode(self, ulaw_data: bytes) -> bytes:
        """Convert μ-law to 16-bit PCM."""
        try:
            return audioop.ulaw2lin(ulaw_data, 2)
        except Exception as e:
            logger.error(f"PCMU decode error: {e}")
            return b''


class PCMACodec(AudioCodec):
    """A-law (PCMA) codec implementation."""
    
    def encode(self, pcm_data: bytes) -> bytes:
        """Convert 16-bit PCM to A-law."""
        try:
            return audioop.lin2alaw(pcm_data, 2)
        except Exception as e:
            logger.error(f"PCMA encode error: {e}")
            return b''
    
    def decode(self, alaw_data: bytes) -> bytes:
        """Convert A-law to 16-bit PCM."""
        try:
            return audioop.alaw2lin(alaw_data, 2)
        except Exception as e:
            logger.error(f"PCMA decode error: {e}")
            return b''


class G711Codec(AudioCodec):
    """G.711 codec supporting both μ-law and A-law."""
    
    def __init__(self, variant: str = "PCMU", **kwargs):
        super().__init__(**kwargs)
        self.variant = variant.upper()
        if self.variant == "PCMU":
            self._codec = PCMUCodec(**kwargs)
        elif self.variant == "PCMA":
            self._codec = PCMACodec(**kwargs)
        else:
            raise ValueError(f"Unsupported G.711 variant: {variant}")
    
    def encode(self, pcm_data: bytes) -> bytes:
        return self._codec.encode(pcm_data)
    
    def decode(self, encoded_data: bytes) -> bytes:
        return self._codec.decode(encoded_data)


class AudioProcessor:
    """Advanced audio processing for real-time conversion."""
    
    def __init__(self):
        self.codecs = {
            'PCMU': PCMUCodec(),
            'PCMA': PCMACodec(),
            'G711U': PCMUCodec(),
            'G711A': PCMACodec(),
        }
        
    def get_codec(self, codec_name: str) -> Optional[AudioCodec]:
        """Get codec instance by name."""
        return self.codecs.get(codec_name.upper())
    
    def convert_format(self, data: bytes, from_codec: str, to_codec: str) -> bytes:
        """Convert audio between different formats."""
        try:
            from_codec_obj = self.get_codec(from_codec)
            to_codec_obj = self.get_codec(to_codec)
            
            if not from_codec_obj or not to_codec_obj:
                logger.error(f"Unsupported codec conversion: {from_codec} -> {to_codec}")
                return data
            
            # Decode to PCM first
            pcm_data = from_codec_obj.decode(data) if from_codec.upper() != 'PCM' else data
            
            # Encode to target format
            return to_codec_obj.encode(pcm_data) if to_codec.upper() != 'PCM' else pcm_data
            
        except Exception as e:
            logger.error(f"Audio conversion error: {e}")
            return data
    
    def resample_audio(self, data: bytes, from_rate: int, to_rate: int, 
                      sample_width: int = 2) -> bytes:
        """Resample audio data to different sample rate."""
        try:
            if from_rate == to_rate:
                return data
            
            # Use audioop for resampling
            resampled, _ = audioop.ratecv(data, sample_width, 1, from_rate, to_rate, None)
            return resampled
            
        except Exception as e:
            logger.error(f"Resampling error: {e}")
            return data
    
    def adjust_volume(self, data: bytes, factor: float, sample_width: int = 2) -> bytes:
        """Adjust audio volume by a factor."""
        try:
            return audioop.mul(data, sample_width, factor)
        except Exception as e:
            logger.error(f"Volume adjustment error: {e}")
            return data
    
    def detect_silence(self, data: bytes, threshold: int = 1000, 
                      sample_width: int = 2) -> bool:
        """Detect if audio data contains mostly silence."""
        try:
            # Calculate RMS (Root Mean Square) amplitude
            rms = audioop.rms(data, sample_width)
            return rms < threshold
        except Exception as e:
            logger.error(f"Silence detection error: {e}")
            return False
    
    def mix_audio(self, data1: bytes, data2: bytes, sample_width: int = 2) -> bytes:
        """Mix two audio streams together."""
        try:
            # Ensure both streams are the same length
            min_len = min(len(data1), len(data2))
            data1 = data1[:min_len]
            data2 = data2[:min_len]
            
            return audioop.add(data1, data2, sample_width)
        except Exception as e:
            logger.error(f"Audio mixing error: {e}")
            return data1
    
    def apply_agc(self, data: bytes, target_level: float = 0.7, 
                  sample_width: int = 2) -> bytes:
        """Apply Automatic Gain Control to normalize audio levels."""
        try:
            # Calculate current RMS level
            rms = audioop.rms(data, sample_width)
            if rms == 0:
                return data
            
            # Calculate gain factor needed
            max_amplitude = (1 << (sample_width * 8 - 1)) - 1
            current_level = rms / max_amplitude
            
            if current_level > 0:
                gain_factor = target_level / current_level
                # Limit gain to prevent distortion
                gain_factor = min(gain_factor, 4.0)
                return self.adjust_volume(data, gain_factor, sample_width)
            
            return data
        except Exception as e:
            logger.error(f"AGC error: {e}")
            return data
    
    def create_silence(self, duration_ms: int, sample_rate: int = 8000,
                      sample_width: int = 2) -> bytes:
        """Create silence of specified duration."""
        samples = int(sample_rate * duration_ms / 1000)
        return b'\x00' * (samples * sample_width)
    
    def fade_in(self, data: bytes, fade_ms: int = 50, sample_rate: int = 8000,
               sample_width: int = 2) -> bytes:
        """Apply fade-in effect to audio data."""
        try:
            fade_samples = int(sample_rate * fade_ms / 1000)
            fade_bytes = fade_samples * sample_width
            
            if len(data) <= fade_bytes:
                # If audio is shorter than fade duration, fade the entire audio
                fade_bytes = len(data)
                fade_samples = fade_bytes // sample_width
            
            # Create fade-in envelope
            fade_data = data[:fade_bytes]
            result = bytearray(data)
            
            for i in range(0, fade_bytes, sample_width):
                sample_idx = i // sample_width
                factor = sample_idx / fade_samples
                
                # Apply fade factor to sample
                if sample_width == 2:
                    sample = struct.unpack('<h', fade_data[i:i+2])[0]
                    faded_sample = int(sample * factor)
                    result[i:i+2] = struct.pack('<h', faded_sample)
            
            return bytes(result)
        except Exception as e:
            logger.error(f"Fade-in error: {e}")
            return data
    
    def fade_out(self, data: bytes, fade_ms: int = 50, sample_rate: int = 8000,
                sample_width: int = 2) -> bytes:
        """Apply fade-out effect to audio data."""
        try:
            fade_samples = int(sample_rate * fade_ms / 1000)
            fade_bytes = fade_samples * sample_width
            
            if len(data) <= fade_bytes:
                fade_bytes = len(data)
                fade_samples = fade_bytes // sample_width
            
            # Create fade-out envelope
            start_pos = len(data) - fade_bytes
            fade_data = data[start_pos:]
            result = bytearray(data)
            
            for i in range(0, fade_bytes, sample_width):
                sample_idx = i // sample_width
                factor = 1.0 - (sample_idx / fade_samples)
                
                if sample_width == 2:
                    sample = struct.unpack('<h', fade_data[i:i+2])[0]
                    faded_sample = int(sample * factor)
                    result[start_pos + i:start_pos + i + 2] = struct.pack('<h', faded_sample)
            
            return bytes(result)
        except Exception as e:
            logger.error(f"Fade-out error: {e}")
            return data
    
    def calculate_audio_level(self, data: bytes, sample_width: int = 2) -> float:
        """Calculate audio level (0.0 to 1.0) for metering."""
        try:
            if not data:
                return 0.0
            
            rms = audioop.rms(data, sample_width)
            max_amplitude = (1 << (sample_width * 8 - 1)) - 1
            return min(rms / max_amplitude, 1.0)
        except Exception as e:
            logger.error(f"Audio level calculation error: {e}")
            return 0.0
    
    def split_frames(self, data: bytes, frame_size_ms: int = 20, 
                    sample_rate: int = 8000, sample_width: int = 2) -> list:
        """Split audio data into frames of specified duration."""
        frame_size_bytes = int(sample_rate * frame_size_ms / 1000) * sample_width
        frames = []
        
        for i in range(0, len(data), frame_size_bytes):
            frame = data[i:i + frame_size_bytes]
            
            # Pad last frame if necessary
            if len(frame) < frame_size_bytes:
                padding = frame_size_bytes - len(frame)
                frame += b'\x00' * padding
            
            frames.append(frame)
        
        return frames
    
    def validate_audio_format(self, data: bytes, expected_sample_rate: int = 8000,
                             expected_channels: int = 1, sample_width: int = 2) -> bool:
        """Validate audio data format."""
        try:
            # Check if data length is consistent with format
            expected_bytes_per_sample = sample_width * expected_channels
            if len(data) % expected_bytes_per_sample != 0:
                return False
            
            # Check for reasonable audio levels (not all zeros or all max)
            if data == b'\x00' * len(data):
                return False  # All silence
            
            # Calculate RMS to check for reasonable audio levels
            if sample_width == 2:
                samples = len(data) // 2
                if samples > 0:
                    rms = audioop.rms(data, 2)
                    max_amplitude = (1 << 15) - 1
                    level = rms / max_amplitude
                    # Reasonable audio should have some content but not be clipping
                    return 0.001 < level < 0.95
            
            return True
        except Exception as e:
            logger.error(f"Audio validation error: {e}")
            return False